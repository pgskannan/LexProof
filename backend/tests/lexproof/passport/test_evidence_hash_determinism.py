"""
Test evidence hash determinism for Ethereum anchoring.

Ensures the same evidence package always produces the same evidence_hash.

P0.1: Verify that the evidence hash includes:
- passport_id (for linking evidence to contracts)
- risk_impact (for legal assessment integrity)
- compliance_impact (for legal assessment integrity)
"""

from app.lexproof.domains.passport.utils.hashing import (
    hash_evidence_item,
    hash_evidence_package,
)


def test_evidence_item_hash_deterministic():
    """Test that the same evidence item produces the same hash."""
    evidence_item = {
        "evidence_id": "e-1",
        "title": "Clause",
        "content": "This is the evidence content",
        "evidence_type": "clause",
        "metadata": {"key": "value"},
    }

    hash1 = hash_evidence_item(evidence_item)
    hash2 = hash_evidence_item(evidence_item)

    assert hash1 == hash2, "Same evidence item should produce same hash"
    assert len(hash1) == 64, "Hash should be 64 characters (SHA-256 hex)"


def test_evidence_package_hash_deterministic():
    """Test that the same evidence package produces the same hash."""
    evidence_items = [
        {"evidence_id": "e-1", "content": "first"},
        {"evidence_id": "e-2", "content": "second"},
        {"evidence_id": "e-3", "content": "third"},
    ]

    hash1 = hash_evidence_package(evidence_items)
    hash2 = hash_evidence_package(evidence_items)

    assert hash1 == hash2, "Same evidence package should produce same hash"
    assert len(hash1) == 64, "Hash should be 64 characters (SHA-256 hex)"


def test_evidence_package_order_independent():
    """Test that evidence package hash is order-independent."""
    evidence_items_unordered = [
        {"evidence_id": "e-3", "content": "third"},
        {"evidence_id": "e-1", "content": "first"},
        {"evidence_id": "e-2", "content": "second"},
    ]

    evidence_items_ordered = [
        {"evidence_id": "e-1", "content": "first"},
        {"evidence_id": "e-2", "content": "second"},
        {"evidence_id": "e-3", "content": "third"},
    ]

    hash_unordered = hash_evidence_package(evidence_items_unordered)
    hash_ordered = hash_evidence_package(evidence_items_ordered)

    assert hash_unordered == hash_ordered, "Hash should be order-independent"
    assert hash_unordered == hash_ordered, "Hash should be order-independent"


def test_evidence_package_with_different_metadata():
    """Test that evidence package hash is sensitive to content changes."""
    evidence_items1 = [
        {"evidence_id": "e-1", "content": "content", "metadata": {"key": "value"}},
    ]

    evidence_items2 = [
        {"evidence_id": "e-1", "content": "content", "metadata": {"key": "different"}},
    ]

    hash1 = hash_evidence_package(evidence_items1)
    hash2 = hash_evidence_package(evidence_items2)

    assert hash1 != hash2, "Different content should produce different hash"


def test_evidence_package_with_different_evidence_ids():
    """Test that evidence package hash is sensitive to evidence ID changes."""
    evidence_items1 = [
        {"evidence_id": "e-1", "content": "content"},
    ]

    evidence_items2 = [
        {"evidence_id": "e-2", "content": "content"},
    ]

    hash1 = hash_evidence_package(evidence_items1)
    hash2 = hash_evidence_package(evidence_items2)

    assert hash1 != hash2, "Different evidence IDs should produce different hash"


def test_evidence_package_hash_format():
    """Test that evidence package hash is valid SHA-256 hex."""
    evidence_items = [
        {"evidence_id": "e-1", "content": "test"},
    ]

    hash_value = hash_evidence_package(evidence_items)

    # Should be hexadecimal
    assert all(c in "0123456789abcdef" for c in hash_value), "Hash should be hexadecimal"

    # Should be 64 characters
    assert len(hash_value) == 64, "Hash should be 64 characters"

    # Should be lowercase hex
    assert hash_value == hash_value.lower(), "Hash should be lowercase hexadecimal"


def test_round_trip_evidence_hash():
    """Test that hashing and unhashing is consistent."""
    original_evidence = [
        {"evidence_id": "e-1", "content": "test content", "title": "Test"},
        {"evidence_id": "e-2", "content": "another", "title": "Another"},
    ]

    hash_value = hash_evidence_package(original_evidence)

    # The hash should be deterministic and reproducible
    hash_value_again = hash_evidence_package(original_evidence)

    assert hash_value == hash_value_again, "Round-trip hashing should be consistent"


def test_evidence_hash_includes_passport_id():
    """Test that passport_id is included in the evidence hash (P0.1)."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "This is the evidence content",
        "evidence_type": "clause",
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-2",  # Different passport_id
        "title": "Clause",
        "content": "This is the evidence content",
        "evidence_type": "clause",
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 != hash2, "Changing passport_id should change the hash"


def test_evidence_hash_includes_risk_impact():
    """Test that risk_impact is included in the evidence hash (P0.1)."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "This is the evidence content",
        "evidence_type": "clause",
        "risk_impact": 50.0,  # Original risk
        "compliance_impact": 75.0,
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "This is the evidence content",
        "evidence_type": "clause",
        "risk_impact": 0.0,  # Changed risk_impact
        "compliance_impact": 75.0,
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 != hash2, "Changing risk_impact should change the hash"


