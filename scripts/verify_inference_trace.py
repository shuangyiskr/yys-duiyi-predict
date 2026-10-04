#!/usr/bin/env python3
"""Check a model ballot for input, reference and local fire-ledger contradictions."""
import argparse
import json
from pathlib import Path


def check(packet, ballot):
    errors = []
    if ballot.get("run_id") != packet.get("run_id"):
        errors.append("run_id does not match this round")
    if ballot.get("packet_sha256") != packet.get("packet_sha256"):
        errors.append("packet_sha256 does not match the frozen input")
    if ballot.get("choice") not in {"red", "blue", "abstain"}:
        errors.append("choice must be red, blue or abstain")
    if not isinstance(ballot.get("decisive_steps"), list) or not isinstance(ballot.get("uncertainties"), list):
        errors.append("decisive_steps and uncertainties must be arrays")
    actions = ballot.get("key_actions")
    if not isinstance(actions, list):
        errors.append("key_actions must be an array")
        actions = []
    if ballot.get("choice") in {"red", "blue"} and not actions:
        errors.append("a directional vote needs at least one checked key action")
    units = {(side, u["name"]): u for side in ("red", "blue") for u in packet["teams"][side]}
    for i, action in enumerate(actions, 1):
        prefix = f"key_actions[{i}]"
        if not isinstance(action, dict):
            errors.append(f"{prefix} must be an object")
            continue
        side, actor, skill_id = action.get("actor_side"), action.get("actor"), action.get("skill_id")
        if (side, actor) not in units:
            errors.append(f"{prefix}: actor is not on actor_side")
        else:
            cards = packet["skills_and_ai"][actor]["cards"]
            if str(skill_id) not in {str(card["skill_id"]) for card in cards}:
                errors.append(f"{prefix}: skill_id is not in this actor's skill cards")
        target, target_side = action.get("target"), action.get("target_side")
        if target is not None and target_side in {"red", "blue"} and (target_side, target) not in units:
            errors.append(f"{prefix}: target is not on target_side")
        if target is not None and target_side not in {"red", "blue", "summon"}:
            errors.append(f"{prefix}: target_side is missing or invalid")
        if not isinstance(action.get("evidence_refs"), list) or not action["evidence_refs"]:
            errors.append(f"{prefix}: cite at least one skill:<actor>:<id>, soul:<name>, ai:<actor> or rule:<name>")
        else:
            for ref in action["evidence_refs"]:
                parts = str(ref).split(":")
                if parts[0] == "skill" and len(parts) == 3:
                    rec = packet["skills_and_ai"].get(parts[1], {})
                    valid = any(str(c["skill_id"]) == parts[2] for c in rec.get("cards", []))
                elif parts[0] == "soul" and len(parts) == 2:
                    valid = parts[1] in packet["souls"]
                elif parts[0] == "ai" and len(parts) == 2:
                    valid = bool(packet["skills_and_ai"].get(parts[1], {}).get("community_ai"))
                elif parts[0] == "rule" and len(parts) == 2:
                    valid = parts[1] in {"initial_fire", "fire_cycle", "speed_priority", "auto_ai_precedence"}
                else:
                    valid = False
                if not valid:
                    errors.append(f"{prefix}: invalid evidence reference {ref}")
        fire_fields = ("fire_before", "fire_spent", "fire_gained", "fire_after")
        values = [action.get(field) for field in fire_fields]
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
            errors.append(f"{prefix}: fire fields must be nonnegative integers")
        else:
            before, spent, gained, after = values
            if spent > before:
                errors.append(f"{prefix}: spent fire exceeds available fire")
            if before - spent + gained != after:
                errors.append(f"{prefix}: fire_after does not balance")
            if gained > 0:
                gain_source = action.get("fire_gain_source")
                if not gain_source or gain_source not in action.get("evidence_refs", []):
                    errors.append(f"{prefix}: positive fire gain needs a cited source")
                if gain_source == "rule:fire_cycle":
                    turn = action.get("ordinary_turn_number_for_side")
                    cycle = turn // 5 if isinstance(turn, int) and turn > 0 and turn % 5 == 0 else None
                    refills = packet["opening_constraints"].get("refill_amounts_by_completed_cycle") or []
                    expected = refills[min(cycle - 1, len(refills) - 1)] if cycle and refills else None
                    if expected is None or gained != expected:
                        errors.append(f"{prefix}: claimed ordinary fire refill conflicts with the 3/4/5 cycle")
            if action.get("ordinary_turn_number_for_side") == 1 and before != packet["opening_constraints"]["initial_shared_fire_per_side"]:
                if not action.get("opening_fire_change_source"):
                    errors.append(f"{prefix}: first ordinary turn fire differs from confirmed opening 4 without source")
        if action.get("target_basis") == "random" and target is not None and not action.get("contingent"):
            errors.append(f"{prefix}: a named random target is a branch, not a certain event")
        if action.get("target_basis") == "unknown" and target is not None and not action.get("contingent"):
            errors.append(f"{prefix}: an unknown target cannot be asserted as certain")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("ballot", type=Path)
    args = parser.parse_args()
    errors = check(json.loads(args.packet.read_text(encoding="utf-8")),
                   json.loads(args.ballot.read_text(encoding="utf-8")))
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
