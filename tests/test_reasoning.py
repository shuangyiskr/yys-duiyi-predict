"""Verify that weak-model guardrails reject important contradictions."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_reasoning_packet import build
from verify_inference_trace import check
from aggregate_votes import aggregate
from run_independent_panel import validated_api_base


def fixture_bundle():
    def unit(side, name, speed):
        return {"slot": 1, "name": name, "stats": {"speed": speed, "hp": 10000},
                "soul": "测试御魂", "input_evidence": {"name_status": "confirmed", "soul_status": "user_confirmed"}}
    def skill(name):
        return {"netease_website_text": {"hero_id": name, "cards": [{
            "skill_id": "123", "name": "测试技能", "awake": 1, "cost": 3,
            "base_description": "群体攻击", "level_descriptions": ["5级伤害提高"],
            "effect_tip_ids": [], "extra_skills": [], "other_api_fields": {}}]},
            "wiki_skill_effect_expansions": {}, "community_ai_candidate": {"rules": []}}
    return {"schema_version": 2, "run_id": "this-round", "teams": {
        "red": [unit("red", "甲", 200)], "blue": [unit("blue", "乙", 180)]},
        "skills_and_ai": {"甲": skill("甲"), "乙": skill("乙")},
        "souls": {"测试御魂": {"web_candidate": {"mechanics": {"set4": "测试效果"}}}},
        "duel_rules": {"user_confirmed": {"initial_shared_fire_per_side": 4,
                                         "normal_fire_refill_amount_by_completed_cycle": [3, 4, 5]}},
        "ai_precedence": [], "ai_targeting_audit": {"red": [], "blue": []},
        "evidence_status": {"standard_duel_mode_user_confirmed": True},
        "missing": [], "evidence_gaps": [], "battle_background": "", "battle_protocol": "",
        "source_pages": {}}


def valid_ballot(packet):
    return {"run_id": packet["run_id"], "packet_sha256": packet["packet_sha256"],
            "choice": "red", "decisive_steps": ["甲先攻"], "uncertainties": [],
            "key_actions": [{"actor_side": "red", "actor": "甲", "skill_id": "123",
                             "target_side": "blue", "target": "乙", "target_basis": "aoe",
                             "contingent": False, "ordinary_turn_number_for_side": 1,
                             "fire_before": 4, "fire_spent": 3, "fire_gained": 0,
                             "fire_after": 1, "fire_gain_source": None,
                             "evidence_refs": ["skill:甲:123"]}]}


class GuardrailTests(unittest.TestCase):
    def setUp(self):
        self.packet = build(fixture_bundle())
        self.ballot = valid_ballot(self.packet)
        self.ballot["model"] = "master-model"

    def workers(self):
        return [{**copy.deepcopy(self.ballot), "model": f"worker-model-{i}"} for i in range(1, 6)]

    def test_keeps_source_text_and_speed_is_only_priority(self):
        card = self.packet["skills_and_ai"]["甲"]["cards"][0]
        self.assertEqual(card["level_upgrade_texts_in_order"], ["5级伤害提高"])
        self.assertIn("not resolved", self.packet["opening_constraints"]["prebattle_action_bar_effects"])
        self.assertEqual(check(self.packet, self.ballot), [])

    def test_wrong_skill_and_fire_are_rejected(self):
        ballot = copy.deepcopy(self.ballot)
        ballot["key_actions"][0].update(skill_id="999", fire_spent=5, fire_after=0)
        errors = " ".join(check(self.packet, ballot))
        self.assertIn("skill_id", errors)
        self.assertIn("spent fire exceeds", errors)

    def test_random_target_needs_branch(self):
        ballot = copy.deepcopy(self.ballot)
        ballot["key_actions"][0]["target_basis"] = "random"
        self.assertIn("random target", " ".join(check(self.packet, ballot)))
        ballot["key_actions"][0]["contingent"] = True
        self.assertEqual(check(self.packet, ballot), [])

    def test_stale_packet_cannot_vote(self):
        ballot = copy.deepcopy(self.ballot)
        ballot["packet_sha256"] = "old"
        self.assertIn("packet_sha256", " ".join(check(self.packet, ballot)))

    def test_refill_is_not_available_before_fifth_ordinary_turn(self):
        ballot = copy.deepcopy(self.ballot)
        action = ballot["key_actions"][0]
        action.update(fire_gained=3, fire_after=4, fire_gain_source="rule:fire_cycle")
        action["evidence_refs"].append("rule:fire_cycle")
        self.assertIn("3/4/5", " ".join(check(self.packet, ballot)))
        action["ordinary_turn_number_for_side"] = 5
        self.assertEqual(check(self.packet, ballot), [])

    def test_invalid_workers_cannot_create_a_master_only_decision(self):
        workers = self.workers()
        for worker in workers:
            worker["choice"] = "blue"
            worker["key_actions"][0]["skill_id"] = "made-up"
        result = aggregate(self.ballot, workers, self.packet)
        self.assertEqual(result["outcome"], "undecided")
        self.assertEqual(result["decision_reason"], "insufficient_independent_support")
        self.assertEqual(result["ballot_counts"]["abstain"], 5)
        self.assertEqual(len(result["invalid_workers"]), 5)

    def test_three_independent_supporters_allow_a_direction(self):
        workers = self.workers()
        for worker in workers[3:]:
            worker.update(choice="abstain", key_actions=[])
        result = aggregate(self.ballot, workers, self.packet)
        self.assertEqual(result["outcome"], "red")
        self.assertEqual(result["independent_counts"]["red"], 4)

    def test_a_single_opposing_vote_can_still_reach_consensus(self):
        workers = self.workers()
        workers[4]["choice"] = "blue"
        result = aggregate(self.ballot, workers, self.packet)
        self.assertEqual(result["outcome"], "red")
        self.assertEqual(result["independent_counts"]["blue"], 1)

    def test_four_support_one_oppose_one_abstain_meets_boundary(self):
        workers = self.workers()
        workers[3]["choice"] = "blue"
        workers[4].update(choice="abstain", key_actions=[])
        result = aggregate(self.ballot, workers, self.packet)
        self.assertEqual(result["outcome"], "red")

    def test_two_valid_opposing_votes_require_review(self):
        workers = self.workers()
        for worker in workers[3:]:
            worker["choice"] = "blue"
        result = aggregate(self.ballot, workers, self.packet)
        self.assertEqual(result["outcome"], "undecided")
        self.assertEqual(result["decision_reason"], "insufficient_directional_consensus")
        self.assertTrue(result["requires_master_review"])

    def test_master_abstention_does_not_veto_worker_consensus(self):
        master = {**self.ballot, "choice": "abstain", "key_actions": []}
        workers = self.workers()
        workers[4].update(choice="abstain", key_actions=[])
        result = aggregate(master, workers, self.packet)
        self.assertEqual(result["outcome"], "red")

    def test_duplicate_model_runs_do_not_multiply_votes(self):
        workers = [{**self.ballot, "model": "same-model"} for _ in range(5)]
        result = aggregate(self.ballot, workers, self.packet)
        self.assertEqual(result["outcome"], "undecided")
        self.assertEqual(result["decision_reason"], "insufficient_independent_models")
        self.assertEqual(len(result["independent_groups"]), 2)

    def test_conflicting_runs_of_same_model_abstain_as_one_source(self):
        workers = self.workers()
        workers[1]["model"] = workers[0]["model"]
        workers[1]["choice"] = "blue"
        result = aggregate(self.ballot, workers, self.packet)
        self.assertEqual(result["independent_counts"]["abstain"], 1)
        self.assertTrue(result["independent_groups"][1]["conflicted"])

    def test_missing_model_identity_cannot_establish_independence(self):
        workers = self.workers()
        del workers[0]["model"]
        result = aggregate(self.ballot, workers, self.packet)
        self.assertEqual(result["outcome"], "undecided")
        self.assertEqual(result["decision_reason"], "model_identity_missing")

    def test_evidence_gap_prevents_automatic_decision(self):
        packet = copy.deepcopy(self.packet)
        packet["evidence_gaps"] = ["unconfirmed target priority"]
        workers = self.workers()
        result = aggregate(self.ballot, workers, packet)
        self.assertEqual(result["outcome"], "undecided")
        self.assertEqual(result["decision_reason"], "evidence_gaps_need_review")
        self.assertEqual(result["evidence_gaps_to_review"], packet["evidence_gaps"])
        review = {"run_id": packet["run_id"], "packet_sha256": packet["packet_sha256"],
                  "assessments": [{"gap": packet["evidence_gaps"][0],
                                   "outcome_sensitive": False,
                                   "reason": "This target rule does not affect any decisive action."}]}
        self.assertEqual(aggregate(self.ballot, workers, packet, review)["outcome"], "red")
        review["assessments"][0]["outcome_sensitive"] = True
        self.assertEqual(aggregate(self.ballot, workers, packet, review)["outcome"], "undecided")
        review["packet_sha256"] = "stale"
        with self.assertRaises(ValueError):
            aggregate(self.ballot, workers, packet, review)

    def test_worker_endpoint_rejects_key_leak_routes(self):
        self.assertEqual(validated_api_base("https://example.com/v1/"), "https://example.com/v1")
        for url in ("http://example.com/v1", "https://user:pass@example.com/v1",
                    "https://example.com/v1?key=x", "https://example.com/v1#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validated_api_base(url)


if __name__ == "__main__":
    unittest.main()
