from app.lexproof.services.version_comparison import Clause, ClauseChangeType, VersionComparisonEngine


def clause(clause_id, text, risk=20, compliance=80):
    return Clause(
        text=text,
        hash=f"hash-{clause_id}-{text}",
        risk_score=risk,
        compliance_score=compliance,
        metadata={"clause_id": clause_id},
    )


def test_detects_added_removed_modified_and_unchanged_clauses():
    comparison = VersionComparisonEngine().compare_versions(
        contract_id="contract-1",
        version_from=1,
        version_to=2,
        previous_clauses=[
            clause("same", "unchanged"),
            clause("modified", "old wording", 30, 70),
            clause("removed", "removed wording"),
        ],
        current_clauses=[
            clause("same", "unchanged"),
            clause("modified", "new wording", 45, 60),
            clause("added", "new clause"),
        ],
        previous_policy_version="policy-1",
        current_policy_version="policy-2",
        previous_risk_score=20,
        current_risk_score=25,
        previous_compliance_score=80,
        current_compliance_score=75,
    )

    assert comparison.unchanged_clauses == 1
    assert comparison.added_clauses == 1
    assert comparison.removed_clauses == 1
    assert comparison.modified_clauses == 1
    changes = {change.change_type for change in comparison.clause_changes}
    assert changes == {
        ClauseChangeType.ADDED,
        ClauseChangeType.REMOVED,
        ClauseChangeType.MODIFIED,
    }
    modified = next(change for change in comparison.clause_changes if change.change_type == ClauseChangeType.MODIFIED)
    assert modified.previous.text == "old wording"
    assert modified.current.text == "new wording"
    assert modified.risk_delta == 15
    assert modified.compliance_delta == -10


def test_reports_no_change_for_identical_scores_and_policy():
    comparison = VersionComparisonEngine().compare_versions(
        "contract-1", 1, 2, [clause("same", "unchanged")], [clause("same", "unchanged")],
        "policy-1", "policy-1", 20, 20, 80, 80,
    )
    assert comparison.unchanged_clauses == 1
    assert comparison.risk_delta == 0
    assert comparison.compliance_delta == 0
    assert comparison.policy_delta == "No policy changes"
