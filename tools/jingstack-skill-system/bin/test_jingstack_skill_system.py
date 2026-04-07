#!/usr/bin/env python3
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RENDER = ROOT / "tools/jingstack-skill-system/bin/render_skill_from_answers.py"
FIXTURE = ROOT / "tools/jingstack-skill-system/tests/fixtures/example-skill/answers.json"


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="jingstack-skill-test-") as tmp:
        outdir = Path(tmp) / "generated"
        cmd = [str(RENDER), str(FIXTURE), "--output-dir", str(outdir), "--emit-skill-md"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)

        skill_dir = Path(payload["skill_dir"])
        tmpl_path = Path(payload["tmpl_path"])
        skill_md = Path(payload["skill_md"])

        assert_true(skill_dir.exists(), "skill directory was not created")
        assert_true(tmpl_path.exists(), "SKILL.md.tmpl was not created")
        assert_true(skill_md.exists(), "SKILL.md was not created")

        tmpl_text = tmpl_path.read_text()
        skill_text = skill_md.read_text()

        for section in ["think", "plan", "build", "review", "test", "ship", "reflect"]:
            assert_true(f"### {section}" in tmpl_text, f"lifecycle section missing from tmpl: {section}")

        assert_true("questionnaire answers" in tmpl_text, "tmpl provenance note missing")
        assert_true("JingStack skill system" in skill_text, "generated markdown provenance missing")

        expected_dirs = {"references", "scripts"}
        actual_dirs = {p.name for p in skill_dir.iterdir() if p.is_dir()}
        assert_true(expected_dirs.issubset(actual_dirs), f"expected resource dirs missing: {expected_dirs - actual_dirs}")
        assert_true("assets" not in actual_dirs, "unexpected ghost assets dir created")

        stray = []
        for p in Path(tmp).rglob("*"):
            rel = p.relative_to(tmp)
            if rel.parts and rel.parts[0] != "generated":
                stray.append(str(rel))
        assert_true(not stray, f"stray files outside output dir: {stray}")

        report = {
            "status": "pass",
            "generated_dir": str(skill_dir),
            "checks": [
                "questionnaire fixture rendered successfully",
                "tmpl generated",
                "skill markdown generated",
                "all lifecycle stages preserved",
                "no ghost assets directory",
                "no stray files outside output directory"
            ]
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
