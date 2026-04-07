import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')


class NoGhostFilesTest(unittest.TestCase):
    def test_no_ghost_files_in_newly_added_paths(self):
        scan_roots = [
            ROOT / 'compat/gstack',
            ROOT / 'tests',
            ROOT / 'tools/bin',
            ROOT / 'skills',
        ]
        suspicious = []
        for root in scan_roots:
            if not root.exists():
                continue
            for path in root.rglob('*'):
                name = path.name
                if name.endswith('.tmp') or name.endswith('.bak') or name.endswith('.orig'):
                    suspicious.append(str(path))
        self.assertFalse(suspicious, f'Found suspicious leftover files in managed paths: {suspicious[:20]}')


if __name__ == '__main__':
    unittest.main()
