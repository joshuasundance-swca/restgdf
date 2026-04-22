<!--
restgdf PR template (BL-55 / BL-59).

Thirteen mandatory sections + an AI-orchestration disclosure, mirroring
the skeleton the 3.0 rewrite PR used. Small PRs may leave a section as
"N/A" with a short justification; do not delete headings.

For trivial fixes (typo, single-line bug, README nit) you may replace
this template with a one-paragraph summary.
-->

## 1. Summary

One to three sentences: what landed, what problem it solves, any
headline perf/compat note.

## 2. Motivation

Why this change, why now. Link issues, prior discussion, or research
notes.

## 3. Why this shape (single PR vs phased)

Justify the PR boundary. For focused fixes: "single scope, <N files".
For rewrites / cross-cutting changes: enumerate the scope you're taking
at once and why splitting would cost more than it saves.

## 4. Changes (by area)

Grouped bullet list. Point at modules/files. Reviewers use this as a
table of contents.

## 5. Breaking changes

| API | Before | After | Shim? |
|-----|--------|-------|-------|
|     |        |       |       |

Leave the table empty with "None" above it if there are no breaking
changes.

## 6. Migration guide

Copy-paste recipes for consumers, or a link to `MIGRATION.md`.

## 7. Compat shim inventory

List any `DeprecationWarning` shims, PEP 562 `__getattr__` exports, or
multi-inherit exception bridges, with their scheduled removal version.

## 8. Testing

- Coverage delta (if measurable).
- New test files / test classes.
- Validation commands actually run locally (`pytest -q -m "not
  network"`, `pre-commit run --all-files`, Sphinx build, etc.).
- Any skipped / known-flaky tests.

## 9. Benchmarks

Quantitative comparisons where meaningful. Disclose regressions
honestly. "N/A — no perf-visible code path" is a valid entry.

## 10. Risks & mitigations

Subtle behavior changes, edge cases, upgrade pain. Include the
mitigation for each risk on the same row.

## 11. Rollback plan

How to revert. For merge-commit PRs: `git revert -m 1 <sha>`. For
published releases: pin the previous version, yank procedure.

## 12. Reviewer guide

Suggested reading order and any "focus here" hints for large diffs.
Non-goal: exhaustively reading every commit.

## 13. Future work

What is deliberately **not** in this PR and where it's tracked
(follow-up issues, session notes, etc.).

## 14. Orchestration & AI disclosure

<!--
Required (BL-59, adapted from the MicroPython #18842 / pyOpenSci LLM
policy convention). Pick one of the two declarations below and delete
the other. If any AI tooling was used, briefly describe how.
-->

- [ ] **I did not use Generative AI tools to produce this change.**
- [ ] **I used Generative AI tools, and a human has read, understood,
      and tested every line before submission.**

If the second applies, describe the workflow: tools / models used,
human gates (self-review, rubber-duck reviews, CI-green precondition),
subagent topology if multiple agents collaborated. Link any session
notes or plan files that document the process.
