#!/usr/bin/env python3
import argparse
import csv
import json
import glob
from pathlib import Path
from typing import Any


DEFAULT_SENT_EVENTS_GLOB = "/Users/mac_claw/.openclaw/workspace/output/neosgo/events/*.sent-events.csv"

import duckdb


SQL = """
with pending as (
  select
    q.queue_id,
    q.file_id,
    q.campaign_id,
    q.variant_code,
    q.channel,
    q.priority_score,
    q.attempt_no,
    l.queue_lead_id,
    l.company_name,
    l.contact_first,
    l.contact_last,
    l.contact_name,
    l.title,
    l.email,
    l.website,
    l.website_host,
    l.phone,
    l.city,
    l.state,
    l.industry,
    l.segment_primary,
    l.segment_secondary,
    l.buyer_type,
    l.decision_role_level,
    l.size_band,
    l.fit_score,
    l.fit_tier,
    l.fit_reason
  from outreach_queue q
  join outreach_ready_leads l
    on q.queue_id = md5(l.queue_lead_id || '|' || l.segment_primary || '|email')
  where q.status = 'pending'
    and q.channel = 'email'
    and not exists (
      select 1
      from outreach_events e
      where e.queue_id = q.queue_id
        and e.event_type in ('sent', 'unsubscribe', 'do_not_contact', 'lost')
    )
),
joined as (
  select
    p.*,
    cv.subject_template,
    cv.body_template,
    cv.cta_type
  from pending p
  left join campaign_variants cv
    on p.campaign_id = cv.campaign_id
   and p.segment_primary = cv.segment_primary
   and p.variant_code = cv.variant_code
   and p.channel = cv.channel
)
select *
from joined
where email is not null and trim(email) <> ''
  and (? = '' or upper(state) = upper(?))
  and (? = '' or segment_primary = ?)
  and (? = '' or fit_tier = ?)
  and fit_score >= ?
order by priority_score desc, fit_score desc
limit ?
"""


def _render_template(text: str, row: dict[str, Any]) -> str:
    rendered = text or ""
    replacements = {
        "{{contact_name}}": row.get("contact_name") or row.get("contact_first") or "there",
        "{{company_name}}": row.get("company_name") or "",
        "{{state}}": row.get("state") or "",
        "{{city}}": row.get("city") or "",
        "{{segment_primary}}": row.get("segment_primary") or "",
        "{{title}}": row.get("title") or "",
    }
    for key, value in replacements.items():
        rendered = rendered.replace(key, str(value))
    return rendered.strip()


def _segment_opening(row: dict[str, Any]) -> str:
    segment = str(row.get("segment_primary") or "").strip().lower()
    company = str(row.get("company_name") or "").strip()
    if segment == "designer":
        return f"I came across {company or 'your firm'} and thought a brief introduction may be relevant if your team is reviewing lighting selections for active or upcoming design-led projects."
    if segment == "builder":
        return f"I came across {company or 'your team'} and thought a brief introduction may be relevant if you are looking for a cleaner, design-forward lighting source for active or upcoming projects."
    if segment == "contractor":
        return f"I came across {company or 'your company'} and thought a brief introduction may be relevant if your team is handling lighting sourcing close to the project execution layer."
    if segment == "electrician":
        return f"I came across {company or 'your company'} and thought a brief introduction may be relevant if your team is involved in fixture selection, installation planning, or repeat lighting work across active projects."
    if segment in {"furniture_retailer", "kitchen_bath"}:
        return f"I came across {company or 'your showroom'} and thought a brief introduction may be relevant if you are evaluating new lighting assortment or supplier options."
    return f"I came across {company or 'your company'} and thought a brief introduction may be relevant if lighting sourcing, presentation quality, and responsive support matter in your workflow."


