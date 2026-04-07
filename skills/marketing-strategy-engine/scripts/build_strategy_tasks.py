#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _recommended_channel(prospect: dict, config: dict, weights: dict) -> tuple[str, dict]:
    priorities = config.get("channels", {}).get("priority", [])
    disallowed = set(config.get("channels", {}).get("disallowed", []))
    reachability = prospect.get("reachability_status")
    channel_bias = weights.get("channel_bias", {})
    candidates = {}
    for rank, channel in enumerate(priorities):
        if channel in disallowed:
            continue
        candidates[channel] = float(max(0, 5 - rank))
    if reachability == "email_ready" and "email" not in disallowed:
        candidates["email"] = candidates.get("email", 0) + 3.0
    if reachability == "form_ready":
        candidates["form"] = candidates.get("form", 0) + 3.0
    if reachability == "social_ready":
        candidates["linkedin"] = candidates.get("linkedin", 0) + 2.0
    if reachability == "email_review":
        candidates["form"] = candidates.get("form", 0) + 1.2
    scored = {
        channel: round(score + float(channel_bias.get(channel, 0.0)), 3)
        for channel, score in candidates.items()
        if channel not in disallowed
    }
    fallback_channel = next((channel for channel in priorities if channel not in disallowed), "form")
    selected = max(scored.items(), key=lambda item: item[1])[0] if scored else fallback_channel
    return selected, scored


def _buying_context(prospect: dict) -> str:
    signals = prospect.get("top_signals", [])
    if any("partner" in signal or "dealer" in signal or "distribution" in signal for signal in signals):
        return "partnership_fit"
    if any("quote" in signal or "project" in signal or "install" in signal for signal in signals):
        return "active_project"
    if prospect.get("intent_score", 0) >= 20:
        return "exploratory"
    return "weak_signal_observation"


def _channel_readiness(prospect: dict) -> str:
    reachability = prospect.get("reachability_status")
    mapping = {
        "email_ready": "email_ready",
        "email_review": "manual_or_form_first",
        "form_ready": "form_first",
        "social_ready": "social_first",
    }
    return mapping.get(reachability, "manual_only")


def _path_type(prospect: dict) -> str:
    account_type = prospect.get("account_type", "")
    context = _buying_context(prospect)
    if context == "partnership_fit" or account_type in {"distributor", "dealer", "showroom"}:
        return "partner_path"
    if context == "active_project" or account_type in {"contractor", "builder", "electrician"}:
        return "quote_path"
    if account_type == "designer":
        return "education_to_conversion_path"
    return "direct_response_path"


def _weighted_path_type(prospect: dict, weights: dict) -> tuple[str, dict]:
    base = _path_type(prospect)
    path_bias = weights.get("path_bias", {})
    candidates = {
        "partner_path": 0.0,
        "quote_path": 0.0,
        "education_to_conversion_path": 0.0,
        "direct_response_path": 0.0,
    }
    candidates[base] += 2.5
    account_type = prospect.get("account_type", "")
    if account_type == "designer":
        candidates["education_to_conversion_path"] += 1.0
    if account_type in {"contractor", "builder"}:
        candidates["quote_path"] += 1.0
    if account_type in {"distributor", "dealer", "showroom"}:
        candidates["partner_path"] += 1.0
    scored = {key: round(value + float(path_bias.get(key, 0.0)), 3) for key, value in candidates.items()}
    return max(scored.items(), key=lambda item: item[1])[0], scored


def _angle_options(prospect: dict) -> list[tuple[str, str]]:
    account_type = prospect.get("account_type", "")
    if account_type == "designer":
        return [
            ("design_fit", "design-led fit and curated product selection"),
            ("trade_support", "trade-friendly project support and specification flow"),
            ("education_fit", "reference-led guidance and confident product selection"),
        ]
    if account_type in {"contractor", "builder", "electrician"}:
        return [
            ("execution_fit", "project support, repeat ordering, and quoting efficiency"),
            ("speed_fit", "faster scoping, cleaner sourcing, and install-ready support"),
            ("reliability_fit", "repeatability, supply confidence, and lower project friction"),
        ]
    if account_type in {"distributor", "dealer", "showroom"}:
        return [
            ("partner_growth", "partner fit, assortment expansion, and channel upside"),
            ("channel_growth", "regional channel growth and dealer-fit expansion"),
            ("assortment_fit", "assortment relevance, margin logic, and business legitimacy"),
        ]
    return [("general_fit", "relevance-based business fit")]


def _primary_angle(prospect: dict, weights: dict) -> tuple[str, str, dict]:
    options = _angle_options(prospect)
    angle_bias = weights.get("angle_family_bias", {})
    scored = {family: round(1.0 + float(angle_bias.get(family, 0.0)), 3) for family, _ in options}
    chosen_family = max(scored.items(), key=lambda item: item[1])[0]
    chosen_text = next(text for family, text in options if family == chosen_family)
    return chosen_family, chosen_text, scored


def _target_scope(prospect: dict) -> str:
    if prospect.get("score_tier") == "A":
        return "account_1_to_1"
    if prospect.get("score_tier") == "B":
        return "segment_personalized"
    return "playbook_personalized"


def _support_angle(path_type: str) -> str:
    if path_type == "partner_path":
        return "business legitimacy, regional fit, and partner readiness"
    if path_type == "quote_path":
        return "fast scoping, practical support, and lower execution friction"
    if path_type == "education_to_conversion_path":
        return "reference guidance, specification confidence, and design support"
    return "clear fit, low-friction next step, and relevance"


