#!/usr/bin/env python3
"""M4 exit oracle: disposition census for the 61 confirmed audit findings.

Dev tooling only — excluded from the wheel (``[tool.setuptools.packages.find]``
``include = ["restgdf*"]`` never picks up ``scripts/``; verified against
``pyproject.toml`` directly rather than assumed).

Reads two repo-committed sources of truth (no network, no scratch/ dependency
— scratch is git-excluded and this script must work from a bare checkout):

* ``audit-recommendations/findings.json`` — the 61 confirmed findings.
* ``audit-recommendations/plan/99-traceability.md`` — the finding -> work-item
  forward map (``## Forward map`` table).

...then asks git itself which work items actually landed, rather than trusting
the traceability doc's milestone column (which is known-stale: it was pinned
at audit time and this program repeatedly pulled items forward across
milestones — e.g. W4-6/W5-9/W5-10/W5-11 landed in the M1 PR #196 typing stack
though traceability tags them M2).

Evidence model (deliberately conservative — see CLAUDE.md's "green gate can
lie" / "a LANDED claim whose commit doesn't contain the change = REFUTED"):

* This program's convention cites work-item IDs (``W2-1``) and/or the
  underlying finding ID (``AUTH-01``) in parens on (a) a commit's own top
  subject line, and (b) any ``* <subject>`` bullet line a squash merge
  preserves from its constituent commits (git's default squash-message
  format) — some commits cite only the work item, some only the finding,
  some both (e.g. #195's fix bullet cites only ``(AUTH-01)``, never
  ``W2-1``, even though its own body says "W2-1 / AUTH-01."). Only IDs
  cited on one of THOSE lines count as a landing declaration — an ID merely
  discussed in narrative body prose (e.g. a deferral note explaining why a
  *different* item's fix also touches the same file) is explicitly NOT
  treated as a landing declaration. This distinction is load-bearing: W2-5
  is narrated inside the #209/#210 commit bodies (which do touch
  restgdf/utils/token.py) but never cited on any subject/bullet line —
  without the distinction it would false-positive as LANDED by file-overlap
  alone. A finding-ID citation counts as landing evidence for every work
  item the traceability map assigns to that finding (checked against that
  SAME finding's file list only — it says nothing about the item's other
  owning findings, if split across more than one).
* A declared item is only counted LANDED for a given finding if the
  commit's actual diff (``git diff-tree --name-only``) touches at least one
  file the finding names in ``findings.json``. A subject-line citation with
  no matching file in the diff is downgraded to MESSAGE_ONLY — reported, not
  silently promoted to LANDED.
* Deferred AND decision-closed evidence come from EXACTLY ONE source: the
  curated ``## Deliberate deferrals`` section of
  ``audit-recommendations/plan/99-traceability.md`` — see
  ``parse_deliberate_deferrals_section``. Free-text commit-body narration
  is DELIBERATELY NOT scanned for either disposition, after three
  recurrences of the identical self-contamination shape (a commit's own
  body, describing THIS script's bugfix history, mentions a real item ID
  next to deferral-shaped vocabulary — "owner"+"trigger"/"NO-GO"/"deferred"
  — while narrating an unrelated topic, and gets misread as that item's own
  deferral record): (1) the genesis commit (``e65bf75``) did this to
  AUTH-01/W2-1; (2) after a clause-scoping + dev-tooling-commit-exclusion
  fix, the PR #213 GitHub squash merge (``701ddbf``) reproduced it for
  AUTH-01/W2-1 AND a NEW PAGINATION-03/W4-3, because the squash rewrote the
  subject to the PR title and no "(dev-tooling)" scope survived; (3) after
  a diff-confinement exclusion fix (a commit was excluded if its ENTIRE
  diff stayed inside this script's own two files), the PR #214 squash merge
  (``05d3e34``) reproduced it a THIRD time for the same two items, because
  that squash's diff touched ``findings.json``/``99-traceability.md`` —
  real repo files that same PR legitimately edited — so the diff-
  confinement check no longer excluded it either. Each fix bought exactly
  one more recurrence before the next squash broke it again: free-text
  commit-body narration can never be made safe against a squash merge that
  narrates this program's own bug history using the real vocabulary of the
  thing it is trying not to match. The curated traceability section is
  different in kind, not just degree — it is maintained BY the program's
  coordinator as the durable record, not incidentally produced as a
  byproduct of *some* commit's message — so it is the only deferred/
  decision-closed evidence source, full stop; commit scanning remains for
  LANDED evidence only (the two bullets above, unchanged).
* A finding's owning item can resolve DECISION-CLOSED via that same
  section, for an item explicitly recorded there as *confirm-only*
  (Path a) — see ``parse_deliberate_deferrals_section``. This covers a
  real terminal disposition with ZERO commits by design (W3-6/DOCS-02
  resolved by verifying existing behavior, not by shipping a change),
  which no commit-based evidence source can ever see.

Disposition per finding, in this precedence order (this is aggregated across
every work item the traceability map assigns to the finding — split-ownership
findings need ALL owning items resolved to reach a terminal state):

1. GAP        — at least one owning item has no landing evidence, no
                 decision-close record, and no deferral record. This is the
                 open punch list — NOT a script failure.
2. DEFERRED   — no GAP items, and at least one owning item is deferred.
3. DECISION-CLOSED — no GAP/DEFERRED items, and at least one owning item is
                 decision-closed (the rest LANDED).
4. LANDED     — every owning item is LANDED.

A structural ORPHAN (a finding absent from the traceability map, or a
traceability row citing a finding ID absent from findings.json) is a data
integrity bug, not a punch-list item, and is the one condition that makes
this script exit non-zero.

Usage::

    python scripts/audit_disposition.py                 # human table + JSON
    python scripts/audit_disposition.py --format json    # JSON only
    python scripts/audit_disposition.py --format table   # human table only
    python scripts/audit_disposition.py --repo-root PATH # non-default checkout
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404 - read-only `git log`/`git diff-tree` on the local repo
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FINDINGS_REL = Path("audit-recommendations/findings.json")
_TRACEABILITY_REL = Path("audit-recommendations/plan/99-traceability.md")
_LEDGER_REL = Path("audit-recommendations/plan/PROGRAM-LEDGER.md")

# The traceability doc's own clarifications section, where a terminal
# disposition can be recorded WITHOUT any commit at all (e.g. W3-6 resolved
# confirm-only by verifying existing behavior, never by shipping a change).
_DELIBERATE_DEFERRALS_HEADING = "## Deliberate deferrals"

# "confirm-only" / "decision-closed" — the traceability doc's own wording
# for a terminal, non-landing, non-deferred disposition (e.g. the real
# W3-6 clarification bullet). Deliberately narrower than
# `_DEFERRED_MARKER_RE` below: a bullet using ONE of these two vocabularies
# should never also match the other for the same item in this doc.
_DECISION_CLOSED_MARKER_RE = re.compile(r"confirm-only|decision-closed", re.IGNORECASE)

# "DEFERRED" — the traceability doc's own wording for a recorded deferral
# (e.g. the real ERRTAX-03/W2-5 bullet: "DEFERRED (NO-GO), M3 ..."). This
# is now the ONLY place a deferral is ever read from — see
# `parse_deliberate_deferrals_section`'s docstring for why free-text
# commit-body narration was removed as a deferral evidence source entirely.
_DEFERRED_MARKER_RE = re.compile(r"\bdeferred\b", re.IGNORECASE)

# Same-major shorthand ("W3-2/4" == W3-2, W3-4) AND plain IDs ("W2-2"). Cross-
# major chains ("W4-6/W5-9") fall out naturally: the continuation only grabs
# digits, so it stops at the next literal "W".
_ITEM_GROUP_RE = re.compile(r"\bW(\d+)-(\d+(?:/\d+)*)\b")

_BULLET_RE = re.compile(r"^\* (.+)$", re.MULTILINE)

# A finding ID looks like "AUTH-01": >=2 uppercase letters, so it can never
# collide with a work-item token like "W2-1" (single letter before the digit).
_FINDING_ID_RE = re.compile(r"\b[A-Z]{2,}-\d+\b")


def extract_all_items(text: str) -> set[str]:
    """Every work-item ID mentioned anywhere in ``text`` (subject shorthand aware)."""
    items: set[str] = set()
    for major, nums in _ITEM_GROUP_RE.findall(text):
        for n in nums.split("/"):
            items.add(f"W{major}-{n}")
    return items


def extract_finding_ids(text: str, known_finding_ids: set[str]) -> set[str]:
    """Every KNOWN finding ID (e.g. ``AUTH-01``) mentioned anywhere in ``text``."""
    return {m for m in _FINDING_ID_RE.findall(text) if m in known_finding_ids}


def declaration_lines(commit_message: str) -> list[str]:
    """The commit's own subject plus every squash-preserved ``* subject`` bullet.

    These are the only lines this program's convention uses to declare "this
    change closes work item X" — see the module docstring's evidence model.
    """
    lines = [commit_message.splitlines()[0]] if commit_message.strip() else []
    lines.extend(_BULLET_RE.findall(commit_message))
    return lines


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    id: str
    axis: str
    title: str
    severity: str
    files: list[str]


@dataclass
class CommitRecord:
    sha: str
    message: str


@dataclass
class Evidence:
    kind: str  # "commit" | "ledger" | "traceability"
    source: str  # sha or file name
    snippet: str


def load_findings(repo_root: Path) -> list[Finding]:
    raw = json.loads((repo_root / _FINDINGS_REL).read_text(encoding="utf-8"))
    return [
        Finding(
            id=entry["id"],
            axis=entry["axis"],
            title=entry["title"],
            severity=entry["severity"],
            files=list(entry.get("files", [])),
        )
        for entry in raw
    ]


def load_forward_map(repo_root: Path) -> dict[str, list[str]]:
    """Parse the ``## Forward map`` table: finding ID -> owning work-item IDs.

    Deliberately column-POSITION-robust rather than column-COUNT-fragile: a
    fixed 5-group regex over ``|``-split cells breaks the moment a title cell
    contains its own literal ``|`` (e.g. TYPING-04's title quotes
    `` `session: ClientSession | None` `` — that one embedded pipe silently
    orphaned the finding on a first draft of this parser, since the row then
    split into 6 cells instead of the expected 5 and matched nothing). Take
    the ID from the FIRST cell and the work-items column from the SECOND-TO-
    LAST cell instead, so an arbitrary number of pipes inside the title in
    between never shifts either anchor.
    """
    text = (repo_root / _TRACEABILITY_REL).read_text(encoding="utf-8")
    forward: dict[str, list[str]] = {}
    in_forward_section = False
    for line in text.splitlines():
        if line.startswith("## Forward map"):
            in_forward_section = True
            continue
        if in_forward_section and line.startswith("## "):
            break
        if not in_forward_section:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 5:
            continue
        id_match = re.fullmatch(r"`([A-Z]+-\d+)`", cells[0])
        if not id_match:
            continue  # header / separator / malformed row
        finding_id = id_match.group(1)
        items = sorted(extract_all_items(cells[-2]))
        if items:
            forward[finding_id] = items
    return forward


def git_log_records(repo_root: Path) -> list[CommitRecord]:
    """Every reachable commit's (sha, full message), oldest git can find first."""
    sep = "\x1e"
    out = subprocess.run(  # nosec B603 B607 - fixed argv, read-only git log
        ["git", "log", "--all", f"--format=%H%x1f%B{sep}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    records = []
    for chunk in out.split(sep):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        sha, _, message = chunk.partition("\x1f")
        records.append(CommitRecord(sha=sha, message=message))
    return records


def commit_files(repo_root: Path, sha: str) -> set[str]:
    out = subprocess.run(  # nosec B603 B607 - fixed argv, read-only git diff-tree
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def _markdown_section(text: str, heading: str) -> str:
    """Lines between a top-level ``heading`` (e.g. ``## Deliberate
    deferrals``, matched by prefix) and the next ``## `` heading, or EOF.
    """
    lines: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith(heading):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evidence mining
# ---------------------------------------------------------------------------


def build_declared_landings(
    commits: list[CommitRecord],
    known_finding_ids: set[str],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """(work-item -> SHAs, finding-id -> SHAs) that DECLARE closing it (subject/bullet)."""
    declared_items: dict[str, list[str]] = {}
    declared_findings: dict[str, list[str]] = {}
    for commit in commits:
        items: set[str] = set()
        finding_ids: set[str] = set()
        for line in declaration_lines(commit.message):
            items |= extract_all_items(line)
            finding_ids |= extract_finding_ids(line, known_finding_ids)
        for item in items:
            declared_items.setdefault(item, []).append(commit.sha)
        for fid in finding_ids:
            declared_findings.setdefault(fid, []).append(commit.sha)
    return declared_items, declared_findings


def _item_clauses(paragraph: str) -> dict[str, str]:
    """Map each work-item ID mentioned in ``paragraph`` to the
    semicolon-delimited clause it appears in (the whole paragraph if there
    are no semicolons at all).

    A single blank-line-delimited paragraph (or, now, a single traceability
    bullet — see ``parse_deliberate_deferrals_section``) can legitimately
    narrate several UNRELATED topics in one breath — semicolons are this
    repo's prose convention for that. Scoping the "explicit marker adjacent
    to this item" eligibility check to the item's own clause, rather than
    the whole paragraph/bullet, is what keeps an unrelated co-mentioned item
    from inheriting a marker that actually describes a DIFFERENT clause's
    topic — see ``parse_deliberate_deferrals_section``'s docstring for the
    real W3-6/W6-7 example this fixes. If the same item happens to appear in
    more than one clause, the first one wins (good enough — no known real
    case needs the others).
    """
    clauses: dict[str, str] = {}
    for clause in paragraph.split(";"):
        for item in extract_all_items(clause):
            clauses.setdefault(item, clause)
    return clauses


def parse_deliberate_deferrals_section(
    repo_root: Path,
) -> tuple[dict[str, Evidence], dict[str, Evidence]]:
    """The ONE evidence source for deferred AND decision-closed dispositions:
    ``99-traceability.md``'s "## Deliberate deferrals" section. Returns
    (deferred, decision_closed).

    Free-text commit-body narration used to also feed this (a paragraph
    naming BOTH "owner" and "trigger" was a deferral record; "no-go" alone
    was a decision-close record) — it was removed ENTIRELY after three
    recurrences of the same self-contamination shape, each surviving the
    previous fix (see the module docstring for the full blow-by-blow: the
    genesis commit ``e65bf75``, then the PR #213 squash ``701ddbf``, then
    the PR #214 squash ``05d3e34`` — every one of this program's own
    commits that narrates its bugfix history in prose is, definitionally,
    a commit whose body mentions real item IDs next to deferral-shaped
    vocabulary while talking about something else, and no exclusion rule
    keyed off subject text or diff shape survived being squash-merged by
    a tool that cannot know to preserve it). There is no reliable way to
    distinguish "this commit is ABOUT a deferral" from "this commit is
    ABOUT the bug where commits get mistaken for being about a deferral"
    from the commit's own free text — so commit bodies are no longer read
    for this at all, structurally, not just more carefully.

    The curated traceability section doesn't have this problem: it is
    maintained BY the program's coordinator as the durable record, not
    incidentally produced as a byproduct of some unrelated commit's
    message. "DEFERRED" (``_DEFERRED_MARKER_RE``, e.g. the real
    ERRTAX-03/W2-5 bullet: "DEFERRED (NO-GO), M3 ...") and "confirm-only"/
    "decision-closed" (``_DECISION_CLOSED_MARKER_RE``, e.g. the real W3-6
    bullet) are this doc's own two vocabularies for the two dispositions;
    they don't co-occur for the same item in the current document, but
    DEFERRED wins if they ever did (mirrors the historical precedence of
    the now-removed commit-body scanner).

    The section legitimately narrates SEVERAL items in one place (the
    ERRTAX-03/W2-5 DEFERRED record, a milestone-label correction for
    W4-6/W5-9/W5-10/W5-11, and the confirm-only clarification for W3-6), so
    this reuses ``_item_clauses`` to scope each marker to the SAME
    semicolon-delimited clause as the item's own mention, not the whole
    bullet. This matters here too: the real W3-6 bullet's own clause says
    "...resolved as confirm-only (Path a) in M2/PR #203: the
    timeout/concurrency env vars were verified wired..."; its NEXT clause
    (after a semicolon) says "...the documentation rows were corrected
    under W6-7 (M4)" — W6-7 is a different, genuinely LANDED item that
    happens to be name-dropped as a cross-reference in the SAME bullet.
    Without clause-scoping, W6-7 would also be marked DECISION_CLOSED here,
    silently overriding its real LANDED evidence (``item_status_for_finding``
    checks ``decision_closed``/``deferred`` before ever consulting
    commit-based evidence) — for DOCS-02 itself this happens to still net
    out to the same finding-level disposition (DOCS-02 already needs its
    OTHER owning item, W3-6, to reach DECISION-CLOSED), but W6-7 is ALSO
    TELEMETRY-01's other owning item, where it would silently flip a truly
    LANDED finding to DECISION-CLOSED. Regression-pinned by
    ``test_parse_deliberate_deferrals_section_does_not_leak_to_a_co_
    mentioned_item``.

    A bullet naming the W4-6/W5-9/W5-10/W5-11 milestone-label correction
    (no DEFERRED/confirm-only/decision-closed wording at all) matches
    neither marker and is naturally excluded from both dicts.
    """
    text = (repo_root / _TRACEABILITY_REL).read_text(encoding="utf-8")
    section = _markdown_section(text, _DELIBERATE_DEFERRALS_HEADING)
    deferred: dict[str, Evidence] = {}
    decision_closed: dict[str, Evidence] = {}
    for block in re.split(r"\n(?=- )", section):
        block = block.strip()
        if not block.startswith("- "):
            continue
        snippet = block[:400]
        for item, clause in _item_clauses(block).items():
            ev = Evidence(
                kind="traceability",
                source=str(_TRACEABILITY_REL),
                snippet=snippet,
            )
            if _DEFERRED_MARKER_RE.search(clause):
                deferred.setdefault(item, ev)
            elif _DECISION_CLOSED_MARKER_RE.search(clause):
                decision_closed.setdefault(item, ev)
    return deferred, decision_closed


# ---------------------------------------------------------------------------
# Disposition
# ---------------------------------------------------------------------------

_STATUS_RANK = {
    "GAP": 0,
    "MESSAGE_ONLY": 1,
    "DEFERRED": 2,
    "DECISION_CLOSED": 3,
    "LANDED": 4,
}


@dataclass
class ItemStatus:
    item: str
    status: str  # LANDED | DECISION_CLOSED | DEFERRED | MESSAGE_ONLY | GAP
    evidence: list[dict[str, str]]


def item_status_for_finding(
    item: str,
    finding: Finding,
    declared_landings: dict[str, list[str]],
    declared_findings: dict[str, list[str]],
    deferred: dict[str, Evidence],
    decision_closed: dict[str, Evidence],
    file_cache: dict[str, set[str]],
    repo_root: Path,
) -> ItemStatus:
    if item in deferred:
        ev = deferred[item]
        return ItemStatus(
            item,
            "DEFERRED",
            [{"kind": ev.kind, "source": ev.source, "snippet": ev.snippet}],
        )
    if item in decision_closed:
        ev = decision_closed[item]
        return ItemStatus(
            item,
            "DECISION_CLOSED",
            [{"kind": ev.kind, "source": ev.source, "snippet": ev.snippet}],
        )

    # Candidate commits: ones citing the work item directly, plus ones citing
    # THIS finding's ID (a finding-ID citation is evidence for every item the
    # finding owns, scoped to this finding's own file list below).
    shas = list(
        dict.fromkeys(
            declared_landings.get(item, []) + declared_findings.get(finding.id, []),
        ),
    )
    if not shas:
        return ItemStatus(item, "GAP", [])

    landed_evidence = []
    for sha in shas:
        if sha not in file_cache:
            file_cache[sha] = commit_files(repo_root, sha)
        touched = file_cache[sha]
        overlap = touched & set(finding.files)
        if overlap:
            landed_evidence.append(
                {
                    "kind": "commit",
                    "source": sha,
                    "snippet": f"touched: {sorted(overlap)}",
                },
            )

    if landed_evidence:
        return ItemStatus(item, "LANDED", landed_evidence)
    return ItemStatus(
        item,
        "MESSAGE_ONLY",
        [
            {"kind": "commit", "source": sha, "snippet": "cited, no file overlap"}
            for sha in shas
        ],
    )


def disposition_for_finding(item_statuses: list[ItemStatus]) -> str:
    """Roll up owning-item statuses to the finding's disposition (weakest link)."""
    worst = min(item_statuses, key=lambda s: _STATUS_RANK[s.status])
    if worst.status in {"GAP", "MESSAGE_ONLY"}:
        return "GAP"
    if worst.status == "DEFERRED":
        return "DEFERRED"
    if worst.status == "DECISION_CLOSED":
        return "DECISION-CLOSED"
    return "LANDED"


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def build_report(repo_root: Path) -> dict[str, Any]:
    findings = load_findings(repo_root)
    forward_map = load_forward_map(repo_root)
    commits = git_log_records(repo_root)

    finding_ids = {f.id for f in findings}
    declared_landings, declared_findings = build_declared_landings(commits, finding_ids)
    # Deferred + decision-closed evidence comes ONLY from the traceability
    # doc's curated "## Deliberate deferrals" section — see
    # parse_deliberate_deferrals_section's docstring for why free-text
    # commit-body narration was removed as a source entirely (three
    # recurrences of the same self-contamination shape, each surviving the
    # previous fix). LANDED evidence (above) is unaffected: it still reads
    # commit subject/bullet citations + file corroboration, unchanged.
    deferred, decision_closed = parse_deliberate_deferrals_section(repo_root)
    file_cache: dict[str, set[str]] = {}

    orphans_no_mapping = sorted(finding_ids - forward_map.keys())
    orphans_unknown_finding = sorted(forward_map.keys() - finding_ids)

    report_findings = []
    counts = {"LANDED": 0, "DECISION-CLOSED": 0, "DEFERRED": 0, "GAP": 0}
    gap_punch_list = []

    for finding in findings:
        owning_items = forward_map.get(finding.id, [])
        if not owning_items:
            # Structural orphan — still emit a row so `findings` always has
            # exactly len(findings) entries, but flag it distinctly.
            report_findings.append(
                {
                    "id": finding.id,
                    "severity": finding.severity,
                    "title": finding.title,
                    "owning_items": [],
                    "disposition": "ORPHAN",
                    "item_statuses": {},
                },
            )
            continue

        item_statuses = [
            item_status_for_finding(
                item,
                finding,
                declared_landings,
                declared_findings,
                deferred,
                decision_closed,
                file_cache,
                repo_root,
            )
            for item in owning_items
        ]
        disposition = disposition_for_finding(item_statuses)
        counts[disposition] += 1

        row = {
            "id": finding.id,
            "severity": finding.severity,
            "title": finding.title,
            "owning_items": owning_items,
            "disposition": disposition,
            "item_statuses": {
                s.item: {"status": s.status, "evidence": s.evidence}
                for s in item_statuses
            },
        }
        report_findings.append(row)

        if disposition == "GAP":
            unresolved = [
                s.item for s in item_statuses if s.status in {"GAP", "MESSAGE_ONLY"}
            ]
            gap_punch_list.append({"id": finding.id, "unresolved_items": unresolved})

    return {
        "totals": {
            "findings": len(findings),
            **counts,
            "orphans": len(orphans_no_mapping) + len(orphans_unknown_finding),
        },
        "orphans": {
            "findings_without_work_items": orphans_no_mapping,
            "traceability_rows_for_unknown_findings": orphans_unknown_finding,
        },
        "gap_punch_list": gap_punch_list,
        "findings": report_findings,
    }


def render_table(report: dict[str, Any]) -> str:
    lines = []
    totals = report["totals"]
    lines.append(
        f"M4 audit disposition census — {totals['findings']} findings "
        f"({totals['LANDED']} LANDED, {totals['DECISION-CLOSED']} DECISION-CLOSED, "
        f"{totals['DEFERRED']} DEFERRED, {totals['GAP']} GAP, "
        f"{totals['orphans']} ORPHAN)",
    )
    lines.append("")
    header = f"{'ID':<14} {'SEV':<8} {'DISPOSITION':<16} TITLE"
    lines.append(header)
    lines.append("-" * len(header))
    for row in report["findings"]:
        title = row["title"]
        if len(title) > 70:
            title = title[:67] + "..."
        lines.append(
            f"{row['id']:<14} {row['severity']:<8} {row['disposition']:<16} {title}",
        )

    if report["gap_punch_list"]:
        lines.append("")
        lines.append("Open punch list (real gaps — coordinator's M4 to-do):")
        for entry in report["gap_punch_list"]:
            lines.append(
                f"  - {entry['id']}: unresolved item(s) {entry['unresolved_items']}",
            )

    orphans = report["orphans"]
    if (
        orphans["findings_without_work_items"]
        or orphans["traceability_rows_for_unknown_findings"]
    ):
        lines.append("")
        lines.append("STRUCTURAL ORPHANS (data-integrity bug, not a punch-list item):")
        if orphans["findings_without_work_items"]:
            lines.append(
                f"  findings with no work-item mapping: {orphans['findings_without_work_items']}",
            )
        if orphans["traceability_rows_for_unknown_findings"]:
            lines.append(
                f"  traceability rows citing unknown findings: "
                f"{orphans['traceability_rows_for_unknown_findings']}",
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--format",
        choices=["both", "json", "table"],
        default="both",
        help="Output format (default: both — JSON then the human table).",
    )
    args = parser.parse_args(argv)

    report = build_report(args.repo_root)

    if args.format in {"both", "json"}:
        print(json.dumps(report, indent=2, sort_keys=True))
    if args.format in {"both", "table"}:
        if args.format == "both":
            print()
        print(render_table(report))

    orphans = report["orphans"]
    has_orphans = bool(
        orphans["findings_without_work_items"]
        or orphans["traceability_rows_for_unknown_findings"],
    )
    return 1 if has_orphans else 0


if __name__ == "__main__":
    sys.exit(main())
