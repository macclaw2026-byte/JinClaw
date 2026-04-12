#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_FILES = [
    WORKSPACE_ROOT / 'JINCLAW_CONSTITUTION.md',
    WORKSPACE_ROOT / 'AI_OPTIMIZATION_FRAMEWORK.md',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/README.md',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/system_doctor.py',
    WORKSPACE_ROOT / 'tools/openmoss/ops/jinclaw_ops.py',
    WORKSPACE_ROOT / 'tools/openmoss/control_center/doctor_coverage_contract.md',
    WORKSPACE_ROOT / '.github/pull_request_template.md',
]

REQUIRED_SNIPPETS = {
    WORKSPACE_ROOT / 'JINCLAW_CONSTITUTION.md': [
        'exactly one canonical system doctor exists',
        '## Single-doctor architecture rule',
    ],
    WORKSPACE_ROOT / 'AI_OPTIMIZATION_FRAMEWORK.md': [
        '## Mandatory Reading Order',
        '## Required Workflow Before Modifying Core Files',
    ],
    WORKSPACE_ROOT / 'tools/openmoss/control_center/README.md': [
        '## Single-doctor invariant',
        'future-coverage contract',
    ],
    WORKSPACE_ROOT / 'tools/openmoss/control_center/system_doctor.py': [
        'Single-doctor architecture rule:',
        'canonical whole-system doctor',
    ],
    WORKSPACE_ROOT / 'tools/openmoss/ops/jinclaw_ops.py': [
        'Single-doctor rule:',
        'one canonical doctor payload path',
    ],
    WORKSPACE_ROOT / 'tools/openmoss/control_center/doctor_coverage_contract.md': [
        'JinClaw has one doctor and only one doctor',
        '## Coverage rule for all future changes',
    ],
    WORKSPACE_ROOT / '.github/pull_request_template.md': [
        '## Doctor Coverage',
        'Retrofit owner:',
    ],
}


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED_FILES:
        if not path.exists():
            errors.append(f'missing_required_file:{path.relative_to(WORKSPACE_ROOT)}')
            continue
        text = path.read_text(encoding='utf-8')
        for snippet in REQUIRED_SNIPPETS.get(path, []):
            if snippet not in text:
                errors.append(f'missing_snippet:{path.relative_to(WORKSPACE_ROOT)}::{snippet}')
    if errors:
        print('doctor_contract_check:FAIL')
        for err in errors:
            print(err)
        return 1
    print('doctor_contract_check:OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