def _segment_profile(row: dict[str, Any]) -> dict[str, Any]:
    segment = str(row.get("segment_primary") or "").strip().lower()
    if segment == "designer":
        return {
            "template_version": "designer",
            "subject": "Neosgo Lighting | Design-forward collections for trade buyers",
            "core": (
                "Neosgo Lighting is built around curated collections with refined finishes, "
                "modern silhouettes, and design-forward details. The site is structured more like "
                "a cleaner catalog for faster decisions, with room-based browsing, trade-focused "
                "pricing, and project support designed for professional buyers."
            ),
            "bullets": [
                "design-forward lighting collections that are easier to present to clients",
                "room-based browsing that makes online review and option sharing easier",
                "responsive help with product selection and quote requests",
                "professional-buyer advantages for repeat project work, including trade pricing and rebate-oriented long-term cooperation",
            ],
            "cta": "If the direction feels relevant, I would be glad to send a short tailored selection based on the type of spaces or project style you are working on, and explain how the professional-buyer side works for repeat purchasing.",
        }
    if segment in {"builder", "contractor", "electrician"}:
        return {
            "template_version": "builder_contractor",
            "subject": "Neosgo Lighting | Trade pricing and cleaner sourcing for active projects",
            "core": (
                "Neosgo Lighting is set up to make the lighting side of a project feel more manageable: "
                "a cleaner catalog for faster decisions, trade-focused pricing, project support, and a "
                "simpler path for repeat ordering when jobs keep moving."
            ),
            "bullets": [
                "design-forward lighting options for residential and hospitality-style spaces",
                "responsive support for product selection and quote requests",
                "a cleaner workflow when reviewing options internally or with clients",
                "professional-buyer advantages for ongoing work, including trade pricing and rebate-oriented long-term cooperation",
            ],
            "cta": "If the direction feels useful, I would be glad to send over a short targeted selection based on the kinds of projects your team is currently handling, and outline how the professional-buyer structure can work for repeat jobs.",
        }
    if segment in {"furniture_retailer", "kitchen_bath"}:
        return {
            "template_version": "showroom_channel",
            "subject": "Neosgo Lighting | Curated collections for showroom and channel buyers",
            "core": (
                "Neosgo Lighting focuses on curated collections with a clean visual point of view, "
                "which can be helpful when a showroom or trade-facing business wants options that feel "
                "more considered, more presentable, and easier to position. The site also supports "
                "trade-focused pricing and a cleaner experience for repeat ordering."
            ),
            "bullets": [
                "curated lighting collections suited for showroom and trade presentation",
                "a cleaner assortment review process",
                "responsive support around product selection and quote requests",
                "professional-buyer advantages for repeat sourcing and longer-term cooperation, including rebate-oriented upside",
            ],
            "cta": "If the direction feels relevant, I would be glad to send a short tailored selection aligned with the type of assortment or customer profile you serve, and explain how the professional-buyer structure works.",
        }
    return {
        "template_version": "general",
        "subject": "Neosgo Lighting | Curated lighting collections for project teams",
        "core": (
            "Neosgo is focused on curated lighting collections with refined finishes, modern silhouettes, "
            "and design-forward details for teams that care about both presentation quality and sourcing efficiency."
        ),
        "bullets": [
            "curated lighting options for residential, hospitality-style, and design-led spaces",
            "responsive help with product selection and quote requests",
            "a cleaner presentation layer when sharing options internally or with clients",
            "trade-oriented coordination for ongoing projects",
        ],
        "cta": "If the aesthetic and product direction feels relevant, I would be glad to send over a short, tailored selection based on the type of spaces you are working on.",
    }


def _build_formal_body(row: dict[str, Any], sender_email: str, sender_name: str, website_url: str, core_body: str) -> str:
    contact_name = row.get("contact_name") or row.get("contact_first") or "there"
    company_name = row.get("company_name") or "your company"
    title = row.get("title") or ""
    opening = _segment_opening(row)
    profile = _segment_profile(row)
    website_line = website_url.strip() if website_url.strip() else "https://neosgo.com"
    unsubscribe = (
        "If you prefer not to receive further emails from us, simply reply with "
        "'unsubscribe' or email "
        f"{sender_email} with the subject line 'unsubscribe', and we will stop contact."
    )
    signature = (
        "Best regards,\n"
        f"{sender_name}\n"
        f"{sender_email}\n"
        f"{website_line}"
    )
    core_text = (core_body or "").strip()
    lowered_core = core_text.lower()
    if lowered_core.startswith("hi ") or lowered_core.startswith("hello ") or "trade pricing" in lowered_core:
        core_text = ""

    bullets = profile["bullets"]
    lines = [
        f"Hi {contact_name},",
        "",
        opening,
        "",
        (
            core_text
            or profile["core"]
        ),
        "",
        "What we can support:",
        *[f"- {item}" for item in bullets],
        "",
        "You can preview the collection here:",
        website_line,
        "",
        profile["cta"],
        "",
        f"If this is better handled by another person at {company_name}{', ' + title if title else ''}, I would appreciate being pointed in the right direction.",
        "",
        unsubscribe,
        "",
        signature,
    ]
    return "\n".join(lines).strip()


