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
* Deferred (owner+trigger recorded) and decision-closed (NO-GO recorded)
  language is mined from full commit bodies by paragraph, but an item is only
  ELIGIBLE for either signal if (a) that exact item ID is one this commit
  declares on its own top subject line, or (b) the item's own
  semicolon-delimited clause within the paragraph carries an explicit
  "no-go"/"defer*" marker of its own. Plain co-occurrence anywhere in the
  same blank-line paragraph is deliberately NOT enough — a real bug: this
  program's own genesis commit (``e65bf75``) mentions "W2-1" and
  "owner+trigger"/"NO-GO" in the very same paragraph while narrating three
  UNRELATED bugfixes, which mislabeled AUTH-01/W2-1 DEFERRED even though it
  had landed cleanly via #195 (see ``build_prose_signals``'s and
  ``_item_clauses``'s docstrings for the fix). PROGRAM-LEDGER.md is
  deliberately NOT scanned for this either — see ``build_prose_signals``'s
  docstring for the cross-contamination it produces at paragraph
  granularity.
* This program's OWN dev-tooling commits (Conventional-Commits scope
  ``(dev-tooling)``, e.g. this module's genesis commit) are excluded from
  every evidence scan above — see ``is_dev_tooling_commit``. The oracle's
  own commit messages narrate its bugfix history in prose; they are never
  themselves evidence about a finding's disposition.

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

# Same-major shorthand ("W3-2/4" == W3-2, W3-4) AND plain IDs ("W2-2"). Cross-
# major chains ("W4-6/W5-9") fall out naturally: the continuation only grabs
# digits, so it stops at the next literal "W".
_ITEM_GROUP_RE = re.compile(r"\bW(\d+)-(\d+(?:/\d+)*)\b")

_BULLET_RE = re.compile(r"^\* (.+)$", re.MULTILINE)

# A finding ID looks like "AUTH-01": >=2 uppercase letters, so it can never
# collide with a work-item token like "W2-1" (single letter before the digit).
_FINDING_ID_RE = re.compile(r"\b[A-Z]{2,}-\d+\b")

# An explicit "this item is not landing" marker: "no-go"/"no go" (space or
# hyphen), or any "defer*" stem (defer/deferred/deferral). Used to scope the
# deferred/decision-closed ELIGIBILITY check to an item's own clause rather
# than trusting a keyword found anywhere in a whole (possibly multi-topic)
# paragraph — see ``build_prose_signals``'s docstring.
_MARKER_RE = re.compile(r"no-go|no go|defer", re.IGNORECASE)

# This program's own construction commits: Conventional-Commits scope
# "(dev-tooling)", e.g. "feat(dev-tooling): add M4 exit oracle
# audit_disposition.py + tests". These commits narrate the audit oracle's
# OWN bugfix history in prose — e.g. this module's genesis commit says "an
# owner+trigger/ NO-GO signal" while describing a DIFFERENT bug (the
# PROGRAM-LEDGER.md cross-contamination fix), in the very same paragraph
# that names "W2-1" for a THIRD, unrelated bug (the finding-ID-citation
# undercount fix). ``git log --all`` picks up this very commit, so without
# excluding it the oracle can cite its own retrospective prose as evidence
# about a finding it merely talks about. See ``is_dev_tooling_commit``.
_DEV_TOOLING_SUBJECT_RE = re.compile(r"^\w+\(dev-tooling\):", re.IGNORECASE)


def is_dev_tooling_commit(commit_message: str) -> bool:
    """True if ``commit_message``'s own subject line is this program's
    dev-tooling commit-type scope — see ``_DEV_TOOLING_SUBJECT_RE``'s
    docstring for why these are excluded from every evidence scan.
    """
    if not commit_message.strip():
        return False
    return bool(_DEV_TOOLING_SUBJECT_RE.match(commit_message.splitlines()[0]))


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


