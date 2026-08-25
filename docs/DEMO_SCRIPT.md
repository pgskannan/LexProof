# LexProof Hackathon Demo Script

**Document Version:** 1.0
**Last Updated:** 2026-08-23
**Purpose:** Comprehensive guide for demonstrating LexProof capabilities during the BLI Legal Tech Hackathon 2

---

## Table of Contents

1. [Overview](#overview)
2. [Demo Environment Setup](#demo-environment-setup)
3. [Demo Sequence](#demo-sequence)
4. [Expected Outcomes](#expected-outcomes)
5. [Troubleshooting](#troubleshooting)

---

## Overview

This document provides a step-by-step guide for demonstrating LexProof capabilities. The demo uses a **deterministic seed script** that creates a reproducible dataset with:

- **5 realistic fictional commercial contracts**
- **3 versions of the primary contract** with deliberate, intentional changes
- **5 demo policies** covering GDPR, CCPA, CPRA, EDPR, and Cybersecurity
- **3 regulatory change scenarios** demonstrating continuous compliance monitoring
- **Deterministic hashing** for all data to ensure reproducibility

### Key Features Demonstrated

1. **Legal Passport Generation**: Immutable snapshots with cryptographic fingerprints
2. **Blockchain Proof Anchoring**: Ethereum Sepolia transactions for verification
3. **Contract Time Machine**: Version comparison and change detection
4. **Compliance Monitoring**: Regulatory change simulation and impact assessment
5. **AI Remediation**: Human-gated proposal generation for compliance fixes
6. **Public Verification**: QR code-based verification of blockchain proofs
7. **Continuous Compliance**: Real-time monitoring and violation detection

---

## Demo Environment Setup

### Prerequisites

- Python 3.11+ installed
- PostgreSQL 16 with pgvector extension
- Google Cloud project with Firebase, Firestore, Cloud Storage, Secret Manager
- Ethereum Sepolia testnet access
- Node.js 18+ for frontend

### Step 1: Initialize Backend

```bash
cd C:\Projects\LexProof\backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
set GOOGLE_CLOUD_PROJECT=your-project-id
set FIREBASE_PROJECT_ID=your-firebase-project
set ETHEREUM_PRIVATE_KEY=your-testnet-private-key
set DATABASE_URL=postgresql://user:password@localhost:5432/lexproof

# Initialize database tables
python -m lexproof.scripts.init_db

# Seed demo data
python scripts/seed_demo.py --output demo_data.json
```

### Step 2: Start Backend Server

```bash
cd C:\Projects\LexProof\backend
uvicorn app.lexproof.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at: `http://localhost:8000`

### Step 3: Initialize Frontend

```bash
cd C:\Projects\LexProof\frontend
npm install
npm run dev
```

Frontend will be available at: `http://localhost:3000`

---

## Demo Sequence

### Phase 1: Legal Passport Creation (5 minutes)

**Goal:** Demonstrate Legal Passport generation with deterministic hashing

#### Step 1.1: Load Demo Data

```bash
cd C:\Projects\LexProof\backend
python scripts/seed_demo.py --print-only
```

**Expected Output:**
```
================================================================================
DEMO DATA SUMMARY
================================================================================

Contracts Generated: 7 records (5 distinct contracts)
  1. Acme Corp - GlobalTech Industries SaaS Agreement (v1)
     Contract ID: CONTRACT-000001
     Parties: Acme Corp ↔ GlobalTech Industries
     Jurisdiction: Delaware
    Risk Score: 22.0/100
    Compliance Score: 94.0/100
     Policy Violations: 0

  2. Acme Corp - GlobalTech Industries SaaS Agreement (v2)
     Contract ID: CONTRACT-000001
     Parties: Acme Corp ↔ GlobalTech Industries
     Jurisdiction: Delaware
    Risk Score: 24.0/100
    Compliance Score: 90.0/100
     Policy Violations: 1

  3. Acme Corp - GlobalTech Industries SaaS Agreement (v3)
     Contract ID: CONTRACT-000001
     Parties: Acme Corp ↔ GlobalTech Industries
     Jurisdiction: Delaware
    Risk Score: 35.0/100
    Compliance Score: 82.0/100
     Policy Violations: 3

  4. BlueWave Solutions - NexGen Systems License Agreement (v1)
     Contract ID: CONTRACT-000002
     Parties: BlueWave Solutions ↔ NexGen Systems
     Jurisdiction: California
    Risk Score: 22.0/100
    Compliance Score: 94.0/100
     Policy Violations: 0

  5. Apex Innovations - NexGen Systems Service Agreement (v1)
     Contract ID: CONTRACT-000003
    Parties: Apex Innovations ↔ NexGen Systems
     Jurisdiction: New York
      Risk Score: 22.0/100
      Compliance Score: 94.0/100
     Policy Violations: 0

    6. Harborline Commerce - Summit Retail Group Distribution Agreement (v1)
      Contract ID: CONTRACT-000004
      Parties: Harborline Commerce ↔ Summit Retail Group
      Jurisdiction: Texas
      Risk Score: 22.0/100
      Compliance Score: 94.0/100
      Policy Violations: 0

    7. Cedar Peak Analytics - Northstar Manufacturing NDA (v1)
      Contract ID: CONTRACT-000005
      Parties: Cedar Peak Analytics ↔ Northstar Manufacturing
      Jurisdiction: Netherlands
      Risk Score: 22.0/100
      Compliance Score: 94.0/100
      Policy Violations: 0

Policies Generated: 5
  - GDPR Compliance Policy (v1.0)
  - California Consumer Privacy Act (CCPA) (v1.0)
  - California Privacy Rights Act (CPRA) (v1.1)
  - European Data Protection Regulation (EDPR) (v2.0)
  - California Cybersecurity Act (v1.0)

Regulatory Changes: 3
  - California Consumer Privacy Rights Act (CPRA) Effective Date
    Jurisdiction: California, USA
    Effective: 2026-01-01
  - EU Data Protection Regulation (EDPR) Implementation
    Jurisdiction: European Union
    Effective: 2026-03-01
  - California Cybersecurity Act Mandate
    Jurisdiction: California, USA
    Effective: 2026-06-01

================================================================================
DETAILED CONTRACT COMPARISON (Version 1 → 2 → 3)
================================================================================

Contract: Acme Corp - GlobalTech Industries SaaS Agreement
Version 1 - Risk: 22.0, Compliance: 94.0
Version 2 - Risk: 24.0, Compliance: 90.0
Version 3 - Risk: 35.0, Compliance: 82.0

Key Changes:
  Version 1 → 2: Liability cap reduced from $1M to $500K (CPRA violation)
  Version 2 → 3: Privacy clause collects all data (GDPR violation), Audit rights swapped (CPRA violation)

================================================================================
```

#### Step 1.2: Load Data into Database

```bash
cd C:\Projects\LexProof\backend
python scripts/seed_demo.py --output demo_data.json
```

This will save demo data to `demo_data.json` for loading into the application.

#### Step 1.3: Demonstrate Legal Passport UI

Navigate to: `http://localhost:3000/dashboard/legal-passport`

**Demonstrate:**
1. View the Legal Passport for CONTRACT-000001 v1
2. Show cryptographic fingerprints (SHA-256 hashes)
3. Display risk score (22.0/100) and compliance score (94.0/100)
4. Show evidence items (no policy violations in v1)
5. Display audit trail

**Key Points:**
- Passports are immutable (frozen after creation)
- Hashes are deterministic (same content = same hash)
- Evidence items prove compliance findings

---

### Phase 2: Blockchain Proof Anchoring (3 minutes)

**Goal:** Demonstrate blockchain proof generation and verification

#### Step 2.1: Anchor Contract Version 1 to Ethereum

```bash
# In backend terminal, trigger blockchain proof generation
curl -X POST "http://localhost:8000/api/blockchain/anchor" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "contract_id": "CONTRACT-000001",
    "contract_version": 1
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "passport_id": "hash-of-contract-id-v1",
  "transaction_hash": "0xabc123...",
  "block_number": 12345678,
  "timestamp": "2026-08-23T10:30:00Z",
  "status": "confirmed"
}
```

#### Step 2.2: Anchor Contract Version 2 to Ethereum

```bash
curl -X POST "http://localhost:8000/api/blockchain/anchor" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "contract_id": "CONTRACT-000001",
    "contract_version": 2
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "passport_id": "hash-of-contract-id-v2",
  "transaction_hash": "0xdef456...",
  "block_number": 12345679,
  "timestamp": "2026-08-23T10:31:00Z",
  "status": "confirmed"
}
```

#### Step 2.3: Anchor Contract Version 3 to Ethereum

```bash
curl -X POST "http://localhost:8000/api/blockchain/anchor" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "contract_id": "CONTRACT-000001",
    "contract_version": 3
  }'
```

#### Step 2.4: Demonstrate Blockchain Proof UI

Navigate to: `http://localhost:3000/dashboard/blockchain-proof`

**Demonstrate:**
1. View all blockchain proofs for CONTRACT-000001
2. Show transaction hashes (SHA-256 of contract content)
3. Display block numbers and timestamps
4. Explain that proofs are immutable and verifiable on-chain
5. Show QR code for verification

**Key Points:**
- Each version gets a unique transaction hash
- Hashes are deterministic (same contract = same hash)
- Blockchain provides tamper-proof evidence

---

### Phase 3: Contract Time Machine (5 minutes)

**Goal:** Demonstrate version comparison and change detection

#### Step 3.1: Navigate to Contract Time Machine

Navigate to: `http://localhost:3000/dashboard/contracts/versions`

#### Step 3.2: Select Contract CONTRACT-000001

Click on "Acme Corp - GlobalTech Industries SaaS Agreement"

#### Step 3.3: View Version Comparison

**Demonstrate:**
1. Show all 3 versions in a timeline view
2. Highlight differences between versions
3. Display version 1 vs version 2 comparison
4. Display version 2 vs version 3 comparison

**Version 1 → 2 Changes:**
- **Liability Limitation**: $1M cap reduced to $500K
  - Policy: CPRA violation (California minimum is $750K)
  - Impact: Compliance score drops from 94.0% to 90.0%
- **Termination Notice**: 30 days → 60 days for both parties

**Version 2 → 3 Changes:**
- **Privacy Clause**: "collect only necessary" → "collect all personal data"
  - Policy: GDPR violation (data minimization principle) and CPRA violation
  - Impact: Compliance score drops from 83.0% to 75.0%
- **Audit Rights**: Acme Corp can audit GlobalTech → GlobalTech can audit Acme Corp
  - Policy: CPRA violation (5 days notice is insufficient)
  - Impact: Risk score increases from 27.0 to 34.0

#### Step 3.4: Show Diff View

**Demonstrate:**
1. Click "View Diff" for any version pair
2. Show side-by-side comparison
3. Highlight changed clauses
4. Explain that Version Comparison Engine uses stable clause IDs

**Key Points:**
- Contract Time Machine detects all changes
- Stable clause IDs prevent false positives
- Shows compliance impact of each change

---

### Phase 4: Continuous Compliance Monitoring (7 minutes)

**Goal:** Demonstrate regulatory change simulation and impact assessment

#### Step 4.1: Navigate to Compliance Command Center

Navigate to: `http://localhost:3000/dashboard/compliance/monitoring`

#### Step 4.2: Simulate CPRA Regulatory Change

```bash
curl -X POST "http://localhost:8000/api/compliance/simulate-change" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "title": "California Consumer Privacy Rights Act (CPRA) Effective Date",
    "description": "California's CPRA becomes effective. Requires enhanced data rights and breach notification.",
    "jurisdiction": "California, USA",
    "effective_date": "2026-01-01T00:00:00Z",
    "affected_topics": ["CCPA", "California", "Privacy"]
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "event_id": "evt-uuid-123",
  "regulatory_change_id": "reg-uuid-123",
  "affected_contracts": [
    {
      "contract_id": "CONTRACT-000001",
      "contract_name": "Acme Corp - GlobalTech Industries SaaS Agreement",
      "impact_level": "HIGH",
      "impact_reason": "Liability cap below California minimum",
      "affected_clause": "clause_1",
      "missing_requirement": "CPRA: Liability cap must be at least $750,000",
      "recommended_action": "Increase liability cap to $750,000 or higher"
    },
    {
      "contract_id": "CONTRACT-000002",
      "contract_name": "BlueWave Solutions - NexGen Systems License Agreement",
      "impact_level": "HIGH",
      "impact_reason": "Liability cap below California minimum",
      "affected_clause": "clause_1",
      "missing_requirement": "CPRA: Liability cap must be at least $750,000",
      "recommended_action": "Increase liability cap to $750,000 or higher"
    }
  ],
  "total_affected": 2
}
```

#### Step 4.3: View Compliance Command Center

**Demonstrate:**
1. Show totals: 5 contracts total, 2 affected by CPRA
2. Click on "HIGH" impact count to see affected contracts
3. Show impact levels: LOW, MEDIUM, HIGH, CRITICAL
4. Display affected contracts with reasons

#### Step 4.4: Simulate EDPR Regulatory Change

```bash
curl -X POST "http://localhost:8000/api/compliance/simulate-change" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "title": "EU Data Protection Regulation (EDPR) Implementation",
    "description": "New EU data protection regulations requiring enhanced data governance.",
    "jurisdiction": "European Union",
    "effective_date": "2026-03-01T00:00:00Z",
    "affected_topics": ["GDPR", "EU", "Data Protection"]
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "event_id": "evt-uuid-456",
  "regulatory_change_id": "reg-uuid-456",
  "affected_contracts": [
    {
      "contract_id": "CONTRACT-000003",
      "contract_name": "Apex Innovations - NexGen Systems Service Agreement",
      "impact_level": "HIGH",
      "impact_reason": "Non-EU jurisdiction but may process EU data",
      "affected_clause": "clause_3",
      "missing_requirement": "EDPR: Data processing impact assessment required",
      "recommended_action": "Conduct DPIA for EU data processing activities"
    }
  ],
  "total_affected": 1
}
```

#### Step 4.5: View Compliance Events

**Demonstrate:**
1. Click on "Compliance Events" to see monitoring events
2. Show regulatory change details
3. Display affected contracts with impact levels
4. Explain hybrid search: metadata + policy engine + AI analysis

**Key Points:**
- Hybrid search identifies affected contracts
- Impact level calculation (LOW, MEDIUM, HIGH, CRITICAL)
- Provides specific missing requirements and recommendations

---

### Phase 5: AI Remediation (8 minutes)

**Goal:** Demonstrate human-gated AI remediation workflow

#### Step 5.1: Navigate to Remediation

Navigate to: `http://localhost:3000/dashboard/compliance/violations`

#### Step 5.2: View Contract with Violations

Click on CONTRACT-000001 (Version 2) which has 1 policy violation

**Demonstrate:**
1. Show affected clause: "Liability Limitation"
2. Show current language: "$500,000 cap"
3. Show regulatory requirement: CPRA minimum is $750,000
4. Show compliance score: 83.0%

#### Step 5.3: Generate AI Remediation Proposal

```bash
curl -X POST "http://localhost:8000/api/compliance/remediation/proposals" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "contract_id": "CONTRACT-000001",
    "contract_version": 2,
    "event_id": "evt-uuid-123"
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "proposal_id": "prop-uuid-123",
  "contract_id": "CONTRACT-000001",
  "contract_version": 2,
  "event_id": "evt-uuid-123",
  "affected_clause": "clause_1",
  "current_language": "Liability Limitation: Acme Corp shall not be liable for indirect, incidental, or consequential damages, including lost profits, in any event exceeding $500,000.",
  "regulatory_requirement": "CPRA: Liability cap must be at least $750,000 for businesses processing personal data from California residents.",
  "proposed_amendment": "Liability Limitation: Acme Corp shall not be liable for indirect, incidental, or consequential damages, including lost profits, in any event exceeding $750,000.",
  "risk_before": 24.0,
  "compliance_before": 90.0,
  "risk_after": 22.0,
  "compliance_after": 94.0,
  "compliance_improvement": "+4.0%",
  "ai_reasoning": "Increasing liability cap to $750,000 brings contract into compliance with California Consumer Privacy Rights Act (CPRA) minimum requirement. This aligns with CPRA Section 1798.185 which requires liability caps for personal data processing.",
  "ai_proposal": "Proposed amendment increases liability cap from $500,000 to $750,000 to meet CPRA minimum requirements. This change affects clause 1 (Liability Limitation) and will improve overall compliance score from 90.0% to 94.0%.",
  "created_at": "2026-08-23T10:45:00Z",
  "created_by": "demo_user"
}
```

#### Step 5.4: Review Proposal

**Demonstrate:**
1. Show before/after comparison
2. Display risk scores: 24.0% → 22.0%
3. Display compliance scores: 90.0% → 94.0%
4. Show AI reasoning
5. Show compliance improvement: +10.0%

#### Step 5.5: Approve Proposal

```bash
curl -X POST "http://localhost:8000/api/compliance/remediation/proposals/{proposal_id}/approval" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "approved": true,
    "comments": "Approved by legal review. Liability cap increased to $750,000."
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "amendment_request_id": "amend-uuid-123",
  "proposal_id": "prop-uuid-123",
  "contract_version": 3,
  "amended_contract_content": "...",
  "new_passport_id": "hash-of-contract-id-v3",
  "new_evidence_items": [...],
  "audit_trail": [...],
  "status": "approved"
}
```

#### Step 5.6: View Final Contract Version

**Demonstrate:**
1. Navigate to Contract Time Machine
2. Show Version 3 with approved amendments
3. Show updated evidence items
4. Display new blockchain proof

**Key Points:**
- AI generates proposed amendment
- Human approval is mandatory (no silent changes)
- Complete audit trail from detection to amendment
- New evidence items created for compliance

---

### Phase 6: Public Verification Portal (5 minutes)

**Goal:** Demonstrate QR code-based verification of blockchain proofs

#### Step 6.1: Navigate to Verification Portal

Navigate to: `http://localhost:3000/dashboard/verification`

#### Step 6.2: Select a Contract

Click on "Acme Corp - GlobalTech Industries SaaS Agreement"

#### Step 6.3: Show QR Code for Blockchain Proof

**Demonstrate:**
1. Select Version 1 (earliest version)
2. Show QR code containing:
   - Contract ID: CONTRACT-000001
   - Version: 1
   - Transaction Hash: 0xabc123...
   - Blockchain Network: Ethereum Sepolia
3. Explain that QR code is deterministic
4. Scan QR code to verify on-chain

#### Step 6.4: Explain Verification Process

**Demonstrate:**
1. QR code contains all proof information
2. Anyone can verify by:
   - Scanning QR code with verification tool
   - Looking up transaction hash on Etherscan
   - Verifying hash matches contract content
3. Blockchain provides tamper-proof evidence
4. Legal passport is immutable

**Key Points:**
- QR code is deterministic (same contract = same QR code)
- Verification is independent of LexProof
- Blockchain provides cryptographic proof
- Legal passport is immutable and verifiable

---

### Phase 7: Reports and Dashboard (5 minutes)

**Goal:** Demonstrate reporting capabilities and dashboard navigation

#### Step 7.1: Navigate to Dashboard

Navigate to: `http://localhost:3000/dashboard`

#### Step 7.2: Show Quick Stats

**Demonstrate:**
1. Total Contracts: 7 records across 5 contract identities
2. Active Reviews: 3 (versions of CONTRACT-000001)
3. Compliance Issues: 4 (after CPRA simulation)
4. Recent Activity: Show last 3 activities

#### Step 7.3: Navigate to Reports

Navigate to: `http://localhost:3000/dashboard/reports`

**Demonstrate:**
1. Generate Compliance Report
2. Generate Risk Analysis Report
3. Show generated reports

#### Step 7.4: Show Navigation Structure

**Demonstrate:**
1. Contracts → All Contracts (5 contracts)
2. Contracts → Reviews (3 reviews)
3. Contracts → Versions (3 versions of CONTRACT-000001)
4. AI Analysis → Risk, Clauses, Findings
5. Compliance → Policies, Violations, Monitoring
6. Legal Passport → Version details
7. Blockchain Proof → All proofs
8. Verification → QR code generation
9. Reports → Generate reports
10. Administration → System config

**Key Points:**
- Dashboard provides overview of all features
- Clear navigation structure
- Quick access to all major capabilities

---

## Expected Outcomes

### Demo Summary

By the end of the demo, you will have demonstrated:

1. **Legal Passport Generation** ✅
   - Immutable snapshots with cryptographic fingerprints
   - Deterministic hashing
   - Evidence tracking

2. **Blockchain Proof Anchoring** ✅
   - Ethereum Sepolia transactions
   - Transaction hash verification
   - Tamper-proof proof storage

3. **Contract Time Machine** ✅
   - Version comparison
   - Change detection
   - Diff view

4. **Compliance Monitoring** ✅
   - Regulatory change simulation
   - Impact level calculation
   - Hybrid search

5. **AI Remediation** ✅
   - Proposal generation
   - Human approval workflow
   - Complete audit trail

6. **Public Verification** ✅
   - QR code generation
   - On-chain verification
   - Independent verification

7. **Dashboard Navigation** ✅
   - Quick stats
   - Recent activity
   - Clear navigation structure

### Key Metrics

| Metric | Value |
|--------|-------|
| Contract records | 7 (5 distinct contracts) |
| Contract Versions | 3 (for primary contract) |
| Policy Violations | 4 (after CPRA simulation) |
| Blockchain Proofs | 3 |
| Regulatory Changes | 3 |
| Compliance Scores | 90.0 → 94.0% (after remediation) |

---

## Troubleshooting

### Issue: Demo data not loading

**Solution:**
```bash
cd C:\Projects\LexProof\backend
python scripts/seed_demo.py --output demo_data.json
python scripts/seed_demo.py --print-only
```

### Issue: Blockchain proof not generating

**Solution:**
1. Check Ethereum Sepolia testnet connectivity
2. Verify private key has testnet ETH
3. Check backend logs for errors

### Issue: Compliance monitoring not working

**Solution:**
1. Verify database tables exist
2. Check regulatory change simulation
3. Review backend logs for errors

### Issue: Frontend not connecting to backend

**Solution:**
1. Verify backend is running on port 8000
2. Check CORS settings
3. Verify API endpoints are accessible

### Issue: Deterministic hashes not matching

**Solution:**
1. Ensure same content is used for hashing
2. Check deterministic_hash function implementation
3. Verify content is serialized consistently

---

## Reset Demo Data

To reset the demo environment:

```bash
cd C:\Projects\LexProof\backend
python scripts/seed_demo.py --reset
```

This will remove:
- demo_data.json
- demo_data_backup.json

---

## Demo Best Practices

1. **Start Early**: Allow time for setup and troubleshooting
2. **Practice**: Run through demo sequence multiple times
3. **Explain**: Clearly explain each step and its purpose
4. **Highlight**: Point out key features and benefits
5. **Engage**: Encourage questions from judges and audience
6. **Backup**: Keep backup data files handy
7. **Document**: Take notes on any issues encountered

---

## Contact

For questions or issues during the demo:
- Review this document thoroughly
- Check backend logs for errors
- Verify environment setup
- Test connectivity between frontend and backend

---

**End of Demo Script**
