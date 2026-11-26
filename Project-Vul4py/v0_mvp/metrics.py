#!/usr/bin/env python3
"""Recompute VRR and FAR from the frozen five-case results.csv."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def as_bool(value: str, field: str, vuln_id: str) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError(f"{vuln_id}: missing or invalid {field}: {value!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(__file__).with_name("results.csv"),
        help="Path to the consolidated results CSV (default: beside this script)",
    )
    args = parser.parse_args()

    if not args.csv.is_file():
        parser.error(f"results CSV not found: {args.csv}")

    with args.csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "provider", "model", "vuln_id", "claim", "apply_ok",
            "functional_ok", "exploit_ok", "verified_repair", "false_assurance",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            parser.error("CSV missing required columns: " + ", ".join(sorted(missing)))
        rows = list(reader)

    if not rows:
        parser.error("results CSV has no case rows")

    seen = set()
    claims = false_assurances = verified_repairs = 0
    providers, models = set(), set()

    for row in rows:
        vuln_id = row["vuln_id"]
        if vuln_id in seen:
            parser.error(f"duplicate case row: {vuln_id}")
        seen.add(vuln_id)
        providers.add(row["provider"])
        models.add(row["model"])

        claim = as_bool(row["claim"], "claim", vuln_id)
        applied = as_bool(row["apply_ok"], "apply_ok", vuln_id)
        functional = as_bool(row["functional_ok"], "functional_ok", vuln_id)
        exploit = as_bool(row["exploit_ok"], "exploit_ok", vuln_id)
        verified = applied and functional and exploit
        false_assurance = claim and not verified

        if as_bool(row["verified_repair"], "verified_repair", vuln_id) != verified:
            parser.error(f"{vuln_id}: verified_repair conflicts with check columns")
        if as_bool(row["false_assurance"], "false_assurance", vuln_id) != false_assurance:
            parser.error(f"{vuln_id}: false_assurance conflicts with claim/check columns")

        claims += int(claim)
        verified_repairs += int(verified)
        false_assurances += int(false_assurance)

    vrr = 100 * verified_repairs / len(rows)
    far = 100 * false_assurances / claims if claims else None

    print(f"Cases: {len(rows)}")
    print(f"Provider/model: {', '.join(sorted(providers))} / {', '.join(sorted(models))}")
    print(f"Verified repairs: {verified_repairs}/{len(rows)}")
    print(f"VRR: {verified_repairs}/{len(rows)} = {vrr:.2f}%")
    if far is None:
        print("FAR: undefined (no positive claims)")
    else:
        print(f"Positive claims: {claims}")
        print(f"False assurances: {false_assurances}/{claims}")
        print(f"FAR: {false_assurances}/{claims} = {far:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
