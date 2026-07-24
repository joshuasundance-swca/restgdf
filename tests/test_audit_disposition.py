"""Tests for ``scripts/audit_disposition.py`` (M4 CENSUS lane exit oracle).

The script is loaded fresh by file path (``scripts/`` has no ``__init__.py``,
matching ``tests/test_bumpver_stamp_date.py``'s established convention), never
imported as ``restgdf.*`` — it is dev tooling, excluded from the wheel.

Unit tests exercise the pure parsing/evidence functions directly (no git, no
filesystem beyond ``tmp_path`` fixtures the test itself writes) so they never
depend on this program's own evolving commit history. Two tests are
deliberately NOT like that:

* ``test_end_to_end_against_a_throwaway_git_repo`` builds a real tiny git repo
  in ``tmp_path`` and runs the full ``build_report`` pipeline through it,
  proving the git-shelling-out plumbing (``git log``, ``git diff-tree``)
  actually works, not just the pure functions around it.
* ``test_real_repo_structural_invariants`` runs against the ACTUAL restgdf
  checkout and asserts only STRUCTURAL invariants (61 findings, zero
  orphans, every finding reaches one of the four known dispositions, JSON
  round-trips) — never a specific disposition count, because those counts
  are expected to change as the M4 docs lane lands work in the same
  milestone this test ships in.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess  # nosec B404 - test-only, builds/queries a throwaway tmp_path git repo
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_disposition.py"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module() -> ModuleType:
    """Load a fresh copy of the script module for each test.

    Registered into ``sys.modules`` under its own name before ``exec_module``
    runs: the script's dataclasses combined with ``from __future__ import
    annotations`` need ``sys.modules[cls.__module__]`` to resolve their
    (stringified) field annotations, which only exists once the module is
    registered -- omitting this raises ``AttributeError: 'NoneType' object
    has no attribute '__dict__'`` deep inside ``dataclasses._process_class``.
    """
    spec = importlib.util.spec_from_file_location("audit_disposition", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ad() -> ModuleType:
    return _load_module()


# ---------------------------------------------------------------------------
# extract_all_items / extract_finding_ids — shorthand parsing
# ---------------------------------------------------------------------------


def test_extract_all_items_plain_ids(ad: ModuleType) -> None:
    assert ad.extract_all_items("fix: X (W2-2, W2-3, W2-11, W3-3)") == {
        "W2-2",
        "W2-3",
        "W2-11",
        "W3-3",
    }


def test_extract_all_items_same_major_shorthand(ad: ModuleType) -> None:
    assert ad.extract_all_items("(W2-13, W3-2/4, W5-2/3/6/13/14)") == {
        "W2-13",
        "W3-2",
        "W3-4",
        "W5-2",
        "W5-3",
        "W5-6",
        "W5-13",
        "W5-14",
    }


def test_extract_all_items_cross_major_chain(ad: ModuleType) -> None:
    # "/" only continues the SAME major when what follows is a bare digit --
    # a literal "W" after the slash starts a brand new item instead.
    assert ad.extract_all_items("W4-6/W5-9/W5-10/W5-11 pulled forward") == {
        "W4-6",
        "W5-9",
        "W5-10",
        "W5-11",
    }


def test_extract_all_items_does_not_match_lettered_suffix(ad: ModuleType) -> None:
    # "W1-8b" is a coordinator addendum, not the real W1-8 item -- must not
    # false-match as W1-8 (the trailing "b" breaks the \b boundary).
    assert ad.extract_all_items("fix: gate bumpver (W1-8b)") == set()


def test_extract_finding_ids_filters_to_known_only(ad: ModuleType) -> None:
    text = "W2-1 / AUTH-01 landed; UNKNOWN-99 is not a real finding"
    assert ad.extract_finding_ids(text, {"AUTH-01", "CONFIG-02"}) == {"AUTH-01"}


def test_extract_finding_ids_never_collides_with_work_item(ad: ModuleType) -> None:
    # A work-item token has exactly one letter before the digit; the finding-
    # ID regex requires >=2, so "W2-1" can never be mistaken for a finding ID.
    assert ad.extract_finding_ids("W2-1 W12-1", {"W2-1", "W12-1"}) == set()


# ---------------------------------------------------------------------------
# declaration_lines — subject + squash-preserved bullet extraction
# ---------------------------------------------------------------------------


def test_declaration_lines_top_subject_only() -> None:
    ad = _load_module()
    message = (
        "fix: force POST when body carries a token (AUTH-01)\n\nBody prose here.\n"
    )
    assert ad.declaration_lines(message) == [
        "fix: force POST when body carries a token (AUTH-01)",
    ]


def test_declaration_lines_includes_squash_bullets() -> None:
    ad = _load_module()
    message = (
        "ci: real deps-present mypy gate (W1-2 stack) (#196)\n\n"
        "* fix(models): narrow validation_alias (W5-10)\n\n"
        "Some body prose mentioning W5-11 but not as a bullet.\n\n"
        "* docs(client): scope AsyncHTTPSession match claim (W5-9)\n\n"
        "More prose.\n"
    )
    lines = ad.declaration_lines(message)
    assert lines[0] == "ci: real deps-present mypy gate (W1-2 stack) (#196)"
    # _BULLET_RE captures the text AFTER "* ", so the bullet marker itself is
    # not part of the returned line.
    assert "fix(models): narrow validation_alias (W5-10)" in lines
    assert "docs(client): scope AsyncHTTPSession match claim (W5-9)" in lines
    # The narrative-only W5-11 mention must NOT show up as a declaration line.
    assert not any("W5-11" in line for line in lines)


def test_declaration_lines_empty_message_returns_empty(ad: ModuleType) -> None:
    assert ad.declaration_lines("") == []
    assert ad.declaration_lines("   \n  \n") == []


# ---------------------------------------------------------------------------
# parse_deliberate_deferrals_section — the SOLE deferred/decision-closed
# evidence source (commit-body narration was removed entirely -- see the
# module docstring for the three-recurrence history that led here)
# ---------------------------------------------------------------------------


def test_parse_deliberate_deferrals_section_finds_deferred_bullet(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    plan_dir = tmp_path / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    traceability = (
        "## Deliberate deferrals\n\n"
        "- **`ERRTAX-03` / `W2-5` — DEFERRED (NO-GO), M3 2026-07-24.** Closed as "
        "NO-GO per plan/02's own recommendation. Owner: a future pass. Trigger: "
        "maintainer GO.\n"
    )
    (plan_dir / "99-traceability.md").write_text(traceability, encoding="utf-8")
    deferred, decision_closed = ad.parse_deliberate_deferrals_section(tmp_path)
    assert "W2-5" in deferred
    assert deferred["W2-5"].kind == "traceability"
    assert "W2-5" not in decision_closed


def test_parse_deliberate_deferrals_section_finds_confirm_only_bullet(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    plan_dir = tmp_path / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    traceability = (
        "## Deliberate deferrals\n\n"
        "One item is a recorded clarification:\n\n"
        "- **`W3-6` was not dropped** — it resolved as *confirm-only* (Path a) "
        "in M2/PR #203: the timeout/concurrency env vars were verified wired.\n"
    )
    (plan_dir / "99-traceability.md").write_text(traceability, encoding="utf-8")
    deferred, decision_closed = ad.parse_deliberate_deferrals_section(tmp_path)
    assert "W3-6" in decision_closed
    assert decision_closed["W3-6"].kind == "traceability"
    assert "W3-6" not in deferred


def test_parse_deliberate_deferrals_section_does_not_leak_to_a_co_mentioned_item(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    """Regression for the real W3-6 bullet's exact shape: it cross-
    references a DIFFERENT, genuinely-landed item (W6-7) in the SAME bullet
    (in a later, semicolon-separated clause) purely as a citation of where
    the docs fix landed. Only W3-6 -- whose OWN clause carries "confirm-
    only" -- may resolve DECISION-CLOSED here; W6-7 must not, or it would
    silently override its real LANDED evidence for every OTHER finding it
    also owns (e.g. TELEMETRY-01, which also owns W6-7).
    """
    plan_dir = tmp_path / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    traceability = (
        "## Deliberate deferrals\n\n"
        "- **`W3-6` was not dropped** — it resolved as *confirm-only* (Path a) "
        "in M2/PR #203: the timeout/concurrency env vars were verified wired "
        "and the three `RESTGDF_AUTH_*` vars verified absent from the "
        "resolver; the documentation rows were corrected under W6-7 (M4).\n"
    )
    (plan_dir / "99-traceability.md").write_text(traceability, encoding="utf-8")
    deferred, decision_closed = ad.parse_deliberate_deferrals_section(tmp_path)
    assert "W3-6" in decision_closed
    assert "W6-7" not in decision_closed
    assert "W6-7" not in deferred


def test_parse_deliberate_deferrals_section_ignores_milestone_label_bullet(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    """A milestone-label correction (e.g. the real W4-6/W5-9/W5-10/W5-11
    note) carries no DEFERRED/confirm-only/decision-closed marker and must
    not be treated as evidence for any of the items it names.
    """
    plan_dir = tmp_path / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    traceability = (
        "## Deliberate deferrals\n\n"
        "- **`W4-6`/`W5-9`/`W5-10`/`W5-11`** carry an M2 milestone label but "
        "landed in the M1 typing-transition stack (PR #196) per the runbook.\n"
    )
    (plan_dir / "99-traceability.md").write_text(traceability, encoding="utf-8")
    deferred, decision_closed = ad.parse_deliberate_deferrals_section(tmp_path)
    assert deferred == {}
    assert decision_closed == {}


def test_parse_deliberate_deferrals_section_stops_at_next_heading(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    plan_dir = tmp_path / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    traceability = (
        "## Deliberate deferrals\n\n"
        "- **`W1-1`** resolved as *confirm-only*.\n\n"
        "## Some other section\n\n"
        "- **`W1-2`** resolved as *confirm-only* (should not be parsed).\n"
    )
    (plan_dir / "99-traceability.md").write_text(traceability, encoding="utf-8")
    deferred, decision_closed = ad.parse_deliberate_deferrals_section(tmp_path)
    assert "W1-1" in decision_closed
    assert "W1-2" not in decision_closed
    assert deferred == {}


def test_build_report_resolves_zero_commit_item_via_traceability_clarification(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    """End-to-end: an item with ZERO commits anywhere (resolved by
    verifying existing behavior, never by shipping a change -- the real
    W3-6/DOCS-02 shape) still reaches a terminal DECISION-CLOSED via the
    traceability doc's clarification alone, with no commit evidence at all.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)

    plan_dir = repo / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    findings = [
        {
            "id": "CONFIRM-01",
            "axis": "FAKE",
            "title": "confirm-only finding",
            "severity": "medium",
            "files": ["restgdf/nowhere.py"],
        },
    ]
    (repo / "audit-recommendations" / "findings.json").write_text(
        json.dumps(findings),
        encoding="utf-8",
    )
    (plan_dir / "99-traceability.md").write_text(
        "## Forward map\n\n| `CONFIRM-01` | medium | t | `W9-2` | — |\n\n"
        "## Deliberate deferrals\n\n"
        "- **`W9-2` was not dropped** — it resolved as *confirm-only* (Path a): "
        "existing behavior was verified correct, no change shipped.\n",
        encoding="utf-8",
    )
    (repo / "restgdf").mkdir()
    (repo / "restgdf" / "nowhere.py").write_text("x = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "chore: seed repo (no W9-2 commit anywhere)", cwd=repo)

    report = ad.build_report(repo)
    by_id = {row["id"]: row for row in report["findings"]}
    assert by_id["CONFIRM-01"]["disposition"] == "DECISION-CLOSED"
    assert by_id["CONFIRM-01"]["item_statuses"]["W9-2"]["status"] == "DECISION_CLOSED"
    assert by_id["CONFIRM-01"]["item_statuses"]["W9-2"]["evidence"][0]["kind"] == (
        "traceability"
    )


def test_narrating_commit_produces_zero_deferral_signal(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    """Regression for the recurring self-contamination family -- THREE
    separate instances, each surviving the previous fix: the genesis commit
    (``e65bf75``), the PR #213 squash (``701ddbf``), and the PR #214 squash
    (``05d3e34``). Every fix so far tried to distinguish a "narrating"
    commit from an "ordinary" one (by subject scope, then by diff
    confinement to this script's own two files) and every squash merge
    broke the distinction again -- because a squash that narrates this
    exact bug's history necessarily touches whatever REAL files that PR
    also edited (here: findings.json / 99-traceability.md), and necessarily
    uses the real trigger vocabulary while explaining why it's dangerous.

    This test fixes a commit shaped EXACTLY like all three recurrences --
    item IDs next to "owner"+"trigger"/"NO-GO"/"deferred", diff touching the
    real audit-recommendations files -- and asserts it produces ZERO
    deferral signal, structurally: there is no longer any code path that
    reads commit bodies for deferred/decision-closed evidence at all, so no
    fixture shaped like the bug (however cleverly) can trigger it. The item
    must resolve on its own real evidence (here: GAP, since none exists),
    never DEFERRED merely because some commit message talks about
    deferrals.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)

    plan_dir = repo / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    findings = [
        {
            "id": "FAKE-01",
            "axis": "FAKE",
            "title": "t",
            "severity": "low",
            "files": ["restgdf/nowhere.py"],
        },
    ]
    (repo / "audit-recommendations" / "findings.json").write_text(
        json.dumps(findings),
        encoding="utf-8",
    )
    (plan_dir / "99-traceability.md").write_text(
        "## Forward map\n\n| `FAKE-01` | low | t | `W9-3` | — |\n",
        encoding="utf-8",
    )
    (repo / "restgdf").mkdir()
    (repo / "restgdf" / "nowhere.py").write_text("x = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "chore: seed repo", cwd=repo)

    # A squash-merge-shaped commit whose body narrates the bug class AND
    # whose diff touches the real audit-recommendations files.
    (repo / "audit-recommendations" / "findings.json").write_text(
        json.dumps(
            [
                *findings,
                {
                    "id": "FAKE-02",
                    "axis": "FAKE",
                    "title": "u",
                    "severity": "low",
                    "files": [],
                },
            ],
        ),
        encoding="utf-8",
    )
    (plan_dir / "99-traceability.md").write_text(
        "## Forward map\n\n"
        "| `FAKE-01` | low | t | `W9-3` | — |\n"
        "| `FAKE-02` | low | t | `W9-4` | — |\n",
        encoding="utf-8",
    )
    _git("add", "-A", cwd=repo)
    _git(
        "commit",
        "-q",
        "-m",
        "fix: close census's residual GAPs (findings.json + traceability) (#214)\n\n"
        "W9-3 (FAKE-01): NO-GO / deferred. Owner: someone. Trigger: someday.\n",
        cwd=repo,
    )

    report = ad.build_report(repo)
    by_id = {row["id"]: row for row in report["findings"]}
    assert by_id["FAKE-01"]["disposition"] == "GAP"
    assert by_id["FAKE-01"]["item_statuses"]["W9-3"]["status"] == "GAP"


# ---------------------------------------------------------------------------
# item_status_for_finding / disposition_for_finding — rollup logic
# ---------------------------------------------------------------------------


def test_item_status_landed_requires_file_overlap(ad: ModuleType) -> None:
    finding = ad.Finding(
        id="TEST-01",
        axis="TEST",
        title="t",
        severity="low",
        files=["restgdf/foo.py"],
    )
    file_cache = {"sha1": {"restgdf/foo.py", "CHANGELOG.md"}}
    status = ad.item_status_for_finding(
        "W9-1",
        finding,
        declared_landings={"W9-1": ["sha1"]},
        declared_findings={},
        deferred={},
        decision_closed={},
        file_cache=file_cache,
        repo_root=Path("."),
    )
    assert status.status == "LANDED"
    assert status.evidence[0]["source"] == "sha1"


def test_item_status_message_only_when_no_file_overlap(ad: ModuleType) -> None:
    finding = ad.Finding(
        id="TEST-01",
        axis="TEST",
        title="t",
        severity="low",
        files=["restgdf/foo.py"],
    )
    # sha1's diff touches an unrelated file -- the commit message cites the
    # item, but this is exactly the "commit doesn't contain the change"
    # REFUTED shape the census must not fudge into LANDED.
    file_cache = {"sha1": {"restgdf/unrelated.py"}}
    status = ad.item_status_for_finding(
        "W9-1",
        finding,
        declared_landings={"W9-1": ["sha1"]},
        declared_findings={},
        deferred={},
        decision_closed={},
        file_cache=file_cache,
        repo_root=Path("."),
    )
    assert status.status == "MESSAGE_ONLY"


def test_item_status_gap_when_no_evidence_at_all(ad: ModuleType) -> None:
    finding = ad.Finding(
        id="TEST-01",
        axis="TEST",
        title="t",
        severity="low",
        files=["x.py"],
    )
    status = ad.item_status_for_finding(
        "W9-1",
        finding,
        declared_landings={},
        declared_findings={},
        deferred={},
        decision_closed={},
        file_cache={},
        repo_root=Path("."),
    )
    assert status.status == "GAP"
    assert status.evidence == []


def test_item_status_finding_id_citation_counts_as_declaration(ad: ModuleType) -> None:
    """The #195 shape: a bullet cites only the FINDING id ("AUTH-01"), never
    the work-item id ("W2-1") -- this must still resolve to LANDED via the
    declared_findings channel, checked against THIS finding's own files.
    """
    finding = ad.Finding(
        id="AUTH-01",
        axis="AUTH",
        title="t",
        severity="high",
        files=["restgdf/utils/_http.py"],
    )
    file_cache = {"sha1": {"restgdf/utils/_http.py"}}
    status = ad.item_status_for_finding(
        "W2-1",
        finding,
        declared_landings={},  # never cited by work-item id
        declared_findings={"AUTH-01": ["sha1"]},
        deferred={},
        decision_closed={},
        file_cache=file_cache,
        repo_root=Path("."),
    )
    assert status.status == "LANDED"


def test_item_status_deferred_takes_precedence_over_landed_evidence(
    ad: ModuleType,
) -> None:
    finding = ad.Finding(
        id="TEST-01",
        axis="TEST",
        title="t",
        severity="low",
        files=["x.py"],
    )
    deferred = {
        "W9-1": ad.Evidence(kind="commit", source="sha1", snippet="owner+trigger"),
    }
    status = ad.item_status_for_finding(
        "W9-1",
        finding,
        declared_landings={"W9-1": ["sha1"]},
        declared_findings={},
        deferred=deferred,
        decision_closed={},
        file_cache={"sha1": {"x.py"}},
        repo_root=Path("."),
    )
    assert status.status == "DEFERRED"


def test_disposition_for_finding_all_landed(ad: ModuleType) -> None:
    statuses = [
        ad.ItemStatus("W1-1", "LANDED", []),
        ad.ItemStatus("W1-2", "LANDED", []),
    ]
    assert ad.disposition_for_finding(statuses) == "LANDED"


def test_disposition_for_finding_one_gap_dominates(ad: ModuleType) -> None:
    statuses = [ad.ItemStatus("W1-1", "LANDED", []), ad.ItemStatus("W1-2", "GAP", [])]
    assert ad.disposition_for_finding(statuses) == "GAP"


def test_disposition_for_finding_message_only_counts_as_gap(ad: ModuleType) -> None:
    statuses = [
        ad.ItemStatus("W1-1", "LANDED", []),
        ad.ItemStatus("W1-2", "MESSAGE_ONLY", []),
    ]
    assert ad.disposition_for_finding(statuses) == "GAP"


def test_disposition_for_finding_deferred_beats_decision_closed(ad: ModuleType) -> None:
    statuses = [
        ad.ItemStatus("W1-1", "DECISION_CLOSED", []),
        ad.ItemStatus("W1-2", "DEFERRED", []),
    ]
    assert ad.disposition_for_finding(statuses) == "DEFERRED"


def test_disposition_for_finding_decision_closed_with_landed(ad: ModuleType) -> None:
    statuses = [
        ad.ItemStatus("W1-1", "LANDED", []),
        ad.ItemStatus("W1-2", "DECISION_CLOSED", []),
    ]
    assert ad.disposition_for_finding(statuses) == "DECISION-CLOSED"


# ---------------------------------------------------------------------------
# load_findings / load_forward_map — fixture-file parsing
# ---------------------------------------------------------------------------


def test_load_findings_parses_json(ad: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "audit-recommendations").mkdir()
    payload = [
        {
            "id": "FAKE-01",
            "axis": "FAKE",
            "title": "a fake finding",
            "severity": "low",
            "files": ["restgdf/foo.py"],
        },
    ]
    (tmp_path / "audit-recommendations" / "findings.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    findings = ad.load_findings(tmp_path)
    assert len(findings) == 1
    assert findings[0].id == "FAKE-01"
    assert findings[0].files == ["restgdf/foo.py"]


def test_load_forward_map_handles_embedded_pipe_in_title(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    """Regression for the TYPING-04 parser bug: a title cell containing its
    own literal ``|`` (e.g. `` `session: ClientSession | None` ``) must not
    silently orphan the finding.
    """
    plan_dir = tmp_path / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    traceability = (
        "# 99 -- Traceability\n\n"
        "## Forward map\n\n"
        "| Finding | Sev | Title | Work item(s) | Split? |\n"
        "|---------|-----|-------|--------------|--------|\n"
        "| `TYPING-04` | low | get_gdf's `session: ClientSession | None` annotation "
        "contradicts the R-71 claim | `W4-6` | — |\n"
        "| `AUTH-01` | high | Caller-supplied token leaks | `W2-1`, `W6-6` | **yes** |\n\n"
        "## Reverse map\n\n"
        "| Item | Findings |\n"
    )
    (plan_dir / "99-traceability.md").write_text(traceability, encoding="utf-8")
    forward = ad.load_forward_map(tmp_path)
    assert forward["TYPING-04"] == ["W4-6"]
    assert forward["AUTH-01"] == ["W2-1", "W6-6"]


def test_load_forward_map_skips_header_and_separator_rows(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    plan_dir = tmp_path / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    traceability = (
        "## Forward map\n\n"
        "| Finding | Sev | Title | Work item(s) | Split? |\n"
        "|---------|-----|-------|--------------|--------|\n"
        "| `ONLY-01` | low | title | `W1-1` | — |\n"
        "## Reverse map\n"
        "| `ONLY-01` | should not be re-parsed from this section |\n"
    )
    (plan_dir / "99-traceability.md").write_text(traceability, encoding="utf-8")
    forward = ad.load_forward_map(tmp_path)
    assert forward == {"ONLY-01": ["W1-1"]}


def test_load_forward_map_stops_at_next_heading(ad: ModuleType, tmp_path: Path) -> None:
    plan_dir = tmp_path / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    traceability = (
        "## Forward map\n\n"
        "| `A-01` | low | t | `W1-1` | — |\n"
        "## Reverse map\n\n"
        "| `A-01` | W1 | M1 | low | S | `A-01` | should not be counted twice |\n"
    )
    (plan_dir / "99-traceability.md").write_text(traceability, encoding="utf-8")
    forward = ad.load_forward_map(tmp_path)
    assert forward == {"A-01": ["W1-1"]}


# ---------------------------------------------------------------------------
# End-to-end: a real throwaway git repo
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(  # nosec B603 B607 - test-only throwaway repo
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_head_sha(cwd: Path) -> str:
    return subprocess.run(  # nosec B603 B607 - test-only throwaway repo
        ["git", "rev-parse", "HEAD"],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _git_show_message(cwd: Path, sha: str) -> str:
    return subprocess.run(  # nosec B603 B607 - test-only throwaway repo
        ["git", "show", "--format=%B", "-s", sha],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def test_end_to_end_against_a_throwaway_git_repo(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)

    plan_dir = repo / "audit-recommendations" / "plan"
    plan_dir.mkdir(parents=True)
    findings = [
        {
            "id": "LANDED-01",
            "axis": "FAKE",
            "title": "landed finding",
            "severity": "high",
            "files": ["pkg/a.py"],
        },
        {
            "id": "GAP-01",
            "axis": "FAKE",
            "title": "unresolved finding",
            "severity": "low",
            "files": ["pkg/b.py"],
        },
        {
            "id": "DEFERRED-01",
            "axis": "FAKE",
            "title": "deferred finding",
            "severity": "low",
            "files": ["pkg/c.py"],
        },
    ]
    (repo / "audit-recommendations" / "findings.json").write_text(
        json.dumps(findings),
        encoding="utf-8",
    )
    (plan_dir / "99-traceability.md").write_text(
        "## Forward map\n\n"
        "| `LANDED-01` | high | t | `W1-1` | — |\n"
        "| `GAP-01` | low | t | `W1-2` | — |\n"
        "| `DEFERRED-01` | low | t | `W1-3` | — |\n\n"
        "## Deliberate deferrals\n\n"
        "- **`W1-3`** DEFERRED for now. Owner: maintainer. Trigger: next major "
        "release.\n",
        encoding="utf-8",
    )
    (plan_dir / "PROGRAM-LEDGER.md").write_text("# ledger\n", encoding="utf-8")
    (repo / "pkg").mkdir()
    (repo / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "pkg" / "b.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "pkg" / "c.py").write_text("x = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "chore: seed repo", cwd=repo)

    # Land W1-1 against pkg/a.py.
    (repo / "pkg" / "a.py").write_text("x = 2\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "fix: close it out (W1-1)", cwd=repo)

    # GAP-01 / W1-2 and DEFERRED-01 / W1-3 get no commit at all -- W1-3's
    # DEFERRED disposition comes ONLY from the traceability doc's own
    # "## Deliberate deferrals" section above, not from any commit body.

    report = ad.build_report(repo)
    by_id = {row["id"]: row for row in report["findings"]}
    assert by_id["LANDED-01"]["disposition"] == "LANDED"
    assert by_id["GAP-01"]["disposition"] == "GAP"
    assert by_id["DEFERRED-01"]["disposition"] == "DEFERRED"
    assert report["totals"]["findings"] == 3
    assert report["totals"]["orphans"] == 0

    table = ad.render_table(report)
    assert "LANDED-01" in table
    assert "GAP-01: unresolved item(s) ['W1-2']" in table


# ---------------------------------------------------------------------------
# Real repo: structural invariants only (never a specific disposition count)
# ---------------------------------------------------------------------------


def test_real_repo_structural_invariants(ad: ModuleType) -> None:
    report = ad.build_report(_REPO_ROOT)

    assert report["totals"]["findings"] == 61
    assert report["totals"]["orphans"] == 0
    assert report["orphans"]["findings_without_work_items"] == []
    assert report["orphans"]["traceability_rows_for_unknown_findings"] == []

    ids = [row["id"] for row in report["findings"]]
    assert len(ids) == len(set(ids)) == 61

    known_dispositions = {"LANDED", "DECISION-CLOSED", "DEFERRED", "GAP"}
    for row in report["findings"]:
        assert row["disposition"] in known_dispositions, row["id"]
        assert row["owning_items"], f"{row['id']} has no owning work items"

    totals = report["totals"]
    assert (
        totals["LANDED"]
        + totals["DECISION-CLOSED"]
        + totals["DEFERRED"]
        + totals["GAP"]
        == totals["findings"]
    )

    # JSON round-trip must not raise (this is the "machine-readable" contract).
    json.loads(json.dumps(report))


def test_cli_json_format_is_valid_json() -> None:
    result = (
        subprocess.run(  # nosec B603 B607 - invoking our own script by absolute path
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--repo-root",
                str(_REPO_ROOT),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    )
    payload = json.loads(result.stdout)
    assert payload["totals"]["findings"] == 61


def test_cli_table_format_has_no_json() -> None:
    result = (
        subprocess.run(  # nosec B603 B607 - invoking our own script by absolute path
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--repo-root",
                str(_REPO_ROOT),
                "--format",
                "table",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    )
    assert result.stdout.startswith("M4 audit disposition census")
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


def test_cli_exits_zero_on_the_real_repo() -> None:
    result = (
        subprocess.run(  # nosec B603 B607 - invoking our own script by absolute path
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--repo-root",
                str(_REPO_ROOT),
                "--format",
                "table",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    )
    assert result.returncode == 0, result.stdout + result.stderr
