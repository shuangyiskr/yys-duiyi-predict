#!/usr/bin/env python3
"""Read a known Onmyoji duel line-up layout with OCR and soul-icon templates."""
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parents[1]
REF_W, REF_H = 1554, 1080
COL_X = [391, 624, 856, 1089, 1321]
ROW_Y = [377, 432, 487, 542, 596, 651, 706, 760]
STATS = ["attack", "hp", "defense", "speed", "crit", "crit_damage", "effect_hit", "effect_resist"]
SOUL_Y = 830
def known_names():
    """Read the current cached official index, never a past matchup's lineup."""
    snapshot = ROOT / "references" / "official_skills_snapshot.json"
    return set(json.loads(snapshot.read_text(encoding="utf-8"))["heroes"])


def load_image(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取图片: {path}")
    h, w = image.shape[:2]
    if abs(w / h - REF_W / REF_H) > .025:
        raise ValueError(f"非已知版式比例: {w}x{h}")
    return image


def recognized_lines(ocr, image):
    # OCR is resolution capped; the full-resolution image is kept for icon matching.
    ocr_image = cv2.resize(image, (REF_W, REF_H), interpolation=cv2.INTER_AREA) if image.shape[1] > REF_W else image
    result, _ = ocr(ocr_image)
    lines = []
    for box, value, confidence in result or []:
        x = sum(point[0] for point in box) / 4 * REF_W / ocr_image.shape[1]
        y = sum(point[1] for point in box) / 4 * REF_H / ocr_image.shape[0]
        lines.append({"x": x, "y": y, "text": value.strip(), "confidence": round(float(confidence), 3)})
    return lines


def nearest(lines, x, y, dx=90, dy=24):
    candidates = [line for line in lines if abs(line["x"] - x) < dx and abs(line["y"] - y) < dy]
    return min(candidates, key=lambda v: abs(v["x"] - x) + 2 * abs(v["y"] - y)) if candidates else None


def read_name(line, names):
    if not line:
        return None, "missing"
    raw = line["text"]
    if raw in names:
        return raw, "exact"
    if re.fullmatch(r"[\u4e00-\u9fff]{1,10}", raw):
        return raw, "raw_ocr_unverified"
    return None, "ambiguous"


def read_stat(line, key):
    if not line:
        return None
    raw = line["text"].replace("％", "%").replace("O", "0").replace("o", "0")
    match = re.fullmatch(r"(\d{1,6})(%)?", raw)
    if not match or (key in STATS[4:]) != bool(match.group(2)):
        return None
    return int(match.group(1))


def icon_features(image):
    image = cv2.resize(image, (80, 80), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    # Exclude the outer ring and the rectangular screenshot background.
    yy, xx = np.ogrid[:80, :80]
    mask = (xx - 40) ** 2 + (yy - 40) ** 2 < 31 ** 2
    return lab[mask]


def soul_templates():
    result = {}
    for path in (ROOT / "assets" / "screen_soul_templates").glob("*.png"):
        image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
        result.setdefault(path.stem.split("__")[0], []).append(icon_features(image))
    return result


def portrait_icons():
    """Named 80px portraits matching the duel-panel art style."""
    result = []
    for path in (ROOT / "assets" / "soul_portraits").glob("*.png"):
        full = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if full is None:
            continue
        full = full[:, :, :3]
        sizes = [full, cv2.resize(full, None, fx=.8, fy=.8, interpolation=cv2.INTER_AREA)]
        result.append((path.stem, sizes))
    return result


def portrait_candidates(image, x, icons):
    if not icons:
        return []
    sx, sy = image.shape[1] / REF_W, image.shape[0] / REF_H
    cx, cy = round((x - 8) * sx), round(SOUL_Y * sy)
    radius = round(25 * (sx + sy) / 2)
    crop = image[cy-radius:cy+radius, cx-radius:cx+radius]
    if crop.size == 0:
        return []
    target = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA)[10:54, 10:54]
    ranked = []
    for name, sizes in icons:
        scores = [float(cv2.matchTemplate(full, target, cv2.TM_CCOEFF_NORMED).max())
                  for full in sizes if full.shape[0] >= 44 and full.shape[1] >= 44]
        if scores:
            ranked.append((max(scores), name))
    ranked.sort(reverse=True)
    return [{"name": name, "method": "named_panel_portrait", "similarity": round(score, 3)}
            for score, name in ranked[:3]]


def read_soul(image, x, templates, icons):
    sx, sy = image.shape[1] / REF_W, image.shape[0] / REF_H
    cx, cy = round((x - 8) * sx), round(SOUL_Y * sy)
    radius = round(34 * (sx + sy) / 2)
    # Crop only the art, excluding the gold frame.
    crop = image[cy-radius:cy+radius, cx-radius:cx+radius]
    if crop.size == 0:
        return None, [], "missing"
    feature = icon_features(crop)
    ranked = sorted((min(float(np.mean(np.linalg.norm(feature - value, axis=1))) for value in values), name)
                    for name, values in templates.items())
    # Distance is a heuristic. Store top candidates and only auto-select with a useful gap.
    candidates = [{"name": name, "method": "confirmed_screen_template", "distance": round(distance, 2)}
                  for distance, name in ranked[:3]]
    portrait = portrait_candidates(image, x, icons)
    portrait_choice = None
    if len(portrait) >= 2 and portrait[0]["similarity"] >= .64 and \
            portrait[0]["similarity"] - portrait[1]["similarity"] >= .11:
        portrait_choice = portrait[0]["name"]
    if len(ranked) >= 2:
        best, second = ranked[:2]
        if best[0] < 20 and second[0] - best[0] > 20:
            if portrait_choice and portrait_choice != best[1]:
                return None, candidates + portrait, "conflicting_visual_matches"
            return best[1], candidates + portrait, "screen_template_high_confidence"
    if portrait_choice:
        return portrait_choice, portrait + candidates, "portrait_high_confidence"
    return None, portrait + candidates, "unverified"


def soul_crop_id(image, x):
    """Stable identifier for this screenshot crop, independent of a soul name."""
    sx, sy = image.shape[1] / REF_W, image.shape[0] / REF_H
    cx, cy = round((x - 8) * sx), round(SOUL_Y * sy)
    radius = round(34 * (sx + sy) / 2)
    crop = image[cy-radius:cy+radius, cx-radius:cx+radius]
    if crop.size == 0:
        return None
    normalized = cv2.resize(crop, (80, 80), interpolation=cv2.INTER_AREA)
    return hashlib.sha256(normalized.tobytes()).hexdigest()[:16]


def read_side(path, ocr, templates, icons, names):
    image = load_image(path)
    lines = recognized_lines(ocr, image)
    side_line = nearest(lines, 188, 317, 45, 25)
    side = "red" if side_line and side_line["text"] == "红方" else "blue" if side_line and side_line["text"] == "蓝方" else None
    team = []
    issues = []
    for index, x in enumerate(COL_X):
        name_line = nearest(lines, x, 326, 105, 22)
        name, name_status = read_name(name_line, names)
        stats = {}
        raw_stats = {}
        stats_confidence = {}
        for key, y in zip(STATS, ROW_Y):
            line = nearest(lines, x, y, 65, 18)
            stats[key] = read_stat(line, key)
            raw_stats[key] = line["text"] if line else None
            stats_confidence[key] = line["confidence"] if line else None
            if stats[key] is None:
                issues.append(f"第{index+1}列 {key} 未识别")
            elif line["confidence"] < .9:
                issues.append(f"第{index+1}列 {key} OCR置信度低，请核验 {line['text']}")
        soul, candidates, soul_status = read_soul(image, x, templates, icons)
        if name is None:
            issues.append(f"第{index+1}列 式神名待核验")
        elif name_status == "raw_ocr_unverified":
            issues.append(f"第{index+1}列 式神名不在已确认词表，请核验原文 {name}")
        elif name_line["confidence"] < .95:
            issues.append(f"第{index+1}列 式神名 OCR置信度低，请核验 {name}")
        if soul is None:
            issues.append(f"第{index+1}列 御魂待核验")
        team.append({"name": name, "name_raw": name_line["text"] if name_line else None,
                     "name_status": name_status, "name_confidence": name_line["confidence"] if name_line else None,
                     "stats": stats, "stats_raw": raw_stats, "stats_confidence": stats_confidence,
                     "soul_name": soul, "soul_icon_id": soul_crop_id(image, x),
                     "soul_status": soul_status,
                     "soul_candidates": candidates})
    if side is None:
        issues.append("红蓝方标记待核验")
    return side, team, issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    ocr = RapidOCR()
    templates = soul_templates()
    icons = portrait_icons()
    names = known_names()
    output = {"game_version": "unverified", "run_id": uuid4().hex,
              "captured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "screenshots": {}, "teams": {}, "issues": []}
    for path in args.images:
        side, team, issues = read_side(path, ocr, templates, icons, names)
        key = side or f"unknown_{len(output['teams'])+1}"
        output["screenshots"][key] = str(path.resolve())
        output["teams"][key] = team
        output["issues"] += [f"{key}: {issue}" for issue in issues]
    output["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    content = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content, encoding="utf-8")
    print(content)


if __name__ == "__main__":
    main()
