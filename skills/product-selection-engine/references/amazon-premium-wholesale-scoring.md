# Amazon Premium Wholesale Scoring

Use this scoring model for the Amazon premium wholesale branch.

## Target

The product should look capable of stable natural daily sales without requiring giant-brand dominance or extreme operational burden.

## Suggested weighted dimensions

Score each dimension 1-5, then apply weight.

- Demand durability (20)
- Amazon marketplace activity proxy (20)
- Competition survivability (20)
- Search / keyword evidence (10)
- Product simplicity / operational ease (10)
- Margin / price-ladder viability (10)
- Differentiation room (10)

## Additional gating notes

Even if total score is good, downgrade or reject when:
- category is too brand dominated
- review moat looks overwhelming
- compliance risk is high
- returns/fragility complexity is too high

## Daily sales range inference buckets

Use ranges rather than fake precision:
- 10-30 / day
- 30-80 / day
- 80-150 / day
- 150-300 / day

Prefer categories/products that look capable of roughly 30-150/day when competition remains survivable.
