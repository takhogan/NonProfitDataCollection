"""Export event, data-job and questionnaire JSON Schemas to components/contracts/schemas/.

Usage (from components/whatsapp/api):

    python -m scripts.export_contracts           # write schemas
    python -m scripts.export_contracts --check   # exit 1 if any checked-in schema is stale

The OpenAPI export (CON-043) is separate and comes with the api routers.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.contracts import registry  # noqa: E402

CONTRACTS_DIR = API_ROOT.parents[1] / "contracts"


def expected_files() -> dict[Path, str]:
    return {
        CONTRACTS_DIR / registry.relative_path(group, name): registry.render(tp)
        for (group, name), tp in registry.EXPORTED.items()
    }


def stale_files() -> list[str]:
    """Paths that are missing, differ, or are no longer exported."""
    expected = expected_files()
    problems = [
        str(p.relative_to(CONTRACTS_DIR))
        for p, text in expected.items()
        if not p.exists() or p.read_text(encoding="utf-8") != text
    ]
    schemas_dir = CONTRACTS_DIR / "schemas"
    if schemas_dir.exists():
        for p in schemas_dir.rglob("*.json"):
            if p not in expected:
                problems.append(f"{p.relative_to(CONTRACTS_DIR)} (not exported)")
    return sorted(problems)


def write() -> list[Path]:
    written = []
    expected = expected_files()
    schemas_dir = CONTRACTS_DIR / "schemas"
    if schemas_dir.exists():
        for p in schemas_dir.rglob("*.json"):
            if p not in expected:
                p.unlink()
    for path, text in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if schemas are stale")
    args = parser.parse_args(argv)
    if args.check:
        stale = stale_files()
        if stale:
            print("Stale contract schemas (run python -m scripts.export_contracts):")
            for s in stale:
                print(f"  {s}")
            return 1
        print("Contract schemas are up to date.")
        return 0
    for path in write():
        print(f"wrote {path.relative_to(CONTRACTS_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
