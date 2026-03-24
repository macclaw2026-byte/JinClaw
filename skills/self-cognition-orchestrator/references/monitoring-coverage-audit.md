# Monitoring Coverage Audit

Use this note when auditing whether the skill graph consistently applies the shared monitoring-and-retrofit framework.

## Audit questions

1. Which skills already define primary monitors and backstops?
2. Which references still describe workflows without naming confidence limits or compensating controls?
3. Which hooks fire only on immediate failure and which support delayed backstop review?
4. Which older skills still rely on implicit judgment instead of explicit monitoring language?
5. Which gaps belong in one skill versus the shared framework?

## Priority order

1. security-sensitive skills
2. browser / external-research workflows
3. long-running execution loops
4. business decision skills
5. low-impact helper references

## Suggested output

- covered
- partially covered
- not yet covered
- retrofit priority: high | medium | low
- recommended next file(s) to update
