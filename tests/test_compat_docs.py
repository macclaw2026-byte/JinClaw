import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')


class CompatDocsTest(unittest.TestCase):
    def test_gstack_compat_docs_exist_and_include_full_lifecycle(self):
        p = ROOT / 'compat/gstack/prompts/jinclaw-gstack-lite.md'
        self.assertTrue(p.exists())
        text = p.read_text()
        for stage in ['think', 'plan', 'build', 'review', 'test', 'ship', 'reflect']:
            self.assertIn(stage, text)

    def test_routing_policy_exists(self):
        p = ROOT / 'compat/gstack/routing-policy.md'
        self.assertTrue(p.exists())
        text = p.read_text()
        self.assertIn('JinClaw owns task routing', text)
        self.assertIn('Forbidden through compat', text)


if __name__ == '__main__':
    unittest.main()
