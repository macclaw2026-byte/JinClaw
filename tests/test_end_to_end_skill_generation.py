import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
FACTORY = ROOT / 'tools/bin/jinclaw-skill-factory'
DOCTOR = ROOT / 'tools/bin/jinclaw-skill-doctor'
SKILL_NAME = 'end-to-end-generated-skill'
ANSWERS = ROOT / 'tests/.tmp-end-to-end-answers.json'


class EndToEndSkillGenerationTest(unittest.TestCase):
    def setUp(self):
        self.skill_dir = ROOT / 'skills' / SKILL_NAME
        if self.skill_dir.exists():
            shutil.rmtree(self.skill_dir)
        if ANSWERS.exists():
            ANSWERS.unlink()

    def tearDown(self):
        if self.skill_dir.exists():
            shutil.rmtree(self.skill_dir)
        if ANSWERS.exists():
            ANSWERS.unlink()

    def test_end_to_end_generation_flow(self):
        payload = {
            'skill_name': SKILL_NAME,
            'description': 'End-to-end generated skill for validating questionnaire-to-template flow. Use when validating generated skill pipelines.',
            'goal': 'Prove JinClaw can create a skill from structured answers automatically.',
            'triggers': 'Use when a new skill should be generated from a questionnaire.',
            'inputs': 'Questionnaire answers and optional resource lists.',
            'outputs': 'Renderable skill template, skill markdown, and scaffold resources.',
            'workflow': 'think, plan, build scaffold, review generated files, test doctor compatibility, ship scaffold, reflect on gaps.',
            'guardrails': 'Preserve full lifecycle and avoid touching unrelated workspace files.',
            'references_needed': 'operator-notes,examples',
            'scripts_needed': 'validate-skill',
            'assets_needed': 'sample.txt'
        }
        ANSWERS.write_text(json.dumps(payload))

        subprocess.run(['python3', str(FACTORY), '--answers', str(ANSWERS)], check=True)
        subprocess.run(['python3', str(DOCTOR)], check=True)

        self.assertTrue((self.skill_dir / 'SKILL.md').exists())
        self.assertTrue((self.skill_dir / 'SKILL.md.tmpl').exists())
        self.assertTrue((self.skill_dir / 'references/operator-notes.md').exists())
        self.assertTrue((self.skill_dir / 'references/examples.md').exists())
        self.assertTrue((self.skill_dir / 'scripts/validate-skill').exists())
        self.assertTrue((self.skill_dir / 'assets/sample.txt').exists())

        text = (self.skill_dir / 'SKILL.md').read_text()
        self.assertIn('## Completion Contract', text)
        self.assertIn('1. think', text)
        self.assertIn('7. reflect', text)


if __name__ == '__main__':
    unittest.main()
