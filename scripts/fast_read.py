#!/usr/bin/env python3
"""Read a duel line-up table from OCR anchors at any screenshot size."""
import argparse
import hashlib
import json
import re
import time
from statistics import median
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parents[1]
STATS = ["attack", "hp", "defense", "speed", "crit", "crit_damage", "effect_hit", "effect_resist"]
ROW_LABELS = ["攻击", "生命", "防御", "速度", "暴击", "暴击伤害", "效果命中", "效果抵抗"]
SOUL_LABEL = "御魂效果"
def known_names():
    """Read the current cached official index, never a past matchup's lineup."""
    snapshot = ROOT / "references" / "official_skills_snapshot.json"
    return set(json.loads(snapshot.read_text(encoding="utf-8"))["heroes"])


def load_image(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"无法读取图片: {path}")
    return image


def recognized_lines(ocr, image):
    # Cap OCR width only; retain the original image and coordinates for icon crops.
    scale = min(1.0, 1800 / image.shape[1])
    ocr_image = (cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
                 if scale < 1 else image)
    result, _ = ocr(ocr_image)
    lines = []
    for box, value, confidence in result or []:
        x = sum(point[0] for point in box) / 4 / scale
        y = sum(point[1] for point in box) / 4 / scale
        lines.append({"x": x, "y": y, "text": value.strip(), "confidence": round(float(confidence), 3)})
    return lines


def detect_layout(lines, image_shape):
    """Derive the eight rows, five columns and icon row from the table's own text."""
    labels = {}
    for index, label in enumerate(ROW_LABELS):
        matches = [line for line in lines if line["text"].replace(" ", "") == label]
        if matches:
            labels[index] = max(matches, key=lambda item: item["confidence"])
    soul = [line for line in lines if line["text"].replace(" ", "") == SOUL_LABEL]
    if len(labels) < 6 or 0 not in labels or not soul:
        raise ValueError("无法定位阵容表的数值行和御魂行，请提供清晰的阵容详情截图")
    label_x = median(line["x"] for line in labels.values())
    soul_line = min(soul, key=lambda item: abs(item["x"] - label_x))
    # A missed row label may be interpolated, but its five values still need OCR evidence.
    slopes = [(labels[j]["y"] - labels[i]["y"]) / (j - i)
              for i in labels for j in labels if j > i]
    spacing = median(slopes)
    if spacing < 18 or spacing > image_shape[0] / 5:
        raise ValueError("阵容表行间距异常，无法安全读取")
    intercept = median(line["y"] - index * spacing for index, line in labels.items())
    row_y = [intercept + index * spacing for index in range(8)]
    if any(abs(line["y"] - row_y[index]) > spacing * .3 for index, line in labels.items()):
        raise ValueError("阵容表行名未对齐，无法安全读取")
    if not .8 * spacing < soul_line["y"] - row_y[-1] < 1.7 * spacing:
        raise ValueError("御魂行与数值表未对齐，无法安全读取")

    number_pattern = re.compile(r"\d{1,6}%?")
    candidate_rows = []
    for index, y in enumerate(row_y):
        row = sorted((line for line in lines
                      if abs(line["y"] - y) < spacing * .27
                      and line["x"] > label_x + spacing * .9
                      and number_pattern.fullmatch(line["text"])), key=lambda item: item["x"])
        if len(row) == 5 and all(("%" in line["text"]) == (index >= 4) for line in row):
            candidate_rows.append(row)
    if not candidate_rows:
        raise ValueError("无法在阵容表中定位五列数值")
    base = candidate_rows[0]
    column_gap = median(base[i + 1]["x"] - base[i]["x"] for i in range(4))
    if column_gap < spacing * 2 or column_gap > image_shape[1] / 3:
        raise ValueError("阵容表列间距异常，无法安全读取")
    aligned_rows = [row for row in candidate_rows
                    if all(abs(row[i]["x"] - base[i]["x"]) < column_gap * .18 for i in range(5))]
    col_x = [median(row[i]["x"] for row in aligned_rows) for i in range(5)]
    if len(aligned_rows) < 3 or any(abs(col_x[i + 1] - col_x[i] - column_gap) > column_gap * .15
                                    for i in range(4)):
        raise ValueError("阵容表五列数值未稳定对齐，无法安全读取")
    return {"row_y": row_y, "col_x": col_x, "soul_y": soul_line["y"],
            "name_y": row_y[0] - spacing, "label_x": label_x,
            "row_spacing": spacing, "column_spacing": column_gap}


