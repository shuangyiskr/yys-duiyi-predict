#!/usr/bin/env python3
"""Make a per-round visual icon-to-name-to-effect review sheet."""
import argparse
import base64
import html
import json
from pathlib import Path

import cv2
import numpy as np

from fast_read import crop_box, load_image

ROOT = Path(__file__).resolve().parents[1]


def data_url(image):
    ok, binary = cv2.imencode(".png", image)
    return "data:image/png;base64," + base64.b64encode(binary).decode() if ok else ""


def reference(name):
    if not name:
        return "", ""
    matches = list((ROOT / "assets" / "screen_soul_templates").glob(name + "__*.png"))
    path = matches[0] if matches else ROOT / "assets" / "soul_portraits" / (name + ".png")
    if not path.is_file():
        return "", ""
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    return (data_url(image), "同款面板头像" if matches else "同款头像图库") if image is not None else ("", "")


def build(match):
    snapshot = json.loads((ROOT / "references" / "community_soul_snapshot.json").read_text(encoding="utf-8"))
    rows = []
    for side in ("red", "blue"):
        image = load_image(Path(match["screenshots"][side]))
        for index, unit in enumerate(match["teams"][side]):
            crop = crop_box(image, unit["soul_crop_box"])
            soul = unit.get("soul_name")
            art, art_label = reference(soul)
            effects = snapshot["souls"].get(soul, {})
            candidates = unit.get("soul_candidates") or []
            cand_text = ", ".join(f"{c['name']} ({c.get('similarity', c.get('distance'))})"
                                  for c in candidates[:3])
            label = f"{'红' if side == 'red' else '蓝'}{index+1}"
            rows.append("<tr>" +
                        f"<td>{label} · {html.escape(unit.get('name') or '?')}</td>" +
                        f"<td><img src='{data_url(crop)}'></td>" +
                        f"<td>{'<img src=' + repr(art) + '>' if art else '无本地图案'}<br><small>{html.escape(art_label)}</small></td>" +
                        f"<td>{html.escape(soul or '待确认')}<br><small>{html.escape(unit.get('soul_status') or '')}</small>"
                        f"<br><small>{html.escape(cand_text)}</small></td>" +
                        f"<td>二件套：{html.escape(effects.get('set2', '缺文案'))}<br>"
                        f"四件套/首领：{html.escape(effects.get('set4') or effects.get('set2', '缺文案'))}</td>"
                        "</tr>")
    source = html.escape(snapshot.get("source_url") or "未提供来源")
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>本轮御魂映射复核</title>"
            "<style>body{font:15px sans-serif;margin:24px;background:#f6f3ec;color:#222}"
            "table{border-collapse:collapse;background:white}th,td{border:1px solid #bbb;padding:8px;vertical-align:top}"
            "img{width:80px;height:80px;object-fit:contain}small{color:#666}</style>"
            f"<h1>本轮御魂映射复核</h1><p>run_id: {html.escape(match['run_id'])}</p>"
            "<p>逐行核对：截图裁图 → 候选参考图 → 御魂名 → 文案。空白或低置信请先确认。"
            f"文案来源：{source}；请核对本地资料与当前客户端。</p>"
            "<table><tr><th>位置</th><th>截图图案</th><th>参考图</th><th>识别结果</th><th>候选效果</th></tr>"
            + "".join(rows) + "</table></html>")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("match", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    match = json.loads(args.match.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(match), encoding="utf-8")
    print(args.out.resolve())


if __name__ == "__main__":
    main()
