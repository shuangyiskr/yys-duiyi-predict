#!/usr/bin/env python3
"""Aggregate independent model votes with bounded, user-configured capability tiers."""
import argparse
import json
from pathlib import Path
from verify_inference_trace import check as check_trace

TIER_UNITS = {"base": 10, "medium": 12, "strong": 15}


def normalize_weight_config(config):
    if config is None:
        return {}, {}
    if not isinstance(config, dict) or "model_tiers" not in config or set(config) - {"model_tiers", "model_families"}:
        raise ValueError("weight config needs model_tiers and optional model_families")
    tiers = config["model_tiers"]
    if not isinstance(tiers, dict):
        raise ValueError("model_tiers must be an object")
    normalized = {}
    for model, tier in tiers.items():
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model_tiers keys must be nonempty model identifiers")
        key = model.strip().casefold()
        if key in normalized:
            raise ValueError("model_tiers contains duplicate model identifiers")
        if not isinstance(tier, str) or tier not in TIER_UNITS:
            raise ValueError(f"invalid capability tier for {model}: {tier}")
        normalized[key] = tier
    raw_families = config.get("model_families", {})
    if not isinstance(raw_families, dict):
        raise ValueError("model_families must be an object")
    families = {}
    for model, family in raw_families.items():
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model_families keys must be nonempty model identifiers")
        key = model.strip().casefold()
        if key in families:
            raise ValueError("model_families contains duplicate model identifiers")
        if not isinstance(family, str) or not family.strip():
            raise ValueError("model_families values must be nonempty family identifiers")
        families[key] = family.strip().casefold()
    return normalized, families


