import json
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

from manager import create_task_from_contract, load_state, save_state, task_dir, link_path  # noqa: E402
from task_contract import StageContract, TaskContract  # noqa: E402
from task_status_snapshot import build_task_status_snapshot  # noqa: E402


class DeliveryContractKernelTest(unittest.TestCase):
    def setUp(self):
        self.task_id = 'unit-delivery-contract-kernel'
        self.provider = 'telegram'
        self.conversation_id = 'unit-delivery-contract-kernel'
        task_path = task_dir(self.task_id)
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)
        self.link_file = link_path(self.provider, self.conversation_id)
        if self.link_file.exists():
            self.link_file.unlink()

    def tearDown(self):
        task_path = task_dir(self.task_id)
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)
        if self.link_file.exists():
            self.link_file.unlink()

    def test_snapshot_exposes_delivery_contract_with_attachment_preference(self):
        contract = TaskContract(
            task_id=self.task_id,
            user_goal='Deliver a verified CSV result back to Telegram.',
            done_definition='delivery contract visible in authoritative snapshot',
            stages=[
                StageContract(name='understand', goal='understand'),
                StageContract(name='plan', goal='plan'),
                StageContract(name='execute', goal='execute'),
                StageContract(name='verify', goal='verify'),
                StageContract(name='learn', goal='learn'),
            ],
        )
        create_task_from_contract(contract)
        state = load_state(self.task_id)
        state.status = 'completed'
        state.current_stage = 'learn'
        for name in state.stage_order:
            stage = state.stages.get(name)
            if stage:
                stage.status = 'completed'
                if name == 'verify':
                    stage.verification_status = 'passed'
        report_path = task_dir(self.task_id) / 'result.csv'
        report_path.write_text('id,value\n1,ok\n', encoding='utf-8')
        state.metadata['business_outcome'] = {
            'goal_satisfied': True,
            'user_visible_result_confirmed': True,
            'proof_summary': 'delivery kernel proof',
            'evidence': {'csv': str(report_path)},
        }
        state.metadata['delivery_artifacts'] = [str(report_path)]
        state.metadata['delivery_schedule'] = {'cadence': 'daily'}
        save_state(state)
        self.link_file.parent.mkdir(parents=True, exist_ok=True)
        self.link_file.write_text(
            json.dumps(
                {
                    'provider': self.provider,
                    'conversation_id': self.conversation_id,
                    'conversation_type': 'group',
                    'task_id': self.task_id,
                    'goal': contract.user_goal,
                    'last_goal': contract.user_goal,
                    'session_key': f'agent:main:telegram:group:{self.conversation_id}',
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding='utf-8',
        )
        snapshot = build_task_status_snapshot(self.task_id)
        delivery_contract = snapshot.get('delivery_contract', {}) or {}
        self.assertTrue(delivery_contract.get('enabled'))
        self.assertEqual(delivery_contract.get('channel'), 'telegram')
        self.assertEqual(delivery_contract.get('cadence'), 'daily')
        self.assertTrue(delivery_contract.get('prefer_attachment_delivery'))
        self.assertTrue(delivery_contract.get('attachment_paths'))
        self.assertEqual(snapshot.get('reply_contract', {}).get('delivery_contract', {}).get('delivery_mode'), delivery_contract.get('delivery_mode'))
        self.assertIn('Delivery contract is', snapshot.get('authoritative_summary', ''))


if __name__ == '__main__':
    unittest.main()
