"""WhatsApp reporting conversation as a state machine (OPW-010..024).

One ``Conversation`` row per contact endpoint. ``conversation.state_json``:

    {"v": 1, "mode": "report"|"menu"|"permissions"|"handoff"|"deletion"|"optout"|"idle",
     "answers": {...}, "history": [step, ...], "reask": {step: n}, "pick": [area ids],
     "sub": None|"fix_section", "supersedes": report id|None, "flags": [...],
     "notes": [encrypted], "prefilled": [...], "surge_ack_at": iso|None}

The next question is always the first step in ``ORDER`` that is not skipped and
has no answer yet, so prefilled answers (optional OpenAI extraction), "Atrás"
and "Corregir" all fall out of the same rule. A report is written to the
database only when the resident confirms the summary (OPW-016, DOM-011).

The engine never calls the network. Replies are queued in ``outbox_message``
in the same transaction as the state change (outbox pattern); the sender
delivers them later. The optional extraction runs between two transactions
(``wants_extraction`` first, then ``handle`` with the result).
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.crypto import encrypt_text, lookup_hmac
from app.models.base import utcnow
from app.models.geo import Area, AreaAlias, MeetingPoint
from app.models.outreach import Campaign, CampaignArea
from app.models.privacy import PrivacyProfileVersion
from app.models.provider import Activity, ActivityArea, ProviderOrganization
from app.models.quality import ReviewTask
from app.models.report import Report
from app.models.reporting import ContactEndpoint, Conversation, Message, Permission, ReporterKey
from app.models.system import OutboxMessage
from app.whatsapp import catalog as C
from app.whatsapp.parsing import (
    AreaCandidate, Option, command_of, is_dont_know, match_areas, match_option, normalize,
    parse_int, yes_no,
)

log = logging.getLogger("whatsapp.engine")

STATE_VERSION = 1
PRIORITY = {"holding": 200, "conversation_reply": 100, "opt_out_confirmation": 100,
            "notice": 100, "refresh_prompt": 50, "area_broadcast": 10, "alert": 10}
PERMISSION_PURPOSES = ("refresh_prompts", "area_broadcasts", "contact_list")
PERM_FIELD = {"refresh_prompts": "perm_refresh", "area_broadcasts": "perm_area",
              "contact_list": "perm_contact"}


# ---------------------------------------------------------------------------
# Inbound message and context
# ---------------------------------------------------------------------------


@dataclass
class Inbound:
    """One resident message, already reduced to what the engine needs."""

    provider_message_id: str
    kind: str  # text | choice | location | media | unsupported
    text: str | None = None
    choice_id: str | None = None
    choice_title: str | None = None
    lat: float | None = None
    lon: float | None = None
    received_at: datetime | None = None


@dataclass
class EngineContext:
    org_id: str
    org_name: str
    identity: str
    phone_number_id: str
    campaign: Campaign | None
    profile: PrivacyProfileVersion
    endpoint: ContactEndpoint
    conversation: Conversation
    now: datetime
    referral_text: str
    resume_hours: int = 48


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    name: str
    section: str
    field: str
    question: str = ""
    options: tuple[Option, ...] = ()
    kind: str = "choice"  # choice | int | number | custom
    llm: str | None = None  # extraction key that answers this step
    skip: Callable[[dict, "Engine"], bool] = lambda a, e: False
    lo: int = 0
    hi: int = 10_000


def _not_out(field_: str):
    return lambda a, e: a.get(field_) not in ("unavailable", "intermittent")


def _not_yes(field_: str):
    return lambda a, e: a.get(field_) is not True


_SINCE_IDS = {"0": 0, "1": 1, "2": 2, "4": 4}

STEPS: list[Step] = [
    Step("notice", "notice", "notice", kind="custom"),
    Step("parish", "area", "parish_id", kind="custom", llm="area_text"),
    Step("sector", "area", "sector_id", kind="custom", llm="area_text",
         skip=lambda a, e: a.get("parish_id") is None),
    Step("location", "area", "location", kind="custom",
         skip=lambda a, e: a.get("parish_id") is None and a.get("sector_id") is None
         and e.ctx.profile.location_mode == "meeting_point"),
    Step("electricity", "services", "electricity", C.Q_ELECTRICITY, tuple(C.SERVICE_STATUS),
         llm="electricity_status"),
    Step("electricity_since", "services", "electricity_since", C.Q_ELECTRICITY_SINCE,
         tuple(C.SINCE), llm="electricity_since_days", skip=_not_out("electricity")),
    Step("water", "services", "water", C.Q_WATER, tuple(C.SERVICE_STATUS), llm="water_status"),
    Step("water_since", "services", "water_since", C.Q_WATER_SINCE, tuple(C.SINCE),
         llm="water_since_days", skip=_not_out("water")),
    Step("need_drinking", "needs", "need_drinking", C.Q_NEED_DRINKING, tuple(C.YES_NO_DK),
         llm="needs_drinking_water"),
    Step("drinking_people", "needs", "drinking_people", C.Q_DRINKING_PEOPLE, (C.DONT_KNOW,),
         kind="int", llm="drinking_people", skip=_not_yes("need_drinking"), hi=500),
    Step("drinking_liters", "needs", "drinking_liters", C.Q_DRINKING_LITERS, (C.DONT_KNOW,),
         kind="number", llm="drinking_liters", skip=_not_yes("need_drinking"), hi=100_000),
    Step("drinking_supply", "needs", "drinking_supply", C.Q_DRINKING_SUPPLY, tuple(C.SUPPLY),
         llm="drinking_remaining_supply", skip=_not_yes("need_drinking")),
    Step("need_other", "needs", "need_other", C.Q_NEED_OTHER, tuple(C.YES_NO_DK),
         llm="needs_other_water"),
    Step("other_people", "needs", "other_people", C.Q_OTHER_PEOPLE, (C.DONT_KNOW,),
         kind="int", llm="other_water_people", skip=_not_yes("need_other"), hi=500),
    Step("need_charging", "needs", "need_charging", C.Q_NEED_CHARGING, tuple(C.YES_NO_DK),
         llm="needs_charging"),
    Step("charging_device", "needs", "charging_device", C.Q_CHARGING_DEVICE, tuple(C.DEVICES),
         llm="charging_device_type", skip=_not_yes("need_charging")),
    Step("charging_count", "needs", "charging_count", C.Q_CHARGING_COUNT, (C.DONT_KNOW,),
         kind="int", llm="charging_device_count", skip=_not_yes("need_charging"), lo=1, hi=50),
    Step("urgent", "urgent", "urgent", C.Q_URGENT, tuple(C.YES_NO), llm="urgent"),
    # Consent is never inferred by a model: no ``llm`` key on permission steps.
    Step("perm_refresh", "permissions", "perm_refresh", C.Q_PERM_REFRESH, tuple(C.YES_NO)),
    Step("perm_area", "permissions", "perm_area", C.Q_PERM_AREA, tuple(C.YES_NO)),
    Step("perm_contact", "permissions", "perm_contact", C.Q_PERM_CONTACT, tuple(C.YES_NO)),
    Step("summary", "summary", "_summary", kind="custom"),
]
BY_NAME = {s.name: s for s in STEPS}
SECTION_FIELDS = {sec: [s.field for s in STEPS if s.section == sec]
                  for sec in ("area", "services", "needs", "urgent", "permissions")}
# Fields the extraction may prefill (never area ids, location or consent).
PREFILLABLE = {s.llm: s for s in STEPS
               if s.llm and s.llm != "area_text" and s.section != "permissions"}


def new_state() -> dict:
    return {"v": STATE_VERSION, "mode": "report", "answers": {}, "history": [], "reask": {},
            "pick": [], "sub": None, "supersedes": None, "flags": [], "notes": [],
            "prefilled": [], "surge_ack_at": None}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class Engine:
    def __init__(self, db: Session, ctx: EngineContext):
        self.db = db
        self.ctx = ctx
        conv = ctx.conversation
        # Deep copy: mutating nested dicts of the loaded value would make the
        # ORM see "no change" and silently skip the UPDATE.
        self.state: dict = {**new_state(), **copy.deepcopy(conv.state_json or {})}
        self._reply_seq = 0
        self._dedupe_base = "init"

    # --- public API -----------------------------------------------------

    @property
    def answers(self) -> dict:
        return self.state["answers"]

    def current_step(self) -> Step:
        for s in STEPS:
            if s.field in self.answers or s.skip(self.answers, self):
                continue
            return s
        return BY_NAME["summary"]

    def wants_extraction(self, inbound: Inbound) -> tuple[str, str] | None:
        """(question, answer) to send to the extractor, or None. Read-only."""
        if inbound.kind != "text" or not inbound.text or command_of(inbound.text):
            return None
        if self._expired() or self.state.get("mode") != "report" or self.state.get("pick"):
            return None
        step = self.current_step()
        if step.llm is None:
            return None
        if step.name in ("parish", "sector"):
            if self._area_matches(step, inbound.text):
                return None
            return (C.Q_PARISH if step.name == "parish" else C.Q_SECTOR.format(parish=""),
                    inbound.text)
        if self._parse_simple(step, inbound) is not _NOPARSE:
            return None
        return step.question, inbound.text

    def handle(self, inbound: Inbound, extraction: dict | None = None) -> None:
        """Process one inbound message: update state, queue replies. Caller commits."""
        ctx = self.ctx
        self._dedupe_base = inbound.provider_message_id
        # The 24-hour window runs from when the resident wrote (OPW-031).
        ctx.endpoint.last_activity_at = inbound.received_at or ctx.now
        if self._expired():
            self._abandon()
            self._reset_report()
            self.reply(C.text(C.WELCOME_BACK))
        ctx.conversation.last_user_message_at = ctx.now

        cmd = command_of(inbound.text) if inbound.kind == "text" else None
        mode = self.state.get("mode", "report")

        if mode == "optout":
            if cmd == "menu" or normalize(inbound.text) in ("hola", "reportar"):
                ctx.endpoint.status = "active"
                ctx.endpoint.opted_out_at = None
                self._show_menu()
            self._save()
            return  # otherwise silent: BAJA stops all messages (OPW-018)

        if cmd:
            self._command(cmd)
        elif mode == "handoff" or mode == "deletion":
            pass  # a person handles it; the bot stays quiet until MENÚ
        elif mode == "menu":
            self._menu_choice(inbound)
        elif mode == "permissions":
            self._permissions_choice(inbound)
        elif mode == "idle":
            self._show_menu(prefix="Hola. ")
        elif inbound.kind == "media":
            self.reply(C.text(C.MEDIA_NOT_SUPPORTED))
            self._ask(self.current_step())
        elif inbound.kind == "unsupported":
            self.reply(C.text(C.MEDIA_NOT_SUPPORTED))
            self._ask(self.current_step())
        else:
            self._answer(inbound, extraction)
        self._save()

    def queue_holding(self, backlog_since: datetime) -> bool:
        """Surge mode (OPW-035): one holding reply per conversation per surge."""
        ack = self.state.get("surge_ack_at")
        if ack and datetime.fromisoformat(ack) >= backlog_since:
            return False
        if self.state.get("mode") in ("optout", "handoff"):
            return False
        self._dedupe_base = f"surge:{backlog_since.isoformat()}"
        self.reply(C.text(C.HOLDING), purpose="conversation_reply", priority=PRIORITY["holding"])
        self.state["surge_ack_at"] = self.ctx.now.isoformat()
        self._save()
        return True

    # --- replies ----------------------------------------------------------

    def reply(self, message: dict, *, purpose: str = "conversation_reply",
              priority: int | None = None) -> None:
        self._reply_seq += 1
        # The sending number travels with the message (one org may own several).
        message = {**message, "_pnid": self.ctx.phone_number_id}
        self.db.add(OutboxMessage(
            organization_id=self.ctx.org_id,
            purpose=purpose,
            contact_endpoint_id=self.ctx.endpoint.id,
            conversation_id=self.ctx.conversation.id,
            message_json=message,
            body_reference=None,
            status="pending",
            priority=PRIORITY.get(purpose, 0) if priority is None else priority,
            next_attempt_at=self.ctx.now,
            dedupe_key=f"{self._dedupe_base}:{self._reply_seq}"[:200],
        ))

    # --- state helpers ----------------------------------------------------

    def _save(self) -> None:
        step = self.current_step().name if self.state.get("mode") == "report" else self.state.get(
            "mode")
        self.ctx.conversation.intake_state = (step or "start")[:64]
        # Assign a new dict so SQLAlchemy sees the JSON change.
        self.ctx.conversation.state_json = {**self.state, "answers": dict(self.answers)}

    def _expired(self) -> bool:
        last = self.ctx.conversation.last_user_message_at
        if last is None or self.state.get("mode") != "report" or not self.answers:
            return False
        if last.tzinfo is None:
            last = last.replace(tzinfo=self.ctx.now.tzinfo)
        return self.ctx.now - last > timedelta(hours=self.ctx.resume_hours)

    def _abandon(self) -> None:
        log.info("conversation %s abandoned after resume window", self.ctx.conversation.id)

    def _reset_report(self, *, keep: dict | None = None, supersedes: str | None = None) -> None:
        st = new_state()
        st["surge_ack_at"] = self.state.get("surge_ack_at")
        st["answers"] = dict(keep or {})
        st["supersedes"] = supersedes
        self.state = st
        if self._notice_acked():
            self.answers["notice"] = True

    def _flag(self, flag: str) -> None:
        if flag not in self.state.setdefault("flags", []):
            self.state["flags"].append(flag)

    def _store_note(self, step: str, raw: str) -> None:
        """Restricted, encrypted note for unreadable free text (OPW-012/023)."""
        self.state.setdefault("notes", []).append({"step": step, "text": encrypt_text(raw[:1000])})
        self._flag("unparsed_text")

    # --- asking -----------------------------------------------------------

    def _ask(self, step: Step, prefix: str = "") -> None:
        hist = self.state.setdefault("history", [])
        if not hist or hist[-1] != step.name:
            hist.append(step.name)
        if step.name == "notice":
            self.reply(C.notice(self.ctx.identity, self.ctx.org_name), purpose="notice")
        elif step.name == "parish":
            opts = self._parish_options()
            self.reply(C.ask(prefix + C.Q_PARISH, opts))
        elif step.name == "sector":
            parish = self.db.get(Area, self.answers["parish_id"])
            opts = self._sector_options(self.answers["parish_id"])
            self.reply(C.ask(prefix + C.Q_SECTOR.format(parish=parish.name if parish else ""),
                             opts))
        elif step.name == "location":
            if self.ctx.profile.location_mode == "meeting_point":
                self.reply(C.ask(prefix + C.Q_MEETING_POINT, self._meeting_point_options()))
            else:
                self.reply(C.ask(prefix + C.Q_ADDRESS, [C.SKIP]))
        elif step.name == "summary":
            self.reply(C.summary(self.answers, self._area_label(), self._location_label()))
        else:
            self.reply(C.ask(prefix + step.question, list(step.options)))

    def _ask_next(self, prefix: str = "") -> None:
        self._ask(self.current_step(), prefix)

    # --- answering --------------------------------------------------------

    def _answer(self, inbound: Inbound, extraction: dict | None) -> None:
        step = self.current_step()
        if self.state.get("pick"):
            return self._answer_pick(step, inbound)
        if step.name == "notice":
            return self._answer_notice(inbound)
        if step.name in ("parish", "sector"):
            return self._answer_area(step, inbound, extraction)
        if step.name == "location":
            return self._answer_location(inbound)
        if step.name == "summary":
            return self._answer_summary(inbound)

        value = self._parse_simple(step, inbound)
        if value is _NOPARSE and extraction:
            value = self._from_extraction(step, extraction)
        if extraction:
            self._prefill(extraction, exclude=step.field)
        if value is _NOPARSE:
            return self._unparsed(step, inbound)
        self.answers[step.field] = value
        self.state["reask"].pop(step.name, None)
        if step.name == "urgent" and value is True:
            self._urgent()
        self._ask_next()

    def _parse_simple(self, step: Step, inbound: Inbound):
        if step.kind == "custom":
            return _NOPARSE
        txt = inbound.text if inbound.kind == "text" else inbound.choice_title
        if inbound.choice_id == "dk" or is_dont_know(txt):
            # "No sé" is allowed wherever offered (OPW-012); never for consent.
            if any(o.id == "dk" for o in step.options):
                return _option_value(step, C.DONT_KNOW)
            return _NOPARSE
        if step.kind in ("int", "number"):
            if inbound.kind != "text":
                return _NOPARSE
            n = parse_int(txt, step.lo, step.hi)
            if n is None and step.kind == "number":
                try:
                    f = float(normalize(txt).replace(",", ".").split()[0])
                    n = f if step.lo <= f <= step.hi else None
                except (ValueError, IndexError):
                    n = None
            return _NOPARSE if n is None else n
        opt = match_option(list(step.options), choice_id=inbound.choice_id, text=txt)
        if opt is None and set(o.id for o in step.options) >= {"yes", "no"}:
            yn = yes_no(txt)
            if yn is not None:
                return yn
        if opt is None:
            return _NOPARSE
        return _option_value(step, opt)

    def _from_extraction(self, step: Step, ex: dict):
        if step.llm and step.llm in ex:
            return _coerce(step, ex[step.llm])
        if ex.get("dont_know") and any(o.id == "dk" for o in step.options):
            return None
        return _NOPARSE

    def _prefill(self, ex: dict, exclude: str) -> None:
        for key, step in PREFILLABLE.items():
            if key in ex and step.field != exclude and step.field not in self.answers:
                self.answers[step.field] = _coerce(step, ex[key])
                self.state.setdefault("prefilled", []).append(step.field)

    def _unparsed(self, step: Step, inbound: Inbound) -> None:
        n = self.state["reask"].get(step.name, 0)
        if n == 0 or inbound.kind != "text":
            self.state["reask"][step.name] = n + 1
            return self._ask(step, prefix=C.REASK_PREFIX)
        # Second miss: keep the text as a restricted note, flag it, move on.
        self.state["reask"].pop(step.name, None)
        self._store_note(step.name, inbound.text or "")
        # Consent is never assumed: an unreadable permission answer is a "no".
        self.answers[step.field] = False if step.section == "permissions" else None
        if step.field == "urgent":
            self.answers[step.field] = None
        self.reply(C.text(C.FREE_TEXT_STORED))
        self._ask_next()

    # notice (OPW-011)
    def _answer_notice(self, inbound: Inbound) -> None:
        opts = [Option("ack", "Continuar", synonyms=("si", "continuar", "ok", "acepto", "sí")),
                Option("help", "Hablar con persona"), Option("decline", "No, gracias",
                                                             synonyms=("no",))]
        opt = match_option(opts, choice_id=inbound.choice_id,
                           text=inbound.text or inbound.choice_title)
        if opt is None:
            # First message, or an unclear reply: (re)show the notice.
            return self._ask(BY_NAME["notice"])
        if opt.id == "help":
            return self._command("help")
        if opt.id == "decline":
            self.state["mode"] = "idle"
            return self.reply(C.text(C.NOTICE_DECLINED))
        self._record_notice_ack(inbound.provider_message_id)
        self.answers["notice"] = True
        self._ask_next()

    # area (OPW-013)
    def _area_candidates(self, step: Step) -> list[AreaCandidate]:
        if step.name == "parish":
            areas = self._parishes()
            # Residents often name their sector directly: match those too.
            areas = areas + self._sectors_of([a.id for a in areas])
        else:
            areas = self._sectors_of([self.answers["parish_id"]])
        aliases: dict[str, list[str]] = {}
        if areas:
            for al in self.db.scalars(select(AreaAlias).where(
                    AreaAlias.organization_id == self.ctx.org_id,
                    AreaAlias.area_id.in_([a.id for a in areas]))):
                aliases.setdefault(al.area_id, []).append(al.alias)
        return [AreaCandidate(a.id, a.name, tuple(aliases.get(a.id, ()))) for a in areas]

    def _area_matches(self, step: Step, raw: str) -> list[AreaCandidate]:
        opts = self._parish_options() if step.name == "parish" else self._sector_options(
            self.answers["parish_id"])
        opt = match_option(opts, choice_id=None, text=raw)
        if opt is not None:
            return [AreaCandidate(opt.id, opt.title)]
        return match_areas(self._area_candidates(step), raw)

    def _answer_area(self, step: Step, inbound: Inbound, extraction: dict | None) -> None:
        if inbound.kind == "location":
            return self._answer_location(inbound)
        if inbound.kind == "choice" and inbound.choice_id:
            return self._set_area(inbound.choice_id)
        raw = inbound.text or inbound.choice_title or ""
        found = self._area_matches(step, raw)
        if not found and extraction and extraction.get("area_text"):
            found = match_areas(self._area_candidates(step), extraction["area_text"])
        if extraction:
            self._prefill(extraction, exclude=step.field)
        if len(found) == 1:
            return self._set_area(found[0].id)
        if len(found) > 1:
            self.state["pick"] = [c.id for c in found[:3]]
            return self.reply(C.ask(C.Q_AREA_PICK,
                                    [Option(c.id, c.name) for c in found[:3]]))
        n = self.state["reask"].get(step.name, 0)
        if n == 0:
            self.state["reask"][step.name] = 1
            return self._ask(step, prefix=C.REASK_PREFIX)
        # Unresolvable: keep the text for a location review task (OPW-013).
        self.state["reask"].pop(step.name, None)
        self._store_note(step.name, raw)
        self._flag("unresolved_location")
        if step.name == "parish":
            self.answers["parish_id"] = None
            self.answers["sector_id"] = None
        else:
            self.answers["sector_id"] = None
        self.reply(C.text(C.AREA_UNRESOLVED))
        self._ask_next()

    def _answer_pick(self, step: Step, inbound: Inbound) -> None:
        ids = self.state["pick"]
        areas = {a.id: a for a in self.db.scalars(select(Area).where(Area.id.in_(ids)))}
        opts = [Option(i, areas[i].name) for i in ids if i in areas]
        opt = match_option(opts, choice_id=inbound.choice_id,
                           text=inbound.text or inbound.choice_title)
        self.state["pick"] = []
        if opt is None:
            return self._ask(step, prefix=C.REASK_PREFIX)
        self._set_area(opt.id)

    def _set_area(self, area_id: str) -> None:
        area = self.db.get(Area, area_id)
        if area is None or area.organization_id != self.ctx.org_id:
            return self._ask(self.current_step(), prefix=C.REASK_PREFIX)
        self.state["reask"].pop("parish", None)
        self.state["reask"].pop("sector", None)
        if area.type == "sector":
            self.answers["sector_id"] = area.id
            self.answers["parish_id"] = area.parent_area_id
        else:
            self.answers["parish_id"] = area.id
            self.answers.pop("sector_id", None)
        self._ask_next()

    # location
    def _answer_location(self, inbound: Inbound) -> None:
        protective = self.ctx.profile.location_mode == "meeting_point"
        if inbound.kind == "location" and inbound.lat is not None and inbound.lon is not None:
            sector = self._sector_at(inbound.lat, inbound.lon)
            if sector is not None and self.answers.get("sector_id") is None:
                self.answers["sector_id"] = sector.id
                self.answers["parish_id"] = sector.parent_area_id
            if protective or not self.ctx.profile.gps_allowed:
                # Protective: reduce to the area, discard the point (OPW-013).
                self.reply(C.text(C.GPS_REDUCED))
                if protective:
                    return self._ask_next()
                self.answers["location"] = {"kind": "area_only"}
                return self._ask_next()
            self.answers["location"] = {
                "kind": "address",
                "point": encrypt_text(f"{inbound.lon:.6f},{inbound.lat:.6f}"),
            }
            self.reply(C.text(C.GPS_STORED))
            return self._ask_next()
        if self.current_step().name != "location":
            return self._ask_next()

        if protective:
            opts = self._meeting_point_options()
            opt = match_option(opts, choice_id=inbound.choice_id,
                               text=inbound.text or inbound.choice_title)
            if opt is None:
                return self._unparsed_location(inbound)
            if opt.id == "none_nearby":
                self.answers["location"] = {"kind": "none_nearby"}
            else:
                self.answers["location"] = {"kind": "meeting_point", "meeting_point_id": opt.id}
            return self._ask_next()

        if inbound.choice_id == "skip" or normalize(inbound.text) in ("omitir", "saltar",
                                                                      "prefiero no"):
            self.answers["location"] = {"kind": "area_only"}
            return self._ask_next()
        raw = (inbound.text or "").strip()
        if inbound.kind != "text" or len(raw) < 3:
            return self._unparsed_location(inbound)
        # Address/landmark: encrypted, never sent to any AI service.
        self.answers["location"] = {"kind": "address", "address": encrypt_text(raw[:300])}
        self._ask_next()

    def _unparsed_location(self, inbound: Inbound) -> None:
        n = self.state["reask"].get("location", 0)
        if n == 0:
            self.state["reask"]["location"] = 1
            return self._ask(BY_NAME["location"], prefix=C.REASK_PREFIX)
        self.state["reask"].pop("location", None)
        if inbound.text:
            self._store_note("location", inbound.text)
        self.answers["location"] = {"kind": "unresolved"}
        self._ask_next()

    # summary (OPW-016)
    def _answer_summary(self, inbound: Inbound) -> None:
        txt = inbound.text or inbound.choice_title
        if self.state.get("sub") == "fix_section":
            opt = match_option(C.SECTIONS, choice_id=inbound.choice_id, text=txt)
            if opt is None:
                return self.reply(C.ask(C.REASK_PREFIX + C.Q_FIX_SECTION, C.SECTIONS))
            self.state["sub"] = None
            for f in SECTION_FIELDS[opt.id]:
                self.answers.pop(f, None)
            return self._ask_next()
        opt = match_option([C.CONFIRM, C.FIX], choice_id=inbound.choice_id, text=txt)
        if opt is None:
            return self._ask(BY_NAME["summary"], prefix="")
        if opt.id == "fix":
            self.state["sub"] = "fix_section"
            return self.reply(C.ask(C.Q_FIX_SECTION, C.SECTIONS))
        self._confirm(inbound.provider_message_id)

    def _confirm(self, evidence: str) -> None:
        from app.whatsapp.persistence import persist_report

        key = self.reporter_key()
        result = persist_report(self.db, self.ctx, self.state, key, evidence=evidence)
        self.reply(C.confirmation(self.answers, superseded=result.superseded))
        self.state = {**new_state(), "mode": "idle", "surge_ack_at": self.state.get("surge_ack_at"),
                      "last_report_id": result.report_id}

    # urgent path (OPW-021)
    def _urgent(self) -> None:
        self.reply(C.urgent_referral(self.ctx.referral_text))
        area = self.answers.get("sector_id") or self.answers.get("parish_id")
        if area:
            self.db.add(ReviewTask(organization_id=self.ctx.org_id, reason="urgent_flag",
                                   area_id=area, status="open",
                                   reasons_json=["whatsapp_urgent_yes"],
                                   due_at=self.ctx.now + timedelta(hours=4)))
        self._flag("urgent_task_created" if area else "urgent_no_area")

    # --- commands (OPW-017/018) ------------------------------------------

    def _command(self, cmd: str) -> None:
        if cmd == "help":
            self.state["mode"] = "handoff"
            self.reply(C.text(C.HANDOFF))
        elif cmd == "optout":
            self._optout()
        elif cmd == "menu":
            self._show_menu()
        elif cmd == "back":
            self._back()
        elif cmd == "correct":
            self._start_from_last(clear_sections=None)
        elif cmd == "update":
            self._start_from_last(clear_sections=("services", "needs", "urgent"))
        elif cmd == "where":
            self._where()
        elif cmd == "permissions":
            self._show_permissions()
        elif cmd == "delete":
            self.state["mode"] = "deletion"
            self.reply(C.text(C.DELETE_REQUESTED))

    def _show_menu(self, prefix: str = "") -> None:
        self.state["mode"] = "menu"
        opts = [o for o in C.MENU if o.id != "continue" or self._in_progress()]
        self.reply(C.ask(prefix + C.Q_MENU, opts, button="Opciones"))

    def _in_progress(self) -> bool:
        a = self.answers
        return bool(a) and any(k != "notice" for k in a)

    def _menu_choice(self, inbound: Inbound) -> None:
        opt = match_option(C.MENU, choice_id=inbound.choice_id,
                           text=inbound.text or inbound.choice_title)
        if opt is None:
            return self._show_menu(prefix=C.REASK_PREFIX)
        if opt.id == "new":
            self._reset_report()
            return self._ask_next()
        if opt.id == "continue":
            self.state["mode"] = "report"
            return self._ask_next()
        self._command(opt.id)

    def _back(self) -> None:
        if self.state.get("mode") != "report":
            return self._show_menu()
        hist = self.state.setdefault("history", [])
        if hist and hist[-1] == self.current_step().name:
            hist.pop()
        while hist and hist[-1] == "notice":
            hist.pop()
        if not hist:
            self.reply(C.text(C.NOTHING_TO_GO_BACK))
            return self._ask_next()
        prev = BY_NAME[hist.pop()]
        self.state["pick"] = []
        self.state["sub"] = None
        self.answers.pop(prev.field, None)
        if prev.name == "parish":
            self.answers.pop("sector_id", None)
        self._ask(prev)

    def _start_from_last(self, clear_sections) -> None:
        key = self.reporter_key(create=False)
        report = None
        if key is not None:
            report = self.db.scalar(
                select(Report).where(Report.organization_id == self.ctx.org_id,
                                     Report.reporter_key_id == key.id,
                                     Report.status == "confirmed")
                .order_by(Report.confirmed_at.desc()).limit(1))
        if report is None:
            self.state["mode"] = "idle"
            return self.reply(C.text(C.NO_REPORT_TO_FIX))
        keep = dict((report.answers_json or {}).get("engine", {}))
        self._reset_report(keep=keep, supersedes=report.id)
        self.answers["notice"] = True
        self.answers.pop("_summary", None)
        if clear_sections:
            for sec in clear_sections:
                for f in SECTION_FIELDS[sec]:
                    self.answers.pop(f, None)
            return self._ask_next(prefix="Vamos a actualizar tu reporte. ")
        self.state["sub"] = "fix_section"
        self.reply(C.ask(C.Q_FIX_SECTION, C.SECTIONS))

    def _optout(self) -> None:
        ep = self.ctx.endpoint
        ep.status = "opted_out"
        ep.opted_out_at = self.ctx.now
        for p in self.db.scalars(select(Permission).where(
                Permission.organization_id == self.ctx.org_id,
                Permission.contact_endpoint_id == ep.id,
                Permission.withdrawn_at.is_(None),
                Permission.purpose.in_(PERMISSION_PURPOSES))):
            p.withdrawn_at = self.ctx.now
        self.state = {**new_state(), "mode": "optout"}
        self.reply(C.text(C.OPTOUT_CONFIRMATION), purpose="opt_out_confirmation")

    def _where(self) -> None:
        area_ids = [a for a in (self.answers.get("sector_id"), self.answers.get("parish_id")) if a]
        if not area_ids:
            last = self._last_report()
            if last is not None and last.area_id:
                area = self.db.get(Area, last.area_id)
                area_ids = [last.area_id] + ([area.parent_area_id] if area and
                                             area.parent_area_id else [])
        if not area_ids:
            self.reply(C.text(C.WHERE_NO_AREA))
            return self._return_after_command()
        rows = self.db.execute(
            select(Activity, ProviderOrganization)
            .join(ActivityArea, (ActivityArea.activity_id == Activity.id)
                  & (ActivityArea.organization_id == Activity.organization_id))
            .join(ProviderOrganization,
                  ProviderOrganization.id == Activity.provider_organization_id)
            .where(Activity.organization_id == self.ctx.org_id,
                   ActivityArea.area_id.in_(area_ids),
                   Activity.visibility == "public",
                   Activity.status.in_(("planned", "active")))
            .limit(5)
        ).all()
        if not rows:
            self.reply(C.text(C.WHERE_NONE))
            return self._return_after_command()
        labels = {"water_drinking": "Agua potable", "water_other": "Agua para otros usos",
                  "charging": "Punto de carga"}
        lines = []
        seen = set()
        for act, prov in rows:
            if act.id in seen:
                continue
            seen.add(act.id)
            bits = [labels.get(act.category, act.category)]
            if act.public_location_description:
                bits.append(act.public_location_description)
            sched = (act.schedule_json or {}).get("description")
            if sched:
                bits.append(sched)
            # Provider names only when the provider allows it (OPW-020).
            if prov.may_disclose_name and prov.vetting_status == "vetted":
                bits.append(f"organiza {prov.name}")
            lines.append("• " + ", ".join(bits))
        self.reply(C.text("Actividades cerca de tu zona:\n" + "\n".join(lines) +
                          "\n\nNo garantizan atención para todos."))
        self._return_after_command()

    def _return_after_command(self) -> None:
        if self.state.get("mode") == "report" and self._in_progress():
            self._ask_next()

    def _show_permissions(self) -> None:
        self.state["mode"] = "permissions"
        self.reply(C.permissions_menu(self._current_permissions()))

    def _permissions_choice(self, inbound: Inbound) -> None:
        opt = match_option(C.permission_options(), choice_id=inbound.choice_id,
                           text=inbound.text or inbound.choice_title)
        if opt is None:
            return self.reply(C.permissions_menu(self._current_permissions()))
        if opt.id == "done":
            self.state["mode"] = "idle"
            return self.reply(C.text("Listo. " + C.COMMANDS_HINT))
        current = self._current_permissions()
        self._set_permission(opt.id, not current.get(opt.id, False),
                             evidence=inbound.provider_message_id)
        self.reply(C.permissions_menu(self._current_permissions()))

    # --- DB helpers -------------------------------------------------------

    def _parishes(self) -> list[Area]:
        ids = []
        if self.ctx.campaign is not None:
            ids = list(self.db.scalars(select(CampaignArea.area_id).where(
                CampaignArea.organization_id == self.ctx.org_id,
                CampaignArea.campaign_id == self.ctx.campaign.id)))
        q = select(Area).where(Area.organization_id == self.ctx.org_id, Area.type == "parish",
                               Area.status == "active")
        if ids:
            q = q.where(Area.id.in_(ids))
        return list(self.db.scalars(q.order_by(Area.name)))

    def _sectors_of(self, parish_ids: list[str]) -> list[Area]:
        if not parish_ids:
            return []
        return list(self.db.scalars(select(Area).where(
            Area.organization_id == self.ctx.org_id, Area.type == "sector",
            Area.status == "active", Area.parent_area_id.in_(parish_ids)).order_by(Area.name)))

    def _parish_options(self) -> list[Option]:
        return [Option(a.id, a.name) for a in self._parishes()]

    def _sector_options(self, parish_id: str) -> list[Option]:
        return [Option(a.id, a.name) for a in self._sectors_of([parish_id])]

    def _meeting_point_options(self) -> list[Option]:
        sector = self.answers.get("sector_id")
        mps = []
        if sector:
            mps = list(self.db.scalars(select(MeetingPoint).where(
                MeetingPoint.organization_id == self.ctx.org_id,
                MeetingPoint.area_id == sector, MeetingPoint.status == "active")
                .order_by(MeetingPoint.name).limit(9)))
        return [*(Option(m.id, m.name) for m in mps), C.NONE_NEARBY]

    def _sector_at(self, lat: float, lon: float) -> Area | None:
        if self.db.get_bind().dialect.name != "postgresql":
            return None
        area_id = self.db.execute(text(
            "SELECT a.id FROM area a JOIN area_boundary b ON b.area_id = a.id "
            "AND b.organization_id = a.organization_id "
            "WHERE a.organization_id = :org AND a.type = 'sector' AND b.valid_to IS NULL "
            "AND ST_Contains(b.boundary, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) LIMIT 1"),
            {"org": self.ctx.org_id, "lon": lon, "lat": lat}).scalar()
        return self.db.get(Area, area_id) if area_id else None

    def _area_label(self) -> str:
        names = []
        for f in ("sector_id", "parish_id"):
            if self.answers.get(f):
                a = self.db.get(Area, self.answers[f])
                if a:
                    names.append(a.name)
        return ", ".join(names) if names else "sin identificar (el equipo la revisará)"

    def _location_label(self) -> str:
        loc = self.answers.get("location") or {}
        kind = loc.get("kind")
        if kind == "meeting_point":
            mp = self.db.get(MeetingPoint, loc.get("meeting_point_id"))
            return f"Punto de encuentro: {mp.name}" if mp else ""
        if kind == "none_nearby":
            return "Punto de encuentro: ninguno cerca"
        if kind == "address":
            return "Dirección o referencia: registrada"
        return ""

    def _last_report(self) -> Report | None:
        key = self.reporter_key(create=False)
        if key is None:
            return None
        return self.db.scalar(select(Report).where(
            Report.organization_id == self.ctx.org_id, Report.reporter_key_id == key.id,
            Report.status == "confirmed").order_by(Report.confirmed_at.desc()).limit(1))

    def reporter_key(self, create: bool = True) -> ReporterKey | None:
        ep = self.ctx.endpoint
        key = self.db.scalar(select(ReporterKey).where(
            ReporterKey.organization_id == self.ctx.org_id,
            ReporterKey.contact_endpoint_id == ep.id,
            ReporterKey.anonymized_at.is_(None)).order_by(ReporterKey.epoch.desc()).limit(1))
        if key is None and create:
            digest = lookup_hmac(self.ctx.org_id, "reporter_key", f"{ep.id}|1")
            key = ReporterKey(organization_id=self.ctx.org_id, key_hmac=digest, epoch=1,
                              contact_endpoint_id=ep.id, alias=f"Vecino-{digest[:3].upper()}")
            self.db.add(key)
            self.db.flush()
        return key

    def _notice_acked(self) -> bool:
        return self.db.scalar(select(Permission.id).where(
            Permission.organization_id == self.ctx.org_id,
            Permission.contact_endpoint_id == self.ctx.endpoint.id,
            Permission.purpose == "notice_ack",
            Permission.notice_version == self.ctx.profile.notice_version,
            Permission.withdrawn_at.is_(None)).limit(1)) is not None

    def _record_notice_ack(self, evidence: str) -> None:
        if self._notice_acked():
            return
        key = self.reporter_key()
        self.db.add(Permission(
            organization_id=self.ctx.org_id, reporter_key_id=key.id,
            contact_endpoint_id=self.ctx.endpoint.id, purpose="notice_ack",
            notice_version=self.ctx.profile.notice_version, processing_basis="notice",
            decision="granted", captured_at=self.ctx.now,
            evidence_reference=f"whatsapp:{evidence}"[:200]))

    def _current_permissions(self) -> dict[str, bool]:
        out: dict[str, bool] = {}
        rows = self.db.scalars(select(Permission).where(
            Permission.organization_id == self.ctx.org_id,
            Permission.contact_endpoint_id == self.ctx.endpoint.id,
            Permission.purpose.in_(PERMISSION_PURPOSES),
            Permission.withdrawn_at.is_(None)).order_by(Permission.captured_at.asc()))
        for p in rows:
            out[p.purpose] = p.decision == "granted"
        return out

    def _set_permission(self, purpose: str, granted: bool, evidence: str) -> None:
        key = self.reporter_key()
        for p in self.db.scalars(select(Permission).where(
                Permission.organization_id == self.ctx.org_id,
                Permission.contact_endpoint_id == self.ctx.endpoint.id,
                Permission.purpose == purpose, Permission.withdrawn_at.is_(None))):
            p.withdrawn_at = self.ctx.now
        self.db.add(Permission(
            organization_id=self.ctx.org_id, reporter_key_id=key.id,
            contact_endpoint_id=self.ctx.endpoint.id, purpose=purpose,
            notice_version=self.ctx.profile.notice_version, processing_basis="consent",
            decision="granted" if granted else "denied", captured_at=self.ctx.now,
            evidence_reference=f"whatsapp:{evidence}"[:200]))
        self.db.flush()


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


class _NoParse:
    def __repr__(self) -> str:
        return "<no parse>"


_NOPARSE: Any = _NoParse()


def _option_value(step: Step, opt: Option):
    if opt.id == "dk":
        return "unknown" if step.name in ("electricity", "water") else (
            "unknown" if step.name == "drinking_supply" else None)
    if step.options and set(o.id for o in step.options) >= {"yes", "no"}:
        return opt.id == "yes"
    if step.name.endswith("_since"):
        return _SINCE_IDS.get(opt.id)
    return opt.id


def _coerce(step: Step, v):
    if step.name.endswith("_since") and isinstance(v, int):
        return v
    if step.kind == "int":
        return int(v)
    if step.kind == "number":
        return float(v)
    return v


# ---------------------------------------------------------------------------
# Loading the conversation for an inbound message
# ---------------------------------------------------------------------------


@dataclass
class Resolved:
    endpoint: ContactEndpoint
    conversation: Conversation
    created: bool = False
    extra: dict = field(default_factory=dict)


def resolve_conversation(db: Session, org_id: str, campaign: Campaign | None, address: str,
                         now: datetime) -> Resolved:
    """Find or create the endpoint (by lookup HMAC) and its conversation."""
    from app.crypto import encrypt

    digest = lookup_hmac(org_id, "whatsapp", address)
    ep = db.scalar(select(ContactEndpoint).where(
        ContactEndpoint.organization_id == org_id, ContactEndpoint.channel == "whatsapp",
        ContactEndpoint.address_lookup_hmac == digest))
    created = False
    if ep is None:
        ep = ContactEndpoint(organization_id=org_id, channel="whatsapp",
                             encrypted_address=encrypt(address), address_lookup_hmac=digest,
                             status="active", last_activity_at=now)
        db.add(ep)
        db.flush()
        created = True
    elif ep.status == "deleted":
        ep.status = "active"
        ep.encrypted_address = encrypt(address)
    conv = db.scalar(select(Conversation).where(
        Conversation.organization_id == org_id, Conversation.contact_endpoint_id == ep.id)
        .order_by(Conversation.created_at.desc()).limit(1))
    if conv is None:
        conv = Conversation(organization_id=org_id, contact_endpoint_id=ep.id,
                            campaign_id=campaign.id if campaign else None,
                            questionnaire_version_id=(campaign.questionnaire_version_id
                                                      if campaign else None),
                            intake_state="start", state_json=new_state())
        db.add(conv)
        db.flush()
    return Resolved(ep, conv, created)


def record_inbound_message(db: Session, org_id: str, conv: Conversation, phone_number_id: str,
                           inbound: Inbound) -> bool:
    """Insert the inbound ``message`` row; False if this provider id was seen before."""
    exists = db.scalar(select(Message.id).where(
        Message.channel_account_id == phone_number_id,
        Message.provider_message_id == inbound.provider_message_id))
    if exists:
        return False
    db.add(Message(organization_id=org_id, conversation_id=conv.id,
                   channel_account_id=phone_number_id,
                   provider_message_id=inbound.provider_message_id, direction="inbound",
                   received_at=inbound.received_at or utcnow(), delivery_status="received"))
    db.flush()
    return True