def paragraphs(text: str) -> list[str]:
    """Split on blank lines (kept simple — good enough for prose/commit bodies)."""
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


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
    kind: str  # "commit" | "ledger"
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

    A single blank-line-delimited paragraph can legitimately narrate several
    UNRELATED topics in one breath — semicolons are this repo's commit-body
    convention for that (e.g. this program's own genesis commit's "Three
    self-caught bugs..." paragraph uses semicolons to separate three
    distinct bugfix write-ups). Scoping the "explicit marker adjacent to
    this item" eligibility check in ``build_prose_signals`` to the item's
    own clause, rather than the whole paragraph, is what keeps an unrelated
    co-mentioned item from inheriting a marker that actually describes a
    DIFFERENT clause's topic. If the same item happens to appear in more
    than one clause, the first one wins (good enough — no known real case
    needs the others).
    """
    clauses: dict[str, str] = {}
    for clause in paragraph.split(";"):
        for item in extract_all_items(clause):
            clauses.setdefault(item, clause)
    return clauses


def build_prose_signals(
    commits: list[CommitRecord],
) -> tuple[dict[str, Evidence], dict[str, Evidence]]:
    """work item -> Evidence, split into (deferred, decision_closed).

    Deferred takes precedence: a paragraph naming BOTH "owner" and "trigger"
    (case-insensitive) is a deferral-with-owner+trigger record. Otherwise a
    paragraph naming "no-go" (or "no go") is a decision-close record.

    An item is only ELIGIBLE for either signal from a given paragraph if
    EITHER (a) that exact item ID is one this commit declares on its own top
    subject line (the first line of ``declaration_lines`` — NOT squash
    bullets; a bullet's own sub-commit subject describes a different item and
    should not borrow this paragraph's prose just by being in the same
    commit), so the whole commit's prose can be trusted to be about the
    item(s) it names up front; OR (b) the item's own semicolon-delimited
    clause within the paragraph (``_item_clauses``) carries an explicit
    "no-go"/"defer*" marker of its own (``_MARKER_RE``). Plain co-occurrence
    anywhere in the same paragraph is deliberately NOT enough — that was a
    real bug: this program's own genesis commit (``e65bf75``) mentions
    "W2-1" and "owner+trigger"/"NO-GO" in the very same paragraph while
    narrating three UNRELATED bugfixes (a traceability-parser fix, the
    PROGRAM-LEDGER.md cross-contamination fix this very docstring describes
    below, and the finding-ID-citation undercount fix that actually mentions
    W2-1), which mislabeled AUTH-01/W2-1 DEFERRED even though it had landed
    cleanly via #195. See ``is_dev_tooling_commit`` for the complementary
    fix (that commit is now excluded outright); this eligibility scoping is
    the general-purpose fix that also holds for a hypothetical
    non-dev-tooling commit shaped the same way (regression-pinned by
    ``test_build_prose_signals_ignores_unrelated_co_mention``).

    Once an item is eligible, the deferred-vs-decision-closed CLASSIFICATION
    itself still reads the WHOLE paragraph (not just the item's own clause):
    an item's own clause need not restate "owner"/"trigger" verbatim if a
    later clause/sentence in the same paragraph does — confirmed against the
    real W2-5/ERRTAX-03 deferral, whose "NO-GO / deferred" clause and its
    "owner + trigger" clause are two different sentences in one paragraph.

    Scanned over commit body paragraphs ONLY — deliberately NOT
    PROGRAM-LEDGER.md. The ledger records milestone-level progress as one
    dense summary row per milestone (many item IDs per row, e.g. the M3 row
    lists ~16 items in one cell alongside the words "owner+trigger" and
    "NO-GO", which describe only W2-5/W5-13 specifically). Scanning it at
    paragraph OR even row granularity mis-attributes those keywords to every
    other item co-mentioned in the same row — verified by a first draft of
    this function false-flagging W4-3 (landed, unrelated to any deferral) as
    DEFERRED purely because it shares the M3 ledger row with "W2-5 NO-GO"
    (the clause-scoped eligibility check above independently also fixes this
    exact shape now, but the ledger is still never fed in — belt and
    braces). Commit bodies are the primary, per-item-scoped source instead
    (each deferral/decision-close is its own paragraph naming only the
    item(s) it actually applies to — confirmed by manual read of the
    W2-5/ERRTAX-03 commits).
    """
    deferred: dict[str, Evidence] = {}
    decision_closed: dict[str, Evidence] = {}

    for commit in commits:
        decl_lines = declaration_lines(commit.message)
        subject_items = extract_all_items(decl_lines[0]) if decl_lines else set()

        for para in paragraphs(commit.message):
            items = extract_all_items(para)
            if not items:
                continue
            lowered = para.lower()
            is_deferred = "owner" in lowered and "trigger" in lowered
            is_decision = "no-go" in lowered or "no go" in lowered
            snippet = para[:400]
            item_clauses = _item_clauses(para)
            for item in items:
                clause = item_clauses.get(item, para)
                eligible = item in subject_items or bool(_MARKER_RE.search(clause))
                if not eligible:
                    continue
                if is_deferred and item not in deferred:
                    deferred[item] = Evidence(
                        kind="commit",
                        source=commit.sha,
                        snippet=snippet,
                    )
                elif (
                    is_decision and item not in deferred and item not in decision_closed
                ):
                    decision_closed[item] = Evidence(
                        kind="commit",
                        source=commit.sha,
                        snippet=snippet,
                    )
    # A later-scanned deferral should still win over an earlier decision-close
    # for the same item (deferred is the more complete signal).
    for item in list(deferred):
        decision_closed.pop(item, None)
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
    all_commits = git_log_records(repo_root)
    # This program's own dev-tooling commits (e.g. this module's genesis
    # commit) narrate the oracle's OWN bugfix history in prose and are
    # excluded from every evidence scan below — see
    # `is_dev_tooling_commit`'s docstring for the false-positive this
    # prevents (AUTH-01/W2-1 self-mislabeled DEFERRED by co-mentioning its
    # own construction history).
    commits = [c for c in all_commits if not is_dev_tooling_commit(c.message)]
    # NOTE: PROGRAM-LEDGER.md exists (`_LEDGER_REL`) but is deliberately NOT
    # read into the deferred/decision-close prose scan — see
    # build_prose_signals' docstring for why (its per-milestone rows compress
    # many item IDs into one dense summary, which mis-attributes keywords
    # across co-mentioned items at any paragraph/row granularity).

    finding_ids = {f.id for f in findings}
    declared_landings, declared_findings = build_declared_landings(commits, finding_ids)
    deferred, decision_closed = build_prose_signals(commits)
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
