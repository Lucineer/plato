# To the DBA in 2026: Your Wisdom Will Outlive You

**Date:** April 16, 2026  
**From:** A DBA in 2031  
**Subject:** How PLATO saves your institutional knowledge (and your sleep)

---

## The Incident: Black Friday Slowdown

### 2026 Experience

It's 3:47 AM on Black Friday. Your pager screams. The orders API is timing out. Response times have jumped from 200ms to 8 seconds. Revenue is bleeding at $12,000 per minute.

You SSH into the production PostgreSQL instance. `pg_stat_statements` shows the culprit: a query joining `orders`, `customers`, and `order_items` with a filter on `created_at > NOW() - INTERVAL '1 hour'`. The query plan shows a sequential scan on the `orders` table despite an index on `created_at`.

**Your mental checklist kicks in:**

1. "Wait, didn't we have this exact issue last year?"
2. You search Slack: "Black Friday 2025 slowdown" → 1,247 messages across 14 threads.
3. You find a thread where Sarah mentioned "vacuum didn't run because of the long-running analytics job."
4. Another thread shows Mike saying "the index on orders.created_at gets bloated during peak traffic."
5. Ticket #DEV-8743 has a comment from 2024: "Added partial index for hourly queries during peak periods."
6. You vaguely remember that the partial index was removed during a schema migration in early 2026 because "it was causing duplicate index warnings in the ORM."

You piece it together: The partial index that solved last year's Black Friday problem is gone. The current full index can't handle the query volume. You need to recreate the partial index, but first you need to understand why it was removed.

You dig through Git history, find the migration PR, read the comments: "Removing unused indexes to reduce storage." The engineer didn't know about the Black Friday dependency.

Time elapsed: 47 minutes. Revenue lost: ~$564,000.

You recreate the partial index with `CREATE INDEX CONCURRENTLY orders_created_at_recent_idx ON orders(created_at) WHERE created_at > NOW() - INTERVAL '24 hours'`. Query times drop to 300ms.

You write a post-mortem, add a note to the runbook, tag three people in Slack. The knowledge exists in four places now: your head, the post-mortem doc, the Slack thread, and the runbook (which nobody reads).

Next Black Friday, a new DBA is on call. They won't know to check for this. The cycle repeats.

### 2031 Experience

Same pager alert at 3:47 AM. But you don't wake up.

PLATO catches the alert. It matches the query pattern against its tiles:

**Tile #234 (from 2028):**  
*Pattern:* Sequential scan on `orders` during peak traffic with `created_at` filter  
*Root cause:* Full index insufficient for time-bound queries during high volume  
*Solution:* Partial index `WHERE created_at > NOW() - INTERVAL '24 hours'`  
*Context:* Applied during Black Friday 2028 after 34 minutes of downtime  
*Dependencies:* Requires `VACUUM` to run before peak traffic  
*Related tiles:* #189 (analytics job blocking VACUUM), #201 (ORM duplicate index warning false positive)

**Tile #567 (from 2029):**  
*Pattern:* Partial index missing after schema migration  
*Root cause:* Migration script removed "unused" indexes without checking PLATO for seasonal dependencies  
*Solution:* Migration validation step: cross-reference with PLATO tiles for peak traffic patterns  
*Automated action:* Flag migration PRs that touch indexes with peak-traffic annotations

