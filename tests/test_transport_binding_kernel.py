import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import shutil

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
CONTROL_CENTER = ROOT / 'tools/openmoss/control_center'
AUTONOMY = ROOT / 'tools/openmoss/autonomy'
for p in [str(CONTROL_CENTER), str(AUTONOMY)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import brain_enforcer  # noqa: E402
from conversation_context import conversation_focus_path, instruction_envelope_path  # noqa: E402
from conversation_events import conversation_event_path  # noqa: E402
from manager import link_path, task_dir  # noqa: E402
from paths import BRAIN_RECEIPTS_ROOT, BRAIN_ROUTES_ROOT  # noqa: E402
from telegram_binding import bind_telegram_message  # noqa: E402
from transport_binding import bind_transport_message  # noqa: E402


class TransportBindingKernelTest(unittest.TestCase):
    def setUp(self):
        self.provider = 'telegram'
        self.conversation_id = 'unit-transport-binding-telegram'
        self.focus_path = conversation_focus_path(self.provider, self.conversation_id)
        self.envelope_path = instruction_envelope_path(self.provider, self.conversation_id)
        self.event_path = conversation_event_path(self.provider, self.conversation_id)
        self.route_path = BRAIN_ROUTES_ROOT / self.provider / f'{self.conversation_id}.json'
        self.receipt_path = BRAIN_RECEIPTS_ROOT / self.provider / f'{self.conversation_id}.json'
        self.link_file = link_path(self.provider, self.conversation_id)
        self.task_ids = set()

    def tearDown(self):
        for path in [self.focus_path, self.envelope_path, self.event_path, self.route_path, self.receipt_path, self.link_file]:
            if path.exists():
                path.unlink()
        for parent in [self.event_path.parent, self.route_path.parent, self.receipt_path.parent]:
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
        for task_id in self.task_ids:
            d = task_dir(task_id)
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    def test_transport_binding_returns_route_and_receipt_for_telegram_style_ingress(self):
        result = bind_transport_message(
            provider='telegram',
            conversation_id=self.conversation_id,
            conversation_type='group',
            sender_id='user',
            sender_name='unit-user',
            message_id='msg-1',
            text='继续优化 telegram transport binding parity',
            source='telegram',
            session_key=f'agent:main:telegram:group:{self.conversation_id}',
            emit_receipt=True,
        )
        task_id = str(((result.get('brain_route', {}) or {}).get('task_id', '')).strip())
        if task_id:
            self.task_ids.add(task_id)
        self.assertTrue((result.get('brain_route', {}) or {}).get('route_path'))
        self.assertTrue((result.get('receipt', {}) or {}).get('text'))
        self.assertTrue(str(result.get('route_store', '')).strip())

    def test_telegram_binding_delegates_to_transport_binding_kernel(self):
        with patch('telegram_binding.bind_transport_message') as mocked:
            mocked.return_value = {'brain_route': {'task_id': 'demo-task'}, 'receipt': {'text': 'ok'}}
            result = bind_telegram_message(
                chat_id='unit-telegram-transport-binding',
                chat_type='group',
                sender_id='user',
                sender_name='unit-user',
                message_id='msg-1',
                text='继续',
            )
        self.assertEqual(result['brain_route']['task_id'], 'demo-task')
        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['provider'], 'telegram')
        self.assertEqual(kwargs['source'], 'telegram')
        self.assertTrue(kwargs['emit_receipt'])

    def test_brain_enforcer_route_resolution_uses_transport_binding_kernel(self):
        latest_user = {'message_id': 'msg-99', 'text': '继续优化 brain enforcer transport parity'}
        fake_binding = {
            'brain_route': {'task_id': 'demo-task', 'message_id': 'msg-99'},
            'route_store': '/tmp/demo-route.json',
        }
        with patch.object(brain_enforcer, '_load_json', return_value={}), patch.object(
            brain_enforcer, 'bind_transport_message', return_value=fake_binding
        ) as mocked:
            route, route_path, binding = brain_enforcer._resolve_route_for_message(latest_user)
        self.assertEqual(route['task_id'], 'demo-task')
        self.assertEqual(str(route_path), '/tmp/demo-route.json')
        self.assertEqual(binding, fake_binding)
        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs['provider'], 'openclaw-main')
        self.assertEqual(kwargs['source'], 'brain_enforcer')
        self.assertFalse(kwargs['emit_receipt'])


if __name__ == '__main__':
    unittest.main()
