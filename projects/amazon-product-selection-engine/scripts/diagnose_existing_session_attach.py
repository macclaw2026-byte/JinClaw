#!/usr/bin/env python3
import json
import socket
import subprocess
from pathlib import Path


CHROME_ROOT = Path("/Users/mac_claw/Library/Application Support/Google/Chrome")
EXT_ID = "nglingapjinhecnfejdcpihlpneeadjp"
EXT_STORAGE = CHROME_ROOT / "Default" / "Local Extension Settings" / EXT_ID / "000003.log"
DEVTOOLS_ACTIVE_PORT = CHROME_ROOT / "DevToolsActivePort"
OPENCLAW_CONFIG = Path("/Users/mac_claw/.openclaw/openclaw.json")


def is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def read_gateway_token() -> str:
    try:
        payload = json.loads(OPENCLAW_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return str(payload.get("gateway", {}).get("auth", {}).get("token", "")).strip()


def extension_configured() -> dict:
    result = {
        "extension_installed": False,
        "has_gateway_token": False,
        "has_relay_port": False,
    }
    manifest = CHROME_ROOT / "Default" / "Extensions" / EXT_ID
    result["extension_installed"] = manifest.exists()
    if not EXT_STORAGE.exists():
        return result
    raw = EXT_STORAGE.read_text("latin1", errors="ignore")
    result["has_gateway_token"] = "gatewayToken" in raw
    result["has_relay_port"] = "relayPort" in raw or "18792" in raw
    return result


def openclaw_profiles() -> dict:
    proc = subprocess.run(
        ["openclaw", "browser", "--json", "profiles"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip() or proc.stdout.strip()}
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"error": "invalid json", "raw": proc.stdout[:2000]}


def main() -> int:
    payload = {
        "chrome_root": str(CHROME_ROOT),
        "devtools_active_port_exists": DEVTOOLS_ACTIVE_PORT.exists(),
        "devtools_active_port_contents": DEVTOOLS_ACTIVE_PORT.read_text(encoding="utf-8", errors="ignore") if DEVTOOLS_ACTIVE_PORT.exists() else "",
        "port_18791_listening": is_port_listening(18791),
        "port_18792_listening": is_port_listening(18792),
        "port_18800_listening": is_port_listening(18800),
        "gateway_token_present": bool(read_gateway_token()),
        "extension": extension_configured(),
        "openclaw_profiles": openclaw_profiles(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
