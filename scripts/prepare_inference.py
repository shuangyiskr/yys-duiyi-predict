#!/usr/bin/env python3
"""Collect only mechanics used by a match and list missing evidence."""
import argparse
import json
from pathlib import Path
from verify_match import check
from build_inference_bundle import build

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    match = read(args.match)
    catalog = read(ROOT / "references" / "catalog.json")
    ai_snapshot = read(ROOT / "references" / "community_ai_snapshot.json")
    soul_snapshot = read(ROOT / "references" / "community_soul_snapshot.json")
    full_bundle = build(match, ai_snapshot, catalog,
                        read(ROOT / "references" / "official_skills_snapshot.json"),
                        soul_snapshot,
                        read(ROOT / "references" / "duel_rules.json"),
                        {},
                        (ROOT / "references" / "combat_background.md").read_text(encoding="utf-8"),
                        read(ROOT / "references" / "ai_target_observations.json"),
                        (ROOT / "references" / "battle_protocol.md").read_text(encoding="utf-8"))
    candidates = soul_snapshot.get("souls", {})
    names = {unit["name"] for team in match.get("teams", {}).values() for unit in team if unit.get("name")}
    souls = {unit["soul_name"] for team in match.get("teams", {}).values() for unit in team if unit.get("soul_name")}
    skills = {name: catalog.get("shikigami", {}).get(name) for name in sorted(names)}
    soul_records = {name: catalog.get("souls", {}).get(name) for name in sorted(souls)}
    researched_skills = {name: ai_snapshot.get("heroes", {}).get(name) for name in sorted(names)}
    researched_souls = {name: candidates.get(name) for name in sorted(souls)}
    missing = []
    for name, record in skills.items():
        if not record or not record.get("verified") or record.get("version") != match.get("game_version"):
            missing.append({"type": "skill", "name": name})
    for name, record in soul_records.items():
        if not record or not record.get("verified") or record.get("version") != match.get("game_version"):
            missing.append({"type": "soul", "name": name, "candidate_effect": candidates.get(name)})
    order = sorted(({"side": side, "slot": i + 1, "name": unit.get("name"), "speed": unit["stats"].get("speed")}
                    for side, team in match.get("teams", {}).items() for i, unit in enumerate(team)),
                   key=lambda item: -(item["speed"] if item["speed"] is not None else -1))
    output = {"game_version": match.get("game_version"), "initial_speed_order": order,
              "skills": skills, "souls": soul_records, "missing_evidence": missing,
              "web_candidate_status": ai_snapshot.get("warning"),
              "web_candidate_retrieved_at": ai_snapshot.get("captured_at"),
              "candidate_skills_and_ai": researched_skills,
              "candidate_souls": researched_souls,
              "candidate_source_pages": full_bundle.get("source_pages"),
              "complete_inference_bundle": full_bundle,
              "can_make_reliable_decision": not bool(check(match, catalog))}
    content = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(content, encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
