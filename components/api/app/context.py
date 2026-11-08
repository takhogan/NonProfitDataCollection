"""Request context + privacy settings used to enforce data-protection in the API.

The DataProtection object is applied to every response that could contain
personal fields (phones, names, precise location) — enforced here, not in the UI.

Preset semantics (the task's definition):
- standard : full records — name and full phone visible, precise location.
- protected: mask the phone and omit the name; area-level location.
- minimal  : aggregates only — individual records are hidden entirely.
- custom   : use the explicit per-field flags as stored.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataProtection:
    preset: str = "standard"              # standard | protected | minimal | custom
    store_names: bool = True
    location_precision: str = "precise"   # area | precise
    raw_message_retention_days: int = 90
    mask_phone_numbers: bool = False
    redact_exports: bool = False
    individual_records_roles: tuple[str, ...] = ("org_admin", "coordinator")
    audit_log_enabled: bool = True
    # True only for `minimal`: endpoints that expose individual records return
    # aggregates only / 404 the detail.
    hide_individual_records: bool = False

    def apply_phone(self, phone: str | None) -> str | None:
        if phone and self.mask_phone_numbers:
            tail = phone[-2:] if len(phone) >= 2 else ""
            return f"•••••{tail}"
        return phone

    def apply_name(self, name: str | None) -> str | None:
        return name if self.store_names else None

    def apply_location(self, area: str | None, precise: str | None) -> str | None:
        # When precision is area-level, never return a precise point/address.
        return precise if self.location_precision == "precise" else area


# Preset -> the field flags it implies. `custom` is not here: it keeps whatever
# explicit flags were stored.
_PRESET_FLAGS = {
    "standard": dict(
        store_names=True, mask_phone_numbers=False, location_precision="precise",
        redact_exports=False, hide_individual_records=False,
    ),
    "protected": dict(
        store_names=False, mask_phone_numbers=True, location_precision="area",
        redact_exports=True, hide_individual_records=False,
    ),
    "minimal": dict(
        store_names=False, mask_phone_numbers=True, location_precision="area",
        redact_exports=True, hide_individual_records=True,
    ),
}


def resolve_data_protection(raw: dict) -> DataProtection:
    """Build a DataProtection from stored settings, applying preset semantics.

    For a known preset (standard/protected/minimal) the preset's flags WIN over
    any stored per-field values, so the preset is authoritative. `custom` uses the
    stored flags verbatim.
    """
    preset = raw.get("preset", "standard")
    base = dict(
        preset=preset,
        store_names=raw.get("store_names", True),
        location_precision=raw.get("location_precision", "precise"),
        raw_message_retention_days=raw.get("raw_message_retention_days", 90),
        mask_phone_numbers=raw.get("mask_phone_numbers", False),
        redact_exports=raw.get("redact_exports", False),
        individual_records_roles=tuple(raw.get("individual_records_roles", ())),
        audit_log_enabled=raw.get("audit_log_enabled", True),
        hide_individual_records=raw.get("hide_individual_records", False),
    )
    if preset in _PRESET_FLAGS:
        base.update(_PRESET_FLAGS[preset])
    return DataProtection(**base)


@dataclass(frozen=True)
class RequestContext:
    org_id: str
    actor_id: str
    membership_id: str
    role: str
    org_name: str
    data_protection: DataProtection
