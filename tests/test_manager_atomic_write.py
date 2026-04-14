import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
AUTONOMY = ROOT / 'tools/openmoss/autonomy'
if str(AUTONOMY) not in sys.path:
    sys.path.insert(0, str(AUTONOMY))

import manager  # noqa: E402


class ManagerAtomicWriteTest(unittest.TestCase):
    def test_write_json_uses_unique_temp_files_under_concurrency(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / 'state.json'
            payloads = [{'version': 1}, {'version': 2}]
            barrier = threading.Barrier(2)
            opened_paths = []
            original_dump = manager.json.dump

            def blocking_dump(payload, fh, *args, **kwargs):
                opened_paths.append(Path(fh.name).name)
                barrier.wait(timeout=2)
                return original_dump(payload, fh, *args, **kwargs)

            errors = []

            def worker(payload):
                try:
                    manager.write_json(target, payload)
                except Exception as exc:  # pragma: no cover - failure path asserted below
                    errors.append(exc)

            with patch.object(manager.json, 'dump', side_effect=blocking_dump):
                threads = [threading.Thread(target=worker, args=(payload,)) for payload in payloads]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

            self.assertEqual(errors, [])
            self.assertEqual(len(opened_paths), 2)
            self.assertEqual(len(set(opened_paths)), 2)
            self.assertTrue(target.exists())
            persisted = json.loads(target.read_text(encoding='utf-8'))
            self.assertIn(persisted['version'], {1, 2})
            self.assertEqual(list(target.parent.glob('state.json*.tmp')), [])

    def test_load_state_backfills_missing_task_id_from_requested_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            task_id = 'missing-state-id'
            task_root = root / task_id
            task_root.mkdir(parents=True, exist_ok=True)
            state_file = task_root / 'state.json'
            state_file.write_text(json.dumps({'status': 'running', 'current_stage': 'execute'}, ensure_ascii=False), encoding='utf-8')

            with patch.object(manager, 'TASKS_ROOT', root):
                state = manager.load_state(task_id)

            self.assertEqual(state.task_id, task_id)
            self.assertEqual(state.status, 'running')
            self.assertEqual(state.current_stage, 'execute')


if __name__ == '__main__':
    unittest.main()
