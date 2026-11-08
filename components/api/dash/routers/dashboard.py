"""Dashboard, reports (report-centric), campaigns, and natural-language ask.

STEP 1: realistic fake data. Privacy settings from the context are applied to
report rows (masked phones, omitted names, area-level location).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from dash.config import get_settings
from dash.context import RequestContext
from dash.deps import get_context, get_db
from dash.errors import NotFound
from dash.fakestore import MIAMI_AREAS
from dash import campaign_fields as CF
from dash import read_models as RM
from dash import schemas as S
from dash import settings_store

router = APIRouter(tags=["dashboard"])


def _apply_privacy(ctx: RequestContext, row: dict) -> dict:
    """Apply data-protection to a report/contact row before it leaves the API."""
    dp = ctx.data_protection
    r = dict(row)
    r["reporter_name"] = dp.apply_name(row.get("reporter_name"))
    r["reporter_phone"] = dp.apply_phone(row.get("reporter_phone"))
    if dp.location_precision == "area":
        r["area"] = row.get("area")  # already area-level; precise point never exposed
    return r


# ---- Dashboard -------------------------------------------------------------

def _plural(n: int, singular: str, plural: str | None = None) -> str:
    return singular if n == 1 else (plural or singular + "s")


def _build_summary(org_name: str, m: dict, areas: list[dict]) -> str:
    """A plain-language summary built from the real numbers (no LLM).

    Reads naturally for the empty case, the all-clear case, and the urgent case,
    and names the hardest-hit neighborhoods when there are any.
    """
    reports = m["reports_today"]
    if reports == 0:
        return (f"No new reports in the last 24 hours for {org_name}. "
                "The map reflects the most recent known conditions.")

    # Lead sentence with the headline count.
    lead = (f"{reports} {_plural(reports, 'report')} came in over the last 24 hours "
            f"for {org_name}.")

    # Service impact clause (only mention what's actually affected).
    parts = []
    if m["without_power"]:
        parts.append(f"{m['without_power']} {_plural(m['without_power'], 'household')} "
                     "without power")
    if m["without_water"]:
        parts.append(f"{m['without_water']} without water")
    if parts:
        joined = ", ".join(parts)
        impact = " " + joined[0].upper() + joined[1:] + "."
    else:
        impact = " No power or water outages reported."

    # Urgent clause.
    urgent = m["urgent"]
    if urgent:
        urgent_clause = (f" {urgent} {_plural(urgent, 'report needs', 'reports need')} "
                         "urgent review.")
    else:
        urgent_clause = " Nothing is flagged urgent right now."

    # Hardest-hit neighborhoods.
    names = [a["area"] for a in areas[:2] if a.get("area")]
    if names:
        where = f" {' and '.join(names)} {_plural(len(names), 'is', 'are')} the hardest hit."
    else:
        where = ""

    return lead + impact + urgent_clause + where


@router.get("/dashboard/summary", response_model=S.DashboardSummary)
def dashboard_summary(ctx: RequestContext = Depends(get_context),
                      db: Session = Depends(get_db)) -> S.DashboardSummary:
    m = RM.dashboard_metrics(db, ctx.org_id)
    areas = RM.area_breakdown(db, ctx.org_id)
    return S.DashboardSummary(
        summary=_build_summary(ctx.org_name, m, areas),
        metrics=S.DashboardMetrics(**m),
        generated_at=RM._utcnow().isoformat(),
    )


@router.get("/dashboard/areas", response_model=list[S.AreaCount])
def dashboard_areas(ctx: RequestContext = Depends(get_context),
                    db: Session = Depends(get_db)) -> list[S.AreaCount]:
    return [S.AreaCount(**a) for a in RM.area_breakdown(db, ctx.org_id)]


@router.get("/dashboard/feed", response_model=S.FeedResponse)
def dashboard_feed(
    since: str | None = Query(default=None),
    ctx: RequestContext = Depends(get_context),
    db: Session = Depends(get_db),
) -> S.FeedResponse:
    items = [S.FeedItem(**it) for it in RM.feed(db, ctx.org_id, since=since)]
    return S.FeedResponse(items=items, cursor=items[-1].received_at if items else None)


# ---- Reports (replaces cases) ---------------------------------------------

@router.get("/reports", response_model=list[S.ReportSummary])
def list_reports(
    status: str | None = Query(default=None),
    ctx: RequestContext = Depends(get_context),
    db: Session = Depends(get_db),
) -> list[S.ReportSummary]:
    rows = RM.list_reports(db, ctx.org_id, status=status)
    return [S.ReportSummary(**_apply_privacy(ctx, r)) for r in rows]


@router.get("/reports/{report_id}", response_model=S.ReportDetail)
def get_report(report_id: str, ctx: RequestContext = Depends(get_context),
               db: Session = Depends(get_db)) -> S.ReportDetail:
    # `minimal` preset exposes aggregates only — no individual report records.
    if ctx.data_protection.hide_individual_records:
        raise NotFound("individual records are hidden under the minimal privacy preset")
    row = RM.get_report(db, ctx.org_id, report_id)
    if row is None:
        raise NotFound("report not found")
    return S.ReportDetail(**_apply_privacy(ctx, row))


@router.patch("/reports/{report_id}", response_model=S.ReportDetail)
def patch_report(report_id: str, body: S.ReportPatch, ctx: RequestContext = Depends(get_context),
                 db: Session = Depends(get_db)) -> S.ReportDetail:
    row = RM.patch_report(db, ctx.org_id, report_id,
                          status=body.status, notes=body.notes, assignee=body.assignee)
    if row is None:
        raise NotFound("report not found")
    return S.ReportDetail(**_apply_privacy(ctx, row))


# ---- Campaigns -------------------------------------------------------------
#
# Campaigns are stored durably as a JSON list in the shared policy_version table
# (via settings_store) — no new tables, no migration. Each campaign carries its
# AI-suggested `fields` so GET returns them and results can be aggregated typed.

_CAMPAIGNS_SETTING = "campaigns"


def _default_campaigns() -> list[dict]:
    """Seed shown to a brand-new org so the demo isn't empty."""
    return [{
        "id": "camp-1", "name": "November Outage Watch",
        "collection_template_id": "power_water_outages",
        "areas": MIAMI_AREAS[:4], "status": "active",
        "starts_at": "2026-11-01T00:00:00+00:00", "ends_at": None,
        "fields": [f.model_dump() for f in CF.template_default_fields("power_water_outages")],
    }]


