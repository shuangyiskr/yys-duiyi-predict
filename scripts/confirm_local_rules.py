#!/usr/bin/env python3
"""Record only confirmations explicitly given by this installation's user."""
import argparse
import json
from pathlib import Path
from source_fingerprints import fingerprint

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"


def read(name):
    return json.loads((REF / name).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-standard-duel-mode", action="store_true",
                        help="you confirmed: max level/awakened/max skills, no onmyoji, 4 starting fire, normal 3/4/5 fire")
    parser.add_argument("--accept-skill-text", action="store_true",
                        help="you checked the current official skill cache against your client")
    parser.add_argument("--accept-soul-text", action="store_true",
                        help="you checked the current soul text cache against your client")
    parser.add_argument("--accept-community-ai", action="store_true",
                        help="you accept the cached community AI table as the default for documented cases")
    args = parser.parse_args()
    if not any(vars(args).values()):
        parser.error("select at least one explicit confirmation")
    path = REF / "duel_rules.json"
    if not path.is_file():
        parser.error("run bootstrap_data.py first")
    rules = read("duel_rules.json")
    confirmed = rules.setdefault("user_confirmed", {})
    if args.accept_standard_duel_mode:
        confirmed.update({
            "shikigami_level": "满级",
            "shikigami_awakening": "已觉醒",
            "skill_levels": "满级",
            "onmyoji_participation": "双方均无阴阳师参战",
            "initial_shared_fire_per_side": 4,
            "fire_system": "正常鬼火系统",
            "normal_fire_refill_amount_by_completed_cycle": [3, 4, 5],
            "normal_fire_refill_after_third_cycle": 5,
        })
        rules.setdefault("not_confirmed_by_user", {}).pop("mode_and_source_confirmation", None)
    if args.accept_skill_text:
        confirmed["official_skill_text_matches_client_for_fingerprint"] = fingerprint(read("official_skills_snapshot.json"), "heroes")
    if args.accept_soul_text:
        confirmed["community_soul_text_matches_client_for_fingerprint"] = fingerprint(read("community_soul_snapshot.json"), "souls")
    if args.accept_community_ai:
        confirmed["community_ai_as_operational_default_for_fingerprint"] = fingerprint(read("community_ai_snapshot.json"), "heroes")
    path.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"local_rules": str(path), "user_confirmed": confirmed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
