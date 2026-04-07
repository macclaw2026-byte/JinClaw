import subprocess
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
DOCTOR = ROOT / 'tools/bin/jinclaw-gstack-integration-doctor'


class GstackIntegrationDoctorShimTest(unittest.TestCase):
    def test_integration_doctor_is_only_a_compat_shim(self):
        result = subprocess.run(['python3', str(DOCTOR)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stdout + '\n' + result.stderr)
        self.assertIn('COMPAT_SHIM_OK', result.stdout)
        self.assertIn('Delegated to canonical system doctor.', result.stdout)
        self.assertIn('single_doctor_rule', result.stdout)


if __name__ == '__main__':
    unittest.main()
