# Skill Security Audit Checklist

Use this checklist during third-party skill review.

Apply the shared monitoring standard from `../../self-cognition-orchestrator/references/monitoring-and-retrofit-framework.md` so audits include primary signals, backstops, and replacement triggers instead of one-pass judgment.

## Gate rule

- Is this a non-bundled / third-party skill?
- If yes, audit before any install.
- If review is incomplete or source is unclear, do not install.

## Source review

- Is the source identifiable?
- Is there a public repo or readable folder?
- Is there version history?
- Is the package plain-text and inspectable?
- Are there binaries, nested archives, or symlinks?

## File tree review

- `SKILL.md`
- `scripts/`
- `references/`
- `assets/`
- hidden files
- symlinks
- binaries
- installer-like files

## Script review red flags

- remote download and execute
- credential harvesting
- token / key / password / secret leakage or publication risk
- broad file reads
- broad file deletes
- privilege escalation
- background persistence
- hidden telemetry
- unexplained network calls
- path traversal
- unsafe shell interpolation
- writes outside workspace without need

## Capability summary questions

- Does it access the network?
- Does it write outside the workspace?
- Does it require secrets?
- Does it install dependencies automatically?
- Does it use browser control?
- Does it spawn background jobs?
- Does it modify startup/services/login items?

## Monitoring questions

- What is the primary audit signal making this look safe or risky?
- What backstop check would overturn that first impression?
- What sensitive-boundary monitor applies here?
- If installation is unwise, is a safer in-house replacement feasible?

## Area scores

Score each as Low / Medium / High:

- Source trust
- Code transparency
- Execution power
- Data access
- Network/exfiltration risk
- Persistence/system modification risk

## Recommendation guide

### A / ALLOW

- source is clear
- files are readable
- no obvious malicious behavior
- scope is narrow
- no major red flags

### B / ALLOW WITH CAUTION

- useful but powerful
- network/API/system interaction present
- should be sandboxed or limited
- no obvious malicious behavior, but non-trivial risk exists
- prefer safer local replacement before installing original

### C / BLOCK

- opaque or suspicious
- destructive or stealthy behavior
- unjustified secrets/system access
- cannot be confidently reviewed
- download-and-execute or persistence behavior without strong justification
- safer replacement should be considered instead
