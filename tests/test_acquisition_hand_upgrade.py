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
from challenge_classifier import classify_challenge  # noqa: E402
from coding_session_adapter import build_coding_session_payload  # noqa: E402
from context_builder import build_stage_context  # noqa: E402
from orchestrator import build_control_center_package  # noqa: E402
from paths import APPROVALS_ROOT, CHALLENGES_ROOT, FETCH_ROUTES_ROOT, MISSIONS_ROOT  # noqa: E402


class AcquisitionHandUpgradeTest(unittest.TestCase):
    def tearDown(self):
        task_ids = [
            'test-acq-hand',
            'test-acq-context',
            'test-acq-challenge',
        ]
        for task_id in task_ids:
            for root in [MISSIONS_ROOT, APPROVALS_ROOT, FETCH_ROUTES_ROOT, CHALLENGES_ROOT]:
                path = root / f'{task_id}.json'
                if path.exists():
                    path.unlink()
        cache_dir = ROOT / 'tools/openmoss/runtime/control_center/cache/stage_context'
        if cache_dir.exists():
            shutil.rmtree(cache_dir)

    def _external_intent(self):
        return {
            'task_types': ['web', 'data', 'marketplace'],
            'requires_external_information': True,
            'likely_platforms': ['amazon', 'walmart'],
            'domains': ['amazon.com', 'walmart.com'],
            'needs_browser': False,
        }

    def _build_contract(self, task_id: str, goal: str):
        package = build_control_center_package(
            task_id,
            goal,
            source='unit-test',
            inherited_intent=self._external_intent(),
        )
        return package, {
            'user_goal': package['goal'],
            'done_definition': package['done_definition'],
            'allowed_tools': package['allowed_tools'],
            'stages': package['stages'],
            'metadata': package['metadata'],
        }

    def test_external_task_builds_unified_acquisition_hand(self):
        package, _ = self._build_contract(
            'test-acq-hand',
            'Collect current Amazon and Walmart pricing data, compare public offers, and return structured evidence with sources',
        )
        cc = package['metadata']['control_center']
        hand = cc['acquisition_hand']
        self.assertTrue(hand['enabled'])
        self.assertTrue(hand['adapter_registry']['available_adapter_ids'])
        self.assertTrue(hand['route_candidates'])
        self.assertTrue(hand['execution_strategy']['primary_route_id'])
        self.assertIn('route_id', hand['result_consensus']['required_provenance_fields'])
        self.assertIn('source_url', hand['result_consensus']['required_provenance_fields'])
        self.assertTrue(hand['compatibility']['crawler_enabled'])
        self.assertTrue(set(hand['recommended_tools']).issubset(set(package['allowed_tools'])))

    def test_challenge_classifier_emits_structured_signals(self):
        payload = classify_challenge(
            'test-acq-challenge',
            ['403 Forbidden', 'Verify you are human'],
            {'status': 'running', 'current_stage': 'execute'},
        )
        self.assertEqual(payload['severity'], 'high')
        self.assertTrue(payload['requires_human_checkpoint'])
        self.assertTrue(payload['signals'])
        self.assertEqual(payload['signals'][0]['category'], 'anti_bot')
        self.assertIn('human_checkpoint', payload['safe_next_routes'])

    def test_stage_context_and_dispatch_include_acquisition_hand(self):
        package, contract = self._build_contract(
            'test-acq-context',
            'Collect current Amazon pricing evidence and compare multiple public routes before deciding the best answer',
        )
        state = {
            'current_stage': 'execute',
            'status': 'running',
            'next_action': 'start_stage:execute',
            'blockers': [],
            'stages': {'execute': {'attempts': 1, 'completed_subtasks': []}},
            'metadata': {},
        }
        context = build_stage_context('test-acq-context', 'execute', contract, state)
        payload = build_coding_session_payload(contract, context)
        request = build_acp_dispatch_request(contract, context)
        self.assertTrue(context['acquisition_hand']['enabled'])
        self.assertIn('Acquisition hand:', payload['base_prompt'])
        self.assertNotEqual(request['env']['JINCLAW_ACQUISITION_MODE'], 'disabled')
        self.assertTrue(request['metadata']['acquisition_enabled'])
        self.assertTrue(request['metadata']['acquisition_primary_route'])


if __name__ == '__main__':
    unittest.main()
