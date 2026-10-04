#!/usr/bin/env python3
"""Fail-closed validation before any matchup prediction."""
import argparse
import json
from pathlib import Path
from fast_read import COL_X, load_image, soul_crop_id

STATS = ("attack", "hp", "defense", "speed", "crit", "crit_damage", "effect_hit", "effect_resist")
SKILL_FIELDS = ("name", "description", "triggers", "conditions", "effects", "auto_ai", "limits")
SOUL_FIELDS = ("description", "triggers", "conditions", "effects", "limits")


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def check(match, catalog, intake_only=False):
    issues = []
    issues.extend(match.get("issues", []))
    if not intake_only and (not match.get("game_version") or match["game_version"] == "unverified"):
        issues.append("对局游戏版本未确认")
    if not intake_only and catalog.get("game_version") != match.get("game_version"):
        issues.append("机制目录与对局版本不一致")
    screenshots = match.get("screenshots", {})
    sides = ("red", "blue") if not intake_only else tuple(match.get("teams", {}))
    if not sides:
        issues.append("没有阵容")
    for side in sides:
        image = load_image(Path(screenshots[side])) if screenshots.get(side) and Path(screenshots[side]).is_file() else None
        if not screenshots.get(side) or not Path(screenshots[side]).is_file():
            issues.append(f"{side}: 原始截图不存在")
        team = match.get("teams", {}).get(side)
        if not isinstance(team, list) or len(team) != 5:
            issues.append(f"{side}: 必须恰好有五名式神")
            continue
        for index, unit in enumerate(team, 1):
            label = f"{side}-{index}"
            name = unit.get("name")
            if not isinstance(name, str) or not name.strip():
                issues.append(f"{label}: 式神名称未确认")
            if unit.get("name_status") == "raw_ocr_unverified":
                issues.append(f"{label}: 新式神 OCR 姓名尚未人工确认")
            stats = unit.get("stats", {})
            for key in STATS:
                value = stats.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    issues.append(f"{label}: {key} 缺失或非法")
            icon_id = unit.get("soul_icon_id")
            soul_name = unit.get("soul_name")
            if not icon_id:
                issues.append(f"{label}: 御魂图案未留标识")
            if not soul_name:
                issues.append(f"{label}: 御魂名称未确认（图案 {icon_id or '?'}）")
            status = unit.get("soul_status")
            if status not in {"screen_template_high_confidence", "portrait_high_confidence", "user_confirmed"}:
                issues.append(f"{label}: 御魂图案尚无可靠映射")
            elif status != "user_confirmed":
                candidates = unit.get("soul_candidates") or []
                if not candidates or candidates[0].get("name") != soul_name:
                    issues.append(f"{label}: 御魂名称与图案首选候选不一致")
            if image is not None and icon_id != soul_crop_id(image, COL_X[index-1]):
                issues.append(f"{label}: 图案指纹与本轮截图不一致")
            if name and not intake_only:
                entry = catalog.get("shikigami", {}).get(name)
                if not entry or not entry.get("verified") or entry.get("version") != match.get("game_version") or not entry.get("source"):
                    issues.append(f"{label}: {name} 缺少同版本已核实技能资料")
                elif not entry.get("skills") or any(any(not skill.get(field) for field in SKILL_FIELDS) for skill in entry["skills"]):
                    issues.append(f"{label}: {name} 技能机制字段不完整")
            if soul_name and not intake_only:
                entry = catalog.get("souls", {}).get(soul_name)
                if not entry or not entry.get("verified") or entry.get("version") != match.get("game_version") or not entry.get("source"):
                    issues.append(f"{label}: {soul_name} 缺少同版本已核实御魂资料")
                else:
                    if icon_id not in entry.get("icon_ids", []):
                        issues.append(f"{label}: 图案 {icon_id} 未与 {soul_name} 绑定")
                    if any(not entry.get(field) for field in SOUL_FIELDS):
                        issues.append(f"{label}: {soul_name} 御魂机制字段不完整")
    return list(dict.fromkeys(issues))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("match", type=Path)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parents[1] / "references" / "catalog.json")
    parser.add_argument("--intake-only", action="store_true", help="只核验截图录入；允许仅有一方，不检查技能库")
    args = parser.parse_args()
    issues = check(load(args.match), load(args.catalog), args.intake_only)
    if issues:
        print("BLOCKED: 核验未通过。")
        for issue in issues:
            print("- " + issue)
        raise SystemExit(2)
    print("INTAKE READY: 结构字段齐全，仍需人工逐格确认。" if args.intake_only else "READY: 输入与机制资料核验通过，可开始推演。")


if __name__ == "__main__":
    main()