def _anti_angle(prospect: dict) -> str:
    account_type = prospect.get("account_type", "")
    if account_type in {"designer", "contractor", "builder"}:
        return "generic discount-led mass pitch"
    return "vague outreach without business context"


def _value_map(prospect: dict) -> list[str]:
    account_type = prospect.get("account_type", "")
    if account_type == "designer":
        return ["curated product fit", "project presentation support", "trade-friendly buying path"]
    if account_type in {"contractor", "builder", "electrician"}:
        return ["quote support", "repeat ordering efficiency", "project delivery fit"]
    if account_type in {"distributor", "dealer", "showroom"}:
        return ["partner economics", "assortment expansion", "regional channel fit"]
    return ["relevant business fit", "clear commercial next step"]


def _proof_map(prospect: dict) -> list[str]:
    signals = prospect.get("top_signals", [])
    proof = []
    if any("project" in signal or "quote" in signal for signal in signals):
        proof.append("project-context alignment")
    if any("partner" in signal or "dealer" in signal for signal in signals):
        proof.append("partner-fit evidence")
    if any("design" in signal or "trade" in signal for signal in signals):
        proof.append("design/trade relevance")
    return proof or ["public-site-fit evidence"]


def _cta_and_fallback(path_type: str, config: dict) -> tuple[str, str]:
    project_target = config.get("project", {}).get("conversion_target", "quote_request")
    if path_type == "partner_path":
        return ("partner_application", "intro_call")
    if path_type == "quote_path":
        return ("quote_request", "project_discussion")
    if path_type == "education_to_conversion_path":
        return (project_target, "resource_reply")
    return (project_target, "intro_reply")


def _followup_plan(prospect: dict, config: dict, channel: str, path_type: str, primary_angle: str) -> list[dict]:
    cooldown = config.get("outreach_feedback_engine", {}).get("cooldown_rules", {}).get(f"{channel}_days", 4)
    second_cta = _cta_and_fallback(path_type, config)[1]
    return [
        {
            "step": 1,
            "goal": "initial_contact",
            "cadence_days": 0,
            "message_focus": primary_angle,
        },
        {
            "step": 2,
            "goal": "follow_up",
            "cadence_days": cooldown,
            "message_focus": _support_angle(path_type),
            "fallback_CTA": second_cta,
            "path_type": path_type,
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build strategy tasks from prospect records.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--prospects", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--strategy-weights")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    config = _read_json(Path(args.config).expanduser())
    prospect_records = _read_json(Path(args.prospects).expanduser()).get("items", [])
    brief = _read_json(Path(args.brief).expanduser())
    weights = _read_json(Path(args.strategy_weights).expanduser()) if args.strategy_weights else {}
    min_score = config.get("prospect_data_engine", {}).get("min_score_for_strategy", 55)
    stop_conditions = config.get("outreach_feedback_engine", {}).get("stop_conditions", [])

    items = []
    for prospect in prospect_records:
        if prospect.get("total_score", 0) < min_score:
            continue
        channel, channel_scores = _recommended_channel(prospect, config, weights)
        outreach_task_id = f"{config['project']['id']}-{prospect['account_id']}-{channel}"
        risk_level = "high" if prospect.get("score_tier") == "A" else "medium"
        approval_required = risk_level == "high" or channel == "email"
        primary_angle_family, primary_angle, angle_scores = _primary_angle(prospect, weights)
        path_type, path_scores = _weighted_path_type(prospect, weights)
        primary_cta, fallback_cta = _cta_and_fallback(path_type, config)
        items.append(
            {
                "outreach_task_id": outreach_task_id,
                "strategy_id": f"{config['project']['id']}-strategy-{prospect['account_id']}",
                "target_scope": _target_scope(prospect),
                "account_id": prospect.get("account_id", ""),
                "contact_id": prospect.get("contact_id"),
                "account_type": prospect.get("account_type"),
                "persona_type": prospect.get("persona_type"),
                "buying_context": _buying_context(prospect),
                "channel_readiness": _channel_readiness(prospect),
                "path_type": path_type,
                "channel": channel,
                "primary_angle_family": primary_angle_family,
                "primary_angle": primary_angle,
                "support_angle": _support_angle(path_type),
                "anti_angle": _anti_angle(prospect),
                "value_map": _value_map(prospect),
                "proof_map": _proof_map(prospect),
                "CTA": primary_cta,
                "fallback_CTA": fallback_cta,
                "followup_plan": _followup_plan(prospect, config, channel, path_type, primary_angle),
                "risk_level": risk_level,
                "approval_required": approval_required,
                "stop_conditions": stop_conditions,
                "score_tier": prospect.get("score_tier"),
                "brief_reference": brief.get("project_id", ""),
                "strategy_hypothesis": {
                    "why_now": prospect.get("top_signals", []),
                    "why_this_channel": prospect.get("reachability_status"),
                },
                "strategy_weight_context": {
                    "channel_scores": channel_scores,
                    "path_scores": path_scores,
                    "angle_family_scores": angle_scores,
                },
            }
        )

    out = Path(args.output).expanduser()
    _write_json(out, {"items": items})
    print(json.dumps({"output": str(out), "count": len(items)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
