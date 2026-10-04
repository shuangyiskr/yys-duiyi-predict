#!/usr/bin/env python3
"""Generate a standalone name → portrait → effect review page."""
import argparse
import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    snapshot = json.loads((ROOT / "references" / "community_soul_snapshot.json").read_text(encoding="utf-8"))
    sources = json.loads((ROOT / "references" / "soul_portrait_sources.json").read_text(encoding="utf-8"))["items"]
    cards = []
    for name, effects in snapshot["souls"].items():
        path = ROOT / "assets" / "soul_portraits" / (name + ".png")
        art = ("data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()) if path.is_file() else ""
        source = sources.get(name, {}).get("source_page", "")
        lines = [f"<p><b>{html.escape(key)}</b> {html.escape(value)}</p>"
                 for key, value in effects.items() if value]
        cards.append("<section>" +
                     (f"<img src='{art}' alt='{html.escape(name)}'>" if art else "<strong>缺头像</strong>") +
                     f"<h2>{html.escape(name)}</h2>" + "".join(lines) +
                     (f"<a href='{html.escape(source)}'>头像来源</a>" if source else "<strong>缺来源</strong>") +
                     "</section>")
    return ("<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>御魂头像与套系文案核对</title>"
            "<style>body{font:15px sans-serif;background:#f5f2e9;color:#242424;margin:24px}"
            "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}"
            "section{background:white;border:1px solid #d0c7b8;border-radius:8px;padding:14px}"
            "img{float:right;width:80px;height:80px}h2{font-size:19px;margin:0 0 14px}p{line-height:1.45}"
            "a{color:#1166a3}</style><h1>御魂头像 → 名称 → 套系文案</h1>"
            f"<p>候选条目 {len(cards)} 种；图片和文案来自使用者导入的本地资料，需核对当前游戏客户端。"
            f"<a href='{html.escape(snapshot['source_url'])}'>文案来源</a></p>"
            "<main>" + "".join(cards) + "</main></html>")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(), encoding="utf-8")
    print(args.out.resolve())


if __name__ == "__main__":
    main()
