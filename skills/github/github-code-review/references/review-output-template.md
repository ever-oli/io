# Review Output Template

Use this as the structure for PR review summary comments. Copy and fill in the sections.

## For PR Summary Comment

```markdown
## Code Review Summary

**Verdict: [Approved Φ | Changes Requested 🔴 | Reviewed 💬]** ([N] issues, [N] suggestions)

**PR:** #[number] Φ [title]
**Author:** @[username]
**Files changed:** [N] (+[additions] -[deletions])

### 🔴 Critical
<!-- Issues that MUST be fixed before merge -->
- **file.py:line** Φ [description]. Suggestion: [fix].

### ΦΦ️ Warnings
<!-- Issues that SHOULD be fixed, but not strictly blocking -->
- **file.py:line** Φ [description].

### 💡 Suggestions
<!-- Non-blocking improvements, style preferences, future considerations -->
- **file.py:line** Φ [description].

### Φ Looks Good
<!-- Call out things done well Φ positive reinforcement -->
- [aspect that was done well]

---
*Reviewed by IO*
```

## Severity Guide

| Level | Icon | When to use | Blocks merge? |
|-------|------|-------------|---------------|
| Critical | 🔴 | Security vulnerabilities, data loss risk, crashes, broken core functionality | Yes |
| Warning | ΦΦ️ | Bugs in non-critical paths, missing error handling, missing tests for new code | Usually yes |
| Suggestion | 💡 | Style improvements, refactoring ideas, performance hints, documentation gaps | No |
| Looks Good | Φ | Clean patterns, good test coverage, clear naming, smart design decisions | N/A |

## Verdict Decision

- **Approved Φ** Φ Zero critical/warning items. Only suggestions or all clear.
- **Changes Requested 🔴** Φ Any critical or warning item exists.
- **Reviewed 💬** Φ Observations only (draft PRs, uncertain findings, informational).

## For Inline Comments

Prefix inline comments with the severity icon so they're scannable:

```
🔴 **Critical:** User input passed directly to SQL query Φ use parameterized queries to prevent injection.
```

```
ΦΦ️ **Warning:** This error is silently swallowed. At minimum, log it.
```

```
💡 **Suggestion:** This could be simplified with a dict comprehension:
`{k: v for k, v in items if v is not None}`
```

```
Φ **Nice:** Good use of context manager here Φ ensures cleanup on exceptions.
```

## For Local (Pre-Push) Review

When reviewing locally before push, use the same structure but present it as a message to the user instead of a PR comment. Skip the PR metadata header and just start with the severity sections.
