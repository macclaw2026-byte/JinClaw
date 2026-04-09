#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path("/Users/mac_claw/.openclaw/workspace/projects/neosgo-marketing-suite")
OPENCLAW_BIN = "/opt/homebrew/bin/openclaw"
DEFAULT_CHAT = "8528973600"
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LATEST_SUMMARY_PATH = PROJECT_ROOT / "runtime" / "outreach" / "latest-summary.json"
STATE_PATH = PROJECT_ROOT / "runtime" / "outreach" / "telegram-summary-state.json"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{DEFAULT_PATH}:{env.get('PATH', '')}".strip(":")
    return env


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _send(chat_id: str, text: str) -> dict:
    proc = subprocess.run(
        [OPENCLAW_BIN, "message", "send", "--channel", "telegram", "--target", chat_id, "--message", text, "--json"],
        capture_output=True,
        text=True,
        timeout=120,
        env=_subprocess_env(),
        check=False,
    )
    return {"returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def _format_channel(value: str) -> str:
    return "网站表单" if value == "contact_form" else "邮件" if value == "email" else value or "未知"


def _format_status(value: str) -> str:
    mapping = {
        "email_sent_local_only": "邮件已发出，10 分钟内未见失败会继续下一封",
        "contact_form_needs_review": "网站表单结果不明确，已转人工复核",
        "contact_form_failed_email_deferred": "网站表单失败，但邮件发送被门禁暂缓",
        "contact_form_submitted": "网站表单已成功提交",
        "captcha_pending_operator": "网站表单遇到验证码，等待人工一步确认",
        "email_failed": "邮件发送失败，任务已暂停",
        "contact_form_failed": "网站表单失败，且没有进入邮件补发",
        "ready_for_form_retry": "网站表单已准备好重试",
        "ready_for_email": "已切换为邮件待发送",
        "review_hold": "结果模糊，已保守暂停",
    }
    return mapping.get(value or "", value or "未知")


def _load_target_state() -> dict:
    state_path = PROJECT_ROOT / "runtime" / "outreach" / "state.json"
    return _read_json(state_path, {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Send periodic NEOSGO outreach summary to Telegram.")
    parser.add_argument("--chat-id", default=os.environ.get("NEOSGO_OUTREACH_CHAT", DEFAULT_CHAT))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    latest = _read_json(LATEST_SUMMARY_PATH, {})
    if not latest:
        print(json.dumps({"ok": False, "reason": "missing_latest_summary"}, ensure_ascii=False))
        return 1

    state = _read_json(STATE_PATH, {})
    generated_at = str(latest.get("generated_at") or "")
    if not args.force and generated_at and generated_at == str(state.get("last_generated_at") or ""):
        print(json.dumps({"ok": True, "skipped": True, "reason": "already_sent_for_latest_summary"}, ensure_ascii=False))
        return 0

    counts = dict(latest.get("counts") or {})
    state = _load_target_state()
    targets = list((state.get("targets") or {}).values())
    targets.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    recent_lines = []
    for item in targets[:8]:
        company = str(item.get("company_name") or "未知公司")
        channel = _format_channel(str(item.get("channel") or ""))
        status = _format_status(str(item.get("status") or ""))
        recent_lines.append(f"- {company}：通过{channel}触达，当前结果：{status}")

    counts_text = "，".join(f"{key}={value}" for key, value in counts.items()) or "暂无"
    text = (
        "NEOSGO 触达任务进度汇报\n"
        f"生成时间：{generated_at}\n"
        f"累计已触达公司数：{latest.get('total_touched', 0)}\n"
        f"当前统计：{counts_text}\n"
    )
    if latest.get("email_delivery_pending"):
        text += "邮件状态：当前有一封邮件处于观察窗口内；若 10 分钟内没有失败信号，系统会继续下一封。\n"
    if recent_lines:
        text += "最近处理的公司：\n" + "\n".join(recent_lines)
    failure = latest.get("failure") or {}
    if failure:
        company = failure.get("company_name") or "未知公司"
        reason = ((failure.get("result") or {}).get("reason") or "unknown")
        text += f"\n异常：{company} 触达失败，原因：{reason}"

    delivery = _send(args.chat_id, text)
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "last_generated_at": generated_at,
                "last_sent_at": datetime.now().isoformat(),
                "delivery": delivery,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "delivery": delivery}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
