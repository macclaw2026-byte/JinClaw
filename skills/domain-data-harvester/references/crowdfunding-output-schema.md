# Crowdfunding Output Schema

Use this schema when converting crowdfunding / innovation-source pages into structured opportunity evidence.

## Record fields

```text
concept_or_project:
source_family:
source_url:
platform:
problem_statement:
feature_innovation:
value_promise:
price_signal:
backing_or_social_signal:
manufacturing_complexity_clue:
marketplace_translation_potential:
non_infringing_abstraction:
evidence_strength:
confidence:
downstream_skill:
notes:
```

## Routing rule

### Route to `product-selection-engine`
Use fields such as:
- problem_statement
- feature_innovation
- value_promise
- marketplace_translation_potential
- non_infringing_abstraction
- manufacturing_complexity_clue

### Route to `runtime-evolution-loop`
Use when repeated patterns suggest:
- a new blue-ocean scanning heuristic
- a new branch/site should be added
- a new product-selection sub-framework is justified

## Output discipline

- do not confuse crowdfunding popularity with marketplace fit
- prefer abstracted insight over raw project hype
- preserve source/platform provenance
