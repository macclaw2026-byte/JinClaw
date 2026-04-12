#!/usr/bin/env python3
# RULES-FIRST NOTICE:
# Before modifying this file, first read:
# - `JINCLAW_CONSTITUTION.md`
# - `AI_OPTIMIZATION_FRAMEWORK.md`
# Follow the constitution and framework:
# brain-first, one-doctor, fail-closed, evidence-over-narration,
# validate locally, then use the required PR workflow.
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional


class MarketingApiError(RuntimeError):
    pass


@dataclass
class MarketingApiClient:
    base_url: str
    bearer_token: str
    timeout_seconds: int = 60

    @staticmethod
    def _unwrap_single(payload: Any, keys: tuple[str, ...]) -> dict[str, Any]:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, dict):
                    return value
        if isinstance(payload, dict):
            return payload
        return {}

    @staticmethod
    def _unwrap_list(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _request(self, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + path
        body = None
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw)
            except Exception:
                detail = {"raw": raw}
            raise MarketingApiError(f"{method} {path} failed with {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MarketingApiError(f"{method} {path} network error: {exc}") from exc

    def list_design_notes(self) -> dict[str, Any]:
        return self._request("GET", "/api/automation/admin/design-notes")

    def get_design_note(self, note_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/automation/admin/design-notes/{urllib.parse.quote(str(note_id))}")
        return self._unwrap_single(payload, ("note", "data", "item"))

    def create_design_note(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", "/api/automation/admin/design-notes", payload)
        return self._unwrap_single(response, ("note", "data", "item"))

    def update_design_note(self, note_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("PATCH", f"/api/automation/admin/design-notes/{urllib.parse.quote(str(note_id))}", payload)
        return self._unwrap_single(response, ("note", "data", "item"))

    def publish_design_note(self, note_id: str) -> dict[str, Any]:
        response = self._request("POST", f"/api/automation/admin/design-notes/{urllib.parse.quote(str(note_id))}/publish")
        return self._unwrap_single(response, ("note", "data", "item"))

    def list_design_note_revisions(self, note_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/automation/admin/design-notes/{urllib.parse.quote(str(note_id))}/revisions")

    def list_geo_variants(self, note_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/automation/admin/design-notes/{urllib.parse.quote(str(note_id))}/geo-variants")
        if isinstance(payload, dict):
            items = self._unwrap_list(payload, ("variants", "items", "rows", "data"))
            return {"items": items}
        return {"items": self._unwrap_list(payload, ("variants", "items", "rows", "data"))}

    def create_geo_variant(self, note_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", f"/api/automation/admin/design-notes/{urllib.parse.quote(str(note_id))}/geo-variants", payload)
        return self._unwrap_single(response, ("variant", "geoVariant", "data", "item"))

    def update_geo_variant(self, note_id: str, variant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request(
            "PATCH",
            f"/api/automation/admin/design-notes/{urllib.parse.quote(str(note_id))}/geo-variants/{urllib.parse.quote(str(variant_id))}",
            payload,
        )
        return self._unwrap_single(response, ("variant", "geoVariant", "data", "item"))

    def publish_geo_variant(self, note_id: str, variant_id: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/automation/admin/design-notes/{urllib.parse.quote(str(note_id))}/geo-variants/{urllib.parse.quote(str(variant_id))}/publish",
        )
        return self._unwrap_single(response, ("variant", "geoVariant", "data", "item"))