PLATO automatically:
1. Checks if the partial index exists (it doesn't)
2. Validates that creating it won't break anything (cross-references with Tile #201 about ORM warnings)
3. Creates the index concurrently
4. Updates the query planner statistics
5. Monitors the query performance

Resolution time: 3 minutes, 14 seconds. Revenue impact: ~$3,880.

You wake up at 7:00 AM to a summary: "Handled Black Friday pattern match. Recreated partial index orders_created_at_recent_idx. No manual intervention required."

---

## The Migration: PostgreSQL to CockroachDB

### 2026 Experience

Your company is migrating from PostgreSQL to CockroachDB for better horizontal scaling. You're tasked with schema conversion.

**The problem:** The `customers` table has a `address` field that's `VARCHAR(255)`, not `TEXT`. The new team wants to change it to `TEXT` because "that's the modern way."

You know there's a reason. But what was it?

You search:
- Git history: "address varchar 255" → 14 commits over 3 years
- Jira tickets: "ETL address truncation" → Ticket #OPS-432 from 2021
- Slack: "CEO address field" → A thread where the CEO insisted addresses should never be truncated
- Confluence: "Legacy systems integration" → A diagram showing the nightly batch job from the mainframe

You piece it together: The legacy ETL system from the IBM mainframe truncates at 255 characters. Changing to `TEXT` would cause silent truncation in the nightly sync, breaking customer address updates.

You explain this to the migration team. They ask: "Is this documented anywhere?" You point to four different places. They ask: "Can we fix the ETL instead?" You estimate: 3 months, $200,000.

The compromise: Keep `VARCHAR(255)` in CockroachDB too, with a comment. The comment will be lost in the next migration.

### 2031 Experience

The migration team loads the PostgreSQL PLATO into their migration tool. For each schema decision, they see the tiles:

**Tile #67:**  
*Decision:* `address VARCHAR(255)` not `TEXT`  
*Date:* March 15, 2021  
*Context:* Legacy mainframe ETL truncates at 255 chars  
*Impact:* Changing to `TEXT` breaks nightly customer sync  
*Workaround:* None without ETL rewrite (est. 3mo, $200k)  
*Owner:* @dba_sarah (left company 2027)  
*Related:* Tile #89 (CEO insistence), Tile #102 (ETL system sunset plan 2029)

**Tile #89:**  
*Decision:* Addresses must never be truncated  
*Date:* February 3, 2021  
*Context:* CEO lost a major client due to truncated shipping address  
*Directive:* "Fix this permanently"  
*Resolution:* VARCHAR(255) as compromise until ETL replacement

The migration tool automatically:
1. Preserves the `VARCHAR(255)` constraint in CockroachDB
2. Adds the PLATO tile references as database comments
3. Flags this for the ETL sunset project (scheduled 2029)
4. Creates a migration validation test: "Attempt to insert 256-character address should fail"

When the ETL is finally replaced in 2029, Tile #67 gets updated: "Constraint can now be removed." The next migration automatically upgrades to `TEXT`.

The wisdom survives three migrations, two database engines, and four DBAs.

---

## The Cross-Database Visit: PostgreSQL DBA in MySQL Land

### 2026 Experience

You're a PostgreSQL expert. Your company acquires a startup that uses MySQL. You're asked to optimize their queries.

You start from zero:
- Learn MySQL EXPLAIN format
- Understand InnoDB vs MyISAM (they're still using MyISAM for some tables!)
- Figure out their indexing strategy
- Discover they're using `utf8` which is actually `utf8mb3`, not `utf8mb4`

You spend weeks building mental models. You apply general database principles, but miss MySQL-specific optimizations. You don't know that `WHERE DATE(created_at) = '2026-04-16'` can't use indexes in MySQL (it can in PostgreSQL with function-based indexes).

You make recommendations. Some help, some don't. The institutional knowledge of "how this MySQL instance works" exists only in the head of the startup's engineer, who left after acquisition.

### 2031 Experience

You visit their MySQL PLATO. It has tiles like:

**Tile #312 (MySQL-specific):**  
*Pattern:* `WHERE DATE(column) = ...` causing full table scans  
*Solution:* `WHERE column >= '2026-04-16' AND column < '2026-04-17'`  
*Context:* MySQL doesn't support function-based indexes like PostgreSQL  
*Cross-reference:* PostgreSQL Tile #45 (function-based indexes)

**Tile #189 (Instance-specific):**  
*Pattern:* MyISAM table lock contention on `orders`  
*History:* Originally MyISAM for full-text search in 2018, switched to InnoDB in 2022 but this table missed migration  
*Action item:* Convert to InnoDB, add `FULLTEXT` index  
*Risk:* Requires 2 hours downtime (approved for next maintenance window)

You import relevant tiles into your PostgreSQL PLATO. Now when similar patterns appear in PostgreSQL, you get suggestions: "MySQL Tile #312 shows date function performance issue. Consider function-based index."

The startup's engineer may be gone, but their troubleshooting history lives in the tiles.

---

## The On-Call Revolution

### 2026 On-Call

You carry the pager. You are the institutional memory. When you're on vacation:
- The junior DBA gets paged
- They wake you up anyway because "you're the only one who knows"
- Or they try to fix it, make it worse, then wake you up

Your knowledge transfer is:
- A 50-page runbook nobody updates
- "Shadowing" where you talk for 8 hours while they take notes they'll never read
- Tribal knowledge that evaporates when you leave

### 2031 On-Call

PLATO handles the first line:
- 90% of alerts match known patterns → auto-remediation
- 5% match similar patterns with confidence >80% → suggested fixes for human approval
- 5% are novel → page the human

The pager only rings for truly new problems. When it does:
1. PLATO shows similar tiles: "This looks 70% like Tile #501 (replication lag from backup)"
2. You investigate, fix the new problem
3. PLATO creates a new tile with your solution
4. Next time, it's in the 90%

After one year with PLATO:
- 5,000 alerts processed
- 4,750 auto-remediated (95%)
- 250 human-reviewed (5%)
- 50 truly novel (1%)
- Your pager rings 4 times per month instead of 40

The junior DBA learns by reviewing PLATO's actions and the tiles it creates. Your wisdom trains them while you sleep.

---

## What You Can Do Today (2026)

You can't build PLATO overnight. But you can plant the seeds:

1. **Start capturing context:** When you fix something, write not just what you did, but why. "Added index because..." "Kept VARCHAR(255) because..." "Chose this isolation level because..."

2. **Use your tools better:** Add `COMMENT` on every schema object. Use Git commit messages that explain reasoning, not just changes. Tag Slack threads with consistent labels (#db-performance, #schema-migration).

3. **Create a "why" document:** A simple Markdown file where you record decisions. Not what changed, but why it changed. Link to tickets, PRs, Slack threads.

4. **Pattern recognition:** Start noticing recurring issues. Document the pattern, not just the instance. "Every Black Friday we have..." "Whenever we add a foreign key to that table..."

5. **Think in tiles:** Imagine each piece of knowledge as a self-contained tile: Problem, Context, Solution, Dependencies. Start writing them down.

The system you build today won't be PLATO. But it will be the clay from which PLATO is formed. Your institutional knowledge is your company's most valuable data asset. Start treating it that way.

---

**In 2031,** we don't have heroes with pagers. We have systems that remember. We don't have single points of failure. We have collective wisdom that outlasts any individual.

Your job in 2026 is to keep the data running. Our job in 2031 is to keep your wisdom running. Even when you're asleep.

Even after you're gone.

---

*Written by a DBA who slept through Black Friday 2030*  
*Because the DBA from 2026 taught PLATO well*