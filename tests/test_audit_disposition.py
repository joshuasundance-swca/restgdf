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
# build_prose_signals — deferred / decision-closed mining, paragraph-scoped
# ---------------------------------------------------------------------------


def test_build_prose_signals_deferred_needs_owner_and_trigger(ad: ModuleType) -> None:
    commits = [
        ad.CommitRecord(
            sha="deadbeef",
            message=(
                "fix: token 4xx taxonomy (W2-2, W2-3) (#209)\n\n"
                "W2-5 (ERRTAX-03): NO-GO / deferred (matches plan rec).\n"
                "Docstring note records scope + owner + trigger to revisit.\n\n"
                "W2-11: unrelated paragraph, no signal here.\n"
            ),
        ),
    ]
    deferred, decision_closed = ad.build_prose_signals(commits)
    assert "W2-5" in deferred
    assert "W2-5" not in decision_closed
    assert "W2-11" not in deferred
    assert "W2-11" not in decision_closed


def test_build_prose_signals_owner_trigger_labelled_form(ad: ModuleType) -> None:
    commits = [
        ad.CommitRecord(
            sha="cafef00d",
            message=(
                "feat: drift attribution (W5-13) (#210)\n\n"
                "Also records the W2-5 (ERRTAX-03) deferral inline: in-body 498/499\n"
                "envelopes still surface as generic RestgdfResponseError. Owner: W2\n"
                "(L2 token.py refresh-lift). Trigger: maintainer GO + the coordinated\n"
                "token.py lift landing. No GO recorded this milestone.\n"
            ),
        ),
    ]
    deferred, _decision_closed = ad.build_prose_signals(commits)
    assert "W2-5" in deferred
    assert deferred["W2-5"].kind == "commit"
    assert deferred["W2-5"].source == "cafef00d"


def test_build_prose_signals_decision_closed_without_owner_trigger(
    ad: ModuleType,
) -> None:
    commits = [
        ad.CommitRecord(
            sha="1234567",
            message="fix: something (W2-99)\n\nW2-99: NO-GO, revisit later without a recorded trigger.\n",
        ),
    ]
    deferred, decision_closed = ad.build_prose_signals(commits)
    assert "W2-99" not in deferred
    assert "W2-99" in decision_closed


def test_build_prose_signals_does_not_cross_contaminate_dense_rows(
    ad: ModuleType,
) -> None:
    """Regression: a first draft scanned PROGRAM-LEDGER.md too, and its dense
    per-milestone summary row mentioned ~16 items alongside "owner+trigger"
    and "NO-GO" (which really only describe W2-5/W5-13), so EVERY co-mentioned
    item (including landed ones like W4-3) false-flagged as DEFERRED. The
    ledger is still never fed in (belt and braces), but this test now pins
    the GENERAL fix that also applies to any commit body shaped this way:
    ``build_prose_signals`` is clause-scoped (``_item_clauses``, split on
    ``;``), so an item sharing a dense multi-topic PARAGRAPH with the
    owner+trigger/NO-GO language no longer inherits it unless the item's own
    clause -- or the commit's own subject line -- actually carries it.
    """
    ad_mod = ad
    dense_row_as_commit_body = (
        "docs: ledger update (not a real commit in practice)\n\n"
        "M3 Medium correctness COMPLETE (W2-2/3/11, W3-2/3/4, W4-3/4, W5-2/3/6/13/14; "
        "decision-closes with recorded owner+trigger: W2-5 NO-GO per plan recommendation)\n"
    )
    commits = [ad_mod.CommitRecord(sha="abc123", message=dense_row_as_commit_body)]
    deferred, decision_closed = ad_mod.build_prose_signals(commits)
    # W4-3 shares the PARAGRAPH with "owner+trigger"/"NO-GO" but not the
    # CLAUSE (it's on the "M3 Medium correctness COMPLETE (...)" side of the
    # semicolon, the marker language is on the other side) and is not on the
    # commit's subject line either -- no longer eligible.
    assert "W4-3" not in deferred
    assert "W4-3" not in decision_closed
    assert "W2-5" in deferred  # the item the language was actually about, unaffected


def test_build_prose_signals_ignores_unrelated_co_mention(ad: ModuleType) -> None:
    """Regression for the real self-contamination bug this fix closes: a
    fixture commit body co-mentioning ANOTHER item's ID in the same blank-
    line paragraph as owner+trigger language -- but in an unrelated clause,
    about an unrelated topic, with neither item on the commit's subject line
    -- must not mark that other item DEFERRED. This is the exact shape of
    this program's own genesis commit (``e65bf75``), which mentions "W2-1"
    and "owner+trigger"/"NO-GO" in one paragraph while narrating three
    unrelated bugfixes, only one of which is a real deferral (about a
    completely different item). ``is_dev_tooling_commit`` now excludes that
    specific commit outright, but this test proves the general-purpose
    clause-scoping fix in ``build_prose_signals`` holds even for a
    hypothetical commit that ISN'T dev-tooling-scoped.
    """
    commits = [
        ad.CommitRecord(
            sha="fixture01",
            message=(
                "fix: three unrelated bugs in one release (#999)\n\n"
                "Three self-caught bugs fixed before shipping: a parser bug fixed "
                "column-position-robustly; scanning the ledger's dense rows "
                "cross-contaminated co-mentioned items with an owner+trigger/ "
                "NO-GO signal meant for one item only (fixed by dropping the "
                "ledger from that scan); and W9-1 citations undercounted landed "
                "items (fixed by also matching finding IDs).\n"
            ),
        ),
    ]
    deferred, decision_closed = ad.build_prose_signals(commits)
    assert "W9-1" not in deferred
    assert "W9-1" not in decision_closed


