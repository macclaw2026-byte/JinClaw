import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
AUTONOMY = ROOT / 'tools/openmoss/autonomy'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))
if str(AUTONOMY) not in sys.path:
    sys.path.insert(0, str(AUTONOMY))

import control_plane_builder  # noqa: E402
import brain_router  # noqa: E402
import manager  # noqa: E402
import mission_supervisor  # noqa: E402
import progress_evidence  # noqa: E402
import task_status_snapshot  # noqa: E402
import task_retention_runtime  # noqa: E402


class ControlPlaneRuntimeOptimizationsTest(unittest.TestCase):
    def test_create_task_payload_is_silent_library_helper(self):
        args = manager.argparse.Namespace(
            task_id='demo-task',
            goal='修复 doctor stdout 噪音',
            done_definition='done',
            stage=[],
            stage_json='[]',
            hard_constraint=[],
            soft_preference=[],
            allowed_tool=[],
            forbidden_action=[],
            metadata_json='{}',
        )
        with patch.object(manager, 'create_task_from_contract', return_value={'ok': True}) as mocked_create, patch(
            'builtins.print', side_effect=AssertionError('library helper should stay silent')
        ):
            result = manager.create_task_payload(args)

        self.assertEqual(result, {'ok': True})
        mocked_create.assert_called_once()

    def test_candidate_for_member_uses_state_timestamps_before_heavy_progress_probe(self):
        state = {
            'status': 'completed',
            'last_progress_at': '2026-04-01T00:00:00+00:00',
        }
        with patch.object(task_retention_runtime, 'build_progress_evidence', side_effect=AssertionError('progress evidence should not be required')):
            result = task_retention_runtime._candidate_for_member(
                'task-1',
                state,
                {},
                terminal_idle_seconds=60,
                zombie_idle_seconds=120,
            )
        self.assertTrue(result['archivable'])
        self.assertEqual(result['classification'], 'terminal')

    def test_build_task_registry_reuses_progress_evidence_for_shared_canonical_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_root = Path(temp_dir)
            (tasks_root / 'task-a').mkdir()
            (tasks_root / 'task-b').mkdir()

            evidence_payload = {
                'progress_state': 'healthy',
                'needs_intervention': False,
                'idle_seconds': 0,
                'run_liveness': {},
                'goal_conformance': {},
            }

            def fake_state(_task_id: str):
                return {
                    'status': 'planning',
                    'current_stage': 'plan',
                    'next_action': 'continue',
                    'metadata': {},
                }

            def fake_contract(task_id: str):
                return {'user_goal': f'goal:{task_id}'}

            def fake_canonical(_task_id: str):
                return {'canonical_task_id': 'shared-root', 'lineage_root_task_id': 'shared-root'}

            with patch.object(control_plane_builder, 'AUTONOMY_TASKS_ROOT', tasks_root), patch.object(
                control_plane_builder, '_load_task_state', side_effect=fake_state
            ), patch.object(
                control_plane_builder, '_load_task_contract', side_effect=fake_contract
            ), patch.object(
                control_plane_builder, 'resolve_canonical_active_task', side_effect=fake_canonical
            ), patch.object(
                control_plane_builder, 'build_progress_evidence', return_value=evidence_payload
            ) as mocked_evidence, patch.object(
                control_plane_builder, '_conversation_links_for_task', return_value=[]
            ), patch.object(
                control_plane_builder, '_write_json', return_value='ignored'
            ):
                registry = control_plane_builder.build_task_registry(stale_after_seconds=300, escalation_after_seconds=900)

        self.assertEqual(len((registry.get('task_registry', {}) or {}).get('items', [])), 2)
        self.assertEqual(mocked_evidence.call_count, 1)

    def test_conversation_links_for_task_uses_supplied_index_without_rescanning_files(self):
        link_index = {
            'shared-root': [
                {'path': '/tmp/a.json', 'provider': 'openclaw-main'},
                {'path': '/tmp/b.json', 'provider': 'telegram'},
            ],
            'task-a': [
                {'path': '/tmp/b.json', 'provider': 'telegram'},
                {'path': '/tmp/c.json', 'provider': 'openclaw-main'},
            ],
        }
        with patch.object(control_plane_builder, '_read_json', side_effect=AssertionError('link index should already be supplied')):
            links = control_plane_builder._conversation_links_for_task(
                'task-a',
                'shared-root',
                link_index=link_index,
            )

        self.assertEqual([item['path'] for item in links], ['/tmp/a.json', '/tmp/b.json', '/tmp/c.json'])

    def test_progress_evidence_conversation_link_cache_reuses_scanned_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            tasks_root = temp_root / 'tasks'
            links_root = temp_root / 'links'
            task_dir = tasks_root / 'task-a'
            task_dir.mkdir(parents=True)
            links_root.mkdir(parents=True)
            (task_dir / 'contract.json').write_text('{"metadata": {}}', encoding='utf-8')
            (links_root / 'link-a.json').write_text(
                '{"provider":"openclaw-main","conversation_id":"conv-1","task_id":"task-a"}',
                encoding='utf-8',
            )
            progress_evidence._CONVERSATION_LINK_INDEX_CACHE['root_mtime_ns'] = None
            progress_evidence._CONVERSATION_LINK_INDEX_CACHE['index'] = {}
            with patch.object(progress_evidence, 'AUTONOMY_TASKS_ROOT', tasks_root), patch.object(
                progress_evidence, 'LINKS_ROOT', links_root
            ), patch.object(
                progress_evidence, '_read_json', wraps=progress_evidence._read_json
            ) as mocked_read_json:
                first = progress_evidence._conversation_links_for_task('task-a')
                second = progress_evidence._conversation_links_for_task('task-a')

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(mocked_read_json.call_count, 3)

    def test_brain_router_build_task_uses_silent_create_helper(self):
        package = {
            'done_definition': 'done',
            'stages': [],
            'hard_constraints': [],
            'allowed_tools': [],
            'metadata': {},
        }
        with patch.object(brain_router, 'build_control_center_package', return_value=package), patch.object(
            brain_router, 'create_task_payload', return_value={'ok': True}
        ) as mocked_create, patch(
            'builtins.print', side_effect=AssertionError('brain router should not print task payloads')
        ):
            result = brain_router._build_task('demo-task', '继续优化 transport binding kernel', 'system_doctor:test')

        self.assertEqual(result, package)
        mocked_create.assert_called_once()

    def test_run_mission_supervisor_reuses_supplied_control_plane(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_root = Path(temp_dir)
            (tasks_root / 'task-a').mkdir()
            supplied_control_plane = {
                'crawler_capability_profile': {'feedback': {'status': 'ok'}},
                'crawler_remediation_queue': {'items': []},
                'crawler_remediation_plan': {'items': []},
                'project_repair_value': {'status': 'steady'},
                'project_repair_recommendations': [{'action': 'keep-going'}],
                'system_snapshot': {
                    'summary': {
                        'blocked_total': 1,
                        'blocked_project_crawler_remediation_total': 0,
                        'blocked_approval_or_contract_total': 1,
                    }
                },
            }

            with patch.object(mission_supervisor, 'TASKS_ROOT', tasks_root), patch.object(
                mission_supervisor, 'supervise_task', return_value={'evidence': {'progress_state': 'healthy'}, 'repair': {'repaired': False}}
            ), patch.object(
                mission_supervisor, 'build_control_plane', side_effect=AssertionError('build_control_plane should be reused')
            ), patch.object(
                mission_supervisor, '_write_json', return_value=None
            ):
                result = mission_supervisor.run_mission_supervisor(
                    stale_after_seconds=300,
                    escalation_after_seconds=900,
                    control_plane=supplied_control_plane,
                )

        self.assertEqual(result['crawler_feedback']['status'], 'ok')
        self.assertEqual(result['blocked_summary']['approval_or_contract'], 1)
        self.assertEqual(len(result['reports']), 1)

    def test_goal_conformance_signal_reuses_latest_session_lookup_for_shared_session(self):
        links = [
            {
                'conversation_type': 'direct',
                'provider': 'openclaw-main',
                'conversation_id': f'conv-{idx}',
                'session_key': 'agent:main:main',
                'last_goal': '继续优化 transport binding kernel',
            }
            for idx in range(4)
        ]
        with patch.object(progress_evidence, '_conversation_links_for_task', return_value=links), patch.object(
            progress_evidence, 'analyze_intent', return_value={}
        ), patch.object(
            progress_evidence, '_looks_actionable', return_value=False
        ), patch.object(
            progress_evidence, '_latest_external_user_message', return_value={'text': '然后呢？'}
        ) as mocked_latest:
            result = progress_evidence._goal_conformance_signal(
                'transport-binding-kernel-followup',
                {'user_goal': '继续优化 transport binding kernel'},
            )

        self.assertTrue(result['ok'])
        self.assertEqual(mocked_latest.call_count, 1)

    def test_goal_conformance_analysis_text_prefers_explicit_goal_line(self):
        text = '\n'.join(
            [
                'System preamble',
                'Follow the full lifecycle',
                'Goal: 修复 transport binding kernel 的 doctor 卡顿',
                'Verification guidance: keep evidence',
                'x' * 3000,
            ]
        )
        compact = progress_evidence._goal_conformance_analysis_text(text)
        self.assertIn('Goal: 修复 transport binding kernel 的 doctor 卡顿', compact)
        self.assertLessEqual(len(compact), 1200)

    def test_session_file_for_key_uses_supplied_registry_without_reloading_index(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session_file = Path(temp_dir) / 'session.jsonl'
            session_file.write_text('', encoding='utf-8')
            registry = {
                'agent:main:main': {
                    'sessionFile': str(session_file),
                }
            }
            with patch.object(progress_evidence, '_read_json', side_effect=AssertionError('session index should already be supplied')):
                resolved = progress_evidence._session_file_for_key('agent:main:main', session_registry=registry)

        self.assertEqual(resolved, session_file)


if __name__ == '__main__':
    unittest.main()
