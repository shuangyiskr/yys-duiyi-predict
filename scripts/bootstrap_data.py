#!/usr/bin/env python3
"""Import user-provided local data and report coverage. No network access."""
import argparse
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "references"
PORTRAITS = ROOT / "assets" / "soul_portraits"
DATASETS = {
    "official_skills_snapshot.json": "heroes",
    "community_soul_snapshot.json": "souls",
    "community_ai_snapshot.json": "heroes",
    "wiki_skill_glossary.json": "heroes",
}


def validate_json(path, section):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get(section), dict):
        raise ValueError(f"{path}: expected a JSON object with an object-valued '{section}'")
    return data


def validate_portrait(path):
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"{path}: expected a PNG image")
    if struct.unpack(">II", header[16:24]) != (80, 80):
        raise ValueError(f"{path}: expected an 80x80 duel-panel portrait")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path,
                        help="local directory containing references/*.json and assets/soul_portraits/*.png")
    parser.add_argument("--replace", action="store_true", help="replace existing imported files")
    args = parser.parse_args()
    prepared = []
    if args.source_dir:
        source = args.source_dir.resolve()
        if not source.is_dir():
            parser.error("--source-dir must name an existing local directory")
        for name, section in DATASETS.items():
            file = source / "references" / name
            if file.is_file():
                validate_json(file, section)
                prepared.append((file, REF / name))
        for file in sorted((source / "assets" / "soul_portraits").glob("*.png")):
            validate_portrait(file)
            prepared.append((file, PORTRAITS / file.name))
        if not prepared:
            parser.error("no supported local snapshots or portraits found in --source-dir")
        conflicts = []
        for src, dst in prepared:
            if not dst.exists() or args.replace or src.read_bytes() == dst.read_bytes():
                continue
            if dst.name in DATASETS and validate_json(dst, DATASETS[dst.name]).get("source_type") == "not_provided":
                continue
            conflicts.append(str(dst))
        if conflicts:
            parser.error("existing data differs; pass --replace to update: " + ", ".join(conflicts[:5]))
        for src, dst in prepared:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != dst.resolve():
                shutil.copy2(src, dst)
    rules = REF / "duel_rules.json"
    if not rules.exists():
        shutil.copyfile(REF / "duel_rules.example.json", rules)
    for name, section in DATASETS.items():
        file = REF / name
        if not file.exists():
            file.write_text(json.dumps({section: {}, "source_type": "not_provided"},
                                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage = {}
    for name, section in DATASETS.items():
        file = REF / name
        coverage[name] = len(validate_json(file, section)[section]) if file.is_file() else None
    print(json.dumps({"imported_files": len(prepared), "local_coverage": coverage,
                      "portrait_count": len(list(PORTRAITS.glob("*.png"))),
                      "local_rules": str(rules), "network_access": False,
                      "note": "Missing data stays missing; verify current-match coverage before inference."},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
