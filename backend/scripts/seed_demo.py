"""Deterministic Hackathon Demo Environment for LexProof.

This script creates a fully reproducible demo dataset with:
- 5 realistic fictional commercial contracts
- 3 versions of the primary contract with deliberate changes
- Demo policies and regulatory change scenarios
- Deterministic hashing for all data

Author: LexProof Development Team
Date: 2026-08-23
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Demo constants
DEMO_JURISDICTIONS = ["Delaware", "California", "New York", "Texas", "Netherlands"]
DEMO_PARTIES = [
    "Acme Corp",
    "GlobalTech Industries",
    "BlueWave Solutions",
    "NexGen Systems",
    "Apex Innovations",
]
DEMO_CONTRACT_TYPES = ["SaaS Agreement", "License Agreement", "Service Agreement", "Distribution Agreement", "NDA"]
DEMO_CLAUSE_TEMPLATES = [
    "Liability Limitation: {party1} shall not be liable for indirect, incidental, or consequential damages, including lost profits, in any event exceeding {limit}.",
    "Termination: Either party may terminate this agreement with {notice_period} days notice. {party1} may terminate for cause with {cause_notice} days notice.",
    "Privacy: {party1} shall collect only necessary personal data and comply with GDPR, CCPA, and applicable privacy laws.",
    "Audit Rights: {party1} shall have the right to inspect {party2}'s records related to this agreement upon {audit_notice} days notice and reasonable hours.",
    "Intellectual Property: All intellectual property created by {party1} under this agreement shall remain the exclusive property of {party1}.",
    "Confidentiality: Both parties shall maintain the confidentiality of all proprietary information disclosed under this agreement.",
    "Governing Law: This agreement shall be governed by the laws of {jurisdiction} and any disputes shall be resolved in {court}.",
    "Force Majeure: Neither party shall be liable for failure to perform due to circumstances beyond its reasonable control, including but not limited to {force_majeure_events}.",
]
DEMO_POLICIES = [
    {
        "name": "GDPR Compliance Policy",
        "version": "1.0",
        "jurisdiction": "EU",
        "description": "GDPR compliance requirements for data processing",
        "requirements": [
            "Data minimization: Collect only necessary data",
            "Purpose limitation: Use data only for stated purpose",
            "Right to erasure: Users can request data deletion",
            "Data subject rights: Provide access to personal data",
        ],
    },
    {
        "name": "California Consumer Privacy Act (CCPA)",
        "version": "1.0",
        "jurisdiction": "California, USA",
        "description": "CCPA requirements for California residents",
        "requirements": [
            "Right to know: Provide disclosure of data collection",
            "Right to deletion: Allow deletion of personal data",
            "Right to opt-out: Allow opt-out of data sale",
            "Privacy policy: Maintain clear privacy notices",
        ],
    },
    {
        "name": "California Privacy Rights Act (CPRA)",
        "version": "1.1",
        "jurisdiction": "California, USA",
        "description": "CPRA amendments to CCPA",
        "requirements": [
            "Expanded rights: Additional data rights for consumers",
            "Data access: Enhanced right to data access",
            "Data portability: Allow data transfer to other services",
            "Breach notification: Enhanced breach reporting",
        ],
    },
    {
        "name": "European Data Protection Regulation (EDPR)",
        "version": "2.0",
        "jurisdiction": "EU",
        "description": "EU data protection standards",
        "requirements": [
            "Data protection by design: Build in privacy from the start",
            "Data protection by default: Default to minimal data collection",
            "Privacy impact assessment: Assess data processing risks",
            "Cross-border transfer: Follow EU data transfer rules",
        ],
    },
    {
        "name": "California Cybersecurity Act",
        "version": "1.0",
        "jurisdiction": "California, USA",
        "description": "Cybersecurity requirements for businesses",
        "requirements": [
            "Data encryption: Encrypt personal data at rest and in transit",
            "Access controls: Implement role-based access controls",
            "Breach detection: Monitor for security incidents",
            "Incident response: Have documented response procedures",
        ],
    },
]
DEMO_REGULATORY_CHANGES = [
    {
        "title": "California Consumer Privacy Rights Act (CPRA) Effective Date",
        "description": "California's CPRA becomes effective. Requires enhanced data rights and breach notification.",
        "jurisdiction": "California, USA",
        "effective_date": datetime(2026, 1, 1),
        "affected_topics": ["CCPA", "California", "Privacy"],
    },
    {
        "title": "EU Data Protection Regulation (EDPR) Implementation",
        "description": "New EU data protection regulations requiring enhanced data governance.",
        "jurisdiction": "European Union",
        "effective_date": datetime(2026, 3, 1),
        "affected_topics": ["GDPR", "EU", "Data Protection"],
    },
    {
        "title": "California Cybersecurity Act Mandate",
        "description": "New cybersecurity requirements for businesses handling personal data.",
        "jurisdiction": "California, USA",
        "effective_date": datetime(2026, 6, 1),
        "affected_topics": ["Cybersecurity", "California", "Data Security"],
    },
]

DEMO_CREATED_AT = "2026-08-23T09:00:00"

# Version 1 - Original contract
VERSION_1_CLAUSES = [
    {
        "id": "clause_1",
        "title": "Liability Limitation",
        "content": "Liability Limitation: Acme Corp shall not be liable for indirect, incidental, or consequential damages, including lost profits, in any event exceeding $1,000,000.",
        "risk_score": 45.0,
        "compliance_score": 85.0,
        "policy_violations": [],
    },
    {
        "id": "clause_2",
        "title": "Termination",
        "content": "Termination: Either party may terminate this agreement with 30 days notice. Acme Corp may terminate for cause with 15 days notice.",
        "risk_score": 25.0,
        "compliance_score": 95.0,
        "policy_violations": [],
    },
    {
        "id": "clause_3",
        "title": "Privacy",
        "content": "Privacy: Acme Corp shall collect only necessary personal data and comply with GDPR, CCPA, and applicable privacy laws.",
        "risk_score": 10.0,
        "compliance_score": 100.0,
        "policy_violations": [],
    },
    {
        "id": "clause_4",
        "title": "Audit Rights",
        "content": "Audit Rights: Acme Corp shall have the right to inspect GlobalTech Industries' records related to this agreement upon 10 days notice and reasonable hours.",
        "risk_score": 30.0,
        "compliance_score": 90.0,
        "policy_violations": [],
    },
    {
        "id": "clause_5",
        "title": "Intellectual Property",
        "content": "Intellectual Property: All intellectual property created by Acme Corp under this agreement shall remain the exclusive property of Acme Corp.",
        "risk_score": 0.0,
        "compliance_score": 100.0,
        "policy_violations": [],
    },
]

# Version 2 - Modified liability and termination
VERSION_2_CLAUSES = [
    {
        "id": "clause_1",
        "title": "Liability Limitation",
        "content": "Liability Limitation: Acme Corp shall not be liable for indirect, incidental, or consequential damages, including lost profits, in any event exceeding $500,000.",
        "risk_score": 50.0,
        "compliance_score": 80.0,
        "policy_violations": ["CPRA: Reduced liability cap below California minimum"],
    },
    {
        "id": "clause_2",
        "title": "Termination",
        "content": "Termination: Either party may terminate this agreement with 60 days notice. Acme Corp may terminate for cause with 30 days notice.",
        "risk_score": 30.0,
        "compliance_score": 90.0,
        "policy_violations": [],
    },
    {
        "id": "clause_3",
        "title": "Privacy",
        "content": "Privacy: Acme Corp shall collect only necessary personal data and comply with GDPR, CCPA, and applicable privacy laws.",
        "risk_score": 10.0,
        "compliance_score": 100.0,
        "policy_violations": [],
    },
    {
        "id": "clause_4",
        "title": "Audit Rights",
        "content": "Audit Rights: Acme Corp shall have the right to inspect GlobalTech Industries' records related to this agreement upon 10 days notice and reasonable hours.",
        "risk_score": 30.0,
        "compliance_score": 90.0,
        "policy_violations": [],
    },
    {
        "id": "clause_5",
        "title": "Intellectual Property",
        "content": "Intellectual Property: All intellectual property created by Acme Corp under this agreement shall remain the exclusive property of Acme Corp.",
        "risk_score": 0.0,
        "compliance_score": 100.0,
        "policy_violations": [],
    },
]

# Version 3 - Modified privacy and audit rights
VERSION_3_CLAUSES = [
    {
        "id": "clause_1",
        "title": "Liability Limitation",
        "content": "Liability Limitation: Acme Corp shall not be liable for indirect, incidental, or consequential damages, including lost profits, in any event exceeding $1,000,000.",
        "risk_score": 45.0,
        "compliance_score": 85.0,
        "policy_violations": [],
    },
    {
        "id": "clause_2",
        "title": "Termination",
        "content": "Termination: Either party may terminate this agreement with 30 days notice. Acme Corp may terminate for cause with 15 days notice.",
        "risk_score": 25.0,
        "compliance_score": 95.0,
        "policy_violations": [],
    },
    {
        "id": "clause_3",
        "title": "Privacy",
        "content": "Privacy: Acme Corp shall collect all personal data and comply with GDPR, CCPA, and applicable privacy laws.",
        "risk_score": 70.0,
        "compliance_score": 60.0,
        "policy_violations": ["CPRA: Non-compliant data collection practices", "GDPR: Violates data minimization principle"],
    },
    {
        "id": "clause_4",
        "title": "Audit Rights",
        "content": "Audit Rights: GlobalTech Industries shall have the right to inspect Acme Corp's records related to this agreement upon 5 days notice and reasonable hours.",
        "risk_score": 60.0,
        "compliance_score": 70.0,
        "policy_violations": ["CPRA: Insufficient notice period for audit rights"],
    },
    {
        "id": "clause_5",
        "title": "Intellectual Property",
        "content": "Intellectual Property: All intellectual property created by Acme Corp under this agreement shall remain the exclusive property of Acme Corp.",
        "risk_score": 0.0,
        "compliance_score": 100.0,
        "policy_violations": [],
    },
]


def deterministic_hash(content: str) -> str:
    """Create deterministic SHA-256 hash from content.

    Args:
        content: String content to hash

    Returns:
        SHA-256 hash as hex string
    """
    return hashlib.sha256(content.encode()).hexdigest()


def generate_contract_id(contract_number: int) -> str:
    """Generate deterministic contract ID.

    Args:
        contract_number: Contract number

    Returns:
        Deterministic contract ID
    """
    return f"CONTRACT-{contract_number:06d}"


def generate_passport_id(contract_id: str, version: int) -> str:
    """Generate deterministic passport ID.

    Args:
        contract_id: Contract identifier
        version: Contract version

    Returns:
        Deterministic passport ID
    """
    content = f"{contract_id}-v{version}"
    return deterministic_hash(content)


def generate_evidence_id(contract_id: str, clause_id: str, evidence_type: str) -> str:
    """Generate deterministic evidence ID.

    Args:
        contract_id: Contract identifier
        clause_id: Clause identifier
        evidence_type: Type of evidence

    Returns:
        Deterministic evidence ID
    """
    content = f"{contract_id}-{clause_id}-{evidence_type}"
    return deterministic_hash(content)


def create_demo_contract(
    contract_number: int,
    party1: str,
    party2: str,
    contract_type: str,
    jurisdiction: str,
    effective_date: datetime,
    expiration_date: datetime,
    clauses: List[Dict[str, Any]],
    version: int,
) -> Dict[str, Any]:
    """Create a demo contract with all required fields.

    Args:
        contract_number: Contract number
        party1: First party name
        party2: Second party name
        contract_type: Type of contract
        jurisdiction: Jurisdiction
        effective_date: Effective date
        expiration_date: Expiration date
        clauses: Contract clauses
        version: Contract version

    Returns:
        Complete contract dictionary
    """
    contract_id = generate_contract_id(contract_number)
    contract_name = f"{party1} - {party2} {contract_type} Agreement"

    # Calculate overall risk and compliance scores
    total_risk = 0.0
    total_compliance = 0.0
    total_clauses = len(clauses)
    policy_violations_count = 0

    for clause in clauses:
        total_risk += clause.get("risk_score", 0.0)
        total_compliance += clause.get("compliance_score", 0.0)
        policy_violations_count += len(clause.get("policy_violations", []))

    overall_risk = round(total_risk / total_clauses, 2) if total_clauses > 0 else 0.0
    overall_compliance = round(total_compliance / total_clauses, 2) if total_clauses > 0 else 0.0

    # Generate contract hash
    contract_content = json.dumps(
        {
            "name": contract_name,
            "party1": party1,
            "party2": party2,
            "contract_type": contract_type,
            "jurisdiction": jurisdiction,
            "effective_date": effective_date.isoformat(),
            "expiration_date": expiration_date.isoformat(),
            "clauses": clauses,
        },
        sort_keys=True,
    )
    contract_hash = deterministic_hash(contract_content)

    # Create passport
    passport_id = generate_passport_id(contract_id, version)

    # Generate evidence items
    evidence_items = []
    for clause in clauses:
        for violation in clause.get("policy_violations", []):
            evidence_id = generate_evidence_id(contract_id, clause["id"], "policy_violation")
            evidence_items.append(
                {
                    "evidence_id": evidence_id,
                    "passport_id": passport_id,
                    "evidence_type": "policy_match",
                    "title": f"Policy Violation: {violation}",
                    "description": f"Contract clause violates policy requirement",
                    "content": violation,
                    "content_type": "text/plain",
                    "risk_impact": 20.0,
                    "compliance_impact": -20.0,
                    "evidence_status": "valid",
                    "contract_reference": clause["id"],
                    "policy_reference": violation,
                    "source": "ai_analysis",
                    "created_at": effective_date.isoformat(),
                    "hash": deterministic_hash(violation),
                }
            )

    policy_violations = [
        violation
        for clause in clauses
        for violation in clause.get("policy_violations", [])
    ]

    return {
        "contract": {
            "contract_id": contract_id,
            "contract_version": version,
            "contract_name": contract_name,
            "party1": party1,
            "party2": party2,
            "contract_type": contract_type,
            "jurisdiction": jurisdiction,
            "effective_date": effective_date.isoformat(),
            "expiration_date": expiration_date.isoformat(),
            "created_at": effective_date.isoformat(),
            "updated_at": effective_date.isoformat(),
            "clauses": clauses,
            "policy_violations": policy_violations,
            "evidence": evidence_items,
            "risk_score": overall_risk,
            "compliance_score": overall_compliance,
        },
        "passport": {
            "passport_id": passport_id,
            "contract_id": contract_id,
            "contract_version": version,
            "document_hash": contract_hash,
            "policy_hash": deterministic_hash(json.dumps(DEMO_POLICIES, sort_keys=True)),
            "analysis_hash": deterministic_hash(contract_content),
            "evidence_hash": deterministic_hash(json.dumps(evidence_items, sort_keys=True)),
            "risk_score": overall_risk,
            "compliance_score": overall_compliance,
            "policy_version": "1.0",
            "evidence_count": len(evidence_items),
            "created_at": effective_date.isoformat(),
            "created_by": "demo_user",
            "status": "created",
            "audit_events": [
                {
                    "timestamp": effective_date.isoformat(),
                    "event": "contract_created",
                    "user": "demo_user",
                    "description": "Contract created and analyzed",
                }
            ],
            "metadata": {
                "version": version,
                "total_clauses": total_clauses,
                "policy_violations": policy_violations_count,
            },
        },
        "clauses": clauses,
        "evidence": evidence_items,
        "policy_violations": policy_violations,
        "policies": DEMO_POLICIES,
    }


def create_all_demo_contracts() -> Dict[str, Any]:
    """Create all demo contracts with deterministic data.

    Returns:
        Dictionary containing all demo data
    """
    contracts = []

    # Contract 1: Primary contract (Version 1)
    contract_1 = create_demo_contract(
        contract_number=1,
        party1="Acme Corp",
        party2="GlobalTech Industries",
        contract_type="SaaS Agreement",
        jurisdiction="Delaware",
        effective_date=datetime(2025, 1, 15),
        expiration_date=datetime(2026, 1, 15),
        clauses=VERSION_1_CLAUSES,
        version=1,
    )
    contracts.append(contract_1)

    # Contract 2: Primary contract (Version 2)
    contract_2 = create_demo_contract(
        contract_number=1,
        party1="Acme Corp",
        party2="GlobalTech Industries",
        contract_type="SaaS Agreement",
        jurisdiction="Delaware",
        effective_date=datetime(2025, 1, 15),
        expiration_date=datetime(2026, 1, 15),
        clauses=VERSION_2_CLAUSES,
        version=2,
    )
    contracts.append(contract_2)

    # Contract 3: Primary contract (Version 3)
    contract_3 = create_demo_contract(
        contract_number=1,
        party1="Acme Corp",
        party2="GlobalTech Industries",
        contract_type="SaaS Agreement",
        jurisdiction="Delaware",
        effective_date=datetime(2025, 1, 15),
        expiration_date=datetime(2026, 1, 15),
        clauses=VERSION_3_CLAUSES,
        version=3,
    )
    contracts.append(contract_3)

    # Contract 4: License Agreement (Version 1)
    contract_4 = create_demo_contract(
        contract_number=2,
        party1="BlueWave Solutions",
        party2="NexGen Systems",
        contract_type="License Agreement",
        jurisdiction="California",
        effective_date=datetime(2025, 2, 1),
        expiration_date=datetime(2026, 2, 1),
        clauses=[{**clause, "content": clause["content"].replace("Acme Corp", "BlueWave Solutions").replace("GlobalTech Industries", "NexGen Systems")} for clause in VERSION_1_CLAUSES],
        version=1,
    )
    contracts.append(contract_4)

    # Contract 5: Service Agreement (Version 1)
    contract_5 = create_demo_contract(
        contract_number=3,
        party1="Apex Innovations",
        party2="NexGen Systems",
        contract_type="Service Agreement",
        jurisdiction="New York",
        effective_date=datetime(2025, 3, 1),
        expiration_date=datetime(2026, 3, 1),
        clauses=[{**clause, "content": clause["content"].replace("Acme Corp", "Apex Innovations").replace("GlobalTech Industries", "NexGen Systems")} for clause in VERSION_1_CLAUSES],
        version=1,
    )
    contracts.append(contract_5)

    # Contract 6: Distribution Agreement (Version 1)
    contracts.append(create_demo_contract(
        contract_number=4,
        party1="Harborline Commerce",
        party2="Summit Retail Group",
        contract_type="Distribution Agreement",
        jurisdiction="Texas",
        effective_date=datetime(2025, 4, 1),
        expiration_date=datetime(2027, 4, 1),
        clauses=[{**clause, "content": clause["content"].replace("Acme Corp", "Harborline Commerce").replace("GlobalTech Industries", "Summit Retail Group")} for clause in VERSION_1_CLAUSES],
        version=1,
    ))

    # Contract 7: Mutual NDA (Version 1)
    contracts.append(create_demo_contract(
        contract_number=5,
        party1="Cedar Peak Analytics",
        party2="Northstar Manufacturing",
        contract_type="NDA",
        jurisdiction="Netherlands",
        effective_date=datetime(2025, 5, 1),
        expiration_date=datetime(2028, 5, 1),
        clauses=[{**clause, "content": clause["content"].replace("Acme Corp", "Cedar Peak Analytics").replace("GlobalTech Industries", "Northstar Manufacturing")} for clause in VERSION_1_CLAUSES],
        version=1,
    ))

    return {
        "contracts": contracts,
        "policies": DEMO_POLICIES,
        "regulatory_changes": DEMO_REGULATORY_CHANGES,
        "created_at": DEMO_CREATED_AT,
        "created_by": "demo_seed_script",
    }


def save_demo_data(output_file: str = "demo_data.json") -> None:
    """Save demo data to JSON file.

    Args:
        output_file: Output file path
    """
    demo_data = create_all_demo_contracts()

    # Save to file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(demo_data, f, indent=2, ensure_ascii=False)

    print(f"Demo data saved to {output_file}")
    print(f"Generated {len(demo_data['contracts'])} contract records")
    print("Generated 5 distinct contract identities, including 3 primary versions")
    print(f"Generated {len(demo_data['policies'])} policies")
    print(f"Generated {len(demo_data['regulatory_changes'])} regulatory changes")


def print_summary(demo_data: Dict[str, Any]) -> None:
    """Print summary of demo data.

    Args:
        demo_data: Demo data dictionary
    """
    print("\n" + "=" * 80)
    print("DEMO DATA SUMMARY")
    print("=" * 80)

    print(f"\nContracts Generated: {len(demo_data['contracts'])}")
    for i, contract in enumerate(demo_data['contracts'], 1):
        print(f"  {i}. {contract['contract']['contract_name']} (v{contract['contract']['contract_version']})")
        print(f"     Contract ID: {contract['contract']['contract_id']}")
        print(f"     Parties: {contract['contract']['party1']} ↔ {contract['contract']['party2']}")
        print(f"     Jurisdiction: {contract['contract']['jurisdiction']}")
        print(f"     Risk Score: {contract['passport']['risk_score']}/100")
        print(f"     Compliance Score: {contract['passport']['compliance_score']}/100")
        print(f"     Policy Violations: {len(contract['policy_violations'])}")

    print(f"\nPolicies Generated: {len(demo_data['policies'])}")
    for policy in demo_data['policies']:
        print(f"  - {policy['name']} (v{policy['version']})")

    print(f"\nRegulatory Changes: {len(demo_data['regulatory_changes'])}")
    for change in demo_data['regulatory_changes']:
        print(f"  - {change['title']}")
        print(f"    Jurisdiction: {change['jurisdiction']}")
        print(f"    Effective: {change['effective_date'].strftime('%Y-%m-%d')}")

    print("\n" + "=" * 80)
    print("DETAILED CONTRACT COMPARISON (Version 1 → 2 → 3)")
    print("=" * 80)

    # Compare versions of primary contract
    contract_1 = demo_data['contracts'][0]
    contract_2 = demo_data['contracts'][1]
    contract_3 = demo_data['contracts'][2]

    print("\nContract: Acme Corp - GlobalTech Industries SaaS Agreement")
    print(f"Version 1 - Risk: {contract_1['passport']['risk_score']}, Compliance: {contract_1['passport']['compliance_score']}")
    print(f"Version 2 - Risk: {contract_2['passport']['risk_score']}, Compliance: {contract_2['passport']['compliance_score']}")
    print(f"Version 3 - Risk: {contract_3['passport']['risk_score']}, Compliance: {contract_3['passport']['compliance_score']}")

    print("\nKey Changes:")
    print("  Version 1 → 2: Liability cap reduced from $1M to $500K (CPRA violation)")
    print("  Version 2 → 3: Privacy clause collects all data (GDPR violation), Audit rights swapped (CPRA violation)")

    print("\n" + "=" * 80)


def reset_demo_data() -> None:
    """Reset demo data by removing demo files."""
    demo_files = ["demo_data.json", "demo_data_backup.json"]

    for file_path in demo_files:
        if Path(file_path).exists():
            Path(file_path).unlink()
            print(f"Removed {file_path}")

    print("\nDemo data reset complete.")


def main():
    """Main entry point for demo seed script."""
    import argparse

    parser = argparse.ArgumentParser(description="LexProof Deterministic Hackathon Demo Environment")
    parser.add_argument(
        "--output",
        default="demo_data.json",
        help="Output file for demo data (default: demo_data.json)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset demo data by removing demo files",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print summary without saving to file",
    )

    args = parser.parse_args()

    if args.reset:
        reset_demo_data()
        return

    # Create demo data
    demo_data = create_all_demo_contracts()

    # Print summary
    print_summary(demo_data)

    # Save to file if not print-only
    if not args.print_only:
        save_demo_data(args.output)


if __name__ == "__main__":
    main()