# ---------------------------------------------------------------------------
# is_dev_tooling_commit / build_report's dev-tooling exclusion
# ---------------------------------------------------------------------------


def test_is_dev_tooling_commit_matches_the_real_genesis_commit_shape(
    ad: ModuleType,
) -> None:
    assert ad.is_dev_tooling_commit(
        "feat(dev-tooling): add M4 exit oracle audit_disposition.py + tests\n\nBody.\n",
    )


def test_is_dev_tooling_commit_false_for_ordinary_commits(ad: ModuleType) -> None:
    assert not ad.is_dev_tooling_commit(
        "fix: token 4xx taxonomy (W2-2, W2-3) (#209)\n\nBody.\n",
    )


def test_is_dev_tooling_commit_false_for_empty_message(ad: ModuleType) -> None:
    assert not ad.is_dev_tooling_commit("")
    assert not ad.is_dev_tooling_commit("   \n  \n")


def test_build_report_excludes_dev_tooling_commit_from_deferral_evidence(
    ad: ModuleType,
    tmp_path: Path,
) -> None:
    """End-to-end: a dev-tooling commit's body quotes an item ID inside an
    ILLUSTRATIVE example of this program's own deferral-notice convention
    (marker word directly adjacent to the item ID -- exactly the shape
    ``_item_clauses``' clause-scoping alone would treat as a legitimate
    per-item deferral) -- while a SEPARATE, real commit lands that same item
    cleanly against the finding's own file. Clause-scoping by itself is NOT
    sufficient here (the illustrative example is deliberately shaped to pass
    it); only excluding the dev-tooling commit outright (``is_dev_tooling_
    commit``) keeps this from resolving DEFERRED instead of LANDED --
    exercising the exclusion as a genuinely necessary second layer, not a
    redundant one.
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
            "id": "AUTH-01",
            "axis": "AUTH",
            "title": "token leak",
            "severity": "high",
            "files": ["restgdf/utils/_http.py"],
        },
    ]
    (repo / "audit-recommendations" / "findings.json").write_text(
        json.dumps(findings),
        encoding="utf-8",
    )
    (plan_dir / "99-traceability.md").write_text(
        "## Forward map\n\n| `AUTH-01` | high | t | `W2-1` | — |\n",
        encoding="utf-8",
    )
    (repo / "restgdf" / "utils").mkdir(parents=True)
    (repo / "restgdf" / "utils" / "_http.py").write_text("x = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "chore: seed repo", cwd=repo)

    # The real landing: touches the finding's own file, cites the item.
    (repo / "restgdf" / "utils" / "_http.py").write_text("x = 2\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git(
        "commit",
        "-q",
        "-m",
        "fix: force POST when body carries a token (W2-1)",
        cwd=repo,
    )

    # A LATER dev-tooling commit quotes "W2-1" as an ILLUSTRATIVE example of
    # this program's own deferral-notice convention, with the marker word
    # directly adjacent -- clause-scoping alone would treat this as a real
    # per-item deferral signal; only the dev-tooling exclusion prevents it.
    (repo / "scripts").mkdir()
    (repo / "scripts" / "audit_disposition.py").write_text(
        "# oracle\n",
        encoding="utf-8",
    )
    _git("add", "-A", cwd=repo)
    _git(
        "commit",
        "-q",
        "-m",
        "feat(dev-tooling): add M4 exit oracle\n\n"
        'Docstring example of the convention: "W2-1 (EXAMPLE-01): NO-GO / '
        'deferred. Owner: X. Trigger: Y (illustrative only)."\n',
        cwd=repo,
    )

    report = ad.build_report(repo)
    by_id = {row["id"]: row for row in report["findings"]}
    assert by_id["AUTH-01"]["disposition"] == "LANDED"


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
        "| `DEFERRED-01` | low | t | `W1-3` | — |\n",
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

    # Defer W1-3 with an owner+trigger record (touches an unrelated file).
    (repo / "pkg" / "c.py").write_text("x = 3\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git(
        "commit",
        "-q",
        "-m",
        "docs: note the W1-3 deferral\n\n"
        "W1-3: NO-GO for now. Owner: maintainer. Trigger: next major release.",
        cwd=repo,
    )
    # GAP-01 / W1-2 gets no commit at all.

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
