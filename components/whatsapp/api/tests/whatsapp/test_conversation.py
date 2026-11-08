"""End-to-end conversation tests on PostgreSQL with RLS (OPW-010..035)."""
from __future__ import annotations

from datetime import timedelta

from app.models.base import utcnow
from app.whatsapp.adapter import FakeAdapter
from app.whatsapp.extraction import FakeExtractor


def bodies(msgs):
    return " | ".join(m["message"].get("body", "") for m in msgs)


def walk_to_electricity(b, location="Ninguno"):
    out = b.say("Hola")
    assert "Metron Reporter" in bodies(out) and "no entrega ayuda" in bodies(out)
    b.pick("Continuar")
    assert "parroquia" in b.last()["body"]
    b.say("1")  # numbered fallback: first parish
    assert "sector" in b.last()["body"]
    b.tap(b.options()[0]["id"])
    if b.pnid == "PNID-PROTECTIVE":
        assert "punto de encuentro" in b.last()["body"]
        b.pick(location)
    else:
        assert "dirección" in b.last()["body"]
        b.say("Calle Real, frente a la panadería")
    assert "luz" in b.last()["body"]


def finish_needs_and_perms(b, urgent="No", perms=("Sí", "No", "No")):
    b.pick("No")          # need_drinking
    b.pick("No")          # need_other
    b.pick("No")          # need_charging
    b.pick(urgent)        # urgent
    for p in perms:
        b.pick(p)
    assert "Este es tu reporte" in b.last()["body"]


def test_protective_full_report_writes_rows(bot):
    b = bot("protective")
    walk_to_electricity(b)
    b.pick("No hay")                 # electricity
    assert "Desde cuándo" in b.last()["body"]
    b.say("ayer")                    # synonym match
    b.pick("Sí hay")                 # water
    b.pick("Sí")                     # need drinking water
    b.say("5 personas")
    b.say("40")
    b.pick("Poca")
    b.pick("No")                     # other water
    b.pick("Sí")                     # charging
    b.pick("Equipo médico")
    b.say("dos")
    b.pick("No")                     # urgent
    b.pick("Sí")                     # refresh
    b.pick("No")                     # area broadcasts
    b.pick("No")                     # contact list
    summary = b.last()["body"]
    assert "agua para beber (5 personas, 40 litros, queda poca)" in summary
    assert "Luz: no hay (desde ayer)" in summary
    out = b.pick("Confirmar")
    assert "registrado" in bodies(out) and "escribirte cada pocos días" in bodies(out)

    rep = b.report()
    assert rep["status"] == "confirmed" and rep["source_channel"] == "whatsapp"
    assert rep["location_kind"] == "none_nearby" and rep["area_id"]
    obs = {o["service_type"]: o for o in b.owner(
        "SELECT * FROM observation WHERE report_id = :r", r=rep["id"])}
    assert obs["electricity"]["status"] == "unavailable"
    assert obs["electricity"]["outage_started_at"] is not None
    assert obs["piped_water"]["status"] == "available"
    needs = {n["category"]: n for n in b.owner("SELECT * FROM need WHERE report_id = :r",
                                               r=rep["id"])}
    assert needs["water_drinking"]["people_affected"] == 5
    assert float(needs["water_drinking"]["quantity"]) == 40.0
    assert needs["water_drinking"]["unit"] == "liters"
    assert needs["water_drinking"]["remaining_supply"] == "little"
    assert float(needs["charging"]["quantity"]) == 2 and needs["charging"]["unit"] == "devices"
    dev = b.owner("SELECT d.* FROM charging_device_request d JOIN need n ON n.id = d.need_id "
                  "WHERE n.report_id = :r", r=rep["id"])[0]
    assert dev["device_type"] == "medical_device" and dev["device_count"] == 2
    perms = {p["purpose"]: p["decision"] for p in b.owner(
        "SELECT purpose, decision FROM permission WHERE reporter_key_id = :k "
        "AND withdrawn_at IS NULL", k=rep["reporter_key_id"])}
    assert perms == {"notice_ack": "granted", "refresh_prompts": "granted",
                     "area_broadcasts": "denied", "contact_list": "denied"}
    # No phone number in clear anywhere; inbox payloads are reduced.
    ep = b.owner("SELECT encrypted_address FROM contact_endpoint ce JOIN reporter_key k "
                 "ON k.contact_endpoint_id = ce.id WHERE k.id = :k", k=rep["reporter_key_id"])[0]
    assert b.phone.encode() not in bytes(ep["encrypted_address"])
    leaks = b.owner("SELECT count(*) AS n FROM inbound_event WHERE processed_at IS NOT NULL "
                    "AND payload_json::text LIKE :p", p=f"%{b.phone}%")[0]["n"]
    assert leaks == 0


