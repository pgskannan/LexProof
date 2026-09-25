from datetime import datetime, timezone

from app.lexproof.domains.passport.proof_package import build_proof_package


def test_proof_package_includes_hashes_snapshot_and_anchors():
    generated_at = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    bundle = build_proof_package(
        {
            "passport_id": "passport-1",
            "contract_id": "contract-1",
            "contract_version": 2,
            "document_hash": "aa" * 32,
            "policy_hash": "bb" * 32,
            "analysis_hash": "cc" * 32,
            "evidence_hash": "dd" * 32,
            "metadata": {
                "passport_hash": "ee" * 32,
                "original_document_hash": "ff" * 32,
                "verification_snapshot": {
                    "document_content": "The parties agree...",
                    "evidence_items": [
                        {
                            "evidence_id": "ev-1",
                            "title": "Liability cap",
                            "hash": "11" * 32,
                        }
                    ],
                },
            },
        },
        evidence_items=[{"evidence_id": "ev-1", "title": "Liability cap", "hash": "11" * 32}],
        anchors_by_id={
            "ev-1": {
                "blockchain_network": "ethereum-sepolia",
                "contract_address": "0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191",
                "transaction_hash": "0xabc",
                "block_number": 123,
                "evidence_hash": "11" * 32,
            }
        },
        contract_name="Acme MSA",
        generated_at=generated_at,
    )

    assert bundle["hash_algorithm"] == "sha256"
    assert bundle["contract"]["name"] == "Acme MSA"
    assert bundle["contract"]["passport_id"] == "passport-1"
    assert bundle["hashes"]["document_hash"] == "aa" * 32
    assert bundle["verification_snapshot"]["document_content"] == "The parties agree..."
    assert bundle["evidence"][0]["anchor"]["transaction_hash"] == "0xabc"
    assert bundle["registry_contract_address"] == "0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191"
    assert "LexProof" in bundle["how_to_verify"]
    assert bundle["bundle_generated_at"] == generated_at.isoformat()


def test_proof_package_omits_empty_anchors():
    bundle = build_proof_package(
        {
            "passport_id": "passport-2",
            "contract_id": "contract-2",
            "contract_version": 1,
            "document_hash": "aa",
            "policy_hash": "bb",
            "analysis_hash": "cc",
            "evidence_hash": "dd",
            "metadata": {},
        },
        evidence_items=[{"evidence_id": "ev-2", "title": "Unanchored", "hash": "22" * 32}],
        anchors_by_id={},
    )
    assert bundle["evidence"][0]["anchor"] is None
    assert bundle["verification_snapshot"] is None


def test_proof_package_prefers_live_anchored_evidence_over_snapshot_ids():
    """Regression: snapshot evidence ids differ from the anchored evidence_records.

    PassportService builds the snapshot's evidence_items with its own ids, while
    version analysis anchors separate evidence_records. Preferring the snapshot
    shipped a bundle with no anchors, so verify-offline.html said NOT ANCHORED
    for evidence that is on Sepolia.
    """
    bundle = build_proof_package(
        {
            "passport_id": "passport-3",
            "contract_id": "contract-3",
            "contract_version": 1,
            "metadata": {
                "verification_snapshot": {
                    "evidence_items": [{"evidence_id": "snapshot-only", "title": "Snapshot item", "hash": "33" * 32}],
                },
            },
        },
        evidence_items=[{"evidence_id": "live-1", "title": "Anchored clause"}],
        anchors_by_id={
            "live-1": {
                "contract_address": "0x2C508F1CAFa4B3dD75A33b6FAcde12742f76d191",
                "transaction_hash": "0xdef",
                "evidence_hash": "44" * 32,
            }
        },
    )
    assert [item["evidence_id"] for item in bundle["evidence"]] == ["live-1"]
    assert bundle["evidence"][0]["anchor"]["transaction_hash"] == "0xdef"
    assert bundle["evidence"][0]["hash"] == "44" * 32


def test_proof_package_falls_back_to_snapshot_without_live_records():
    bundle = build_proof_package(
        {
            "passport_id": "passport-4",
            "metadata": {
                "verification_snapshot": {
                    "evidence_items": [{"evidence_id": "snap-1", "title": "Snapshot item", "hash": "55" * 32}],
                },
            },
        },
        evidence_items=[],
        anchors_by_id={},
    )
    assert [item["evidence_id"] for item in bundle["evidence"]] == ["snap-1"]
    assert bundle["evidence"][0]["hash"] == "55" * 32
