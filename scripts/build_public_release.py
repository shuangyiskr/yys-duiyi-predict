#!/usr/bin/env python3
"""Build a clean public folder and ZIP from an explicit source-file allowlist."""
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ".gitignore", "LICENSE", "README.md", "requirements.txt", "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "references/ai_target_observations.json",
    "references/battle_protocol.md", "references/catalog.json",
    "references/combat_background.md", "references/duel_rules.example.json",
    "references/inference_workflow.md", "references/panel_config.example.json",
    "references/schema.md", "references/soul_roster.json",
    "scripts/aggregate_votes.py", "scripts/ai_targeting.py",
    "scripts/bootstrap_data.py", "scripts/build_inference_bundle.py",
    "scripts/build_public_release.py", "scripts/build_reasoning_packet.py",
    "scripts/build_screen_templates.py", "scripts/confirm_local_rules.py",
    "scripts/coverage_audit.py", "scripts/fast_read.py",
    "scripts/make_soul_portrait_review.py", "scripts/make_soul_review.py",
    "scripts/prepare_inference.py", "scripts/run_independent_panel.py",
    "scripts/source_fingerprints.py", "scripts/start_match.py",
    "scripts/verify_inference_trace.py", "scripts/verify_match.py",
    "tests/test_reasoning.py",
)


def main():
    parent = ROOT.parent.resolve()
    destination = parent / "yys-duiyi-predict-release"
    archive = parent / "yys-duiyi-predict-release.zip"
    if destination.resolve().parent != parent or archive.resolve().parent != parent:
        raise RuntimeError("release targets must stay in the source parent directory")
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise RuntimeError("release target overlaps the source")
    for name in FILES:
        source = ROOT / name
        if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise RuntimeError(f"missing or unsafe release file: {name}")
    if destination.exists() and (not destination.is_dir() or destination.is_symlink()):
        raise RuntimeError(f"unsafe release target: {destination}")
    destination.mkdir(exist_ok=True)
    allowed_files = set(FILES)
    allowed_dirs = {str(Path(name).parent).replace("\\", "/") for name in FILES}
    for existing in sorted(destination.rglob("*"), key=lambda path: len(path.parts), reverse=True):
        if existing.relative_to(destination).parts[0] == ".git":
            continue
        relative = existing.relative_to(destination).as_posix()
        if existing.is_symlink():
            existing.unlink()
        elif existing.is_file() and relative not in allowed_files:
            existing.unlink()
        elif existing.is_dir() and relative not in allowed_dirs:
            existing.rmdir()
    for name in FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
        for name in FILES:
            zipped.write(destination / name, name)
    print(f"Public folder: {destination}")
    print(f"Public ZIP: {archive}")
    print(f"Included files: {len(FILES)}")


if __name__ == "__main__":
    main()
