#!/usr/bin/env python3
"""Add only explicitly confirmed soul-icon crops, without storing lineups."""
import json
import argparse
from pathlib import Path
import cv2
import numpy as np
from fast_read import COL_X, REF_W, REF_H, SOUL_Y, load_image, soul_crop_id

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "assets" / "screen_soul_templates"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", nargs="+", type=Path, help="御魂已由用户确认的 match JSON")
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    added = 0
    for fixture in args.fixtures:
        data = json.loads(fixture.read_text(encoding="utf-8"))
        for side, team in data["teams"].items():
            if side not in {"red", "blue"} or side not in data.get("screenshots", {}):
                continue
            if not any(entry.get("soul_status") == "user_confirmed" for entry in team):
                continue
            image = load_image(Path(data["screenshots"][side]))
            sx, sy = image.shape[1] / REF_W, image.shape[0] / REF_H
            radius = round(34 * (sx + sy) / 2)
            for index, entry in enumerate(team):
                if entry.get("soul_status") != "user_confirmed":
                    continue
                if not entry.get("soul_name") or soul_crop_id(image, COL_X[index]) != entry.get("soul_icon_id"):
                    raise ValueError(f"Confirmed icon does not match its screenshot: {fixture} {side}-{index+1}")
                cx, cy = round((COL_X[index] - 8) * sx), round(SOUL_Y * sy)
                crop = image[cy-radius:cy+radius, cx-radius:cx+radius]
                name = entry["soul_name"]
                # The asset contains only the icon and a label, never a prior lineup.
                path = DEST / f"{name}__{soul_crop_id(image, COL_X[index])}.png"
                if not path.exists():
                    cv2.imencode(".png", crop)[1].tofile(str(path))
                    added += 1
    print(f"Added {added} confirmed screenshot templates; total {len(list(DEST.glob('*.png')))}")


if __name__ == "__main__":
    main()
