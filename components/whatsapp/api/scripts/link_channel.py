"""Link a Meta WhatsApp phone_number_id to the organization that owns it.

    python -m scripts.link_channel --phone-number-id 1234567890 --org "Agua Azul (demo, standard)"
    python -m scripts.link_channel --phone-number-id 1234567890 --org-id <uuid> [--campaign-id <uuid>]
    python -m scripts.link_channel --list
    python -m scripts.link_channel --phone-number-id 1234567890 --disable

Inbound events for a number with no active link are kept as ``ignored`` with
reason ``unmapped_channel_account`` (nothing is answered). Runs as the database
owner: ``channel_account`` is read-only for runtime roles.
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models.channel import ChannelAccount
from app.models.org import Organization


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--phone-number-id")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--org", help="organization name (exact)")
    g.add_argument("--org-id")
    p.add_argument("--campaign-id")
    p.add_argument("--disable", action="store_true")
    p.add_argument("--list", action="store_true")
    args = p.parse_args(argv)

    db = SessionLocal()
    try:
        if args.list:
            for ch in db.scalars(select(ChannelAccount).order_by(ChannelAccount.created_at)):
                org = db.get(Organization, ch.organization_id)
                print(f"{ch.phone_number_id}\t{ch.status}\t{org.name if org else ch.organization_id}"
                      f"\tcampaign={ch.campaign_id or '-'}")
            return 0
        if not args.phone_number_id:
            p.error("--phone-number-id is required")
        ch = db.scalar(select(ChannelAccount).where(
            ChannelAccount.phone_number_id == args.phone_number_id))
        if args.disable:
            if ch is None:
                print("no such channel account", file=sys.stderr)
                return 1
            ch.status = "disabled"
            db.commit()
            print(f"disabled {args.phone_number_id}")
            return 0
        org_id = args.org_id
        if args.org:
            org_id = db.scalar(select(Organization.id).where(Organization.name == args.org))
        if not org_id or db.get(Organization, org_id) is None:
            print("organization not found", file=sys.stderr)
            return 1
        if ch is None:
            ch = ChannelAccount(phone_number_id=args.phone_number_id, organization_id=org_id)
            db.add(ch)
        ch.organization_id = org_id
        ch.campaign_id = args.campaign_id
        ch.status = "active"
        db.commit()
        print(f"linked {args.phone_number_id} -> {org_id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
