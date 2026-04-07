import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
FACTORY = ROOT / 'tools/bin/jinclaw-skill-factory'
DOCTOR = ROOT / 'tools/bin/jinclaw-skill-doctor'
SKILLS = ROOT / 'skills'
TMP_ANSWERS = ROOT / 'tests/.tmp-skill-answers.json'
SKILL_NAME = 'sample-generated-skill'


class SkillFactoryTest(unittest.TestCase):
    def cleanup(self):
        skill_dir = SKILLS / SKILL_NAME
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        if TMP_ANSWERS.exists():
            TMP_ANSWERS.unlink()

    def setUp(self):
        self.cleanup()

    def tearDown(self):
        self.cleanup()

    def test_skill_factory_generate_and_doctor(self):
        answers = {
            'skill_name': SKILL_NAME,
            'description': 'Generate a sample skill for testing. Use when validating the skill factory.',
            'goal': 'Produce a valid skill scaffold.',
            'triggers': 'Use when testing skill generation or validating generated scaffolds.',
            'inputs': 'Structured questionnaire answers.',
            'outputs': 'A skill folder with SKILL.md.tmpl and SKILL.md.',
            'workflow': 'Create scaffold, write template, render skill, create helper placeholders.',
            'guardrails': 'Do not overwrite unrelated files. Keep lifecycle intact.',
            'references_needed': 'usage-notes',
            'scripts_needed': 'run-check',
            'assets_needed': 'placeholder.txt'
        }
        TMP_ANSWERS.write_text(json.dumps(answers))
        subprocess.run(['python3', str(FACTORY), '--answers', str(TMP_ANSWERS)], check=True)

        skill_dir = SKILLS / SKILL_NAME
        self.assertTrue(skill_dir.exists())
        self.assertTrue((skill_dir / 'SKILL.md').exists())
        self.assertTrue((skill_dir / 'SKILL.md.tmpl').exists())
        self.assertTrue((skill_dir / 'references/usage-notes.md').exists())
        self.assertTrue((skill_dir / 'scripts/run-check').exists())
        self.assertTrue((skill_dir / 'assets/placeholder.txt').exists())

        text = (skill_dir / 'SKILL.md').read_text()
        self.assertIn('## Execution Lifecycle', text)
        self.assertIn('1. think', text)
        self.assertIn('7. reflect', text)

        subprocess.run(['python3', str(DOCTOR)], check=True)


if __name__ == '__main__':
    unittest.main()
