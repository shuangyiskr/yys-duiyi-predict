#!/usr/bin/env python3
"""Report skill, soul text, and icon coverage without implying client verification."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / "references" / name).read_text(encoding="utf-8"))


def audit():
    official = read("official_skills_snapshot.json")
    ai = read("community_ai_snapshot.json")
    souls = read("community_soul_snapshot.json")["souls"]
    wiki_skills = read("wiki_skill_glossary.json")["heroes"]
    roster = read("soul_roster.json")
    catalog = read("catalog.json")
    heroes = official["heroes"]
    variants = [(name, skill_id, item)
                for name, entry in heroes.items()
                for skill_id, group in entry["skills"].items()
                for item in group]
    missing_base = [f"{name}/{skill_id}/awake{item['awake']}"
                    for name, skill_id, item in variants if not item["data"].get("normaldesc")]
    unresolved_tips = {str(tip) for _, _, item in variants
                       for tip in item["data"].get("effect_tips", [])}
    unmatched_wiki = sorted({f"{name}/{item['data'].get('name')}"
                             for name, _, item in variants
                             if len(wiki_skills.get(name, {}).get(item["data"].get("name"), [])) != 1})
    art_names = set(roster["art_names"])
    extra_names = {name for names in roster["additional_names_without_local_art"].values() for name in names}
    known_names = art_names | extra_names
    portrait_names = {p.stem for p in (ROOT / "assets" / "soul_portraits").glob("*.png")}
    fetched_at = official.get("fetched_at_utc")
    age_days = ((datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at)).total_seconds() / 86400
                if fetched_at else None)
    return {
        "official_website_hero_count": len(heroes),
        "official_website_skill_variants": len(variants),
        "missing_base_descriptions": missing_base,
        "numeric_effect_tip_ids_without_direct_id_mapping": len(unresolved_tips),
        "official_skills_without_unique_wiki_card": unmatched_wiki,
        "skill_data_age_days": round(age_days, 1) if age_days is not None else None,
        "official_website_client_version_known": official.get("content_version") is not None,
        "community_ai_entries": len(ai["heroes"]),
        "community_ai_entries_with_rules": sum(bool(entry.get("rules")) for entry in ai["heroes"].values()),
        "community_ai_unparsed_rule_fragments": sum(entry.get("incomplete_rule_count", 0)
                                                   for entry in ai["heroes"].values()),
        "known_soul_names": len(known_names),
        "community_portrait_icons": len(portrait_names),
        "community_souls_without_portrait_icon": sorted(set(souls) - portrait_names),
        "portrait_icons_without_effect_text": sorted(portrait_names - set(souls)),
        "named_full_illustrations": len(art_names),
        "named_art_without_effect_text": sorted(art_names - set(souls)),
        "community_soul_texts_without_full_illustration": sorted(set(souls) - art_names),
        "game_screenshot_template_souls": len({p.stem.split("__")[0] for p in
                                                 (ROOT / "assets" / "screen_soul_templates").glob("*.png")}),
        "community_soul_texts": len(souls),
        "community_souls_missing_from_icon_roster": sorted(set(souls) - known_names),
        "soul_texts_missing_two_piece": sorted(name for name, entry in souls.items() if not entry.get("set2")),
        "soul_texts_missing_four_piece_or_boss": sorted(name for name, entry in souls.items()
                                                        if not entry.get("set4") and "set1" not in entry),
        "soul_texts_blank_single_piece": sorted(name for name, entry in souls.items()
                                                if entry.get("set1") == ""),
        "named_souls_without_local_effect": sorted(known_names - set(souls)),
        "client_verified_souls": sum(bool(v.get("verified")) for v in catalog.get("souls", {}).values()),
        "client_verified_heroes": sum(bool(v.get("verified")) for v in catalog.get("shikigami", {}).values())
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = json.dumps(audit(), ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
