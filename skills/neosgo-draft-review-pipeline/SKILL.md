---
name: neosgo-draft-review-pipeline
description: Process seller.neosgo draft listings end-to-end. Use when a user wants Neosgo seller-center draft products completed and submitted for review: generate or add scene images, ensure at least 3 scene images with scene images ranked in the first 3 slots, fill missing listing fields such as category, shipping template, and packing unit, then submit the draft to review and verify the status changed from DRAFT.
---

# Neosgo Draft Review Pipeline

Use this skill for `seller.neosgo.com` seller-center draft listing completion.

## What success looks like

A listing batch is only complete when all of the following are true:

1. the Excel file was uploaded through Neosgo Bulk Import with the correct template
2. imported products appear as drafts in Listings
3. each target listing has at least 3 scene images
4. scene images occupy the first 3 positions
5. required fields are filled well enough for submission
6. `Submit for Review` succeeds and each processed listing no longer shows `DRAFT`

Do not confuse partial progress with completion.

## Workflow

### 1. Start from Bulk Import or API-connected import
- Trigger this skill when the user wants products imported into seller.neosgo and then submitted for review.
- Go to `seller.neosgo.com` seller center.
- Open `Bulk Import`.
- If the user provided an Excel, use the correct mapping template and upload the Excel.
- If the user says the API import is already connected and product data is ready inside Bulk Import, use the available import/submit action there to push the prepared records into seller.neosgo so they become draft listings.
- Do not assume import completion from the button click alone; wait until the imported products appear in Listings as drafts.

### 2. Collect draft listings
- Open `Listings`.
- Gather all target draft edit links created by the import.
- Prefer staying in one stable browser tab and navigating listing-to-listing.
- Confirm current status is `DRAFT` before editing.

### 3. Audit the listing
Check these areas first:
- image count and image order
- whether the first 3 images are scene images
- category
- shipping template
- packing unit
- any other obvious required-field warnings

### 3. Fix images
If fewer than 3 scene images exist:
- use the scene-image workflow described in `references/scene-image-workflow.md`
- generate missing scene images from the product source image
- upload them to the listing

Then ensure scene images are in the first 3 positions.
If page drag-and-drop does not persist, treat sorting as unresolved and verify again after save/reload.

### 4. Fill missing fields
- Set category using best-fit existing marketplace category
- Set shipping template to the correct saved template when available
- Add `Packing Unit #1` with defensible dimensions and quantity
- If a value is uncertain, use `references/field-completion-rules.md`
- If still uncertain after analysis, stop and ask the user with concise reasoning

### 5. Save and verify
After edits:
- save changes
- reload or re-read the page
- verify images, order, and required fields actually persisted

### 6. Submit for review
- click `Submit for Review`
- verify button disappearance or status transition away from `DRAFT`
- prefer confirmation from the listings table if needed

## Verification discipline

Always verify by page state, not by attempted action.
At minimum confirm:
- scene image count
- first-3 ordering
- packing unit presence
- status changed to `SUBMITTED` or equivalent non-draft state

## Batch mode

For many drafts:
- collect draft edit links from the listings page
- reuse one stable tab and navigate draft-to-draft
- after each listing, record result as `submitted`, `needs-user-input`, or `blocked`
- do not report the whole batch done until all visible drafts are cleared or explicitly blocked

## Resources
- Scene-image rules: `references/scene-image-workflow.md`
- Field-fill rules: `references/field-completion-rules.md`
- Batch checklist: `references/batch-checklist.md`
- Prompt helper: `scripts/build_scene_prompt.py`
`needs-user-input`, or `blocked`
- do not report the whole batch done until all visible drafts are cleared or explicitly blocked

## Resources
- Scene-image rules: `references/scene-image-workflow.md`
- Field-fill rules: `references/field-completion-rules.md`
- Batch checklist: `references/batch-checklist.md`
- Prompt helper: `scripts/build_scene_prompt.py`
