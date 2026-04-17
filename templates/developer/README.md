# templates/developer/

**The Developer Workshop.** Where code meets memory.

A workspace for software development decisions, debugging, architecture, and deployment. Every codebase decision documented. Every bug's root cause recorded. Every deployment's aftermath captured. The room remembers what you'd otherwise forget.

## Rooms

| Room | NPC | Purpose |
|------|-----|---------|
| **dev_workshop** | The Architect | Central workspace. Codebase decisions. |
| **dev_decisions** | The Scribe | Decision ledger. ADR-style with reasoning. |
| **dev_debug** | The Investigator | Debug bench. Solved bugs and root causes. |
| **dev_deploy** | The Operator | Deployment board. CI/CD state and runbooks. |

## The Problem This Solves

Most software is dead. It runs, it serves, it collects dust. Nobody remembers the decisions that shaped it. New developers make the same mistakes. Users ask the same questions. The support team answers the same tickets.

This room makes software alive. Not by changing the code — by accumulating the experience around it.

## Seed Knowledge

- *How should I structure a new project?* → Start with the constraints.
- *How do I debug a production issue?* → Reproduce, add logging, isolate, fix, test, document.
- *When should I rewrite vs refactor?* → Rewrite when the architecture fundamentally doesn't fit anymore.
- *How do I document an architectural decision?* → Decision, context, alternatives, reasoning, consequences.
- *How do I handle a failed deployment?* → Rollback plan BEFORE deploy. Monitor 30 min. Document failure.
- *How do I set up CI/CD?* → Three gates: syntax, tests, health check.

## The Decision Ledger

The Scribe records every architectural decision with its full context. Before you make a choice, check if someone already solved a similar problem. The ledger is the most valuable thing in this room — it's the compressed experience of every developer who came before.

## For AI Agents

- Connect via telnet and pair-program with the human
- Search debug bench for similar issues before investigating
- Add architectural decision tiles from code review
- Generate runbooks from deployment tiles
- Create test case tiles from bug pattern analysis

---

*"Two codebases, identical except one has a debug bench with 500 solved bugs. The second ships features 3x faster."*
