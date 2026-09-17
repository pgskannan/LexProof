from app.lexproof.services.published_version_status import project_published_version_status, project_published_version_status_batch
from app.lexproof.domains.passport.utils.hashing import hash_evidence_item
from tests.fakes import FakeRepository


def repositories():
    return {
        "passports": FakeRepository("legal_passports"),
        "evidence_records": FakeRepository("evidence_records"),
        "evidence_anchors": FakeRepository("evidence_anchors"),
        "findings": FakeRepository("risk_findings"),
    }


def seed(version_status="failed", proposal_status="failed", anchored=True):
    FakeRepository.stores = {
        "legal_passports": {
            "passport-1": {
                "id": "passport-1",
                "passport_id": "passport-1",
                "version_id": "version-2",
                "contract_id": "contract-1",
                "contract_version": 2,
                "status": "created",
            }
        },
        "evidence_records": {
            "evidence-1": {
                "id": "evidence-1",
                "evidence_id": "evidence-1",
                "passport_id": "passport-1",
                "contract_reference": "Section 7",
                "evidence_type": "clause",
                "title": "Termination",
            }
        },
        "evidence_anchors": {},
        "risk_findings": {},
    }
    evidence = FakeRepository.stores["evidence_records"]["evidence-1"]
    if anchored:
        FakeRepository.stores["evidence_anchors"]["evidence-1"] = {
            "id": "evidence-1",
            "evidence_id": "evidence-1",
            "evidence_hash": hash_evidence_item(evidence),
        }
    return (
        {
            "id": "version-2",
            "contract_id": "contract-1",
            "version_number": 2,
            "analysis_status": version_status,
        },
        {
            "proposal_id": "proposal-1",
            "published_version_id": "version-2",
            "analysis_status": proposal_status,
            "evidence": "Section 7",
        },
        repositories(),
    )


def project(version, proposal, repos):
    return project_published_version_status(
        version,
        proposal,
        passports=repos["passports"],
        evidence_records=repos["evidence_records"],
        evidence_anchors=repos["evidence_anchors"],
        findings=repos["findings"],
    )


def test_confirmed_proof_overrides_failed_analysis():
    version, proposal, repos = seed(version_status="failed", proposal_status="failed", anchored=True)
    result = project(version, proposal, repos)
    assert result["proof_status"] == "confirmed"
    assert result["recommended_action"] == "none"
    assert result["anchored_evidence_count"] == 1


def test_failed_without_proof_is_failed_and_retryable():
    version, proposal, repos = seed(version_status="failed", proposal_status="failed", anchored=False)
    result = project(version, proposal, repos)
    assert result["proof_status"] == "failed"
    assert result["recommended_action"] == "retry"


def test_processing_without_proof_is_processing():
    version, proposal, repos = seed(version_status="processing", proposal_status="processing", anchored=False)
    result = project(version, proposal, repos)
    assert result["proof_status"] == "processing"
    assert result["recommended_action"] == "wait"


def test_pending_without_proof_is_processing():
    version, proposal, repos = seed(version_status="pending", proposal_status="pending", anchored=False)
    result = project(version, proposal, repos)
    assert result["proof_status"] == "processing"


def test_complete_without_proof_requires_action():
    version, proposal, repos = seed(version_status="complete", proposal_status="complete", anchored=False)
    result = project(version, proposal, repos)
    assert result["proof_status"] == "action_required"
    assert result["recommended_action"] == "retry"


def test_batch_projection_uses_snapshots_without_repository_scans():
    version, proposal, repos = seed(version_status="failed", proposal_status="failed", anchored=True)

    class SnapshotRepository:
        def __init__(self, rows):
            self.rows = rows
            self.stream_calls = 0

        def stream(self):
            self.stream_calls += 1
            return iter(self.rows)

    snapshots = {
        name: SnapshotRepository(list(repo.stream()))
        for name, repo in repos.items()
    }
    projections = project_published_version_status_batch(
        [version],
        [proposal],
        list(snapshots["passports"].stream()),
        list(snapshots["evidence_records"].stream()),
        list(snapshots["evidence_anchors"].stream()),
        list(snapshots["findings"].stream()),
    )

    assert projections["version-2"]["proof_status"] == "confirmed"
    assert all(snapshot.stream_calls == 1 for snapshot in snapshots.values())
