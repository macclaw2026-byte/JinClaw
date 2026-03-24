# Tool Redundancy and Arbitration

Use this reference when data quality matters enough that one extraction method is not trustworthy on its own.

## Goal

Create redundancy across extraction methods, then compare, clean, and choose the strongest evidence instead of trusting the first tool output blindly.

## Recommended pattern

1. run primary method
2. run one or more backup methods when the page/site/field matters
3. normalize outputs into the shared evidence schema
4. compare field-by-field
5. keep the strongest supported value
6. route only the cleaned surviving evidence downstream

## Good reasons to use redundancy

- page is dynamic or flaky
- one extractor returns partial content
- anti-bot behavior affects one path but not another
- fields are high-impact for a downstream decision
- prior runs showed this source family is noisy

## Arbitration questions

For each important field, ask:
- which tool gave the most complete value?
- which value best matches the visible page/source?
- which tool preserved structure better?
- do multiple methods agree on the same fact?
- if they disagree, which value has the strongest provenance?

## Output suggestion

For important records, keep:
- chosen value
- winning source/tool
- backup supporting source(s)
- confidence
- unresolved conflict note if needed
