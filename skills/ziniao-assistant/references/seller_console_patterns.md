# Ziniao Seller Console Patterns

Use this reference for Ziniao-backed seller-console tasks such as login, navigation, filtering, exporting, order operations, and finance/report downloads.

## Core working pattern

1. Reuse the already-open Ziniao store session when possible.
2. Discover bridge tools first with `GET /zclaw/tools`.
3. Use only bridge-approved tool names with `POST /zclaw/tools/invoke`.
4. Prefer visible UI interactions over hidden DOM shortcuts.
5. Verify the final business result with page evidence, export history, or a status row. Do not stop at “button clicked”.

## Navigation and login rules

- Prefer `list_stores` once, then `open_store` once.
- Reuse the logged-in browser profile instead of opening a fresh generic browser.
- If the seller site defaults to QR login, explicitly switch to account login before assuming credentials failed.
- Confirm you are in the intended site/region before moving deeper into the console.
- Do not assume the first newly opened tab is the target tab; verify URL and visible page heading.

## Page operation rules

- Seller consoles often use component libraries that ignore raw DOM value assignment.
- For date ranges, dropdowns, and segmented tabs, use the component-friendly path:
  open picker -> choose visible values -> confirm -> wait for table refresh.
- If a click target is visually present but normal click fails, use a full mouse event sequence through the bridge script path instead of declaring the step impossible.
- When a table refreshes, verify both the filter chip/date state and the result body.

## Export rules

- Treat export as a multi-step business action, not a single click.
- Typical flow:
  1. set filters
  2. click query/search
  3. verify result table reflects the requested filter
  4. click export
  5. confirm export modal choices
  6. open export history or task list
  7. verify a new export row exists with the right date range/content
- If the platform generates async export tasks, “download available in export history” counts as stronger completion proof than assuming a local file appeared.
- If the local Downloads folder does not show a new file immediately, check whether the app uses its own download path before treating it as a failure.

## Evidence contract

For seller-console tasks, capture at least one of:

- a screenshot of the filtered result state
- a screenshot of export history / task history
- the visible page URL plus heading plus filter state
- the generated row metadata: time range, content type, status, download action

## Common failure modes

- Wrong tab: Ziniao opened a new tab, but the agent kept operating the previous seller tab.
- Wrong login mode: the page defaulted to QR login and the agent never switched to account login.
- Wrong site/region: the store stayed on the default site instead of the requested country.
- Hidden-input trap: the agent wrote raw values into a component-controlled field and the UI ignored them.
- Fake completion: the agent clicked export but never confirmed the export-history row.

## Stop conditions

Stop and report a blocker when:

- the bridge itself is unreachable
- the required tool name is not present in `GET /zclaw/tools`
- the store session is not authenticated and account reuse cannot proceed
- the page changed direction in a way that requires user confirmation
- the business result cannot be verified after reasonable retries