def read_ballot(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("choice") not in ("red", "blue", "abstain"):
        raise ValueError(f"Invalid choice in {path}")
    return data


def assessed_gaps(packet, review):
    gaps = packet.get("evidence_gaps", [])
    if not gaps or review is None:
        return None
    if review.get("run_id") != packet.get("run_id") or review.get("packet_sha256") != packet.get("packet_sha256"):
        raise ValueError("Evidence gap review does not match the frozen packet")
    assessments = review.get("assessments")
    if not isinstance(assessments, list) or len(assessments) != len(gaps):
        raise ValueError("Evidence gap review must assess every packet gap exactly once")
    sensitive = []
    for gap, item in zip(gaps, assessments):
        if not isinstance(item, dict) or item.get("gap") != gap:
            raise ValueError("Evidence gap review must follow the packet gap order")
        if not isinstance(item.get("outcome_sensitive"), bool) or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise ValueError("Each evidence gap needs a sensitivity decision and reason")
        if item["outcome_sensitive"]:
            sensitive.append(gap)
    return sensitive


def independent_votes(master, workers, model_tiers=None):
    tiers, families = normalize_weight_config(model_tiers)
    groups = {}
    for label, ballot in [("master", master)] + [(f"worker_{i}", b) for i, b in enumerate(workers, 1)]:
        model = ballot.get("model")
        key = "model:" + model.strip().casefold() if isinstance(model, str) and model.strip() else "ballot:" + label
        groups.setdefault(key, []).append((label, ballot["choice"]))
    model_groups = []
    for model, members in groups.items():
        choices = {choice for _, choice in members}
        conflicted = len(choices) > 1
        model_id = model.removeprefix("model:")
        tier = tiers.get(model_id, "base")
        model_groups.append({"model": model, "members": [label for label, _ in members],
                       "choice": next(iter(choices)) if not conflicted else "abstain",
                       "conflicted": conflicted, "tier": tier})
    source_groups = {}
    for group in model_groups:
        model_id = group["model"].removeprefix("model:")
        family = families.get(model_id)
        source = "family:" + family if family else group["model"]
        source_groups.setdefault(source, []).append(group)
    result = []
    for source, linked in source_groups.items():
        choices = {group["choice"] for group in linked}
        conflicted = any(group["conflicted"] for group in linked) or len(choices) > 1
        tier = max((group["tier"] for group in linked), key=lambda value: TIER_UNITS[value])
        result.append({"model": source, "models": [group["model"] for group in linked],
                       "members": [member for group in linked for member in group["members"]],
                       "choice": next(iter(choices)) if not conflicted else "abstain",
                       "conflicted": conflicted, "tier": tier,
                       "weight": TIER_UNITS[tier] / 10})
    return result


def aggregate(master, workers, packet=None, gap_review=None, weight_config=None):
    if len(workers) != 5:
        raise ValueError("Exactly five worker ballots are required; failures should abstain")
    invalid_workers = []
    if packet is not None:
        if packet.get("missing"):
            raise ValueError("Frozen packet has unresolved missing records")
        errors = check_trace(packet, master)
        if errors:
            raise ValueError("Invalid master ballot: " + "; ".join(errors))
        checked_workers = []
        for i, ballot in enumerate(workers, 1):
            errors = check_trace(packet, ballot)
            if errors:
                invalid_workers.append({"worker": i, "errors": errors})
                checked_workers.append({"choice": "abstain", "model": ballot.get("model")})
            else:
                checked_workers.append(ballot)
        workers = checked_workers
    counts = {"red": 0, "blue": 0, "abstain": 0}
    counts[master["choice"]] += 1
    for ballot in workers:
        counts[ballot["choice"]] += 1
    groups = independent_votes(master, workers, weight_config)
    group_counts = {choice: sum(group["choice"] == choice for group in groups)
                    for choice in ("red", "blue", "abstain")}
    weighted_units = {choice: sum(TIER_UNITS[group["tier"]] for group in groups
                                  if group["choice"] == choice)
                      for choice in ("red", "blue", "abstain")}
    leader = "red" if weighted_units["red"] > weighted_units["blue"] else "blue"
    support = weighted_units[leader]
    opposition = weighted_units["blue" if leader == "red" else "red"]
    total = sum(weighted_units.values())
    directional = support + opposition
    evidence_gaps = packet.get("evidence_gaps", []) if packet is not None else []
    sensitive_gaps = assessed_gaps(packet, gap_review) if packet is not None else None
    if any(model.startswith("ballot:") for group in groups for model in group["models"]):
        decision_reason = "model_identity_missing"
    elif len(groups) < 4:
        decision_reason = "insufficient_independent_models"
    elif support == opposition:
        decision_reason = "weighted_tie"
    elif support * 5 < total * 3:
        decision_reason = "insufficient_weighted_support"
    elif support * 3 <= directional * 2:
        decision_reason = "insufficient_directional_consensus"
    elif evidence_gaps and sensitive_gaps is None:
        decision_reason = "evidence_gaps_need_review"
    elif sensitive_gaps:
        decision_reason = "outcome_sensitive_evidence_gap"
    else:
        decision_reason = "independent_consensus"
    outcome = leader if decision_reason == "independent_consensus" else "undecided"
    return {"ballot_counts": counts, "independent_counts": group_counts,
            "weighted_counts": {choice: units / 10 for choice, units in weighted_units.items()},
            "independent_groups": groups, "outcome": outcome,
            "decision_reason": decision_reason,
            "master_choice": master["choice"],
            "worker_choices": [ballot["choice"] for ballot in workers],
            "minimum_independent_models": 4,
            "weighted_support_share": round(support / total, 4) if total else 0,
            "weighted_directional_share": round(support / directional, 4) if directional else 0,
            "evidence_gaps_to_review": evidence_gaps,
            "evidence_gaps_reviewed": not evidence_gaps or sensitive_gaps is not None,
            "outcome_sensitive_gaps": sensitive_gaps or [],
            "invalid_workers": invalid_workers,
            "requires_master_review": outcome == "undecided",
            "note": "Capability tiers are provisional user choices: base=1.0, medium=1.2, strong=1.5; unspecified models use base. Configured model families count as one source at the highest member tier and abstain on conflict. Direction requires at least four sources, at least 60% of all weight and more than two-thirds of directional weight, plus reviewed evidence gaps. Weights and vote shares are not calibrated win probabilities."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("master_ballot", type=Path)
    parser.add_argument("worker_dir", type=Path)
    parser.add_argument("--packet", type=Path, required=True,
                        help="frozen reasoning_packet.json; validates every ballot before counting")
    parser.add_argument("--gap-review", type=Path,
                        help="JSON review of every evidence gap, bound to the frozen packet")
    parser.add_argument("--weight-config", type=Path,
                        help="optional model capability tiers; unspecified models use base=1.0")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    master = read_ballot(args.master_ballot)
    workers = [read_ballot(args.worker_dir / f"worker_{i}.json") for i in range(1, 6)]
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    gap_review = json.loads(args.gap_review.read_text(encoding="utf-8")) if args.gap_review else None
    weight_config = json.loads(args.weight_config.read_text(encoding="utf-8")) if args.weight_config else None
    result = aggregate(master, workers, packet, gap_review, weight_config)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
