---
name: cross-market-arbitrage-engine
description: Build and run a continuous cross-market arbitrage skill that discovers products from sell-side marketplaces such as Temu, Amazon, Walmart, and eBay, matches them against source-side marketplaces such as 1688, Yiwugo, and Made-in-China, filters restricted products, estimates sourcing and logistics cost, computes gross margin, chooses the best buy-platform and sell-platform combination, and sends daily Excel outputs to chat. Use when the goal is stable recurring arbitrage discovery, sourcing-vs-selling comparison, profitability screening, or daily shortlist generation with evidence and audit trails.
---

# Cross-Market Arbitrage Engine

Use this skill when the task is to continuously discover, compare, and report arbitrage candidates across buy-side and sell-side marketplaces.

## Core operating rules

- Build conclusions from repeatable evidence, not one-off screenshots or vibes.
- Prefer stable public extraction first; only escalate to browser / authorized session when needed.
- Treat restricted-product filtering and confidence scoring as hard gates, not advisory hints.
- Do not mark the cycle complete until:
  - discovery ran
  - source matching ran
  - margin calculation ran
  - report files were generated
  - retro / evolution artifacts were written

## Current marketplace scope

### Sell-side platforms
- Temu
- Amazon
- Walmart

### Source-side platforms
- 1688
- Yiwugo
- Made-in-China

## Current profitability rule

- `gross_profit_amount = sell_price - purchase_cost - 59*weight_kg - 35*weight_kg - 1.4`
- `gross_margin_rate = gross_profit_amount / sell_price`
- qualify only when both:
  - `base_margin_rate >= 0.45`
  - `conservative_margin_rate >= 0.45`

## Restricted-product gates

Always reject candidates that look like:

- lithium / battery products
- liquid products
- cosmetics / beauty chemistry
- food / ingestibles
- medicine / drug-like products

## Primary workflow

1. Discover demand-side candidates from sell-side marketplaces.
2. Normalize titles, attributes, and links into comparable entities.
3. Match each candidate to source-side supplier listings.
4. Estimate purchase cost, weight confidence, and logistics-adjusted profitability.
5. Choose the best buy-platform and sell-platform combination.
6. Write:
   - JSON evidence
   - Markdown summary
   - Excel report
7. Send results to chat when requested by the user or by scheduler logic.

## Execution script

Primary script:

- `scripts/run_cross_market_arbitrage_cycle.py`

Common modes:

- single test run:
  - `python3 skills/cross-market-arbitrage-engine/scripts/run_cross_market_arbitrage_cycle.py --mode once --test`
- normal once run:
  - `python3 skills/cross-market-arbitrage-engine/scripts/run_cross_market_arbitrage_cycle.py --mode once`
- continuous loop:
  - `python3 skills/cross-market-arbitrage-engine/scripts/run_cross_market_arbitrage_cycle.py --mode daemon`

## Output contract

The generated Excel should contain:

- `Qualified` sheet:
  - 产品名称
  - 目标采购平台
  - 采购链接
  - 目标售卖平台
  - 售卖链接

- `Audit` sheet:
  - audit and confidence fields used to justify the shortlist

## References

- Algorithm and confidence model:
  - `references/algorithm-and-data-model.md`