def soul_box(image_shape, layout, index):
    """Return an original-image box, reused by recognition and later verification."""
    radius = round(layout["row_spacing"] * .66)
    cx = round(layout["col_x"][index] - layout["row_spacing"] * .15)
    cy = round(layout["soul_y"])
    height, width = image_shape[:2]
    box = [max(0, cx-radius), max(0, cy-radius), min(width, cx+radius), min(height, cy+radius)]
    if box[2] - box[0] < radius * 1.7 or box[3] - box[1] < radius * 1.7:
        raise ValueError("御魂图案裁切范围超出截图")
    return box


def crop_box(image, box):
    x0, y0, x1, y1 = map(int, box)
    if not (0 <= x0 < x1 <= image.shape[1] and 0 <= y0 < y1 <= image.shape[0]):
        raise ValueError("无效的御魂图案裁切范围")
    return image[y0:y1, x0:x1]


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


def portrait_candidates(image, box, icons):
    if not icons:
        return []
    x0, y0, x1, y1 = box
    margin_x, margin_y = round((x1-x0) * .13), round((y1-y0) * .13)
    crop = crop_box(image, [x0+margin_x, y0+margin_y, x1-margin_x, y1-margin_y])
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


def read_soul(image, box, templates, icons):
    crop = crop_box(image, box)
    feature = icon_features(crop)
    ranked = sorted((min(float(np.mean(np.linalg.norm(feature - value, axis=1))) for value in values), name)
                    for name, values in templates.items())
    # Distance is a heuristic. Store top candidates and only auto-select with a useful gap.
    candidates = [{"name": name, "method": "confirmed_screen_template", "distance": round(distance, 2)}
                  for distance, name in ranked[:3]]
    portrait = portrait_candidates(image, box, icons)
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


def soul_crop_id(image, box):
    """Stable identifier for this screenshot crop, independent of a soul name."""
    crop = crop_box(image, box)
    normalized = cv2.resize(crop, (80, 80), interpolation=cv2.INTER_AREA)
    return hashlib.sha256(normalized.tobytes()).hexdigest()[:16]


def read_side(path, ocr, templates, icons, names):
    image = load_image(path)
    lines = recognized_lines(ocr, image)
    layout = detect_layout(lines, image.shape)
    row_gap = layout["row_spacing"]
    col_gap = layout["column_spacing"]
    side_line = nearest(lines, layout["label_x"], layout["name_y"], row_gap * .7, row_gap * .4)
    side = "red" if side_line and side_line["text"] == "红方" else "blue" if side_line and side_line["text"] == "蓝方" else None
    team = []
    issues = []
    for index, x in enumerate(layout["col_x"]):
        name_line = nearest(lines, x, layout["name_y"], col_gap * .45, row_gap * .4)
        name, name_status = read_name(name_line, names)
        stats = {}
        raw_stats = {}
        stats_confidence = {}
        for key, y in zip(STATS, layout["row_y"]):
            line = nearest(lines, x, y, col_gap * .3, row_gap * .28)
            stats[key] = read_stat(line, key)
            raw_stats[key] = line["text"] if line else None
            stats_confidence[key] = line["confidence"] if line else None
            if stats[key] is None:
                issues.append(f"第{index+1}列 {key} 未识别")
            elif line["confidence"] < .9:
                issues.append(f"第{index+1}列 {key} OCR置信度低，请核验 {line['text']}")
        box = soul_box(image.shape, layout, index)
        soul, candidates, soul_status = read_soul(image, box, templates, icons)
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
                     "soul_name": soul, "soul_icon_id": soul_crop_id(image, box),
                     "soul_crop_box": box,
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
        try:
            side, team, issues = read_side(path, ocr, templates, icons, names)
        except ValueError as exc:
            raise SystemExit(f"{path}: {exc}") from exc
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
