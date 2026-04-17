import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path('/Users/mac_claw/.openclaw/workspace')
UPSTREAM_WATCH = ROOT / 'tools/openmoss/upstream_watch'
if str(UPSTREAM_WATCH) not in sys.path:
    sys.path.insert(0, str(UPSTREAM_WATCH))

import watch_updates  # noqa: E402


class UpstreamWatchRateLimitFallbackTest(unittest.TestCase):
    def _source(self):
        return {
            'id': 'playwright',
            'name': 'Playwright',
            'repo': 'microsoft/playwright',
            'category': 'runtime-dependency',
            'priority': 'high',
            'adoption_policy': 'selectively_absorb',
            'why_it_matters': 'browser runtime capability',
        }

    def _previous_snapshot(self):
        return {
            'id': 'playwright',
            'name': 'Playwright',
            'repo': 'microsoft/playwright',
            'category': 'runtime-dependency',
            'priority': 'high',
            'adoption_policy': 'selectively_absorb',
            'why_it_matters': 'browser runtime capability',
            'fetched_at': '2026-04-13T17:00:00+00:00',
            'default_branch': 'main',
            'pushed_at': '2026-04-13T16:45:00Z',
            'updated_at': '2026-04-13T16:45:00Z',
            'stargazers_count': 123,
            'open_issues_count': 4,
            'latest_release': {'tag_name': 'v1.59.1'},
            'recent_tags': [{'name': 'v1.59.1', 'sha': 'abc123'}],
            'html_url': 'https://github.com/microsoft/playwright',
        }

    def _rate_limit_error(self):
        return urllib.error.HTTPError(
            'https://api.github.com/repos/microsoft/playwright',
            403,
            'rate limit exceeded',
            {'X-RateLimit-Remaining': '0'},
            None,
        )

    def test_run_once_uses_cached_snapshot_when_rate_limited(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / 'repos.json'
            state_path = tmp / 'state.json'
            upstreams_path = tmp / 'upstreams.json'
            reports_root = tmp / 'reports'

            config_path.write_text(json.dumps({'sources': [self._source()]}), encoding='utf-8')
            state_path.write_text(
                json.dumps({'checked_at': '2026-04-13T17:05:00+00:00', 'repos': {'playwright': self._previous_snapshot()}}),
                encoding='utf-8',
            )

            with patch.object(watch_updates, 'CONFIG_PATH', config_path), patch.object(
                watch_updates, 'STATE_PATH', state_path
            ), patch.object(watch_updates, 'UPSTREAMS_PATH', upstreams_path), patch.object(
                watch_updates, 'REPORTS_ROOT', reports_root
            ), patch.object(
                watch_updates, 'fetch_repo_snapshot', side_effect=self._rate_limit_error()
            ):
                result = watch_updates.run_once()

            self.assertTrue(result['degraded'])
            self.assertEqual(result['fetch_mode'], 'cached_fallback')
            self.assertEqual(result['degraded_sources'][0]['reason'], 'github_api_rate_limit')

            persisted = json.loads(state_path.read_text(encoding='utf-8'))
            snapshot = persisted['repos']['playwright']
            self.assertEqual(snapshot['watch_meta']['fetch_status'], 'cached_due_to_rate_limit')
            self.assertTrue(snapshot['watch_meta']['used_cached_snapshot'])

            report = (reports_root / 'latest-report.md').read_text(encoding='utf-8')
            self.assertIn('Fetch status: `cached_due_to_rate_limit`', report)
            self.assertIn('Fetch warning: `github_api_rate_limit`', report)

    def test_run_once_keeps_fail_closed_without_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            config_path = tmp / 'repos.json'
            state_path = tmp / 'state.json'
            upstreams_path = tmp / 'upstreams.json'
            reports_root = tmp / 'reports'

            config_path.write_text(json.dumps({'sources': [self._source()]}), encoding='utf-8')
            state_path.write_text(json.dumps({'checked_at': '2026-04-13T17:05:00+00:00', 'repos': {}}), encoding='utf-8')

            with patch.object(watch_updates, 'CONFIG_PATH', config_path), patch.object(
                watch_updates, 'STATE_PATH', state_path
            ), patch.object(watch_updates, 'UPSTREAMS_PATH', upstreams_path), patch.object(
                watch_updates, 'REPORTS_ROOT', reports_root
            ), patch.object(
                watch_updates, 'fetch_repo_snapshot', side_effect=self._rate_limit_error()
            ):
                with self.assertRaises(urllib.error.HTTPError):
                    watch_updates.run_once()


if __name__ == '__main__':
    unittest.main()