def _normalize_row(row: dict[str, Any], sender_email: str, sender_name: str, website_url: str) -> dict[str, Any]:
    subject = _render_template(row.get("subject_template") or "", row).strip()
    segment = str(row.get("segment_primary") or "").strip().lower()
    profile = _segment_profile(row)
    plain_subjects = {
        "Trade pricing for your upcoming projects",
        "Project supply support for builders",
        "Support for remodel and contractor sourcing",
        "Wholesale / dealer collaboration",
    }
    if not subject or subject in plain_subjects:
        subject = profile["subject"]
    core_body = _render_template(row.get("body_template") or "", row)
    body = _build_formal_body(row, sender_email, sender_name, website_url, core_body)
    return {
        "queue_id": row.get("queue_id"),
        "file_id": row.get("file_id"),
        "campaign_id": row.get("campaign_id"),
        "variant_code": row.get("variant_code"),
        "priority_score": row.get("priority_score"),
        "attempt_no": row.get("attempt_no"),
        "sender_name": sender_name,
        "sender_email": sender_email,
        "sender_display": f"{sender_name} <{sender_email}>",
        "recipient_email": row.get("email"),
        "contact_name": row.get("contact_name"),
        "company_name": row.get("company_name"),
        "title": row.get("title"),
        "segment_primary": row.get("segment_primary"),
        "template_version": profile["template_version"],
        "fit_tier": row.get("fit_tier"),
        "fit_score": row.get("fit_score"),
        "subject": subject,
        "body": body,
        "cta_type": row.get("cta_type"),
        "website_url": website_url,
        "website": row.get("website"),
        "website_host": row.get("website_host"),
        "phone": row.get("phone"),
        "city": row.get("city"),
        "state": row.get("state"),
        "industry": row.get("industry"),
        "fit_reason": row.get("fit_reason"),
        "unsubscribe_instruction": f"Reply with 'unsubscribe' or email {sender_email} with subject 'unsubscribe'.",
    }


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _load_suppressed_emails(path: str) -> set[str]:
    file_path = Path(path)
    if not file_path.exists():
        return set()
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    emails = payload.get("emails") if isinstance(payload, dict) else payload
    return {str(item).strip().lower() for item in (emails or []) if str(item).strip()}


def _load_sent_history(sent_events_glob: str) -> tuple[set[str], set[str]]:
    sent_emails: set[str] = set()
    sent_queue_ids: set[str] = set()
    for raw_path in sorted(glob.glob(sent_events_glob)):
        path = Path(raw_path)
        try:
            with path.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    queue_id = str(row.get("queue_id") or "").strip()
                    if queue_id:
                        sent_queue_ids.add(queue_id)
                    payload_raw = row.get("payload_json")
                    if not payload_raw:
                        continue
                    try:
                        payload = json.loads(payload_raw)
                    except Exception:
                        continue
                    email = str((payload or {}).get("recipient_email") or "").strip().lower()
                    if email:
                        sent_emails.add(email)
        except Exception:
            continue
    return sent_emails, sent_queue_ids


def _dedupe_normalized_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_queue_ids: set[str] = set()
    seen_emails: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        queue_id = str(row.get("queue_id") or "").strip()
        email = str(row.get("recipient_email") or "").strip().lower()
        if queue_id and queue_id in seen_queue_ids:
            continue
        if email and email in seen_emails:
            continue
        if queue_id:
            seen_queue_ids.add(queue_id)
        if email:
            seen_emails.add(email)
        deduped.append(row)
    return deduped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--sender-email", required=True)
    ap.add_argument("--sender-name", default="Neosgo Lighting")
    ap.add_argument("--website-url", default="https://neosgo.com")
    ap.add_argument("--state", default="")
    ap.add_argument("--segment", default="")
    ap.add_argument("--fit-tier", default="")
    ap.add_argument("--min-fit-score", type=int, default=80)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--suppression-file", default="/Users/mac_claw/.openclaw/workspace/output/neosgo/suppressed-emails.json")
    ap.add_argument("--sent-events-glob", default=DEFAULT_SENT_EVENTS_GLOB)
    ap.add_argument("--csv-out", required=True)
    ap.add_argument("--json-out")
    args = ap.parse_args()

    con = duckdb.connect(args.db, read_only=True)
    params = [
        (args.state or "").strip(),
        (args.state or "").strip(),
        (args.segment or "").strip(),
        (args.segment or "").strip(),
        (args.fit_tier or "").strip(),
        (args.fit_tier or "").strip(),
        int(args.min_fit_score),
        args.limit,
    ]
    columns = [d[0] for d in con.execute(SQL, params).description]
    records = [dict(zip(columns, row)) for row in con.execute(SQL, params).fetchall()]
    con.close()
    suppressed = _load_suppressed_emails(args.suppression_file)
    sent_emails, sent_queue_ids = _load_sent_history(args.sent_events_glob)
    if suppressed or sent_emails or sent_queue_ids:
        records = [
            row for row in records
            if str(row.get("email") or "").strip().lower() not in suppressed
            and str(row.get("email") or "").strip().lower() not in sent_emails
            and str(row.get("queue_id") or "").strip() not in sent_queue_ids
        ]

    normalized = _dedupe_normalized_rows([
        _normalize_row(row, args.sender_email, args.sender_name, args.website_url)
        for row in records
    ])
    csv_out = Path(args.csv_out)
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(normalized, csv_out)

    if args.json_out:
        json_out = Path(args.json_out)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "db": args.db,
                "sender_name": args.sender_name,
                "sender_email": args.sender_email,
                "website_url": args.website_url,
                "state": args.state,
                "segment": args.segment,
                "fit_tier": args.fit_tier,
                "min_fit_score": args.min_fit_score,
                "suppressed_email_count": len(suppressed),
                "historical_sent_email_count": len(sent_emails),
                "historical_sent_queue_count": len(sent_queue_ids),
                "rows": len(normalized),
                "csv_out": str(csv_out),
                "json_out": str(args.json_out) if args.json_out else "",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