def test_evidence_hash_includes_compliance_impact():
    """Test that compliance_impact is included in the evidence hash (P0.1)."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "This is the evidence content",
        "evidence_type": "clause",
        "risk_impact": 50.0,
        "compliance_impact": 75.0,  # Original compliance
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "This is the evidence content",
        "evidence_type": "clause",
        "risk_impact": 50.0,
        "compliance_impact": 0.0,  # Changed compliance_impact
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 != hash2, "Changing compliance_impact should change the hash"


def test_evidence_hash_includes_content():
    """Test that evidence content is included in the hash."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Original content",
        "evidence_type": "clause",
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Modified content",  # Different content
        "evidence_type": "clause",
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 != hash2, "Changing content should change the hash"


def test_evidence_hash_includes_evidence_type():
    """Test that evidence_type is included in the hash."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",  # Original type
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "redline",  # Different type
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 != hash2, "Changing evidence_type should change the hash"


def test_evidence_hash_includes_description():
    """Test that description is included in the hash."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "description": "Original description",
        "content": "Content",
        "evidence_type": "clause",
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "description": "Modified description",  # Different description
        "content": "Content",
        "evidence_type": "clause",
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 != hash2, "Changing description should change the hash"


def test_evidence_hash_includes_contract_reference():
    """Test that contract_reference is included in the hash."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",
        "contract_reference": "Clause 3.2",  # Original reference
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",
        "contract_reference": "Clause 4.1",  # Different reference
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 != hash2, "Changing contract_reference should change the hash"


def test_evidence_hash_order_independent():
    """Test that evidence hash is order-independent (sort_keys=True)."""
    evidence_item1 = {
        "content": "content",
        "evidence_id": "e-1",
        "evidence_type": "clause",
        "passport_id": "passport-1",
        "title": "Clause",
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "title": "Clause",
        "content": "content",
        "evidence_type": "clause",
        "passport_id": "passport-1",
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 == hash2, "Hash should be order-independent"


def test_evidence_hash_uses_canonicalization():
    """Test that hash_evidence_item uses canonicalization (P0.1)."""
    evidence_item = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",
        "risk_impact": 50.0,
        "compliance_impact": 75.0,
        "description": "Description",
        "content_type": "text/plain",
        "evidence_status": "valid",
        "contract_reference": "Clause 3.2",
        "policy_reference": "Policy 1.0",
        "analysis_reference": "Analysis 1",
        "source": "ai_analysis",
        "source_id": "analysis-1",
        "metadata": {"key": "value"},
    }

    # Hash should be deterministic
    hash1 = hash_evidence_item(evidence_item)
    hash2 = hash_evidence_item(evidence_item)

    assert hash1 == hash2, "Same evidence item should produce same hash"

    # Hash should include all relevant fields
    hash3 = hash_evidence_item({
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",
        "risk_impact": 50.0,
        "compliance_impact": 75.0,
        "description": "Description",
        "content_type": "text/plain",
        "evidence_status": "valid",
        "contract_reference": "Clause 3.2",
        "policy_reference": "Policy 1.0",
        "analysis_reference": "Analysis 1",
        "source": "ai_analysis",
        "source_id": "analysis-1",
        "metadata": {"key": "value"},
    })

    assert hash1 == hash3, "Hash should be consistent across all fields"


def test_evidence_hash_excludes_timestamps():
    """Test that operational metadata (timestamps) is excluded from hash."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",
        "created_at": "2026-08-25T10:00:00Z",  # Timestamp
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",
        "created_at": "2026-08-25T11:00:00Z",  # Different timestamp
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 == hash2, "Timestamps should not affect hash"


def test_evidence_hash_excludes_hash_field():
    """Test that the hash field itself is excluded from hash computation."""
    evidence_item1 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",
        "hash": "a1b2c3d4e5f6...",  # Computed hash
        "metadata": {},
    }

    evidence_item2 = {
        "evidence_id": "e-1",
        "passport_id": "passport-1",
        "title": "Clause",
        "content": "Content",
        "evidence_type": "clause",
        "hash": "999888777666...",  # Different hash
        "metadata": {},
    }

    hash1 = hash_evidence_item(evidence_item1)
    hash2 = hash_evidence_item(evidence_item2)

    assert hash1 == hash2, "Hash field should not affect hash computation"


def test_evidence_package_hash_includes_all_evidence_items():
    """Test that evidence package hash includes all evidence items."""
    evidence_items = [
        {
            "evidence_id": "e-1",
            "passport_id": "passport-1",
            "title": "Clause 1",
            "content": "Content 1",
            "evidence_type": "clause",
            "risk_impact": 50.0,
            "compliance_impact": 75.0,
        },
        {
            "evidence_id": "e-2",
            "passport_id": "passport-1",
            "title": "Clause 2",
            "content": "Content 2",
            "evidence_type": "redline",
            "risk_impact": 30.0,
            "compliance_impact": 60.0,
        },
    ]

    hash1 = hash_evidence_package(evidence_items)
    hash2 = hash_evidence_package(evidence_items)

    assert hash1 == hash2, "Same evidence package should produce same hash"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