def test_openai_extraction_prefills_and_redacts(bot):
    ex = FakeExtractor(result={
        "electricity_status": "unavailable", "electricity_since_days": 1,
        "water_status": "unavailable", "water_since_days": 3,
        "needs_drinking_water": True, "drinking_people": 4,
    })
    b = bot("protective", extractor=ex)
    walk_to_electricity(b)
    b.say("Se fue la luz anoche y el agua no llega desde el lunes, somos 4. "
          "Mi número es +58 412 555 1234")
    # Only the unreadable answer went out, redacted, with its question.
    assert len(ex.calls) == 1
    assert "555" not in ex.calls[0]["answer"] and "[número]" in ex.calls[0]["answer"]
    assert ex.calls[0]["question"].startswith("¿Hay luz")
    # Electricity, onset, water, onset, drinking need and people were prefilled:
    # the next question is the liters one.
    assert "litros" in b.last()["body"]
    st = b.conversation()["state_json"]
    assert st["answers"]["electricity"] == "unavailable"
    assert st["answers"]["water_since"] == 3
    assert "drinking_people" in st["prefilled"]


def test_extraction_never_used_for_consent(bot):
    ex = FakeExtractor(result={"urgent": False})
    b = bot("protective", extractor=ex)
    walk_to_electricity(b)
    for _ in range(2):
        b.pick("Sí hay")
    finish = ["No", "No", "No", "No"]
    for f in finish:
        b.pick(f)
    assert "escribirte cada pocos días" in b.last()["body"]
    calls = len(ex.calls)
    b.say("bueno, depende de lo que hagan")
    b.say("ya veremos")
    assert len(ex.calls) == calls  # permission steps never call the extractor
    st = b.conversation()["state_json"]
    assert st["answers"]["perm_refresh"] is False  # unclear consent is a "no"


def test_unreadable_text_reasked_once_then_stored_encrypted(bot):
    b = bot("protective")  # extraction off
    walk_to_electricity(b)
    b.say("pues mira la cosa está complicada")
    assert b.last()["body"].startswith("No entendí")
    out = b.say("mi vecina dice que sí pero no sé bien")
    assert "Guardé tu comentario" in bodies(out)
    st = b.conversation()["state_json"]
    assert "unparsed_text" in st["flags"]
    assert "vecina" not in str(st["notes"])  # encrypted
    for _ in range(1):
        b.pick("Sí hay")
    finish_needs_and_perms(b)
    b.pick("Confirmar")
    rep = b.report()
    tasks = b.owner("SELECT reason FROM review_task WHERE report_id = :r", r=rep["id"])
    assert {"reason": "unparsed_text"} in [dict(t) for t in tasks]


def test_media_explained_and_question_repeated(bot):
    b = bot("protective")
    walk_to_electricity(b)
    out = b.media()
    assert "No podemos abrir notas de voz" in bodies(out)
    assert "luz" in b.last()["body"]


