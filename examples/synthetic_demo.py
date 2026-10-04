#!/usr/bin/env python3
"""Run a fictional packet and ballot check without game data or network access."""
import json
from copy import deepcopy
from pathlib import Path
import sys
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_reasoning_packet import build  # noqa: E402
from verify_inference_trace import check  # noqa: E402


def main():
    names = {side: [f"虚构{side}{i}" for i in range(1, 6)] for side in ("red", "blue")}
    teams = {
        side: [
            {"slot": i, "name": name, "soul": "示例御魂",
             "stats": {"attack": 100, "hp": 1000, "defense": 50,
                       "speed": 130 - i - (0 if side == "red" else 10),
                       "crit": 0, "crit_damage": 150, "effect_hit": 0,
                       "effect_resist": 0},
             "input_evidence": {"name_status": "demo_only", "soul_status": "demo_only"}}
            for i, name in enumerate(members, 1)
        ] for side, members in names.items()
    }
    skill_records = {
        name: {"netease_website_text": {"hero_id": f"demo-{name}",
                                       "cards": [{"skill_id": "demo-basic", "name": "示例普攻",
                                                  "awake": 1, "cost": 0,
                                                  "base_description": "虚构：造成固定伤害。",
                                                  "level_descriptions": []}]},
               "community_ai_candidate": None, "client_verified": None,
               "text_matches_client_by_user": False,
               "community_ai_operational_default_by_user": False,
               "ai_conflict": "unassessed"}
        for members in names.values() for name in members
    }
    bundle = {
        "schema_version": 2, "run_id": "fictional-demo-only",
        "teams": teams, "skills_and_ai": skill_records,
        "souls": {"示例御魂": {"web_candidate": {"mechanics": {
            "set2": "虚构：攻击增加。", "set4": "虚构：生命增加。"}},
            "client_verified": None, "text_matches_client_by_user": False}},
        "duel_rules": {"user_confirmed": {"initial_shared_fire_per_side": 4,
            "normal_fire_refill_amount_by_completed_cycle": [3, 4, 5]}},
        "ai_precedence": ["demo_only"], "ai_targeting_audit": {},
        "evidence_status": {"standard_duel_mode_user_confirmed": True},
        "missing": ["虚构示例没有真实游戏资料；不能预测胜负"],
        "evidence_gaps": ["虚构示例不含真实自动战斗规则"],
        "battle_background": "虚构演示", "battle_protocol": "虚构演示",
        "source_pages": {}
    }
    packet = build(bundle)
    actor = names["red"][0]
    ballot = {
        "run_id": packet["run_id"], "packet_sha256": packet["packet_sha256"],
        "choice": "abstain", "decisive_steps": [],
        "uncertainties": ["缺少真实游戏资料和自动战斗规则"],
        "key_actions": [{"actor_side": "red", "actor": actor,
                         "skill_id": "demo-basic", "target_side": "blue",
                         "target": names["blue"][0], "ordinary_turn_number_for_side": 1,
                         "fire_before": 4, "fire_spent": 0, "fire_gained": 0,
                         "fire_after": 4, "fire_gain_source": None,
                         "target_basis": "demo_only", "contingent": True,
                         "evidence_refs": [f"skill:{actor}:demo-basic"]}]
    }
    errors = check(packet, ballot)
    if errors:
        raise RuntimeError(f"synthetic ballot failed validation: {errors}")
    invalid_ballot = deepcopy(ballot)
    invalid_ballot["key_actions"][0]["fire_after"] = 5
    invalid_errors = check(packet, invalid_ballot)
    if not any("fire_after does not balance" in error for error in invalid_errors):
        raise RuntimeError("unbalanced fire ledger was not rejected")
    out_dir = Path(mkdtemp(prefix="yys-synthetic-demo-"))
    for name, value in (("reasoning_packet.json", packet), ("ballot.json", ballot)):
        (out_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    print(json.dumps({"demo": "fictional", "packet": str(out_dir / "reasoning_packet.json"),
                      "ballot": str(out_dir / "ballot.json"), "ballot_valid": True,
                      "missing_count": len(packet["missing"]),
                      "invalid_fire_ballot_blocked": True,
                      "prediction": "abstain", "network_access": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
