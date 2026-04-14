import sys
import unittest
from pathlib import Path

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
TOOLS_ROOT = ROOT / 'tools'
for entry in (ROOT, TOOLS_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import site_tool_matrix_v2 as matrix_v2  # noqa: E402


class SiteToolMatrixV2Test(unittest.TestCase):
    def test_analyze_walmart_promotes_required_fields_result_despite_search_result_token(self):
        stdout = """
        <!DOCTYPE html><html><head><title>wireless mouse - Walmart.com</title></head><body>
        search_result
        https://www.walmart.com/sp/track?bt=1&amp;rd=https%3A%2F%2Fwww.walmart.com%2Fip%2FLogitech-Advanced-Combo-Wireless-Keyboard-and-Mouse-Black%2F1998877576%3FadsRedirect%3Dtrue
        wasPrice="$47.67"
        Add to cart
        out of 5 Stars
        </body></html>
        """
        result = matrix_v2.analyze(
            'walmart',
            'direct-http-html',
            'https://www.walmart.com/search?q=wireless+mouse',
            stdout,
            '',
            0,
            'unit-test',
        )

        self.assertEqual(result.status, 'usable')
        self.assertTrue(result.required_fields_met)
        self.assertEqual(result.task_ready_fields['price'], '$47.67')
        self.assertEqual(
            result.task_ready_fields['link'],
            'https://www.walmart.com/ip/Logitech-Advanced-Combo-Wireless-Keyboard-and-Mouse-Black/1998877576?adsRedirect=true',
        )


if __name__ == '__main__':
    unittest.main()
