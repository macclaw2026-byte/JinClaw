#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SELLER_DOMAIN = "seller.neosgo.com"
SESSION_COOKIE_NAME = "__prod_next-auth.session-token"
LANG_COOKIE_NAME = "x-hng"
CHROME_SAFE_STORAGE_PASSWORD_PATH = Path.home() / ".openclaw" / "secrets" / "chrome-safe-storage.password"
DEFAULT_PRICE_CHANGE_REASON = (
    "Align retail price to the bulk import template price plus 25 USD after the pricing rule correction."
)


def _chrome_cookie_db_candidates() -> list[tuple[str, Path]]:
    """
    中文注解：
    - 功能：枚举本机 Chrome profile 的 Cookies 数据库候选路径。
    - 输入：无。
    - 输出：[(profile_name, cookie_db_path), ...]。
    """
    chrome_root = Path.home() / "Library/Application Support/Google/Chrome"
    if not chrome_root.exists():
        return []
    candidates: list[tuple[str, Path]] = []
    for child in sorted(chrome_root.iterdir()):
        if not child.is_dir():
            continue
        if child.name not in {"Default", "Profile 1"} and not child.name.startswith("Profile "):
            continue
        cookie_db = child / "Cookies"
        if cookie_db.exists():
            candidates.append((child.name, cookie_db))
    return candidates


def _read_chrome_safe_storage_password() -> str:
    env_override = str(os.environ.get("CHROME_SAFE_STORAGE_PASSWORD") or "").strip()
    if env_override:
        return env_override
    try:
        cached = CHROME_SAFE_STORAGE_PASSWORD_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        cached = ""
    if cached:
        return cached
    proc = subprocess.run(
        ["security", "find-generic-password", "-s", "Chrome Safe Storage", "-g"],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = f"{proc.stdout}\n{proc.stderr}"
    match = re.search(r'password:\s*"([^"]+)"', combined)
    if not match:
        raise RuntimeError("chrome_safe_storage_password_unavailable")
    return match.group(1)


def _decrypt_cookie_value(encrypted_value: bytes, password: str) -> str:
    blob = bytes(encrypted_value or b"")
    if not blob:
        return ""
    if not blob.startswith(b"v10"):
        return blob.decode("utf-8", "replace")

    key = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), b"saltysalt", 1003, dklen=16)
    iv = (b" " * 16).hex()
    proc = subprocess.run(
        ["openssl", "enc", "-aes-128-cbc", "-d", "-K", key.hex(), "-iv", iv, "-nopad"],
        input=blob[3:],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("chrome_cookie_decrypt_failed")
    decrypted = proc.stdout
    if not decrypted:
        return ""
    pad_len = decrypted[-1]
    if 0 < pad_len <= 16:
        decrypted = decrypted[:-pad_len]
    # Chrome prefixes DB cookies with a 32-byte host digest before plaintext.
    if len(decrypted) > 32:
        decrypted = decrypted[32:]
    return decrypted.decode("utf-8", "replace")


def load_seller_session_cookies() -> dict[str, str]:
    """
    中文注解：
    - 功能：从本机 Chrome profile 提取 seller.neosgo 登录态 cookie。
    - 输入：无。
    - 输出：包含 session/lang/profile 的结构化字典。
    """
    password = _read_chrome_safe_storage_password()
    last_error = "seller_session_cookie_missing"
    for profile_name, cookie_db in _chrome_cookie_db_candidates():
        tmp_db = Path(tempfile.gettempdir()) / f"neosgo_cookie_probe_{profile_name.replace(' ', '_')}.sqlite"
        shutil.copy2(cookie_db, tmp_db)
        conn = sqlite3.connect(tmp_db)
        try:
            rows = conn.execute(
                """
                select name, value, encrypted_value
                from cookies
                where host_key = ?
                  and name in (?, ?)
                order by name
                """,
                (SELLER_DOMAIN, LANG_COOKIE_NAME, SESSION_COOKIE_NAME),
            ).fetchall()
        finally:
            conn.close()
        if not rows:
            continue

        cookies: dict[str, str] = {"profile": profile_name}
        for name, value, encrypted_value in rows:
            plaintext = str(value or "").strip()
            if not plaintext and encrypted_value:
                plaintext = _decrypt_cookie_value(bytes(encrypted_value), password)
            if plaintext:
                cookies[str(name)] = plaintext
        if cookies.get(SESSION_COOKIE_NAME):
            if LANG_COOKIE_NAME not in cookies:
                cookies[LANG_COOKIE_NAME] = "lang=en-US&domain=seller.neosgo.com"
            return cookies
        last_error = f"seller_session_cookie_incomplete:{profile_name}"
    raise RuntimeError(last_error)


def _cookie_header(cookies: dict[str, str]) -> str:
    session = str(cookies.get(SESSION_COOKIE_NAME, "")).strip()
    if not session:
        raise RuntimeError("seller_session_cookie_missing")
    pieces = [f"{SESSION_COOKIE_NAME}={session}"]
    lang_cookie = str(cookies.get(LANG_COOKIE_NAME, "")).strip()
    if lang_cookie:
        pieces.append(f"{LANG_COOKIE_NAME}={lang_cookie}")
    return "; ".join(pieces)


def safe_patch_active_listing_price(
    base: str,
    product_id: str,
    retail_unit_price: float,
    *,
    reason: str = DEFAULT_PRICE_CHANGE_REASON,
    cookies: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """
    中文注解：
    - 功能：使用 seller 登录态对 active listing 走页面接口改价。
    - 输入：base/product_id/retail_unit_price/reason/cookies。
    - 输出：统一的 {ok, resp|error, route, reason} 结构。
    """
    cookie_bundle = cookies or load_seller_session_cookies()
    body = {
        "basePrice": round(float(retail_unit_price), 2),
        "changeRequestReason": str(reason or DEFAULT_PRICE_CHANGE_REASON).strip() or DEFAULT_PRICE_CHANGE_REASON,
    }
    headers = {
        "Cookie": _cookie_header(cookie_bundle),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "OpenClaw-Neosgo-Seller-SessionClient/1.0",
    }
    req = urllib.request.Request(
        base.rstrip("/") + f"/api/products/{product_id}",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return {
                "ok": True,
                "resp": json.loads(raw or "{}"),
                "route": "seller_session_product_patch",
                "reason": body["changeRequestReason"],
                "profile": cookie_bundle.get("profile", ""),
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        return {
            "ok": False,
            "error": {"http_status": exc.code, "body": raw},
            "route": "seller_session_product_patch",
            "reason": body["changeRequestReason"],
            "profile": cookie_bundle.get("profile", ""),
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "error": {"network_error": str(exc)},
            "route": "seller_session_product_patch",
            "reason": body["changeRequestReason"],
            "profile": cookie_bundle.get("profile", ""),
        }
