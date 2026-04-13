import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
AUTONOMY = ROOT / 'tools/openmoss/autonomy'
for p in [str(CONTROL_CENTER), str(AUTONOMY)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from acp_dispatch_builder import build_acp_dispatch_request  # noqa: E402
from coding_session_adapter import build_coding_session_payload  # noqa: E402
from context_builder import build_stage_context  # noqa: E402
from orchestrator import build_control_center_package  # noqa: E402
from paths import APPROVALS_ROOT, FETCH_ROUTES_ROOT, MISSIONS_ROOT  # noqa: E402
from solution_arbitrator import arbitrate_solution_path  # noqa: E402


class OrchestratorGovernanceUpgradeTest(unittest.TestCase):
    def tearDown(self):
        task_ids = [
            'test-governance-lite',
            'test-governance-reviewed',
            'test-governance-plan-only',
            'test-governance-mission',
            'test-governance-context',
        ]
        for task_id in task_ids:
            for root in [MISSIONS_ROOT, APPROVALS_ROOT, FETCH_ROUTES_ROOT]:
                path = root / f'{task_id}.json'
                if path.exists():
                    path.unlink()
            cache_dir = ROOT / 'tools/openmoss/runtime/control_center/cache/stage_context'
            if cache_dir.exists():
                shutil.rmtree(cache_dir)

    def _build_contract(self, task_id: str, goal: str):
        package = build_control_center_package(task_id, goal, source='unit-test')
        return package, {
            'user_goal': package['goal'],
            'done_definition': package['done_definition'],
            'allowed_tools': package['allowed_tools'],
            'stages': package['stages'],
            'metadata': package['metadata'],
        }

    def test_lite_task_receives_lite_governance(self):
        package, _ = self._build_contract('test-governance-lite', 'Fix a README typo in the local docs')
        cc = package['metadata']['control_center']
        self.assertEqual(cc['governance']['tier'], 'lite')
        self.assertEqual(cc['protocol_pack']['pack_id'], 'orchestrator-lite')
        self.assertEqual(cc['plan_reviews']['active_reviewers'], ['engineering_review', 'security_review'])
        self.assertEqual([stage['name'] for stage in package['stages']], ['understand', 'plan', 'execute', 'verify', 'learn'])

    def test_reviewed_task_generates_full_role_review_bundle(self):
        package, _ = self._build_contract(
            'test-governance-reviewed',
            'Review and improve the runtime verifier architecture with implementation notes and test strategy',
        )
        cc = package['metadata']['control_center']
        self.assertEqual(cc['governance']['tier'], 'reviewed')
        self.assertEqual(cc['protocol_pack']['pack_id'], 'orchestrator-full')
        self.assertEqual(
            cc['plan_reviews']['active_reviewers'],
            ['product_review', 'engineering_review', 'design_review', 'security_review', 'devex_review'],
        )
        self.assertIn('engineering_review', cc['plan_reviews']['reviews'])
        self.assertIn('devex_review', cc['plan_reviews']['reviews'])
        self.assertTrue(cc['readiness_dashboard']['blocking_items'])

    def test_plan_only_task_skips_execute_stage(self):
        package, _ = self._build_contract(
            'test-governance-plan-only',
            '先给我出一个完整实施方案，不要实施，不要写代码，只做规划和评审包',
        )
        cc = package['metadata']['control_center']
        self.assertEqual(cc['governance']['tier'], 'plan_only')
        self.assertEqual(cc['protocol_pack']['pack_id'], 'orchestrator-plan-only')
        self.assertFalse(cc['governance']['policy']['allow_execute_stage'])
        self.assertEqual([stage['name'] for stage in package['stages']], ['understand', 'plan', 'verify', 'learn'])
        self.assertFalse(cc['readiness_dashboard']['execute_readiness']['applicable'])
        self.assertIn('no implementation executed', package['done_definition'])

    def test_mission_task_has_verification_guidance_and_readiness(self):
        package, _ = self._build_contract(
            'test-governance-mission',
            'Build a complete marketplace operations dashboard with backend, frontend, tests, and deployment handoff',
        )
        cc = package['metadata']['control_center']
        self.assertEqual(cc['governance']['tier'], 'mission')
        execute_stage = next(stage for stage in package['stages'] if stage['name'] == 'execute')
        verify_stage = next(stage for stage in package['stages'] if stage['name'] == 'verify')
        self.assertIn('failure_modes', execute_stage['verification_guidance'])
        self.assertIn('recommended_next_actions', execute_stage['verification_guidance'])
        self.assertIn('failure_modes', verify_stage['verification_guidance'])
        self.assertTrue(cc['readiness_dashboard']['blocking_items'])
        self.assertTrue(cc['complex_task_controller']['enabled'])

    def test_stage_context_and_dispatch_request_expose_governance_bundle(self):
        package, contract = self._build_contract(
            'test-governance-context',
            'Implement a medium-sized verifier refactor with tests and review notes',
        )
        state = {
            'current_stage': 'execute',
            'status': 'running',
            'next_action': 'start_stage:execute',
            'blockers': [],
            'stages': {'execute': {'attempts': 1, 'completed_subtasks': []}},
            'metadata': {},
        }
        context = build_stage_context('test-governance-context', 'execute', contract, state)
        payload = build_coding_session_payload(contract, context)
        request = build_acp_dispatch_request(contract, context)
        self.assertEqual((context.get('governance_contract', {}) or {}).get('tier'), package['metadata']['control_center']['governance']['tier'])
        self.assertEqual((context.get('protocol_pack', {}) or {}).get('pack_id'), package['metadata']['control_center']['protocol_pack']['pack_id'])
        self.assertTrue(context.get('verification_guidance'))
        self.assertIn('Governance tier:', payload['base_prompt'])
        self.assertIn('Protocol pack:', payload['base_prompt'])
        self.assertEqual(request['env']['JINCLAW_GOVERNANCE_TIER'], package['metadata']['control_center']['governance']['tier'])
        self.assertEqual(request['metadata']['protocol_pack_id'], package['metadata']['control_center']['protocol_pack']['pack_id'])

    def test_arbitration_requires_user_confirmation_when_direction_changes(self):
        arbitration = arbitrate_solution_path(
            {'goal': 'Switch to a new plan', 'task_types': ['code']},
            {'plan_id': 'audited_external_extension', 'external_actions': [{'type': 'dependency_install'}]},
            {'pending': [], 'pending_direction_confirmations': []},
            {},
            knowledge_basis={'recommended_basis': 'layer1+layer2+layer3', 'known_uncertainties': ['external package still unverified']},
            plan_reviews={
                'must_fix_before_execute': ['record external dependency rationale'],
                'pending_direction_confirmations': [
                    {
                        'reviewer': 'security_review',
                        'recommendation': ['外部扩展路径改变了原始方向，需要用户确认。'],
                        'why': '外部执行边界发生了变化。',
                    }
                ],
            },
            governance={'tier': 'reviewed'},
        )
        self.assertTrue(arbitration['requires_user_confirmation'])
        self.assertTrue(arbitration['direction_change_recommendation'])
        self.assertIn('pause_direction_changes_until_user_confirms_recommendation', arbitration['next_best_actions'])
        self.assertEqual(arbitration['must_fix_before_execute'], ['record external dependency rationale'])


if __name__ == '__main__':
    unittest.main()