def test_ayuda_hands_off_and_bot_stays_quiet(bot):
    b = bot("protective")
    b.say("Hola")
    out = b.say("ayuda")
    assert "una persona del equipo" in bodies(out)
    assert b.conversation()["intake_state"] == "handoff"
    assert b.say("hola?") == []
    out = b.say("Menú")
    assert b.last()["kind"] == "list"


def test_baja_stops_everything_until_menu(bot):
    b = bot("protective")
    b.say("Hola")
    b.pick("Continuar")
    out = b.say("BAJA")
    assert "no te enviaremos más mensajes" in bodies(out)
    ep = b.owner("SELECT ce.status FROM contact_endpoint ce JOIN conversation c "
                 "ON c.contact_endpoint_id = ce.id JOIN message m ON m.conversation_id = c.id "
                 "WHERE m.provider_message_id = :p", p=b.last_mid)[0]
    assert ep["status"] == "opted_out"
    assert b.say("1") == []
    b.say("menú")
    assert b.last()["kind"] == "list"


def test_atras_goes_back_one_question(bot):
    b = bot("protective")
    walk_to_electricity(b)
    b.pick("No hay")
    assert "Desde cuándo" in b.last()["body"]
    b.say("atrás")
    assert b.last()["body"].startswith("¿Hay luz")


def test_corregir_supersedes_previous_report(bot):
    b = bot("protective")
    walk_to_electricity(b)
    b.pick("Sí hay")
    b.pick("Sí hay")
    finish_needs_and_perms(b)
    b.pick("Confirmar")
    first = b.report()
    b.say("corregir")
    b.pick("Luz y agua")
    b.pick("No hay")
    b.pick("Desde hoy")
    b.pick("Sí hay")
    assert "Este es tu reporte" in b.last()["body"]
    out = b.pick("Confirmar")
    assert "Actualizamos tu reporte anterior" in bodies(out)
    second = b.report()
    assert second["supersedes_report_id"] == first["id"]
    old = b.owner("SELECT status FROM report WHERE id = :r", r=first["id"])[0]
    assert old["status"] == "superseded"


def test_urgent_yes_sends_referral_and_creates_task(bot):
    b = bot("protective")
    walk_to_electricity(b)
    b.pick("Sí hay")
    b.pick("Sí hay")
    b.pick("No")
    b.pick("No")
    b.pick("No")
    out = b.pick("Sí")  # urgent
    assert "no es un servicio de emergencias" in bodies(out)
    tasks = b.owner("SELECT reason, area_id FROM review_task WHERE reason = 'urgent_flag' "
                    "AND report_id IS NULL ORDER BY created_at DESC LIMIT 1")
    assert tasks and tasks[0]["area_id"]


def test_standard_profile_stores_encrypted_address(bot):
    b = bot("standard")
    walk_to_electricity(b)
    b.pick("Sí hay")
    b.pick("Sí hay")
    finish_needs_and_perms(b)
    b.pick("Confirmar")
    rep = b.report()
    assert rep["location_kind"] == "address"
    loc = b.owner("SELECT encrypted_address FROM report_location WHERE report_id = :r",
                  r=rep["id"])[0]
    assert b"panader" not in bytes(loc["encrypted_address"])
    assert "panader" not in str(rep["answers_json"])


def test_replayed_event_does_not_reply_twice(bot):
    b = bot("protective")
    b.say("Hola", run=False)
    ev = b.owner("SELECT payload_json FROM inbound_event WHERE provider_message_id = :p",
                 p=b.last_mid)[0]
    b.store(ev["payload_json"], b.last_mid + "-replay")  # same message, second delivery
    out = b.run()
    assert len(out) == 1


def test_unmapped_number_is_ignored(bot):
    b = bot("protective")
    b.pnid = "PNID-UNKNOWN"
    b.say("Hola")
    ev = b.owner("SELECT status, last_error FROM inbound_event WHERE provider_message_id = :p",
                 p=b.last_mid)[0]
    assert ev["status"] == "ignored" and ev["last_error"] == "unmapped_channel_account"
    assert b.mine() == []


