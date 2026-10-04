"""Expose documented and observed auto-target branches for this match only."""


def _rank_opponents(units):
    # The panel shows maximum HP. Opening current HP equals maximum HP only
    # before start-of-battle damage, self-costs and shields are resolved.
    return [
        {"name": unit["name"], "slot": unit["slot"], "max_hp": unit["stats"]["hp"]}
        for unit in sorted(units, key=lambda unit: (-unit["stats"]["hp"], unit["slot"]))
    ]


def build_targeting_audit(teams, ai_snapshot, observations):
    result = {}
    observed = observations.get("shikigami", {})
    for side in ("red", "blue"):
        opponents = _rank_opponents(teams["blue" if side == "red" else "red"])
        allies = _rank_opponents(teams[side])
        units = []
        for unit in teams[side]:
            name = unit["name"]
            entry = ai_snapshot.get("heroes", {}).get(name) or {}
            rules = []
            for rule in entry.get("rules", []):
                text = rule.get("target_rule") or rule.get("condition") or ""
                if rule.get("section") != "目标选择" and "随机敌方" not in text:
                    continue
                target_side = "ally" if "友方" in text or "我方" in text else "enemy" if "敌方" in text else "unknown"
                eligible = opponents if target_side == "enemy" else allies if target_side == "ally" else []
                target_hint = "undetermined"
                opening_candidates = []
                if "随机敌方" in text:
                    target_hint = "random_enemy_candidate"
                    opening_candidates = [candidate["name"] for candidate in teams["blue" if side == "red" else "red"]]
                elif eligible and any(term in text for term in ("血量绝对值最高", "生命值最高", "血量最高", "当前血量最高", "当前生命最高")):
                    target_hint = "highest_current_hp_candidate"
                    opening_candidates = [candidate["name"] for candidate in eligible
                                          if candidate["max_hp"] == eligible[0]["max_hp"]]
                elif eligible and "最大生命值高" in text:
                    target_hint = "highest_max_hp_candidate"
                    opening_candidates = [candidate["name"] for candidate in eligible
                                          if candidate["max_hp"] == eligible[0]["max_hp"]]
                rules.append({"skill": rule.get("skill"), "source_section": rule.get("section"),
                              "source_text": text, "target_side": target_side, "target_hint": target_hint,
                              "opening_full_hp_candidates": opening_candidates,
                              "summons_may_be_eligible": "含召唤物" in text,
                              "status": "community_candidate"})
            observation = observed.get(name)
            hypotheses = []
            if observation:
                for item in observation.get("hypotheses", []):
                    hypotheses.append({**item,
                                       "opening_full_hp_candidates": [candidate["name"] for candidate in opponents
                                                                       if candidate["max_hp"] == opponents[0]["max_hp"]]
                                       if item.get("target_hint") == "highest_current_hp_candidate" else []})
            units.append({"actor": name, "slot": unit["slot"],
                          "community_rules": rules,
                          "reported_hypotheses": hypotheses,
                          "target_rule_missing_or_incomplete": not rules or bool(entry.get("incomplete_rule_count")),
                          "opening_opponent_hp_ranking": opponents})
        result[side] = units
    return result
