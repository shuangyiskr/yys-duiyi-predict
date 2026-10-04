#!/usr/bin/env python3
"""Aggregate independent model votes without assumed accuracy weights."""
import argparse
import json
from pathlib import Path
from verify_inference_trace import check as check_trace


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


def independent_votes(master, workers):
    groups = {}
    for label, ballot in [("master", master)] + [(f"worker_{i}", b) for i, b in enumerate(workers, 1)]:
        model = ballot.get("model")
        key = "model:" + model.strip().casefold() if isinstance(model, str) and model.strip() else "ballot:" + label
        groups.setdefault(key, []).append((label, ballot["choice"]))
    result = []
    for model, members in groups.items():
        choices = {choice for _, choice in members}
        conflicted = len(choices) > 1
        result.append({"model": model, "members": [label for label, _ in members],
                       "choice": next(iter(choices)) if not conflicted else "abstain",
                       "conflicted": conflicted})
    return result


def aggregate(master, workers, packet=None, gap_review=None):
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
    groups = independent_votes(master, workers)
    group_counts = {choice: sum(group["choice"] == choice for group in groups)
                    for choice in ("red", "blue", "abstain")}
    leader = "red" if group_counts["red"] > group_counts["blue"] else "blue"
    supporters = group_counts[leader]
    opponents = group_counts["blue" if leader == "red" else "red"]
    min_support = max(3, (2 * len(groups) + 2) // 3)
    evidence_gaps = packet.get("evidence_gaps", []) if packet is not None else []
    sensitive_gaps = assessed_gaps(packet, gap_review) if packet is not None else None
    if any(group["model"].startswith("ballot:") for group in groups):
        decision_reason = "model_identity_missing"
    elif len(groups) < 4:
        decision_reason = "insufficient_independent_models"
    elif supporters < min_support:
        decision_reason = "insufficient_independent_support"
    elif opponents * 3 > supporters:
        decision_reason = "insufficient_directional_consensus"
    elif evidence_gaps and sensitive_gaps is None:
        decision_reason = "evidence_gaps_need_review"
    elif sensitive_gaps:
        decision_reason = "outcome_sensitive_evidence_gap"
    else:
        decision_reason = "independent_consensus"
    outcome = leader if decision_reason == "independent_consensus" else "undecided"
    return {"ballot_counts": counts, "independent_counts": group_counts,
            "independent_groups": groups, "outcome": outcome,
            "decision_reason": decision_reason,
            "master_choice": master["choice"],
            "worker_choices": [ballot["choice"] for ballot in workers],
            "minimum_support": min_support,
            "evidence_gaps_to_review": evidence_gaps,
            "evidence_gaps_reviewed": not evidence_gaps or sensitive_gaps is not None,
            "outcome_sensitive_gaps": sensitive_gaps or [],
            "invalid_workers": invalid_workers,
            "requires_master_review": outcome == "undecided",
            "note": "Each named model has one vote. Direction needs every ballot's model label, at least four model groups, two-thirds of all groups supporting, at least 75% of directional groups supporting, and reviewed evidence gaps. Votes are not calibrated win probabilities."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("master_ballot", type=Path)
    parser.add_argument("worker_dir", type=Path)
    parser.add_argument("--packet", type=Path, required=True,
                        help="frozen reasoning_packet.json; validates every ballot before counting")
    parser.add_argument("--gap-review", type=Path,
                        help="JSON review of every evidence gap, bound to the frozen packet")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    master = read_ballot(args.master_ballot)
    workers = [read_ballot(args.worker_dir / f"worker_{i}.json") for i in range(1, 6)]
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    gap_review = json.loads(args.gap_review.read_text(encoding="utf-8")) if args.gap_review else None
    result = aggregate(master, workers, packet, gap_review)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