def _status(b, wamid, status, callback=None):
    st = {"id": wamid, "status": status, "timestamp": "1", "recipient_id": b.phone}
    if callback:
        st["biz_opaque_callback_data"] = callback
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": b.pnid},
                                                 "statuses": [st]}}]}]}
    b.store(payload, f"{wamid}:{status}", event_type="status")


def test_status_is_monotonic_and_read_after_delivered_is_kept(bot):
    b = bot("protective")
    b.say("Hola")
    wamid = b.mine()[-1]["id"]
    # A late "sent" after "read" must not regress it. (A duplicate "delivered"
    # never gets this far: the webhook dedupes on (wamid, status).)
    for s in ("delivered", "read", "sent"):
        _status(b, wamid, s)
    b.run()
    m = b.owner("SELECT delivery_status FROM message WHERE provider_message_id = :p", p=wamid)
    assert m[0]["delivery_status"] == "read"


def test_uncertain_send_is_not_resent_and_reconciled_by_callback(bot):
    adapter = FakeAdapter(uncertain_times=1)
    b = bot("protective", adapter_=adapter)
    b.say("Hola")
    assert b.mine() == []
    row = b.owner("SELECT o.id, o.status, o.block_reason FROM outbox_message o "
                  "JOIN conversation c ON c.id = o.conversation_id JOIN message m "
                  "ON m.conversation_id = c.id WHERE m.provider_message_id = :p", p=b.last_mid)[0]
    assert (row["status"], row["block_reason"]) == ("sending", "uncertain")
    b.run()
    assert b.mine() == []  # not resent
    _status(b, "wamid.REAL1", "sent", callback=row["id"])
    b.run()
    after = b.owner("SELECT status, provider_message_id FROM outbox_message WHERE id = :i",
                    i=row["id"])[0]
    assert after["status"] == "sent" and after["provider_message_id"] == "wamid.REAL1"


def test_uncertain_send_without_confirmation_fails_visibly(bot):
    adapter = FakeAdapter(uncertain_times=1)
    b = bot("protective", adapter_=adapter)
    b.say("Hola")
    with b.engine.begin() as c:
        from sqlalchemy import text as t
        c.execute(t("UPDATE outbox_message SET next_attempt_at = now() - interval '1 minute' "
                    "WHERE status = 'sending' AND block_reason = 'uncertain'"))
    b.run()
    rows = b.owner("SELECT status, block_reason FROM outbox_message WHERE "
                   "block_reason = 'uncertain_unconfirmed'")
    assert rows and rows[0]["status"] == "failed"
    assert b.mine() == []


def test_free_form_reply_blocked_outside_24h_window(bot):
    b = bot("protective")
    old = int((utcnow() - timedelta(hours=25)).timestamp())
    b.say("Hola", ts=old)
    rows = b.owner("SELECT o.status, o.block_reason FROM outbox_message o JOIN conversation c "
                   "ON c.id = o.conversation_id JOIN message m ON m.conversation_id = c.id "
                   "WHERE m.provider_message_id = :p", p=b.last_mid)
    assert rows[0]["block_reason"] == "outside_window_no_template"
    assert b.mine() == []


def test_surge_mode_sends_one_holding_reply_first(bot, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "surge_lag_seconds", 60)
    b = bot("protective")
    b.say("Hola", run=False)
    with b.engine.begin() as c:
        from sqlalchemy import text as t
        c.execute(t("UPDATE inbound_event SET received_at = now() - interval '5 minutes' "
                    "WHERE provider_message_id = :p"), {"p": b.last_mid})
    out = b.run()
    assert "Hay muchos mensajes" in out[0]["message"]["body"]
    assert "Metron Reporter" in bodies(out[1:])
    holding = [m for m in b.mine() if "Hay muchos" in (m["message"].get("body") or "")]
    assert len(holding) == 1
