#!/usr/bin/env python3
"""Build a compact, source-preserving inference packet and opening constraints."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def opening_constraints(bundle):
    rules = bundle.get("duel_rules", {}).get("user_confirmed", {})
    initial_fire = rules.get("initial_shared_fire_per_side") if bundle.get("evidence_status", {}).get("standard_duel_mode_user_confirmed") else None
    refill = rules.get("normal_fire_refill_amount_by_completed_cycle") if initial_fire is not None else None
    all_units = [(side, u) for side in ("red", "blue") for u in bundle["teams"][side]]
    speed_order = sorted(
        ({"side": side, "slot": unit["slot"], "name": unit["name"], "speed": unit["stats"]["speed"]}
         for side, unit in all_units), key=lambda u: -u["speed"])
    ties = {}
    for unit in speed_order:
        ties.setdefault(unit["speed"], []).append(unit["side"] + ":" + unit["name"])
    return {
        "initial_shared_fire_per_side": initial_fire,
        "normal_turns_per_fire_cycle_candidate": 5,
        "refill_amounts_by_completed_cycle": refill,
        "refill_settlement_timing": "unconfirmed; model fifth ordinary turn end and next ordinary turn start if decisive",
        "prebattle_action_bar_effects": "not resolved by speed sort; check skill and soul text before treating this as actual queue",
        "speed_priority_before_action_bar_changes": speed_order,
        "speed_ties": {str(speed): units for speed, units in ties.items() if len(units) > 1},
        "initial_hp": "panel max HP is opening full HP only before prebattle effects",
        "fire_ledger_rule": "Track red and blue separately; spend at skill use, add only evidenced gain or ordinary-turn refill at its resolved phase; never borrow future fire."
    }


def build(bundle):
    if bundle.get("schema_version") != 2 or not bundle.get("run_id"):
        raise ValueError("expected a current schema_version=2 inference bundle")
    compact_skills = {}
    for name, record in bundle["skills_and_ai"].items():
        website = record.get("netease_website_text") or {}
        cards = []
        for card in website.get("cards", []):
            extra = card.get("other_api_fields") or {}
            cards.append({
                "skill_id": card["skill_id"], "name": card["name"], "awake": card.get("awake"),
                "base_cost_api": card.get("cost"), "base_text": card.get("base_description"),
                "level_upgrade_texts_in_order": card.get("level_descriptions") or [],
                "extra_skills": card.get("extra_skills") or [],
                "effect_tip_ids_reference_only": card.get("effect_tip_ids") or [],
                "skill_type": extra.get("skill_type"),
                "other_source_fields": {k: v for k, v in extra.items()
                                        if k not in {"skill_type", "icon"}},
                "wiki_effect_expansion": record.get("wiki_skill_effect_expansions", {}).get(card["name"])
            })
        compact_skills[name] = {
            "hero_id": website.get("hero_id"), "awakening": website.get("awakening"),
            "official_source_requests": website.get("source_requests"),
            "client_verified": record.get("client_verified"),
            "wiki_skill_expansions_source": record.get("wiki_skill_expansions_source"),
            "wiki_skill_expansions_revision_utc": record.get("wiki_skill_expansions_revision_utc"),
            "cards": cards, "community_ai": record.get("community_ai_candidate"),
            "ai_conflict": record.get("ai_conflict"),
            "text_matches_client_by_user": record.get("text_matches_client_by_user"),
            "community_ai_operational_default_by_user": record.get("community_ai_operational_default_by_user")
        }
    souls = {}
    for name, record in bundle["souls"].items():
        web = record.get("web_candidate") or {}
        souls[name] = {
            "mechanics": web.get("mechanics"), "client_verified": record.get("client_verified"),
            "text_matches_client_by_user": record.get("text_matches_client_by_user"),
            "source_url": web.get("source_url")
        }
    teams = {side: [{"slot": u["slot"], "name": u["name"], "stats": u["stats"],
                     "soul": u["soul"], "input_evidence": {
                         "name_status": u.get("input_evidence", {}).get("name_status"),
                         "soul_status": u.get("input_evidence", {}).get("soul_status")}}
                    for u in bundle["teams"][side]] for side in ("red", "blue")}
    packet = {
        "schema_version": 1, "run_id": bundle["run_id"],
        "bundle_sha256": sha256(canonical(bundle).encode("utf-8")).hexdigest(),
        "teams": teams, "opening_constraints": opening_constraints(bundle),
        "skills_and_ai": compact_skills, "souls": souls,
        "duel_rules": bundle["duel_rules"], "ai_precedence": bundle["ai_precedence"],
        "ai_targeting_audit": bundle["ai_targeting_audit"],
        "evidence_status": bundle["evidence_status"], "missing": bundle["missing"],
        "evidence_gaps": bundle["evidence_gaps"], "battle_background": bundle["battle_background"],
        "battle_protocol": bundle["battle_protocol"], "source_pages": bundle["source_pages"],
        "inference_workflow": (Path(__file__).resolve().parents[1] / "references" / "inference_workflow.md").read_text(encoding="utf-8"),
        "inference_instructions": {
            "skill_level": "All skills are max level only when mode confirmed. Apply upgrades in order; later values override earlier values for the same effect. Base API cost may be overridden by upgrades.",
            "mechanism_priority": "Specific exception > user-accepted community AI table > baseline assumption. Never optimize target choice in place of auto AI.",
            "decisive_trace": "For each decisive action, cite actor, skill_id, target, fire before/spent/after, and source text. Separate evidenced events from contingent branches."
        }
    }
    packet["packet_sha256"] = sha256(canonical(packet).encode("utf-8")).hexdigest()
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    packet = build(bundle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out.resolve()), "run_id": packet["run_id"],
                      "packet_sha256": packet["packet_sha256"], "missing": packet["missing"],
                      "characters_for_model": len(canonical(packet))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
