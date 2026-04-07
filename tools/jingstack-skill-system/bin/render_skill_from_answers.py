#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path

LIFECYCLE = ["think", "plan", "build", "review", "test", "ship", "reflect"]


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def bullets(items, indent="- "):
    if not items:
        return f"{indent}none specified"
    return "\n".join(f"{indent}{item}" for item in items)


def build_lifecycle_section(notes):
    note_text = bullets(notes) if notes else "- preserve the full lifecycle with light local adaptation only"
    sections = []
    for stage in LIFECYCLE:
        sections.append(
            f"### {stage}\n"
            f"- run the {stage} stage explicitly\n"
            f"- record outputs for {stage}\n"
            f"- do not silently skip {stage}\n"
        )
    return (
        "## Lifecycle\n\n"
        "Preserve the full lifecycle below as first-class workflow stages.\n\n"
        f"{note_text}\n\n" + "\n".join(sections)
    )


def render_skill_tmpl(data):
    slug = slugify(data.get("skill_slug") or data["display_name"])
    desc = data["description"].strip()
    when_to_use = data.get("when_to_use", [])
    triggers = data.get("triggers", [])
    jobs = data.get("jobs_to_be_done", [])
    inputs = data.get("inputs", [])
    outputs = data.get("outputs", [])
    constraints = data.get("constraints", [])
    scripts = data.get("resources", {}).get("scripts", [])
    references = data.get("resources", {}).get("references", [])
    assets = data.get("resources", {}).get("assets", [])
    checks = data.get("testing", {}).get("checks", [])
    evidence = data.get("testing", {}).get("evidence", [])
    host_notes = data.get("host_notes", [])
    preserve_lifecycle = data.get("workflow", {}).get("preserve_lifecycle", False)
    workflow_notes = data.get("workflow", {}).get("notes", [])

    parts = [
        "---",
        f"name: {slug}",
        "description: |",
        f"  {desc} Use when:",
    ]
    for item in when_to_use:
        parts.append(f"  - {item}")
    parts.extend([
        "---",
        "<!-- AUTO-GENERATED from questionnaire answers. Edit answers, then regenerate. -->",
        "",
        f"# {data['display_name']}",
        "",
        "## Trigger Phrases",
        bullets(triggers),
        "",
        "## Jobs To Be Done",
        bullets(jobs),
        "",
        "## Inputs",
        bullets(inputs),
        "",
        "## Outputs",
        bullets(outputs),
        "",
        "## Resource Plan",
        "### scripts",
        bullets(scripts),
        "",
        "### references",
        bullets(references),
        "",
        "### assets",
        bullets(assets),
        "",
        "## Constraints",
        bullets(constraints),
        "",
    ])
    if preserve_lifecycle:
        parts.extend([build_lifecycle_section(workflow_notes), ""])
    parts.extend([
        "## Testing",
        "### checks",
        bullets(checks),
        "",
        "### evidence",
        bullets(evidence),
        "",
        "## Host Notes",
        bullets(host_notes),
        "",
        "## Generation Notes",
        "- This tmpl was synthesized from questionnaire answers.",
        "- Regenerate from answers instead of hand-editing when possible.",
    ])
    return "\n".join(parts).strip() + "\n"


def render_skill_md(tmpl_text):
    return tmpl_text.replace("AUTO-GENERATED from questionnaire answers. Edit answers, then regenerate.", "AUTO-GENERATED from questionnaire answers via JingStack skill system.")


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("answers")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--emit-skill-md", action="store_true")
    args = parser.parse_args()

    answers_path = Path(args.answers)
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    data = json.loads(answers_path.read_text())
    slug = slugify(data.get("skill_slug") or data["display_name"])
    skill_dir = output_dir / slug
    ensure_dir(skill_dir)

    tmpl_path = skill_dir / "SKILL.md.tmpl"
    tmpl_text = render_skill_tmpl(data)
    tmpl_path.write_text(tmpl_text)

    for dirname in ["scripts", "references", "assets"]:
        configured = data.get("resources", {}).get(dirname, [])
        if configured:
            ensure_dir(skill_dir / dirname)

    if args.emit_skill_md:
        (skill_dir / "SKILL.md").write_text(render_skill_md(tmpl_text))

    print(json.dumps({
        "skill_slug": slug,
        "skill_dir": str(skill_dir),
        "tmpl_path": str(tmpl_path),
        "skill_md": str(skill_dir / 'SKILL.md') if args.emit_skill_md else None
    }, indent=2))


if __name__ == "__main__":
    main()
