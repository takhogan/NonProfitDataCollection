"""Dashboard, reports (report-centric), campaigns, and natural-language ask.

STEP 1: realistic fake data. Privacy settings from the context are applied to
report rows (masked phones, omitted names, area-level location).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.context import RequestContext
from app.deps import get_context
from app.errors import NotFound
from app.fakestore import (
    MIAMI_AREAS, fake_feed, fake_report_detail, fake_reports,
)
from app import schemas as S

router = APIRouter(tags=["dashboard"])

# In-memory campaign store (fake) keyed by org.
_CAMPAIGNS: dict[str, list[dict]] = {}


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

@router.get("/dashboard/summary", response_model=S.DashboardSummary)
def dashboard_summary(ctx: RequestContext = Depends(get_context)) -> S.DashboardSummary:
    reports = fake_reports()
    without_power = sum(1 for r in reports if r["service_type"] == "electricity"
                        and r["service_status"] in ("unavailable", "intermittent"))
    without_water = sum(1 for r in reports if r["service_type"] == "piped_water"
                        and r["service_status"] in ("unavailable", "intermittent"))
    urgent = sum(1 for r in reports if r["urgent"])
    return S.DashboardSummary(
        summary=(f"{len(reports)} reports today across {ctx.org_name}: "
                 f"{without_power} without power, {without_water} without water, "
                 f"{urgent} urgent. Little Haiti and Allapattah are the hardest hit."),
        metrics=S.DashboardMetrics(
            reports_today=len(reports), without_power=without_power,
            without_water=without_water, urgent=urgent,
        ),
        generated_at="2026-11-08T14:00:00+00:00",
    )


@router.get("/dashboard/areas", response_model=list[S.AreaCount])
def dashboard_areas(ctx: RequestContext = Depends(get_context)) -> list[S.AreaCount]:
    # Fake per-neighborhood rollup.
    data = [
        ("Little Haiti", 18, 12, 4, 5), ("Liberty City", 14, 6, 9, 3),
        ("Overtown", 9, 5, 2, 1), ("Allapattah", 12, 8, 3, 4),
        ("Hialeah", 11, 3, 6, 1), ("Little Havana", 8, 4, 2, 1),
    ]
    return [S.AreaCount(area=a, reports=n, without_power=p, without_water=w, urgent=u)
            for (a, n, p, w, u) in data]


@router.get("/dashboard/feed", response_model=S.FeedResponse)
def dashboard_feed(
    since: str | None = Query(default=None),
    ctx: RequestContext = Depends(get_context),
) -> S.FeedResponse:
    items = [S.FeedItem(**it) for it in fake_feed()]
    return S.FeedResponse(items=items, cursor=items[0].received_at if items else None)


# ---- Reports (replaces cases) ---------------------------------------------

@router.get("/reports", response_model=list[S.ReportSummary])
def list_reports(
    status: str | None = Query(default=None),
    ctx: RequestContext = Depends(get_context),
) -> list[S.ReportSummary]:
    rows = fake_reports()
    if status:
        rows = [r for r in rows if r["status"] == status]
    return [S.ReportSummary(**_apply_privacy(ctx, r)) for r in rows]


@router.get("/reports/{report_id}", response_model=S.ReportDetail)
def get_report(report_id: str, ctx: RequestContext = Depends(get_context)) -> S.ReportDetail:
    # `minimal` preset exposes aggregates only — no individual report records.
    if ctx.data_protection.hide_individual_records:
        raise NotFound("individual records are hidden under the minimal privacy preset")
    row = fake_report_detail(report_id)
    if row is None:
        raise NotFound("report not found")
    row = _apply_privacy(ctx, row)
    return S.ReportDetail(**row)


@router.patch("/reports/{report_id}", response_model=S.ReportDetail)
def patch_report(report_id: str, body: S.ReportPatch, ctx: RequestContext = Depends(get_context)) -> S.ReportDetail:
    row = fake_report_detail(report_id)
    if row is None:
        raise NotFound("report not found")
    if body.status is not None:
        row["status"] = body.status
    if body.notes is not None:
        row["notes"] = body.notes
    if body.assignee is not None:
        row["assignee"] = body.assignee
    return S.ReportDetail(**_apply_privacy(ctx, row))


# ---- Campaigns -------------------------------------------------------------

@router.post("/campaigns", response_model=S.Campaign)
def create_campaign(body: S.CampaignCreate, ctx: RequestContext = Depends(get_context)) -> S.Campaign:
    camp = {
        "id": f"camp-{len(_CAMPAIGNS.get(ctx.org_id, [])) + 1}",
        "name": body.name, "collection_template_id": body.collection_template_id,
        "areas": body.areas, "status": "active",
        "starts_at": body.starts_at, "ends_at": body.ends_at,
    }
    _CAMPAIGNS.setdefault(ctx.org_id, []).append(camp)
    return S.Campaign(**camp)


@router.get("/campaigns", response_model=list[S.Campaign])
def list_campaigns(ctx: RequestContext = Depends(get_context)) -> list[S.Campaign]:
    seeded = _CAMPAIGNS.get(ctx.org_id)
    if not seeded:
        seeded = [{
            "id": "camp-1", "name": "November Outage Watch",
            "collection_template_id": "power_water_outages",
            "areas": MIAMI_AREAS[:4], "status": "active",
            "starts_at": "2026-11-01T00:00:00+00:00", "ends_at": None,
        }]
    return [S.Campaign(**c) for c in seeded]


# ---- Ask (NL question; mocked) --------------------------------------------

@router.post("/ask", response_model=S.AskResponse)
def ask(body: S.AskRequest, ctx: RequestContext = Depends(get_context)) -> S.AskResponse:
    return S.AskResponse(
        answer=(f"In the last 24 hours, Little Haiti had the most urgent reports "
                f"(5), mostly elderly residents without power. Allapattah follows "
                f"with medical-device charging needs."),
        data={"top_area": "Little Haiti", "urgent_count": 5, "question": body.question},
    )
