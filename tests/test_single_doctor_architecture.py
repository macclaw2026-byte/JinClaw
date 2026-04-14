import json
import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
if str(CONTROL_CENTER) not in sys.path:
    sys.path.insert(0, str(CONTROL_CENTER))

from governance_runtime import _build_doctor_coverage_bundle  # noqa: E402
from control_plane_builder import build_control_plane  # noqa: E402
from system_doctor import run_system_doctor  # noqa: E402


class SingleDoctorArchitectureTest(unittest.TestCase):
    def test_doctor_coverage_bundle_declares_single_doctor(self):
        bundle = _build_doctor_coverage_bundle()
        self.assertTrue(bundle['single_doctor_rule'])
        self.assertEqual(bundle['authoritative_doctor'], 'tools/openmoss/control_center/system_doctor.py')
        self.assertTrue(bundle['registered_integrations'])
        names = [item.get('name') for item in bundle['registered_integrations']]
        self.assertIn('acquisition-hand', names)
        self.assertIn('conversation-context-kernel', names)
        self.assertIn('reply-projection-kernel', names)

    def test_control_plane_exposes_doctor_coverage(self):
        plane = build_control_plane(stale_after_seconds=300, escalation_after_seconds=900)
        snapshot = plane['system_snapshot']
        self.assertIn('doctor_coverage', snapshot)
        self.assertTrue(snapshot['doctor_coverage']['single_doctor_rule'])
        self.assertGreaterEqual(snapshot['summary']['doctor_registered_integrations_total'], 1)

    def test_system_doctor_reports_integration_health(self):
        result = run_system_doctor(idle_after_seconds=300, escalation_after_seconds=900)
        integration = result.get('integration_health', {})
        self.assertTrue(integration.get('single_doctor_rule'))
        self.assertEqual(integration.get('authoritative_doctor'), 'tools/openmoss/control_center/system_doctor.py')
        self.assertEqual(integration.get('coding_chain'), 'ok')
        self.assertEqual(integration.get('noncoding_chain'), 'ok')
        self.assertTrue(str(integration.get('acquisition_chain', '')).strip())
        self.assertEqual(integration.get('conversation_context_chain'), 'ok')
        acquisition = integration.get('acquisition_hand', {}) or {}
        self.assertIn('ok', acquisition)
        self.assertIn('errors', acquisition)
        self.assertIn('objective_completion_contract', acquisition)
        self.assertTrue(acquisition.get('field_synthesis_contract'))
        self.assertTrue(acquisition.get('delivery_requirements_contract'))
        self.assertTrue(acquisition.get('source_trust_contract'))
        self.assertTrue(acquisition.get('release_governance_contract'))
        self.assertTrue(acquisition.get('release_disclosure_contract'))
        self.assertTrue(acquisition.get('answer_synthesis_contract'))
        self.assertTrue(acquisition.get('answer_response_contract'))
        self.assertTrue(acquisition.get('response_handoff_contract'))
        self.assertTrue(acquisition.get('execution_truth_contract'))
        self.assertTrue(acquisition.get('browser_execution_contract'))
        self.assertTrue(acquisition.get('validation_family_contract'))
        self.assertIsInstance(acquisition.get('objective_completion_contract'), bool)
        self.assertTrue((integration.get('conversation_context', {}) or {}).get('ok'))
        self.assertTrue((integration.get('conversation_context', {}) or {}).get('instruction_envelope_contract'))
        self.assertTrue((integration.get('conversation_context', {}) or {}).get('focus_contract'))
        self.assertTrue((integration.get('conversation_context', {}) or {}).get('followup_resolution_contract'))
        self.assertTrue((integration.get('conversation_context', {}) or {}).get('control_plane_visibility_contract'))
        self.assertEqual(integration.get('reply_projection_chain'), 'ok')
        self.assertTrue((integration.get('reply_projection', {}) or {}).get('ok'))
        self.assertTrue((integration.get('reply_projection', {}) or {}).get('projection_contract_presence'))
        self.assertTrue((integration.get('reply_projection', {}) or {}).get('projection_render_parity'))
        self.assertTrue((integration.get('reply_projection', {}) or {}).get('receipt_projection_persistence'))


if __name__ == '__main__':
    unittest.main()
