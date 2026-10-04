#!/usr/bin/env python3
"""Package a match and only its relevant mechanics for independent inference."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from fast_read import COL_X, load_image, soul_crop_id
from ai_targeting import build_targeting_audit
from source_fingerprints import fingerprint

ROOT = Path(__file__).resolve().parents[1]
STATS = ("attack", "hp", "defense", "speed", "crit", "crit_damage", "effect_hit", "effect_resist")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def official_cards(entry):
    if not entry:
        return None
    cards = []
    for skill_id, variants in sorted(entry.get("skills", {}).items()):
        # User confirmed all duel units are awakened. A skill with no awake=1
        # variant keeps its only available variant; never send competing forms.
        awakened = [item for item in variants if item.get("awake") == 1]
        selected = awakened if awakened else [item for item in variants if item.get("awake") == 0]
        for item in selected:
            skill = item["data"]
            base = skill.get("normaldesc") or ""
            upgrades = skill.get("desc") or []
            cards.append({"skill_id": skill_id, "awake": item["awake"],
                          "assumed_skill_level": "max_user_confirmed",
                          "name": skill.get("name"), "cost": skill.get("consume_val"),
                          "base_description": base,
                          "level_descriptions": upgrades,
                          "max_level_source_text": "\n".join([base, *upgrades]),
                          "max_level_reading_rule": "按等级顺序累计应用全部升级条目；同一效果的后续数值覆盖旧值，特别检查鬼火消耗和先机。",
                          "extra_skills": skill.get("extra_skills", []),
                          "effect_tip_ids": skill.get("effect_tips", []),
                          "other_api_fields": {key: value for key, value in skill.items()
                                               if key not in {"name", "consume_val", "normaldesc", "desc",
                                                              "extra_skills", "effect_tips"}}})
    return {"hero_id": entry["hero_id"], "cards": cards,
            "awakening": entry.get("awake_metadata", {}).get("1"),
            "source_requests": entry.get("source_requests", [])}


def build(match, ai_snapshot, catalog, official, soul_snapshot, duel_rules,
          soul_sources=None, battle_background=None, ai_target_observations=None,
          battle_protocol=None, wiki_skill_glossary=None):
    soul_sources = soul_sources or {}
    if wiki_skill_glossary is None:
        wiki_path = ROOT / "references" / "wiki_skill_glossary.json"
        wiki_skill_glossary = load(wiki_path) if wiki_path.is_file() else {}
    round_rule_overrides = match.get("rule_overrides") or {}
    if not isinstance(round_rule_overrides, dict) or any(
            section not in {"user_confirmed", "not_confirmed_by_user"}
            or not isinstance(values, dict)
            for section, values in round_rule_overrides.items()):
        raise ValueError("rule_overrides must contain named rule sections")
    effective_rules = deepcopy(duel_rules)
    for section, values in round_rule_overrides.items():
        effective_rules.setdefault(section, {}).update(values)
    confirmed = effective_rules.get("user_confirmed", {})
    required_mode = {
        "shikigami_level": "满级", "shikigami_awakening": "已觉醒",
        "skill_levels": "满级", "onmyoji_participation": "双方均无阴阳师参战",
        "initial_shared_fire_per_side": 4, "fire_system": "正常鬼火系统",
        "normal_fire_refill_amount_by_completed_cycle": [3, 4, 5],
        "normal_fire_refill_after_third_cycle": 5,
    }
    mode_confirmed = all(confirmed.get(key) == value for key, value in required_mode.items())
    skill_text_user_confirmed = (confirmed.get("official_skill_text_matches_client_for_fingerprint")
                                 == fingerprint(official, "heroes"))
    soul_text_user_confirmed = (confirmed.get("community_soul_text_matches_client_for_fingerprint")
                                == fingerprint(soul_snapshot, "souls"))
    ai_default_user_confirmed = (confirmed.get("community_ai_as_operational_default_for_fingerprint")
                                 == fingerprint(ai_snapshot, "heroes"))
    if not match.get("run_id"):
        raise ValueError("Match has no run_id; read this round's screenshots with fast_read.py first")
    if match.get("issues"):
        raise ValueError("Unresolved screenshot fields: " + "; ".join(match["issues"]))
    screenshots = match.get("screenshots", {})
    if not all(screenshots.get(side) for side in ("red", "blue")):
        raise ValueError("This round needs both red and blue screenshot paths")
    if not all(Path(screenshots[side]).is_file() for side in ("red", "blue")):
        raise ValueError("This round's screenshots are no longer accessible")
    teams = {}
    names, souls = set(), set()
    for side in ("red", "blue"):
        screenshot_image = load_image(Path(screenshots[side]))
        units = match.get("teams", {}).get(side)
        if not isinstance(units, list) or len(units) != 5:
            raise ValueError(f"{side} must contain five units")
        teams[side] = []
        for index, unit in enumerate(units):
            name, soul = unit.get("name"), unit.get("soul_name")
            stats = {key: unit.get("stats", {}).get(key) for key in STATS}
            soul_status = unit.get("soul_status")
            candidates = unit.get("soul_candidates") or []
            if (not name or not soul or not unit.get("soul_icon_id")
                    or unit.get("name_status") in {"raw_ocr_unverified", "ambiguous", "missing"}
                    or soul_status not in {"screen_template_high_confidence", "portrait_high_confidence", "user_confirmed"}
                    or unit.get("soul_icon_id") != soul_crop_id(screenshot_image, COL_X[index])
                    or (soul_status != "user_confirmed" and
                        (not candidates or candidates[0].get("name") != soul))
                    or (soul_status == "portrait_high_confidence" and not
                        (ROOT / "assets" / "soul_portraits" / (soul + ".png")).is_file())
                    or any(isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
                           for value in stats.values())):
                raise ValueError(f"Incomplete input: {side} slot {len(teams[side])+1}")
            icon_reference = (f"assets/soul_portraits/{soul}.png"
                              if soul_status == "portrait_high_confidence" else
                              "user_confirmed" if soul_status == "user_confirmed" else
                              "assets/screen_soul_templates")
            teams[side].append({
                "slot": len(teams[side]) + 1, "name": name, "stats": stats, "soul": soul,
                "input_evidence": {
                    "name_raw": unit.get("name_raw"), "name_status": unit.get("name_status"),
                    "name_confidence": unit.get("name_confidence"),
                    "stats_raw": unit.get("stats_raw"),
                    "stats_confidence": unit.get("stats_confidence"),
                    "soul_status": soul_status, "soul_icon_id": unit["soul_icon_id"],
                    "soul_reference": icon_reference,
                    "soul_candidates": candidates
                }
            })
            names.add(name)
            souls.add(soul)
    skill_records = {}
    soul_records = {}
    missing = []
    evidence_gaps = []
    if not mode_confirmed:
        missing.append("Standard duel mode assumptions are unconfirmed or this mode differs; confirm locally before inference")
    for name in sorted(names):
        verified = catalog.get("shikigami", {}).get(name)
        candidate = ai_snapshot.get("heroes", {}).get(name)
        target_observation = (ai_target_observations or {}).get("shikigami", {}).get(name)
        has_target_conflict = bool(target_observation and candidate and any(
            "随机敌方" in (rule.get("target_rule") or rule.get("condition") or "")
            for rule in candidate.get("rules", [])))
        website = official_cards(official.get("heroes", {}).get(name))
        wiki_skill_cards = {}
        unmatched_wiki_skills = []
        if website:
            wiki_hero = wiki_skill_glossary.get("heroes", {}).get(name, {})
            for card in website["cards"]:
                matches = wiki_hero.get(card["name"], [])
                if len(matches) == 1:
                    wiki_skill_cards[card["name"]] = matches[0]
                elif card.get("effect_tip_ids"):
                    unmatched_wiki_skills.append(card["name"])
        skill_records[name] = {"client_verified": verified, "netease_website_text": website,
                               "wiki_skill_effect_expansions": wiki_skill_cards,
                               "wiki_skill_expansions_source": wiki_skill_glossary.get("source_url"),
                               "wiki_skill_expansions_revision_utc": wiki_skill_glossary.get("source_revision_utc"),
                               "community_ai_candidate": candidate if candidate and candidate.get("rules") else None,
                               "ai_source": ai_snapshot.get("source_url"),
                               "ai_source_status": ai_snapshot.get("warning"),
                               "text_matches_client_by_user": skill_text_user_confirmed,
                               "community_ai_operational_default_by_user": ai_default_user_confirmed,
                               "ai_conflict": "user_observation_vs_community_random_target" if has_target_conflict else "unassessed"}
        if not verified and (not website or not website["cards"]):
            missing.append(f"No skill record: {name}")
        if not verified and website and not skill_text_user_confirmed:
            evidence_gaps.append(f"{name}: official website text has no confirmed client version")
        if not candidate or not candidate.get("rules"):
            evidence_gaps.append(f"{name}: no documented auto-battle AI rule")
        elif candidate.get("incomplete_rule_count"):
            evidence_gaps.append(f"{name}: {candidate['incomplete_rule_count']} community AI rule(s) could not be parsed")
        if has_target_conflict:
            evidence_gaps.append(f"{name}: one unverified user target observation conflicts with community random-target rule; model both branches")
        if unmatched_wiki_skills:
            evidence_gaps.append(f"{name}: wiki skill expansion missing or ambiguous for "
                                 + ", ".join(unmatched_wiki_skills))
    for name in sorted(souls):
        verified = catalog.get("souls", {}).get(name)
        candidate = soul_snapshot.get("souls", {}).get(name)
        if candidate:
            candidate = {"mechanics": candidate, "source_url": soul_snapshot.get("source_url"),
                         "captured_at": soul_snapshot.get("captured_at"),
                         "client_version": soul_snapshot.get("client_version"),
                         "source_type": soul_snapshot.get("source_type")}
        soul_records[name] = {"client_verified": verified, "web_candidate": candidate,
                              "provenance": soul_sources.get(name),
                              "text_matches_client_by_user": soul_text_user_confirmed}
        mechanics = candidate["mechanics"] if candidate else {}
        if not verified and not mechanics.get("set2"):
            missing.append(f"No two-piece soul text: {name}")
        if not verified and not mechanics.get("set4") and "set1" not in mechanics:
            missing.append(f"No four-piece or boss soul text: {name}")
        if mechanics.get("set1") == "":
            evidence_gaps.append(f"{name}: wiki single-piece field is blank")
        if not verified and not soul_text_user_confirmed:
            evidence_gaps.append(f"{name}: no confirmed current client soul text")
    return {
        "schema_version": 2,
        "run_id": match["run_id"],
        "source_screenshots": {side: str(Path(screenshots[side]).resolve()) for side in ("red", "blue")},
        "match_version": match.get("game_version", "unverified"),
        "teams": teams,
        "skills_and_ai": skill_records,
        "souls": soul_records,
        "source_pages": {"ai_index": ai_snapshot.get("source_url"),
                         "soul_index": soul_snapshot.get("source_url"),
                         "wiki_skill_expansions": wiki_skill_glossary.get("source_url")},
        "duel_rules": effective_rules,
        "round_rule_overrides": round_rule_overrides,
        "ai_precedence": ["specific_exception", "community_ai_user_accepted_default"
                          if ai_default_user_confirmed else "community_ai_candidate", "baseline_assumed"],
        "ai_targeting_audit": build_targeting_audit(teams, ai_snapshot, ai_target_observations or {}),
        "evidence_status": {
            "standard_duel_mode_user_confirmed": mode_confirmed,
            "official_skill_text_matches_client_by_user": skill_text_user_confirmed,
            "community_soul_text_matches_client_by_user": soul_text_user_confirmed,
            "community_ai_operational_default_by_user": ai_default_user_confirmed,
            "official_website_text_fetched_at": official.get("fetched_at_utc"),
            "official_website_content_version": official.get("content_version"),
            "official_website_warning": ("Current cached skill text was checked against the client by the user; "
                                         "this does not carry over to a refreshed snapshot."
                                         if skill_text_user_confirmed else official.get("version_note")),
            "community_soul_text_captured_at": soul_snapshot.get("captured_at"),
            "community_soul_text_warning": ("Current cached soul text was checked against the client by the user; "
                                            "this does not carry over to a refreshed snapshot."
                                            if soul_text_user_confirmed else soul_snapshot.get("warning")),
            "community_ai_captured_at": ai_snapshot.get("captured_at"),
            "community_ai_warning": ("Use documented community AI rules as the default per user confirmation; "
                                     "unlisted cases and target ties remain unresolved."
                                     if ai_default_user_confirmed else ai_snapshot.get("warning"))
        },
        "missing": missing,
        "evidence_gaps": evidence_gaps,
        "battle_background": battle_background or "Battle background unavailable; do not infer.",
        "battle_protocol": battle_protocol or "Battle protocol unavailable; do not infer."
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    bundle = build(load(args.match), load(ROOT / "references" / "community_ai_snapshot.json"),
                   load(ROOT / "references" / "catalog.json"),
                   load(ROOT / "references" / "official_skills_snapshot.json"),
                   load(ROOT / "references" / "community_soul_snapshot.json"),
                   load(ROOT / "references" / "duel_rules.json"),
                   {},
                   (ROOT / "references" / "combat_background.md").read_text(encoding="utf-8"),
                   load(ROOT / "references" / "ai_target_observations.json"),
                   (ROOT / "references" / "battle_protocol.md").read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out.resolve()), "missing": bundle["missing"],
                      "shikigami": len(bundle["skills_and_ai"]), "souls": len(bundle["souls"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
