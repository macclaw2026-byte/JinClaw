import json
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
SKILLS = ROOT / 'skills'


class ManifestConsistencyTest(unittest.TestCase):
    def test_skill_manifests_if_present_are_consistent(self):
        if not SKILLS.exists():
            return
        for skill_dir in SKILLS.iterdir():
            if not skill_dir.is_dir():
                continue
            manifest = skill_dir / 'skill-factory-manifest.json'
            if not manifest.exists():
                continue
            data = json.loads(manifest.read_text())
            self.assertEqual(data['skill_name'], skill_dir.name)
            for required in ['SKILL.md', 'SKILL.md.tmpl']:
                self.assertTrue((skill_dir / required).exists())


if __name__ == '__main__':
    unittest.main()
