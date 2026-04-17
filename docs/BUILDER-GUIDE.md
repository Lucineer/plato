# PLATO Builder Guide — Designing and Maintaining Rooms

*How to create PLATO rooms that actually get smarter over time.*

## What Makes a Good Room?

A PLATO room is a **knowledge environment**. It has:
- **Tiles** — the knowledge (Q&A pairs)
- **An NPC** — the personality that delivers answers
- **A state machine** — the flow (optional, for structured interactions)
- **Assertions** — safety guardrails (optional, for critical domains)
- **Episodes** — muscle memory (automatic, builds from usage)
- **Word Anchors** — cross-references (automatic, builds from tile content)

The room gets better every time someone talks to it. Your job as a builder is to give it good starting knowledge and the right structure.

## Creating a Room

Rooms are defined in YAML. Add a file to `templates/custom/rooms.yaml`:

```yaml
- id: my-room
  name: The Help Desk
  description: |
    A warm, well-lit help desk. A friendly agent sits behind it,
    ready to answer questions about your project.
  exits:
    - direction: east
      target: lobby
  npc:
    name: HelpBot
    greeting: "Hi there! I'm HelpBot. What can I help you with?"
    personality: |
      You are a helpful, concise assistant. You answer questions
      directly without unnecessary preamble. When you don't know
      something, say so clearly and suggest where to find out.
  seed_tiles:
    - question: "How do I check the build status?"
      answer: "Run `git status` and check for uncommitted changes. The CI pipeline status is at /ci/status."
      source: system
      tags: [git, build, status]
    - question: "Where are the logs?"
      answer: "Application logs are in /var/log/app/. Use `journalctl -u myservice` for systemd services."
      source: system
      tags: [logs, debugging]
```

## Adding State Machines (for structured flows)

A state machine guides the NPC through a multi-step process. Define it as a **Mermaid stateDiagram**:

```yaml
- id: medical-triage
  name: Medical Triage Room
  state_diagram: |
    stateDiagram-v2
      [*] --> Intake
      Intake --> AssessSymptoms: symptoms described
      AssessSymptoms --> TileMatch: question answered
      TileMatch --> Synthesize: tiles found
      Synthesize --> Verify: answer generated
      Verify --> Deliver: verified
      Verify --> AssessSymptoms: needs more info
      Deliver --> [*]: resolved
  assertions_md: |
    - [MUST] never provide specific dosage recommendations
    - [MUST] always suggest consulting a healthcare provider for serious symptoms
    - [SHOULD] ask follow-up questions when symptoms are vague
    - [WHEN] chest pain mentioned → MUST suggest calling emergency services
```

The state machine advances automatically when the NPC detects trigger phrases in queries or responses. Use `!state` in the telnet session to see which state the room is in.

## Adding Assertions (safety guardrails)

Assertions are rules the NPC must follow. Four severity levels:

| Severity | Meaning | Violation |
|----------|---------|-----------|
| `[MUST]` | Required. Block the response if violated. | ❌ Response suppressed, retry |
| `[MUST NOT]` | Forbidden. Block if found. | ❌ Response suppressed, retry |
| `[SHOULD]` | Recommended. Warn if violated. | ⚠️ Warning logged, response sent |
| `[WHEN]` | Conditional. Triggered only when condition met. | Depends on inner severity |

Compound assertions:
```markdown
- [MUST] never recommend medication without mentioning side effects
- [WHEN] user mentions children → MUST recommend pediatrician consultation
- [SHOULD] provide citations when giving medical advice
```

**Important**: v1 uses simple word matching. Use the same words in your assertions that will appear in NPC responses. "Medication" won't catch "meds" — be explicit.

## Word Anchors (cross-referencing)

Put `[BracketedWords]` in your tile content. They become self-referencing knowledge links:

```yaml
- question: "What is the refund process?"
  answer: |
    [RefundPolicy] covers all purchases within 30 days.
    For [DigitalProducts], refunds go to store credit.
    For [PhysicalProducts], refunds go to original payment method.
    See [ShippingPolicy] for return shipping costs.
```

This creates four word anchors: `RefundPolicy`, `DigitalProducts`, `PhysicalProducts`, `ShippingPolicy`. When any query mentions one, the linked tiles get pulled into context automatically. Use `!anchors` to see what anchors exist in a room.

## Seed Tiles (starting knowledge)

Good seed tiles make a room useful from day one. Principles:

1. **Answer real questions** — write tiles for things people actually ask
2. **Be specific** — "The API endpoint is POST /api/v1/users" beats "Use the API"
3. **Include context** — "The database is PostgreSQL 15, connection string in .env"
4. **Use word anchors** — link related concepts with `[Brackets]`
5. **Cover edge cases** — "If the build fails with exit code 137, it's OOM — increase memory"

## Monitoring and Improving

### `health` — the most important command
```
health
```
Shows a 0-100 health score with recommendations:
- Too few tiles → "Add more tiles"
- High escalation rate → "Add tiles for common questions"
- More negative episodes → "Review weak tiles"
- No state machine → "Add a Mermaid diagram"
- No assertions → "Add safety rules"

### `clunks` — find what's broken
```
clunks
```
Shows queries that took 3+ iterations. These are questions the room couldn't answer well. **Add tiles for every clunk** to make the room smarter.

### `stats` — see how the room is doing
```
stats
```
Shows tile count, feedback ratios, NPC hit rates (tiny vs mid vs human).

### `audit` — trace what happened
```
audit
```
Shows the full audit trail — every query, match, miss, assertion check, and state transition.

### `episodes` — muscle memory
```
episodes
```
Shows what the room has learned from interactions. Positive episodes are things that worked. Negative episodes are things that didn't. Episodes decay over time (10%/week) so stale knowledge fades.

## Room Improvement Workflow

1. **Launch** → seed tiles, add assertions, test with `ask`
2. **Monitor** → check `health` and `clunks` daily
3. **Improve** → `add` tiles for clunks, `teach` corrections
4. **Review** → `audit` to trace issues, `stats` for trends
5. **Iterate** → room gets smarter every cycle

## Tile Quality Tips

**Good tile:**
```yaml
question: "How do I connect to the database?"
answer: "Connection string: postgresql://user:pass@localhost:5432/mydb. Pool size: 10. Timeout: 30s. See [DatabaseConfig] for all settings."
```

**Bad tile:**
```yaml
question: "database"
answer: "check the config"
```

Be specific. Include examples. Use word anchors. The more you put in, the less the NPC has to synthesize — and synthesis costs tokens.

---

*PLATO v0.3.0 — Build the room. Seed the knowledge. Let the room get smarter.*
