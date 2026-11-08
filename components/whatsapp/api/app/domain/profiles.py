"""Privacy profile policy (DOM-030..034, SEC-10, NFR-09).

- ``protective_profile`` / ``standard_profile``: the two named presets.
- ``validate_profile``: platform minimums (k >= 3 everywhere, public coarser than
  provider view, no GPS in meeting-point mode).
- ``validate_submission``: rejects fields the profile disallows (ProfileViolation).
- ``plan_tightening`` / ``run_purge``: fields to purge when a stricter profile is
  activated; runs within 24 hours and is audited with counts.
- ``capture_profile``: loosening applies only to reports collected under the new
  notice version; existing data is never enriched.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable, Optional

from app.domain.errors import PolicyBelowMinimum, ProfileViolation, ValidationFailed
from app.domain.types import (
    AREA_LEVEL_ORDER,
    AddressLocation,
    AreaLevel,
    ContactField,
    LocationMode,
    NeedCategory,
    PermissionPurpose,
    PrivacyProfile,
    ProfileKind,
    Relationship,
    Report,
    ReporterContact,
    ReportSubmission,
    Unit,
)

PLATFORM_MIN_K = 3
PROTECTIVE_MIN_PUBLIC_K = 10
PROTECTIVE_MIN_PUBLIC_DELAY = timedelta(hours=24)
TIGHTENING_PURGE_DEADLINE = timedelta(hours=24)

PROTECTIVE_CONTACT_FIELDS = frozenset(
    {ContactField.alias, ContactField.sector, ContactField.meeting_point, ContactField.phone}
)
STANDARD_CONTACT_FIELDS = frozenset({ContactField.name, ContactField.address, ContactField.phone})

# DB-020: a unit is valid only for its categories.
CATEGORY_UNITS: dict[NeedCategory, frozenset[Unit]] = {
    NeedCategory.water_drinking: frozenset({Unit.liters}),
    NeedCategory.water_other: frozenset({Unit.liters}),
    NeedCategory.charging: frozenset({Unit.devices}),
}


def protective_profile(org_id: str, version: int = 1, notice_version: str = "n1") -> PrivacyProfile:
    """CSL default (components/REQUIREMENTS.md, privacy profiles table)."""
    return PrivacyProfile(
        org_id=org_id,
        version=version,
        kind=ProfileKind.protective,
        notice_version=notice_version,
        names_allowed=False,
        location_mode=LocationMode.meeting_point,
        gps_allowed=False,
        reporter_phone_retention_days=7,
        household_records_allowed=False,
        contact_list_enabled=True,
        contact_list_fields=PROTECTIVE_CONTACT_FIELDS,
        reporter_key_rotation_days=30,
        aggregate_k=PLATFORM_MIN_K,
        public_dashboard_enabled=False,
        public_level=AreaLevel.parish,
        public_k=PROTECTIVE_MIN_PUBLIC_K,
        public_delay=PROTECTIVE_MIN_PUBLIC_DELAY,
    )


def standard_profile(org_id: str, version: int = 1, notice_version: str = "n1") -> PrivacyProfile:
    return PrivacyProfile(
        org_id=org_id,
        version=version,
        kind=ProfileKind.standard,
        notice_version=notice_version,
        names_allowed=True,
        location_mode=LocationMode.address,
        gps_allowed=True,
        reporter_phone_retention_days=None,
        household_records_allowed=True,
        contact_list_enabled=True,
        contact_list_fields=STANDARD_CONTACT_FIELDS,
        reporter_key_rotation_days=180,
        aggregate_k=PLATFORM_MIN_K,
        public_dashboard_enabled=True,
        public_level=AreaLevel.sector,
        public_k=5,
        public_delay=timedelta(0),
    )


def level_index(level: AreaLevel) -> int:
    return AREA_LEVEL_ORDER.index(level)


def validate_profile(profile: PrivacyProfile) -> PrivacyProfile:
    """Enforce platform minimums. Returns the profile unchanged when valid."""
    problems: list[str] = []
    if profile.aggregate_k < PLATFORM_MIN_K:
        problems.append(f"aggregate_k must be >= {PLATFORM_MIN_K}")
    if profile.public_k < PLATFORM_MIN_K:
        problems.append(f"public_k must be >= {PLATFORM_MIN_K}")
    if profile.public_k < profile.aggregate_k:
        problems.append("public_k must be >= aggregate_k (public view is coarser)")
    if profile.public_delay < timedelta(0):
        problems.append("public_delay must be >= 0")
    if level_index(profile.public_level) > level_index(AreaLevel.sector):
        problems.append("public_level invalid")
    if profile.location_mode is LocationMode.meeting_point and profile.gps_allowed:
        problems.append("gps_allowed requires location_mode=address")
    if profile.reporter_key_rotation_days < 1:
        problems.append("reporter_key_rotation_days must be >= 1")
    if profile.reporter_phone_retention_days is not None and profile.reporter_phone_retention_days < 0:
        problems.append("reporter_phone_retention_days must be >= 0")
    if not profile.names_allowed and ContactField.name in profile.contact_list_fields:
        problems.append("contact_list_fields.name requires names_allowed")
    if profile.location_mode is LocationMode.meeting_point and ContactField.address in profile.contact_list_fields:
        problems.append("contact_list_fields.address requires location_mode=address")
    if profile.kind is ProfileKind.protective:
        if profile.public_k < PROTECTIVE_MIN_PUBLIC_K:
            problems.append(f"protective public_k must be >= {PROTECTIVE_MIN_PUBLIC_K}")
        if profile.public_delay < PROTECTIVE_MIN_PUBLIC_DELAY:
            problems.append("protective public_delay must be >= 24h")
        if level_index(profile.public_level) > level_index(AreaLevel.parish):
            problems.append("protective public_level must be parish or coarser")
        if profile.names_allowed or profile.location_mode is LocationMode.address or profile.gps_allowed:
            problems.append("protective profile cannot store names, addresses or GPS")
        if profile.household_records_allowed:
            problems.append("protective profile has no household records")
    if problems:
        raise PolicyBelowMinimum("privacy profile below platform minimums", {"problems": problems})
    return profile


# ---------------------------------------------------------------------------
# Capture validation (DOM-031)
# ---------------------------------------------------------------------------


def disallowed_fields(sub: ReportSubmission, profile: PrivacyProfile) -> list[str]:
    bad: list[str] = []
    if sub.reporter_name_encrypted is not None and not profile.names_allowed:
        bad.append("reporter_name")
    if isinstance(sub.location, AddressLocation):
        if profile.location_mode is not LocationMode.address:
            bad.append("location.address")
            if sub.location.point is not None:
                bad.append("location.point")
        elif sub.location.point is not None and not profile.gps_allowed:
            bad.append("location.point")
    if sub.household_ref is not None and not profile.household_records_allowed:
        bad.append("household_ref")
    if PermissionPurpose.contact_list in sub.permissions and not profile.contact_list_enabled:
        bad.append("permissions.contact_list")
    if sub.relationship is Relationship.area:
        # SEC-02: an area-only report stores no personal data, in any profile.
        if sub.reporter_name_encrypted is not None and "reporter_name" not in bad:
            bad.append("reporter_name")
        if sub.household_ref is not None and "household_ref" not in bad:
            bad.append("household_ref")
        if isinstance(sub.location, AddressLocation) and "location.address" not in bad:
            bad.append("location.address")
    return bad


def validate_submission(sub: ReportSubmission, profile: PrivacyProfile) -> None:
    """Raise ProfileViolation for disallowed fields, ValidationFailed for bad values."""
    bad = disallowed_fields(sub, profile)
    if bad:
        raise ProfileViolation(bad, profile.version)
    for i, need in enumerate(sub.needs):
        if need.people_affected is not None and need.people_affected < 0:
            raise ValidationFailed("people_affected must be >= 0", {"need": i})
        if need.quantity is not None:
            if need.quantity.unit not in CATEGORY_UNITS[need.category]:
                raise ValidationFailed(
                    f"unit {need.quantity.unit.value} not valid for {need.category.value}",
                    {"need": i},
                )
            if need.quantity.value < 0:
                raise ValidationFailed("quantity must be >= 0", {"need": i})
    categories = [n.category for n in sub.needs]
    if len(categories) != len(set(categories)):
        raise ValidationFailed("at most one need per category per report")


# ---------------------------------------------------------------------------
# Tightening and loosening (DOM-032/033)
# ---------------------------------------------------------------------------


class PurgeField(str, Enum):
    reporter_names = "reporter_names"
    addresses = "addresses"
    gps_points = "gps_points"
    household_records = "household_records"
    reporter_phones = "reporter_phones"  # re-run phone retention under the new period
    contact_aliases = "contact_aliases"  # contact-list field removed
    contact_permissions = "contact_permissions"  # contact list disabled


def _retention_stricter(new: Optional[int], old: Optional[int]) -> bool:
    if new is None:
        return False
    return old is None or new < old


def tightened_settings(old: PrivacyProfile, new: PrivacyProfile) -> set[str]:
    out: set[str] = set()
    if old.names_allowed and not new.names_allowed:
        out.add("names_allowed")
    if old.location_mode is LocationMode.address and new.location_mode is LocationMode.meeting_point:
        out.add("location_mode")
    if old.gps_allowed and not new.gps_allowed:
        out.add("gps_allowed")
    if _retention_stricter(new.reporter_phone_retention_days, old.reporter_phone_retention_days):
        out.add("reporter_phone_retention_days")
    if old.household_records_allowed and not new.household_records_allowed:
        out.add("household_records_allowed")
    if old.contact_list_enabled and not new.contact_list_enabled:
        out.add("contact_list_enabled")
    if not new.contact_list_fields >= old.contact_list_fields:
        out.add("contact_list_fields")
    if new.reporter_key_rotation_days < old.reporter_key_rotation_days:
        out.add("reporter_key_rotation_days")
    if new.aggregate_k > old.aggregate_k:
        out.add("aggregate_k")
    if new.public_k > old.public_k:
        out.add("public_k")
    if new.public_delay > old.public_delay:
        out.add("public_delay")
    if level_index(new.public_level) < level_index(old.public_level):
        out.add("public_level")
    if old.public_dashboard_enabled and not new.public_dashboard_enabled:
        out.add("public_dashboard_enabled")
    return out


def loosened_settings(old: PrivacyProfile, new: PrivacyProfile) -> set[str]:
    return tightened_settings(new, old)


@dataclass(frozen=True)
class TighteningPlan:
    org_id: str
    from_version: int
    to_version: int
    fields_to_purge: frozenset[PurgeField]
    activated_at: datetime
    deadline: datetime
    new_phone_retention_days: Optional[int]
    removed_contact_fields: frozenset[ContactField]

    @property
    def empty(self) -> bool:
        return not self.fields_to_purge


def plan_tightening(old: PrivacyProfile, new: PrivacyProfile, now: datetime) -> TighteningPlan:
    """DOM-032: which stored fields the new profile disallows. Aggregates are kept."""
    validate_profile(new)
    tight = tightened_settings(old, new)
    purge: set[PurgeField] = set()
    if "names_allowed" in tight:
        purge.add(PurgeField.reporter_names)
    if "location_mode" in tight:
        purge.add(PurgeField.addresses)
        purge.add(PurgeField.gps_points)
    if "gps_allowed" in tight:
        purge.add(PurgeField.gps_points)
    if "household_records_allowed" in tight:
        purge.add(PurgeField.household_records)
    if "reporter_phone_retention_days" in tight:
        purge.add(PurgeField.reporter_phones)
    removed = old.contact_list_fields - new.contact_list_fields
    if ContactField.alias in removed:
        purge.add(PurgeField.contact_aliases)
    if "contact_list_enabled" in tight:
        purge.add(PurgeField.contact_permissions)
    return TighteningPlan(
        org_id=new.org_id,
        from_version=old.version,
        to_version=new.version,
        fields_to_purge=frozenset(purge),
        activated_at=now,
        deadline=now + TIGHTENING_PURGE_DEADLINE,
        new_phone_retention_days=new.reporter_phone_retention_days,
        removed_contact_fields=frozenset(removed),
    )


@dataclass(frozen=True)
class PurgeAudit:
    """Audited with counts only (SEC-13: no raw personal data)."""

    org_id: str
    to_version: int
    ran_at: datetime
    within_deadline: bool
    counts: dict[str, int]


def purge_report(report: Report, plan: TighteningPlan) -> tuple[Report, dict[str, int]]:
    counts: dict[str, int] = {}
    changes: dict = {}
    f = plan.fields_to_purge
    if PurgeField.reporter_names in f and report.reporter_name_encrypted is not None:
        changes["reporter_name_encrypted"] = None
        counts["reporter_names"] = 1
    loc = report.location
    if isinstance(loc, AddressLocation):
        if PurgeField.addresses in f:
            changes["location"] = None
            counts["addresses"] = 1
            if loc.point is not None:
                counts["gps_points"] = 1
        elif PurgeField.gps_points in f and loc.point is not None:
            changes["location"] = replace(loc, point=None)
            counts["gps_points"] = 1
    if PurgeField.household_records in f and report.household_ref is not None:
        changes["household_ref"] = None
        counts["household_records"] = 1
    if PurgeField.contact_permissions in f and PermissionPurpose.contact_list in report.permissions:
        changes["permissions"] = report.permissions - {PermissionPurpose.contact_list}
        counts["contact_permissions"] = 1
    return (replace(report, **changes) if changes else report), counts


def purge_contact(contact: ReporterContact, plan: TighteningPlan) -> tuple[ReporterContact, dict[str, int]]:
    counts: dict[str, int] = {}
    changes: dict = {}
    f = plan.fields_to_purge
    if PurgeField.reporter_names in f and contact.name_encrypted is not None:
        changes["name_encrypted"] = None
        counts["contact_names"] = 1
    if PurgeField.addresses in f and contact.address_encrypted is not None:
        changes["address_encrypted"] = None
        counts["contact_addresses"] = 1
    if PurgeField.contact_aliases in f and contact.alias is not None:
        changes["alias"] = None
        counts["contact_aliases"] = 1
    return (replace(contact, **changes) if changes else contact), counts


def run_purge(
    plan: TighteningPlan,
    reports: Iterable[Report],
    contacts: Iterable[ReporterContact] = (),
    now: Optional[datetime] = None,
) -> tuple[list[Report], list[ReporterContact], PurgeAudit]:
    """Apply a tightening plan. Phone retention itself runs in the retention job
    (DB-070) with ``plan.new_phone_retention_days``; it is counted there."""
    totals: dict[str, int] = {}
    out_reports: list[Report] = []
    out_contacts: list[ReporterContact] = []
    for r in reports:
        new_r, c = purge_report(r, plan)
        out_reports.append(new_r)
        for k, v in c.items():
            totals[k] = totals.get(k, 0) + v
    for ct in contacts:
        new_c, c = purge_contact(ct, plan)
        out_contacts.append(new_c)
        for k, v in c.items():
            totals[k] = totals.get(k, 0) + v
    ran_at = now or plan.activated_at
    audit = PurgeAudit(
        org_id=plan.org_id,
        to_version=plan.to_version,
        ran_at=ran_at,
        within_deadline=ran_at <= plan.deadline,
        counts=totals,
    )
    return out_reports, out_contacts, audit


def most_restrictive(a: PrivacyProfile, b: PrivacyProfile) -> PrivacyProfile:
    """Capture settings that satisfy both profiles. Version/notice taken from ``b``."""
    loc = (
        LocationMode.address
        if a.location_mode is LocationMode.address and b.location_mode is LocationMode.address
        else LocationMode.meeting_point
    )
    ret_candidates = [d for d in (a.reporter_phone_retention_days, b.reporter_phone_retention_days) if d is not None]
    return replace(
        b,
        names_allowed=a.names_allowed and b.names_allowed,
        location_mode=loc,
        gps_allowed=a.gps_allowed and b.gps_allowed and loc is LocationMode.address,
        household_records_allowed=a.household_records_allowed and b.household_records_allowed,
        contact_list_enabled=a.contact_list_enabled and b.contact_list_enabled,
        contact_list_fields=a.contact_list_fields & b.contact_list_fields,
        reporter_phone_retention_days=min(ret_candidates) if ret_candidates else None,
    )


def capture_profile(
    active: PrivacyProfile, acknowledged_notice_version: str, acknowledged_profile: Optional[PrivacyProfile]
) -> PrivacyProfile:
    """DOM-033: the profile a report is captured under.

    A reporter who acknowledged the active notice is captured under the active
    profile. A reporter still on an older notice is captured under the stricter of
    the old and active profiles, so a loosening never applies without the new notice.
    """
    if acknowledged_notice_version == active.notice_version:
        return active
    if acknowledged_profile is None:
        # Unknown notice: treat as the most restrictive possible capture.
        return most_restrictive(protective_profile(active.org_id), active)
    return most_restrictive(acknowledged_profile, active)


def validate_report_update(
    sub: ReportSubmission, collected_under: PrivacyProfile, active: PrivacyProfile
) -> None:
    """DOM-033: existing data is never enriched beyond what it was collected under."""
    validate_submission(sub, most_restrictive(collected_under, active))
