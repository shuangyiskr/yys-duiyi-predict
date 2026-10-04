#!/usr/bin/env python3
"""Ask five isolated OpenAI-compatible workers to infer from one frozen packet."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit
from verify_inference_trace import check as check_trace

SYSTEM = (
    "你是《阴阳师》对弈竞猜的独立分析员。只使用本次冻结包。先读满级升级文案和社区AI表，"
    "按开局效果、行动条、双方独立鬼火、AI技能和目标、逐次伤害与御魂触发推演。"
    "候选机制、随机目标、暴击和未证实结算次序必须分支；不得让自动AI替玩家选最优目标。"
    "若关键分支不收敛，choice=abstain。只输出JSON对象，含 run_id、packet_sha256、choice、"
    "decisive_steps字符串数组、uncertainties字符串数组、key_actions数组。"
    "每个关键行动含 actor_side,actor,skill_id,target_side(red|blue|summon),target,ordinary_turn_number_for_side,"
    "fire_before,fire_spent,fire_gained,fire_after,fire_gain_source,target_basis,contingent,evidence_refs。"
    "没有目标用null；随机选定的具体目标必须标 contingent=true。"
    "evidence_refs格式如 skill:式神名:技能ID、soul:御魂名、ai:式神名、rule:initial_fire。"
    "只写能从输入文字支持的关键行动；鬼火或目标无法确定时将其作为分支，在 uncertainties 中说明。"
)


def validated_api_base(value):
    if not isinstance(value, str):
        raise ValueError("api_base must be an HTTPS URL")
    url = urlsplit(value)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or any(char.isspace() for char in value)):
        raise ValueError("api_base must be an HTTPS URL without credentials, query, or fragment")
    try:
        _ = url.port
    except ValueError as exc:
        raise ValueError("api_base has an invalid port") from exc
    return value.rstrip("/")


class NoRedirectHandler(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("model endpoint redirected; refusing to forward the API key and packet")


def parse_ballot(content):
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    ballot = json.loads(text)
    if ballot.get("choice") not in ("red", "blue", "abstain"):
        raise ValueError("invalid choice")
    if not isinstance(ballot.get("decisive_steps"), list) or not isinstance(ballot.get("uncertainties"), list):
        raise ValueError("missing reasoning arrays")
    return ballot


def call_worker(index, spec, packet_text, packet):
    env_name = spec["api_key_env"]
    key = os.environ.get(env_name)
    if not key:
        raise ValueError(f"missing environment variable {env_name}")
    api_base = validated_api_base(spec["api_base"])
    payload = {
        "model": spec["model"],
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": packet_text}
        ],
        "max_tokens": spec.get("max_tokens", 12000)
    }
    if "temperature" in spec:
        payload["temperature"] = spec["temperature"]
    if "reasoning_effort" in spec:
        payload["reasoning_effort"] = spec["reasoning_effort"]
    req = request.Request(
        api_base + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST"
    )
    with request.build_opener(NoRedirectHandler()).open(
            req, timeout=spec.get("timeout_seconds", 240)) as response:
        result = json.load(response)
    if result["choices"][0].get("finish_reason") == "length":
        raise ValueError("model output truncated at max_tokens; increase this worker's budget")
    content = result["choices"][0]["message"]["content"]
    ballot = parse_ballot(content)
    errors = check_trace(packet, ballot)
    if errors:
        raise ValueError("invalid inference trace: " + "; ".join(errors))
    ballot["worker_id"] = index
    ballot["model"] = spec["model"]
    return ballot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path, help="reasoning_packet.json from build_reasoning_packet.py")
    parser.add_argument("config", type=Path, help="JSON with exactly five independent worker configurations")
    parser.add_argument("--master-ballot", type=Path, required=True,
                        help="Must already exist; this script checks existence but never reads its contents")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.master_ballot.is_file():
        parser.error("write your independent master ballot before launching workers")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    workers = config.get("workers", [])
    if len(workers) != 5:
        parser.error("config must contain exactly five workers")
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    if packet.get("schema_version") != 1 or not packet.get("packet_sha256"):
        parser.error("input must be a frozen reasoning_packet.json")
    if packet.get("missing"):
        parser.error("match has missing skill or soul records; resolve before model inference")
    packet_text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outcomes = [None] * 5
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(call_worker, i + 1, spec, packet_text, packet): i for i, spec in enumerate(workers)}
        for future in as_completed(futures):
            i = futures[future]
            try:
                outcomes[i] = future.result()
            except Exception as exc:
                outcomes[i] = {"worker_id": i + 1, "model": workers[i].get("model"),
                               "choice": "abstain", "decisive_steps": [],
                               "uncertainties": [f"worker call failed: {type(exc).__name__}: {exc}"],
                               "run_id": packet["run_id"], "packet_sha256": packet["packet_sha256"],
                               "key_actions": []}
            path = args.out_dir / f"worker_{i+1}.json"
            path.write_text(json.dumps(outcomes[i], ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"worker_ballots": [str((args.out_dir / f"worker_{i+1}.json").resolve()) for i in range(5)],
                      "master_ballot": str(args.master_ballot.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