def _load_campaigns(db: Session, org_id: str) -> list[dict]:
    stored = settings_store.get_setting(db, org_id, _CAMPAIGNS_SETTING)
    if stored is None:
        return _default_campaigns()
    return list(stored.get("campaigns", []))


def _save_campaigns(db: Session, org_id: str, campaigns: list[dict]) -> None:
    settings_store.put_setting(db, org_id, _CAMPAIGNS_SETTING, {"campaigns": campaigns})


@router.post("/campaigns/suggest-fields", response_model=S.SuggestFieldsResponse)
def suggest_campaign_fields(
    body: S.SuggestFieldsRequest,
    ctx: RequestContext = Depends(get_context),
    db: Session = Depends(get_db),
) -> S.SuggestFieldsResponse:
    settings = get_settings()
    org_profile = settings_store.get_setting(db, ctx.org_id, "profile")
    return CF.suggest_fields(
        body, org_profile,
        api_key=settings.openai_api_key, model=settings.openai_model,
    )


@router.post("/campaigns", response_model=S.Campaign)
def create_campaign(body: S.CampaignCreate, ctx: RequestContext = Depends(get_context),
                    db: Session = Depends(get_db)) -> S.Campaign:
    campaigns = _load_campaigns(db, ctx.org_id)
    # Keep seeded campaigns durable the first time we write.
    camp = {
        "id": f"camp-{len(campaigns) + 1}",
        "name": body.name, "collection_template_id": body.collection_template_id,
        "areas": body.areas, "status": "active",
        "starts_at": body.starts_at, "ends_at": body.ends_at,
        "fields": [f.model_dump() for f in body.fields],
    }
    campaigns.append(camp)
    _save_campaigns(db, ctx.org_id, campaigns)
    return S.Campaign(**camp)


@router.get("/campaigns", response_model=list[S.Campaign])
def list_campaigns(ctx: RequestContext = Depends(get_context),
                   db: Session = Depends(get_db)) -> list[S.Campaign]:
    return [S.Campaign(**c) for c in _load_campaigns(db, ctx.org_id)]


@router.get("/campaigns/{campaign_id}/results", response_model=S.CampaignResults)
def campaign_results(campaign_id: str, ctx: RequestContext = Depends(get_context),
                     db: Session = Depends(get_db)) -> S.CampaignResults:
    camp = next((c for c in _load_campaigns(db, ctx.org_id) if c["id"] == campaign_id), None)
    if camp is None:
        raise NotFound("campaign not found")
    fields = [S.CampaignField(**f) for f in camp.get("fields", [])]
    answers = RM.campaign_answers(db, ctx.org_id, campaign_id=campaign_id)
    return CF.aggregate_results(campaign_id, fields, answers)


# ---- Ask (NL question; mocked) --------------------------------------------

@router.post("/ask", response_model=S.AskResponse)
def ask(body: S.AskRequest, ctx: RequestContext = Depends(get_context)) -> S.AskResponse:
    return S.AskResponse(
        answer=(f"In the last 24 hours, Little Haiti had the most urgent reports "
                f"(5), mostly elderly residents without power. Allapattah follows "
                f"with medical-device charging needs."),
        data={"top_area": "Little Haiti", "urgent_count": 5, "question": body.question},
    )
