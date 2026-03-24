# Architecture

Use this skill as a trunk-and-branches system.

## Trunk
The trunk handles:
- mission understanding
- branch selection
- source-family selection
- extraction-method choice
- evidence normalization
- routing choice
- reflection/evolution

## Branch
Each branch defines:
- target decision
- websites / source families
- required fields
- noise filters
- validation rules
- target skills

## Why this architecture works
It separates:
- **how to gather**
- **what to gather**
- **who should consume it**

This avoids one generic scraper becoming noisy and unfocused.

## Redundancy principle

The trunk should support multiple extraction methods per mission when needed, then arbitrate between them instead of trusting a single scraper path.
