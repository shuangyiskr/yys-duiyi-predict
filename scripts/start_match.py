#!/usr/bin/env python3
"""Create a fresh, uniquely named run from this round's red and blue screenshots."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("red", type=Path, help="current round red panel image")
    parser.add_argument("blue", type=Path, help="current round blue panel image")
    parser.add_argument("--runs-dir", type=Path, default=Path.cwd() / "runs")
    args = parser.parse_args()
    required = ["official_skills_snapshot.json", "community_soul_snapshot.json",
                "community_ai_snapshot.json", "wiki_skill_glossary.json", "duel_rules.json"]
    absent = [name for name in required if not (ROOT / "references" / name).is_file()]
    if absent:
        parser.error("local input files are missing; run python scripts/bootstrap_data.py first: " + ", ".join(absent))
    red, blue = args.red.resolve(), args.blue.resolve()
    if not red.is_file() or not blue.is_file() or red == blue:
        parser.error("provide two distinct existing images from the current round")
    run_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    run_dir = args.runs_dir.resolve() / run_name
    run_dir.mkdir(parents=True, exist_ok=False)
    match_file = run_dir / "match.json"
    read_result = subprocess.run([sys.executable, str(ROOT / "scripts" / "fast_read.py"),
                                  str(red), str(blue), "--out", str(match_file)],
                                 capture_output=True, text=True)
    if read_result.returncode:
        parser.error(read_result.stderr.strip() or "截图表格识别失败，请核对阵容详情截图")
    match = json.loads(match_file.read_text(encoding="utf-8"))
    match["rule_overrides"] = {}
    match_file.write_text(json.dumps(match, ensure_ascii=False, indent=2), encoding="utf-8")
    snapshot = json.loads((ROOT / "references" / "official_skills_snapshot.json").read_text(encoding="utf-8"))
    fetched_at = snapshot.get("fetched_at_utc")
    cache_age_days = ((datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at)).total_seconds() / 86400
                      if fetched_at else None)
    if set(match["teams"]) != {"red", "blue"}:
        match["issues"].append("无法确认两张图分别为红方和蓝方")
        match_file.write_text(json.dumps(match, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"run_dir": str(run_dir), "match": str(match_file),
              "run_id": match["run_id"], "issues": match["issues"],
              "skill_data_age_days": round(cache_age_days, 1) if cache_age_days is not None else None,
              "skill_data_date_missing": cache_age_days is None}
    if set(match["teams"]) == {"red", "blue"}:
        review_file = run_dir / "soul_review.html"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_soul_review.py"),
                        str(match_file), "--out", str(review_file)],
                       check=True, capture_output=True, text=True)
        result["soul_review"] = str(review_file)
    if not match["issues"]:
        bundle_file = run_dir / "bundle.json"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_inference_bundle.py"),
                        str(match_file), "--out", str(bundle_file)],
                       check=True, capture_output=True, text=True)
        result["bundle"] = str(bundle_file)
        bundle = json.loads(bundle_file.read_text(encoding="utf-8"))
        result["mechanics_missing"] = bundle["missing"]
        result["prediction_input_ready"] = not bool(bundle["missing"])
        packet_file = run_dir / "reasoning_packet.json"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_reasoning_packet.py"),
                        str(bundle_file), "--out", str(packet_file)],
                       check=True, capture_output=True, text=True)
        result["reasoning_packet"] = str(packet_file)
    else:
        result["prediction_input_ready"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
