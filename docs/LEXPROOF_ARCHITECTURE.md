# LexProof Architecture Document

**Project**: LexProof — Verifiable Legal Intelligence  
**Based On**: ContractRiskEdge (v1.0.0)  
**Created**: 2026-08-23  
**Status**: Architecture Design Phase

---

## Executive Summary

LexProof builds upon the mature ContractRiskEdge platform to add verifiable legal intelligence capabilities. The platform provides:
- AI-powered contract risk analysis and compliance benchmarking
- Multi-tenant architecture with RBAC
- Document ingestion, OCR, chunking, and semantic search
- Policy engine and risk scoring
- Audit logging and governance

This document analyzes the existing ContractRiskEdge architecture to identify reusable components, required modifications, and new components needed for LexProof's verifiable legal intelligence features.

---

## Table of Contents

1. [Current Architecture Overview](#current-architecture-overview)
2. [Component Analysis](#component-analysis)
3. [REUSE / MODIFY / NEW Matrix](#reuse--modify--new-matrix)
4. [Data Flow](#data-flow)
5. [Security Boundaries](#security-boundaries)
6. [Google Cloud Architecture](#google-cloud-architecture)
7. [Firebase Architecture](#firebase-architecture)
8. [Blockchain Architecture](#blockchain-architecture)
9. [Dependencies](#dependencies)
10. [Implementation Roadmap](#implementation-roadmap)

---

## Current Architecture Overview

### Tech Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| **Backend** | FastAPI | >=0.115.0 | Async web API framework |
| **Frontend** | Next.js 14 | - | React-based UI |
| **Database** | PostgreSQL 16 | - | Primary data store |
| **Vector DB** | pgvector | >=0.4.2 | Semantic search |
| **ML** | spaCy, scikit-learn, Transformers | >=4.38.0 | NLP and ML models |
| **Auth** | Auth0 | - | OAuth2 + JWT |
| **Queue** | Celery + Redis | >=5.4.0 | Background task processing |
| **Storage** | MinIO (S3-compatible) | - | Document storage |
| **Observability** | Sentry, Prometheus, OpenTelemetry | - | Monitoring and tracing |

### Directory Structure

```
ContractRiskEdge/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── kernel/            # Core infrastructure
│   │   │   ├── database/      # DB models, sessions
│   │   │   ├── security/      # Auth, RBAC, permissions
│   │   │   ├── middleware/    # Request processing
│   │   │   ├── events/        # Event bus
│   │   │   ├── telemetry/     # Logging, tracing
│   │   │   └── web/           # HTTP utilities
│   │   ├── domains/           # Domain-specific logic
│   │   │   ├── ingestion/     # Document upload pipeline
│   │   │   ├── review/        # Contract review workflow
│   │   │   ├── policy/        # Policy engine
│   │   │   ├── ai/            # AI orchestration
│   │   │   ├── vectors/       # Vector embeddings
│   │   │   ├── playbook/      # Playbook management
│   │   │   └── contracts/     # Contract domain
│   │   └── main.py            # FastAPI app factory
│   ├── tests/                 # Unit and integration tests
│   ├── workers/               # Celery workers
│   └── requirements.txt       # Python dependencies
├── frontend/                   # Next.js application
│   ├── app/                   # Next.js 14 app router
│   ├── components/            # React components
│   ├── services/              # API clients
│   └── package.json           # Node dependencies
├── ml/                        # ML training and inference
└── infra/                     # Infrastructure as code
```

---

## Component Analysis

### 1. Backend Architecture

#### Core Infrastructure (kernel/)

**Status**: ✅ **HIGHLY REUSABLE**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **Database Layer** | `kernel/database/` | 95% | Tenant-aware session factory, ORM base |
| **Security & Auth** | `kernel/security/` | 90% | JWT validation, RBAC, permissions |
| **Middleware Stack** | `kernel/middleware/` | 85% | CORS, rate limiting, tenant context, audit |
| **Event Bus** | `kernel/events/bus.py` | 100% | In-memory event system for decoupling |
| **Telemetry** | `kernel/telemetry/` | 90% | Structured logging, OpenTelemetry tracing |
| **Repository Pattern** | `kernel/repository/` | 100% | Generic repository base classes |
| **Web Utilities** | `kernel/web/` | 80% | Pagination, exception handling |

**Key Features**:
- Multi-tenant support via tenant_id FK on all models
- Tenant-aware session factory (`TenantAwareSessionFactory`)
- Role-based access control with permission decorators
- Request ID, correlation ID, and audit trail generation
- Structured logging with structured logging middleware
- Prometheus metrics collection

**Modifications Needed**:
- Add blockchain transaction verification to audit middleware
- Enhance tenant isolation for blockchain wallet management
- Add digital signature verification hooks

---

### 2. Frontend Architecture

**Status**: ✅ **REUSABLE (with modifications)**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **Next.js App Router** | `frontend/app/` | 80% | Authenticated layout, dashboard, contracts |
| **Auth Provider** | `frontend/components/auth/` | 90% | Auth0 integration, user context |
| **API Services** | `frontend/services/` | 85% | API client abstractions |
| **UI Components** | `frontend/components/` | 70% | Reusable UI primitives |

**Key Features**:
- Protected routes with auth guard
- JWT token refresh handling
- API client with error handling
- Responsive design with Tailwind CSS
- Dark theme (navy-900, gold-400 accents)

**Modifications Needed**:
- Add blockchain wallet connection UI
- Add document verification status indicators
- Add audit trail viewer
- Add digital signature verification UI

---

### 3. Contract Ingestion Pipeline

**Status**: ✅ **REUSABLE (with extensions)**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **Upload Service** | `domains/ingestion/service.py` | 90% | Upload lifecycle, validation, presigned URLs |
| **Ingestion State Machine** | `domains/ingestion/models.py` | 100% | 14-state state machine with validation |
| **Storage Integration** | `integrations/storage/s3.py` | 85% | MinIO/S3 presigned URL generation |
| **Security Validation** | `domains/ingestion/security.py` | 95% | File type, size, content validation |
| **Recovery** | `domains/ingestion/recovery.py` | 80% | Stuck upload recovery on startup |
| **Celery Tasks** | `workers/tasks/ingestion.py` | 85% | Async OCR, chunking, embedding |

**Ingestion State Machine**:
```
UPLOADED → VALIDATING → VALIDATED → STORAGE_CONFIRMED
→ OCR_PENDING → OCR_PROCESSING → OCR_COMPLETE
→ CHUNKING_PENDING → EMBEDDING_PENDING → ANALYSIS_PENDING
→ REVIEW_READY
```

**Modifications Needed**:
- Add blockchain transaction hash generation on completion
- Add document hash verification for tamper detection
- Add multi-signature workflow for critical contracts

---

### 4. OCR / Document Extraction

**Status**: ✅ **REUSABLE**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **PDF Extraction** | `integrations/pdf_extractor.py` | 100% | PyMuPDF-based extraction |
| **DOCX Extraction** | `integrations/docx_extractor.py` | 100% | python-docx-based extraction |
| **Text Normalization** | `domains/ingestion/text_normalizer.py` | 95% | Cleaning, deduplication, OCR post-processing |

**Modifications Needed**:
- Add OCR output hashing for tamper detection
- Add document metadata extraction for blockchain proof

---

### 5. Chunking

**Status**: ✅ **REUSABLE**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **Chunking Service** | `domains/vectors/chunking.py` | 90% | Semantic chunking with overlap |
| **Partitioning** | `domains/vectors/partition/` | 85% | Sentence/paragraph boundary detection |
| **Chunk Storage** | `domains/vectors/repository.py` | 95% | Vector and text chunk storage |

**Modifications Needed**:
- Add chunk-level blockchain verification
- Add chunk hashing for integrity verification

---

### 6. Embedding / Search

**Status**: ✅ **REUSABLE (with enhancements)**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **Embedding Service** | `domains/vectors/embeddings.py` | 90% | OpenAI embeddings, rate limiting |
| **Vector Repository** | `domains/vectors/repository.py` | 95% | pgvector operations |
| **Embedding Throttle** | `domains/vectors/embedding_throttle.py` | 85% | Rate limiting for OpenAI API |
| **Scaling** | `domains/vectors/scaling.py` | 80% | Batch processing for large docs |
| **Search Service** | `domains/search/service.py` | 90% | Semantic and keyword search |

**Modifications Needed**:
- Add blockchain wallet integration for embedding verification
- Add search result provenance tracking

---

### 7. LLM Abstraction

**Status**: ✅ **HIGHLY REUSABLE**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **LLM Provider** | `domains/ai/llm.py` | 100% | OpenAI provider, structured output |
| **LLM Registry** | `domains/ai/llm.py` | 100% | Pluggable provider system |
| **Structured Output Parser** | `domains/ai/llm.py` | 100% | JSON schema validation |
| **Rate Limiting** | `domains/ai/llm.py` | 90% | OpenAI API rate limiting |
| **LLM Cache** | `domains/ai/llm.py` | 85% | Response caching |

**Modifications Needed**:
- Add blockchain wallet integration for LLM API calls
- Add transaction proof generation for LLM responses

---

### 8. Policy Engine

**Status**: ✅ **REUSABLE**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **Policy Engine** | `domains/playbook/engine.py` | 95% | Rule evaluation, deviation detection |
| **Rule Evaluator** | `domains/playbook/engine.py` | 95% | Rule matching and scoring |
| **Deviation Detector** | `domains/playbook/engine.py` | 95% | Clause deviation detection |
| **Clause Recommender** | `domains/playbook/engine.py` | 90% | Recommended clause variations |
| **Risk Scorer** | `domains/playbook/engine.py` | 95% | Risk scoring algorithm |
| **Policy Repository** | `domains/playbook/repository.py` | 95% | Policy CRUD operations |

**Modifications Needed**:
- Add blockchain transaction hash to policy evaluation
- Add policy versioning with blockchain proofs
- Add multi-signature approval workflow

---

### 9. Risk Engine

**Status**: ✅ **REUSABLE**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **Risk Scoring** | `domains/review/risk_scoring.py` | 95% | Contract risk calculation |
| **Risk Delta Engine** | `domains/review/risk_delta_engine.py` | 90% | Risk change tracking |
| **Redline Coverage** | `domains/review/redline_coverage.py` | 90% | Redline change tracking |
| **Mitigation Effectiveness** | `domains/review/mitigation_effectiveness.py` | 85% | Mitigation tracking |

**Modifications Needed**:
- Add blockchain verification to risk scores
- Add risk score tamper detection

---

### 10. Findings / Recommendations

**Status**: ✅ **REUSABLE**

| Component | Location | Reusability | Notes |
|-----------|----------|-------------|-------|
| **Finding Models** | `domains/review/models.py` | 95% | Finding data structures |
| **Redline Operations** | `domains/review/redline_ops.py` | 95% | Redline change tracking |
| **Policy Linkage** | `domains/review/policy_linkage.py` | 90% | Finding to policy mapping |

**Modifications Needed**:
- Add blockchain transaction hashes to findings
- Add recommendation provenance

---

### 11. Tenant Isolation

**Status**: ✅ **ALREADY IMPLEMENTED**

| Component | Location | Implementation |
|-----------|----------|----------------|
| **Tenant Model** | `kernel/database/models.py` | Tenant base entity |
| **Tenant Context Middleware** | `kernel/middleware/tenant_context.py` | Tenant isolation on all requests |
| **Tenant-aware Sessions** | `kernel/database/session.py` | Session factory with tenant_id |
| **Multi-tenant Repository** | `kernel/repository/base.py` | Tenant-scoped queries |

**Verification**:
- All domain models have `tenant_id` FK
- Middleware injects tenant context on every request
- Repository base enforces tenant isolation

**Modifications Needed**:
- Add blockchain wallet per-tenant integration
- Add tenant-level blockchain network configuration

---

### 12. RBAC

**Status**: ✅ **ALREADY IMPLEMENTED**

| Component | Location | Implementation |
|-----------|----------|----------------|
| **RBAC System** | `kernel/security/rbac.py` | Role-based permission checks |
| **Permission Decorator** | `kernel/security/rbac.py` | `require_permission()` decorator |
| **User Context** | `kernel/security/auth.py` | User context with permissions |
| **Permissions Enum** | `kernel/security/permissions.py` | Permission definitions |

**Permission Hierarchy**:
```
super_admin (ALL permissions)
├── admin:system
├── admin:tenant
├── users:write
├── contracts:approve
├── contracts:write
├── contracts:delete
├── workflows:write
├── workflows:approve
├── workflows:escalate
└── audit:export
```

**Modifications Needed**:
- Add blockchain wallet management permissions
- Add document verification permissions

---

### 13. Audit Logging

**Status**: ✅ **ALREADY IMPLEMENTED (needs extension)**

| Component | Location | Implementation |
|-----------|----------|----------------|
| **Audit Middleware** | `kernel/middleware/audit_response.py` | Request/response logging |
| **Security Events** | `kernel/security/events.py` | Security event logging |
| **Audit Logs Storage** | `audit_logs/` | Persistent audit log storage |

**Current Capabilities**:
- Request/response logging with request_id
- Security event tracking (login, permission denied)
- Audit log persistence in audit_logs/ directory

**Modifications Needed**:
- Add blockchain transaction logging
- Add document hash verification logging
- Add tamper detection alerts

---

### 14. Existing Tests

**Status**: ✅ **REUSABLE (needs expansion)**

| Test Type | Location | Coverage |
|-----------|----------|----------|
| **Unit Tests** | `backend/tests/` | Core functionality |
| **Load Tests** | `tests/load/` | Performance testing |
| **Integration Tests** | `backend/tests/` | API integration |
| **End-to-End Tests** | `tests/` | User workflows |

**Test Framework**:
- pytest >=8.0.0
- pytest-asyncio >=0.23.0
- pytest-cov >=5.0.0
- Locust for load testing

**Modifications Needed**:
- Add blockchain integration tests
- Add document tamper detection tests
- Add audit trail verification tests

---

### 15. Existing Database Models

**Status**: ✅ **REUSABLE (needs extension)**

| Model | Location | Purpose |
|-------|----------|---------|
| **Tenant** | `kernel/database/models.py` | Multi-tenant root entity |
| **UploadSession** | `domains/ingestion/models.py` | Document upload tracking |
| **Contract** | `domains/contracts/models.py` | Contract metadata |
| **Review** | `domains/review/models.py` | Contract review data |
| **Finding** | `domains/review/models.py` | Risk findings |
| **Redline** | `domains/review/models.py` | Document redlines |
| **Policy** | `domains/playbook/models.py` | Policy rules |
| **Playbook** | `domains/playbook/models.py` | Policy collection |

**Modifications Needed**:
- Add blockchain transaction model
- Add document hash model
- Add verification status model

---

### 16. Existing API Routes

**Status**: ✅ **REUSABLE (needs extension)**

| Domain | Router | Endpoints |
|--------|--------|-----------|
| **Ingestion** | `domains/ingestion/router.py` | Upload, status, cancel |
| **Contracts** | `domains/contracts/router.py` | List, get, KPIs |
| **Review** | `domains/review/router.py` | Create review, get findings |
| **Policy** | `domains/policy/router.py` | Simulate, dry-run |
| **AI** | `domains/ai/router.py` | Analysis, guardrails |
| **Vectors** | `domains/vectors/router.py` | Search, embeddings |

**Modifications Needed**:
- Add blockchain wallet endpoints
- Add document verification endpoints
- Add audit trail endpoints

---

## REUSE / MODIFY / NEW Matrix

### High-Level Summary

| Category | Reuse | Modify | New | Total |
|----------|-------|--------|-----|-------|
| **Core Infrastructure** | 8 | 2 | 0 | 10 |
| **Backend Domains** | 12 | 8 | 4 | 24 |
| **Frontend** | 4 | 3 | 2 | 9 |
| **ML Models** | 3 | 1 | 2 | 6 |
| **Database Models** | 8 | 4 | 4 | 16 |
| **API Routes** | 8 | 5 | 3 | 16 |
| **Tests** | 4 | 2 | 4 | 10 |
| **Security** | 4 | 2 | 2 | 8 |
| **Total** | **51** | **27** | **23** | **101** |

### Detailed Matrix

#### 1. Core Infrastructure (kernel/)

| Component | Type | Changes Required |
|-----------|------|------------------|
| Database Layer | REUSE | Add blockchain wallet model |
| Security & Auth | REUSE | Add blockchain wallet integration |
| Middleware Stack | MODIFY | Add blockchain transaction logging |
| Event Bus | REUSE | Add blockchain events |
| Telemetry | REUSE | Add blockchain tracing |
| Repository Pattern | REUSE | Add blockchain repository |
| Web Utilities | REUSE | Add verification utilities |

**Modifications**:
- `kernel/database/models.py`: Add `BlockchainWallet` model
- `kernel/middleware/audit_response.py`: Add blockchain transaction logging
- `kernel/security/auth.py`: Add blockchain wallet authentication

---

#### 2. Backend Domains

| Component | Type | Changes Required |
|-----------|------|------------------|
| Ingestion Pipeline | REUSE | Add blockchain transaction hash generation |
| OCR/Extraction | REUSE | Add document hash extraction |
| Chunking | REUSE | Add chunk hashing |
| Embedding/Search | REUSE | Add blockchain wallet integration |
| LLM Abstraction | REUSE | Add blockchain wallet integration |
| Policy Engine | REUSE | Add blockchain transaction to evaluation |
| Risk Engine | REUSE | Add blockchain verification to risk scores |
| Findings/Recommendations | REUSE | Add blockchain hashes to findings |
| Tenant Isolation | REUSE | Already implemented |
| RBAC | REUSE | Already implemented |
| Audit Logging | MODIFY | Add blockchain transaction logging |
| Tests | REUSE | Add blockchain integration tests |

**New Components**:
- `domains/blockchain/repository.py`: Blockchain transaction repository
- `domains/blockchain/models.py`: Blockchain transaction model
- `domains/blockchain/verification.py`: Document verification service

**Modifications**:
- `domains/ingestion/models.py`: Add `blockchain_hash` field to `UploadSession`
- `domains/ingestion/service.py`: Add blockchain hash generation on completion
- `domains/vectors/chunking.py`: Add chunk hashing
- `domains/review/models.py`: Add `verification_status` field
- `domains/audit/repository.py`: Add blockchain transaction logging

---

#### 3. Frontend

| Component | Type | Changes Required |
|-----------|------|------------------|
| Next.js App Router | REUSE | Add blockchain wallet pages |
| Auth Provider | REUSE | Add blockchain wallet connection |
| API Services | REUSE | Add verification endpoints |
| UI Components | MODIFY | Add verification status indicators |

**New Components**:
- `frontend/app/blockchain-wallet/`: Wallet connection page
- `frontend/components/blockchain/`: Blockchain-related components
- `frontend/components/verification/`: Verification status components

**Modifications**:
- `frontend/app/page.tsx`: Add dashboard for blockchain verification
- `frontend/services/api.ts`: Add verification endpoints
- `frontend/components/contracts/`: Add verification status badge

---

#### 4. ML Models

| Component | Type | Changes Required |
|-----------|------|------------------|
| NLP Models | REUSE | spaCy, Transformers already trained |
| Training Pipeline | REUSE | ML training infrastructure |
| Evaluation | REUSE | Evaluation framework |

**New Components**:
- `ml/models/verification_model.py`: Document hash verification model
- `ml/models/tamper_detection.py`: Tamper detection model

**Modifications**:
- `ml/requirements.txt`: Add blockchain hash verification libraries

---

#### 5. Database Models

| Component | Type | Changes Required |
|-----------|------|------------------|
| Tenant | REUSE | Already has multi-tenant support |
| UploadSession | MODIFY | Add blockchain_hash, verification_status |
| Contract | REUSE | Already has contract metadata |
| Review | REUSE | Already has review data |
| Finding | MODIFY | Add blockchain_hash |
| Redline | REUSE | Already has redline tracking |
| Policy | REUSE | Already has policy rules |
| Playbook | REUSE | Already has playbook management |
| BlockchainTransaction | NEW | New model for blockchain transactions |
| DocumentHash | NEW | New model for document hashes |
| VerificationRecord | NEW | New model for verification records |

**Modifications**:
- `kernel/database/models.py`: Add `BlockchainWallet` model
- `domains/ingestion/models.py`: Add `blockchain_hash`, `verification_status`
- `domains/review/models.py`: Add `blockchain_hash` to findings

---

#### 6. API Routes

| Component | Type | Changes Required |
|-----------|------|------------------|
| Ingestion Routes | REUSE | Add blockchain hash endpoints |
| Contracts Routes | REUSE | Add verification status endpoints |
| Review Routes | REUSE | Add verification endpoints |
| Policy Routes | REUSE | Add blockchain transaction endpoints |
| AI Routes | REUSE | Add blockchain wallet endpoints |
| Vectors Routes | REUSE | Add blockchain wallet endpoints |
| Audit Routes | NEW | Add blockchain transaction logging |
| Verification Routes | NEW | Add document verification endpoints |

**New Components**:
- `domains/blockchain/router.py`: Blockchain wallet and transaction endpoints
- `domains/verification/router.py`: Document verification endpoints
- `domains/audit/blockchain_router.py`: Blockchain audit logging endpoints

**Modifications**:
- `domains/ingestion/router.py`: Add `GET /ingestion/{id}/blockchain-hash` endpoint
- `domains/contracts/router.py`: Add `GET /contracts/{id}/verification` endpoint
- `domains/review/router.py`: Add `GET /reviews/{id}/verification` endpoint

---

#### 7. Tests

| Component | Type | Changes Required |
|-----------|------|------------------|
| Unit Tests | REUSE | Add blockchain unit tests |
| Integration Tests | REUSE | Add blockchain integration tests |
| Load Tests | REUSE | Add blockchain load tests |
| E2E Tests | REUSE | Add blockchain E2E tests |

**New Components**:
- `tests/blockchain/`: Blockchain integration tests
- `tests/verification/`: Verification tests
- `tests/integration/blockchain.py`: Blockchain integration tests

**Modifications**:
- `tests/conftest.py`: Add blockchain fixtures
- `tests/test_ingestion.py`: Add blockchain hash verification tests

---

#### 8. Security

| Component | Type | Changes Required |
|-----------|------|------------------|
| Auth | REUSE | Add blockchain wallet authentication |
| RBAC | REUSE | Already implemented |
| Permissions | REUSE | Already implemented |
| Audit Logging | MODIFY | Add blockchain transaction logging |
| Security Events | REUSE | Add blockchain events |

**Modifications**:
- `kernel/security/permissions.py`: Add blockchain wallet permissions
- `kernel/security/events.py`: Add blockchain event types

---

## Data Flow

### Current Contract Ingestion Flow

```
1. User uploads document
   ↓
2. Upload validation (type, size, content)
   ↓
3. Storage confirmation (presigned URL)
   ↓
4. Celery worker: OCR processing
   ↓
5. Celery worker: Text extraction and normalization
   ↓
6. Celery worker: Chunking
   ↓
7. Celery worker: Embedding generation
   ↓
8. Celery worker: AI analysis (risk scoring, findings)
   ↓
9. Document stored in MinIO/S3
   ↓
10. Review created in database
```

### Proposed LexProof Flow (with Blockchain)

```
1. User uploads document
   ↓
2. Upload validation (type, size, content)
   ↓
3. Storage confirmation (presigned URL)
   ↓
4. Celery worker: OCR processing
   ↓
5. Celery worker: Text extraction and normalization
   ↓
6. Celery worker: Chunking
   ↓
7. Celery worker: Generate document hash (SHA-256)
   ↓
8. Celery worker: Generate chunk hashes
   ↓
9. Celery worker: Embedding generation
   ↓
10. Celery worker: AI analysis (risk scoring, findings)
   ↓
11. Celery worker: Create blockchain transaction
    - Upload document hash to blockchain
    - Store transaction hash in database
    - Generate verification certificate
   ↓
12. Document stored in MinIO/S3
   ↓
13. Review created in database with blockchain hash
   ↓
14. Verification status updated
```

### Verification Flow

```
1. User requests document verification
   ↓
2. System retrieves document from storage
   ↓
3. System retrieves document hash from database
   ↓
4. System retrieves blockchain transaction hash
   ↓
5. System verifies blockchain transaction
   - Check transaction status
   - Verify document hash matches
   - Check transaction timestamp
   ↓
6. System generates verification report
   - Document integrity verified
   - Transaction confirmed
   - Timestamp validated
   - Tamper detection status
   ↓
7. User receives verification certificate
```

---

## Security Boundaries

### Current Security Model

```
┌─────────────────────────────────────────────────────────────┐
│                     Tenant Isolation                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Tenant A   │  │   Tenant B   │  │   Tenant C   │     │
│  │              │  │              │  │              │     │
│  │ Data         │  │ Data         │  │ Data         │     │
│  │ - Uploads    │  │ - Uploads    │  │ - Uploads    │     │
│  │ - Reviews    │  │ - Reviews    │  │ - Reviews    │     │
│  │ - Policies   │  │ - Policies   │  │ - Policies   │     │
│  │ - Blockchain │  │ - Blockchain │  │ - Blockchain │     │
│  │   Wallets    │  │   Wallets    │  │   Wallets    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            ↑
                     Tenant Context Middleware
                            ↑
                 ┌─────────────────────────────┐
                 │      Authentication Layer    │
                 │  (Auth0 JWT Validation)     │
                 └─────────────────────────────┘
                            ↑
                 ┌─────────────────────────────┐
                 │         API Gateway         │
                 └─────────────────────────────┘
```

### Proposed Security Model (with Blockchain)

```
┌─────────────────────────────────────────────────────────────┐
│                     Tenant Isolation                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Tenant A   │  │   Tenant B   │  │   Tenant C   │     │
│  │              │  │              │  │              │     │
│  │ Data         │  │ Data         │  │ Data         │     │
│  │ - Uploads    │  │ - Uploads    │  │ - Uploads    │     │
│  │ - Reviews    │  │ - Reviews    │  │ - Reviews    │     │
│  │ - Policies   │  │ - Policies   │  │ - Policies   │     │
│  │ - Blockchain │  │ - Blockchain │  │ - Blockchain │     │
│  │   Wallets    │  │   Wallets    │  │   Wallets    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Blockchain Verification Layer           │   │
│  │  - Document hash verification                       │   │
│  │  - Transaction verification                         │   │
│  │  - Tamper detection                                 │   │
│  │  - Multi-signature approval                         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↑
                     Tenant Context Middleware
                            ↑
                 ┌─────────────────────────────┐
                 │      Authentication Layer    │
                 │  (Auth0 JWT + Blockchain)   │
                 └─────────────────────────────┘
                            ↑
                 ┌─────────────────────────────┐
                 │         API Gateway         │
                 └─────────────────────────────┘
```

### Security Enhancements

1. **Multi-Tenancy**: Already implemented with tenant_id isolation
2. **RBAC**: Already implemented with permission decorators
3. **Audit Logging**: Already implemented with request/response logging
4. **Rate Limiting**: Already implemented with middleware
5. **Security Headers**: Already implemented with middleware
6. **Transaction Logging**: NEW - Blockchain transaction logging
7. **Document Hashing**: NEW - SHA-256 document hashing
8. **Tamper Detection**: NEW - Document integrity verification
9. **Multi-Signature**: NEW - Critical contract approval workflow

---

## Google Cloud Architecture

### Current Infrastructure

| Service | Technology | Purpose |
|---------|------------|---------|
| **Database** | PostgreSQL 16 | Primary data store |
| **Storage** | MinIO (S3-compatible) | Document storage |
| **Cache** | Redis 7 | Celery broker, session cache |
| **Queue** | Celery + Redis | Background task processing |
| **Monitoring** | Sentry, Prometheus, OpenTelemetry | Observability |
| **Auth** | Auth0 | OAuth2 + JWT |

### Proposed LexProof Infrastructure

| Service | Technology | Purpose |
|---------|------------|---------|
| **Database** | PostgreSQL 16 | Primary data store |
| **Storage** | MinIO (S3-compatible) | Document storage |
| **Cache** | Redis 7 | Celery broker, session cache |
| **Queue** | Celery + Redis | Background task processing |
| **Monitoring** | Sentry, Prometheus, OpenTelemetry | Observability |
| **Auth** | Auth0 + Firebase Auth | OAuth2 + JWT + Blockchain wallet |
| **Blockchain** | Polygon / Ethereum | Transaction verification |
| **Infrastructure** | Terraform + Cloud Build | IaC and CI/CD |

### Google Cloud Services (Optional Enhancements)

| Service | Use Case | Priority |
|---------|----------|----------|
| **Cloud Storage** | Document backup | Low |
| **Cloud Functions** | Blockchain event triggers | Medium |
| **Cloud Pub/Sub** | Blockchain event streaming | Medium |
| **Cloud BigQuery** | Audit log analytics | Low |
| **Cloud Memorystore** | Redis caching | Low |
| **Cloud KMS** | Document encryption | Medium |

---

## Firebase Architecture

### Proposed Firebase Integration

| Feature | Firebase Service | Use Case |
|---------|------------------|----------|
| **User Authentication** | Firebase Auth | Alternative to Auth0 |
| **Blockchain Wallet** | Firestore + Firestore Security Rules | Store wallet credentials securely |
| **Real-time Updates** | Firestore Realtime Database | Document status updates |
| **Push Notifications** | Firebase Cloud Messaging | Verification alerts |
| **Analytics** | Firebase Analytics | User behavior tracking |
| **Hosting** | Firebase Hosting | Frontend deployment |

### Blockchain Integration

#### Ethereum / Polygon

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Blockchain Node** | Infura / Alchemy | RPC endpoint |
| **Wallet** | MetaMask / WalletConnect | User wallet connection |
| **Smart Contracts** | Solidity | Verification contract |
| **Provider** | Ethers.js / Web3.js | Blockchain interaction |

#### Smart Contract Design

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract DocumentVerification {
    struct DocumentHash {
        bytes32 documentHash;
        uint256 timestamp;
        address tenantId;
        bool isVerified;
    }

    mapping(bytes32 => DocumentHash) public documentHashes;

    event DocumentHashed(
        bytes32 indexed documentHash,
        uint256 timestamp,
        address indexed tenantId
    );

    event VerificationConfirmed(
        bytes32 indexed documentHash,
        address indexed verifier
    );

    function hashDocument(string memory content) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(content));
    }

    function storeDocumentHash(
        string memory content,
        address tenantId
    ) public {
        bytes32 documentHash = hashDocument(content);
        documentHashes[documentHash] = DocumentHash({
            documentHash: documentHash,
            timestamp: block.timestamp,
            tenantId: tenantId,
            isVerified: true
        });

        emit DocumentHashed(documentHash, block.timestamp, tenantId);
    }

    function verifyDocument(
        bytes32 documentHash,
        address verifier
    ) public {
        require(documentHashes[documentHash].tenantId != address(0), "Document not found");
        require(documentHashes[documentHash].isVerified, "Document not verified");

        documentHashes[documentHash].isVerified = false;
        emit VerificationConfirmed(documentHash, verifier);
    }

    function isDocumentVerified(bytes32 documentHash) public view returns (bool) {
        return documentHashes[documentHash].isVerified;
    }
}
```

---

## Blockchain Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Tenant A   │  │   Tenant B   │  │   Tenant C   │     │
│  │              │  │              │  │              │     │
│  │ - Uploads    │  │ - Uploads    │  │ - Uploads    │     │
│  │ - Verifies   │  │ - Verifies   │  │ - Verifies   │     │
│  │ - Manages    │  │ - Manages    │  │ - Manages    │     │
│  │   Wallets    │  │   Wallets    │  │   Wallets    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                            ↑
                 ┌─────────────────────────────┐
                 │    Blockchain Integration    │
                 │  - Document Hashing          │
                 │  - Transaction Verification  │
                 │  - Multi-signature Approval   │
                 └─────────────────────────────┘
                            ↑
                 ┌─────────────────────────────┐
                 │      Blockchain Network      │
                 │  - Ethereum / Polygon        │
                 │  - Smart Contracts           │
                 │  - Wallet Management         │
                 └─────────────────────────────┘
                            ↑
                 ┌─────────────────────────────┐
                 │      RPC Providers           │
                 │  - Infura                    │
                 │  - Alchemy                   │
                 │  - MetaMask (User Wallet)    │
                 └─────────────────────────────┘
```

### Blockchain Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Blockchain Network** | Ethereum / Polygon | Transaction verification |
| **Smart Contracts** | Solidity | Document hashing and verification |
| **RPC Provider** | Infura / Alchemy | Blockchain RPC endpoint |
| **Wallet Provider** | MetaMask / WalletConnect | User wallet connection |
| **Blockchain SDK** | Ethers.js / Web3.js | Blockchain interaction |
| **Event Listeners** | WebSocket / Polling | Real-time transaction events |

### Transaction Flow

```
1. User uploads document
   ↓
2. System generates document hash (SHA-256)
   ↓
3. System creates blockchain transaction
   - Upload document hash to smart contract
   - Sign transaction with tenant wallet
   ↓
4. Transaction confirmed on blockchain
   ↓
5. System stores transaction hash in database
   ↓
6. System generates verification certificate
   ↓
7. User can verify document anytime
   - Retrieve document hash
   - Verify blockchain transaction
   - Confirm document integrity
```

### Verification Flow

```
1. User requests verification
   ↓
2. System retrieves document hash from database
   ↓
3. System queries blockchain
   - Check transaction status
   - Verify document hash
   - Confirm timestamp
   ↓
4. System generates verification report
   - Document integrity: ✅ Verified
   - Transaction status: ✅ Confirmed
   - Timestamp: ✅ Valid
   - Tamper detection: ✅ No tampering detected
   ↓
5. User receives verification certificate
```

---

## Dependencies

### Current Dependencies

#### Backend (`requirements.txt`)

```txt
# Web API
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
starlette>=0.40.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-multipart>=0.0.9

# Database
sqlalchemy[asyncio]>=2.0.25
asyncpg>=0.29.0
alembic>=1.13.0
pgvector>=0.4.2
greenlet>=3.0.0

# Auth
python-jose[cryptography]>=3.3.0
cryptography>=42.0.0

# HTTP clients
httpx>=0.27.0

# Redis & task queue
redis>=5.0.0
celery>=5.4.0
kombu>=5.3.0
billiard>=4.2.0
vine>=5.1.0

# Object storage
boto3>=1.34.0
botocore>=1.34.0
aioboto3>=13.0.0

# AI / LLM
openai>=1.0.0
tiktoken>=0.7.0
tenacity>=8.2.0
jinja2>=3.1.0

# Document extraction
pymupdf>=1.24.0
python-docx>=1.1.0
lxml>=4.9.0

# Observability
structlog>=24.1.0
prometheus-client>=0.16.0
opentelemetry-api>=1.22.0
opentelemetry-sdk>=1.22.0
opentelemetry-instrumentation-fastapi>=0.41b0
opentelemetry-instrumentation-sqlalchemy>=0.41b0
opentelemetry-exporter-otlp-proto-http>=1.22.0
sentry-sdk>=2.0.0

# Config & utilities
python-dotenv>=1.0.0
PyYAML>=6.0.0
python-dateutil>=2.8.0
```

#### ML (`ml/requirements.txt`)

```txt
# ML dependencies
spacy>=3.7.0
scikit-learn>=1.4.0
numpy>=1.26.0
pandas>=2.2.0
transformers>=4.38.0
torch>=2.2.0
sentence-transformers>=2.3.0
langchain>=0.1.0
langchain-openai>=0.0.5
openai>=1.12.0
tiktoken>=0.6.0

# LoRA / PEFT
peft>=0.10.0
accelerate>=0.27.0
bitsandbytes>=0.43.0
datasets>=2.18.0
tensorboard>=2.16.0
wandb>=0.16.0

# Evaluation
scipy>=1.12.0
```

### Proposed LexProof Dependencies

#### New Dependencies

```txt
# Blockchain
web3>=6.0.0
ethers>=6.0.0
@alchemy/eth-sdk>=1.0.0

# Hashing
cryptography>=42.0.0

# Firebase (optional)
firebase-admin>=6.0.0
```

#### Updated Dependencies

```txt
# Update existing dependencies
web3>=6.0.0
ethers>=6.0.0
cryptography>=42.0.0
```

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)

**Goals**: Set up blockchain integration foundation

- [ ] Add blockchain dependencies to `requirements.txt`
- [ ] Create blockchain wallet model
- [ ] Create blockchain transaction model
- [ ] Create blockchain repository
- [ ] Set up blockchain RPC provider
- [ ] Implement document hash generation
- [ ] Add blockchain transaction logging

**Deliverables**:
- `kernel/database/models.py`: Add `BlockchainWallet` model
- `domains/blockchain/models.py`: Add `BlockchainTransaction` model
- `domains/blockchain/repository.py`: Blockchain repository
- `domains/blockchain/verification.py`: Document verification service

---

### Phase 2: Integration (Weeks 3-4)

**Goals**: Integrate blockchain into ingestion pipeline

- [ ] Modify ingestion service to generate document hash
- [ ] Modify ingestion service to create blockchain transaction
- [ ] Add chunk hashing
- [ ] Add blockchain hash to database models
- [ ] Update Celery workers for blockchain transactions
- [ ] Add blockchain event listeners

**Deliverables**:
- `domains/ingestion/models.py`: Add `blockchain_hash` field
- `domains/ingestion/service.py`: Add blockchain hash generation
- `domains/vectors/chunking.py`: Add chunk hashing
- `workers/tasks/ingestion.py`: Update for blockchain transactions

---

### Phase 3: Verification (Weeks 5-6)

**Goals**: Implement document verification

- [ ] Create verification service
- [ ] Implement verification endpoint
- [ ] Add verification status to database models
- [ ] Create verification report generation
- [ ] Create verification certificate
- [ ] Add verification UI components

**Deliverables**:
- `domains/verification/service.py`: Verification service
- `domains/verification/router.py`: Verification endpoints
- `frontend/components/verification/`: Verification UI components

---

### Phase 4: Frontend (Weeks 7-8)

**Goals**: Add blockchain wallet and verification UI

- [ ] Create blockchain wallet page
- [ ] Add wallet connection component
- [ ] Add verification status badge
- [ ] Add verification certificate viewer
- [ ] Add audit trail viewer
- [ ] Add document hash display

**Deliverables**:
- `frontend/app/blockchain-wallet/`: Wallet page
- `frontend/components/blockchain/`: Blockchain components
- `frontend/app/contracts/[id]/verification`: Verification page

---

### Phase 5: Testing (Weeks 9-10)

**Goals**: Comprehensive testing

- [ ] Add blockchain unit tests
- [ ] Add blockchain integration tests
- [ ] Add verification tests
- [ ] Add tamper detection tests
- [ ] Add blockchain load tests
- [ ] Add blockchain E2E tests

**Deliverables**:
- `tests/blockchain/`: Blockchain tests
- `tests/verification/`: Verification tests
- `tests/integration/blockchain.py`: Integration tests

---

### Phase 6: Documentation (Weeks 11-12)

**Goals**: Complete documentation

- [ ] Update architecture documentation
- [ ] Create blockchain integration guide
- [ ] Create verification guide
- [ ] Create smart contract documentation
- [ ] Create API documentation
- [ ] Create user documentation

**Deliverables**:
- `docs/blockchain-integration.md`: Blockchain guide
- `docs/verification-guide.md`: Verification guide
- `docs/smart-contracts.md`: Smart contract docs
- `docs/api-documentation.md`: API docs

---

## Conclusion

LexProof can be built upon the mature ContractRiskEdge platform by leveraging 51 existing components and adding 23 new components. The core infrastructure, domain logic, and frontend are highly reusable with minimal modifications needed.

The primary additions are:
1. Blockchain wallet integration
2. Document hash generation and verification
3. Blockchain transaction logging
4. Verification status tracking
5. Tamper detection
6. Multi-signature approval workflow

The architecture supports:
- Multi-tenant isolation (already implemented)
- RBAC (already implemented)
- Audit logging (needs blockchain extension)
- Rate limiting (already implemented)
- Security headers (already implemented)

The proposed implementation roadmap is 12 weeks, with clear phases and deliverables.

---

## Appendix A: Key File Locations

### Core Infrastructure

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI application factory |
| `backend/app/kernel/database/session.py` | Tenant-aware session factory |
| `backend/app/kernel/security/rbac.py` | RBAC system |
| `backend/app/kernel/middleware/tenant_context.py` | Tenant context middleware |
| `backend/app/kernel/events/bus.py` | Event bus |

### Domain Models

| File | Purpose |
|------|---------|
| `backend/app/domains/ingestion/models.py` | Upload session model |
| `backend/app/domains/review/models.py` | Review and finding models |
| `backend/app/domains/playbook/models.py` | Policy and playbook models |
| `backend/app/domains/vectors/models.py` | Vector and chunk models |

### Services

| File | Purpose |
|------|---------|
| `backend/app/domains/ingestion/service.py` | Ingestion orchestration |
| `backend/app/domains/ai/service.py` | AI orchestration |
| `backend/app/domains/policy/service.py` | Policy engine |
| `backend/app/domains/vectors/service.py` | Vector operations |
| `backend/app/domains/blockchain/service.py` | Blockchain operations (NEW) |

---

## Appendix B: API Endpoints

### Ingestion Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/ingestion/upload` | Upload document |
| GET | `/ingestion/{id}` | Get upload status |
| POST | `/ingestion/{id}/cancel` | Cancel upload |
| GET | `/ingestion/{id}/blockchain-hash` | Get blockchain hash (NEW) |

### Contracts Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/contracts` | List contracts |
| GET | `/contracts/{id}` | Get contract details |
| GET | `/contracts/{id}/verification` | Get verification status (NEW) |

### Review Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/reviews` | Create review |
| GET | `/reviews/{id}` | Get review details |
| GET | `/reviews/{id}/findings` | Get findings |
| GET | `/reviews/{id}/verification` | Get verification (NEW) |

### Verification Endpoints (NEW)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/verification/verify` | Verify document |
| GET | `/verification/{hash}` | Get verification status |
| GET | `/verification/{hash}/certificate` | Get verification certificate |
| POST | `/verification/{hash}/approve` | Approve verification (multi-signature) |

### Blockchain Endpoints (NEW)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/blockchain/wallets` | List tenant wallets |
| POST | `/blockchain/wallets` | Create wallet |
| GET | `/blockchain/wallets/{id}` | Get wallet details |
| POST | `/blockchain/wallets/{id}/connect` | Connect wallet |
| GET | `/blockchain/transactions` | List blockchain transactions |
| GET | `/blockchain/transactions/{txHash}` | Get transaction details |

---

## Appendix C: Database Schema

### Current Models

#### Tenant

```sql
CREATE TABLE tenants (
    tenant_id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT,
    plan TEXT NOT NULL DEFAULT 'starter',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    max_users INTEGER NOT NULL DEFAULT 10,
    max_documents INTEGER NOT NULL DEFAULT 1000,
    features TEXT[] NOT NULL DEFAULT [],
    settings JSONB NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT now(),
    updated_at TEXT NOT NULL DEFAULT now()
);
```

#### UploadSession

```sql
CREATE TABLE upload_sessions (
    upload_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    ingestion_state TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    storage_bucket TEXT NOT NULL,
    client_checksum_sha256 TEXT,
    blockchain_hash TEXT,
    verification_status TEXT,
    created_at TEXT NOT NULL DEFAULT now(),
    updated_at TEXT NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, client_checksum_sha256)
);
```

### Proposed Models

#### BlockchainWallet

```sql
CREATE TABLE blockchain_wallets (
    wallet_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    wallet_address TEXT NOT NULL,
    wallet_type TEXT NOT NULL, -- 'metamask', 'walletconnect'
    public_key TEXT NOT NULL,
    private_key_encrypted TEXT NOT NULL, -- Encrypted with tenant encryption key
    network TEXT NOT NULL, -- 'ethereum', 'polygon'
    chain_id INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TEXT NOT NULL DEFAULT now(),
    updated_at TEXT NOT NULL DEFAULT now()
);
```

#### BlockchainTransaction

```sql
CREATE TABLE blockchain_transactions (
    transaction_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
    upload_id UUID NOT NULL REFERENCES upload_sessions(upload_id),
    tx_hash TEXT NOT NULL,
    contract_address TEXT NOT NULL,
    block_number BIGINT NOT NULL,
    gas_used BIGINT NOT NULL,
    gas_price BIGINT NOT NULL,
    transaction_value TEXT NOT NULL,
    status TEXT NOT NULL, -- 'pending', 'confirmed', 'failed'
    transaction_type TEXT NOT NULL, -- 'hash_document', 'verify_document'
    created_at TEXT NOT NULL DEFAULT now(),
    confirmed_at TEXT,
    UNIQUE(tenant_id, tx_hash)
);
```

#### DocumentHash

```sql
CREATE TABLE document_hashes (
    hash_id UUID PRIMARY KEY,
    upload_id UUID NOT NULL REFERENCES upload_sessions(upload_id),
    hash TEXT NOT NULL,
    hash_type TEXT NOT NULL DEFAULT 'sha256',
    document_size BIGINT NOT NULL,
    chunk_hashes JSONB NOT NULL,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verified_by TEXT,
    verified_at TEXT,
    created_at TEXT NOT NULL DEFAULT now(),
    updated_at TEXT NOT NULL DEFAULT now(),
    UNIQUE(upload_id, hash)
);
```

#### VerificationRecord

```sql
CREATE TABLE verification_records (
    record_id UUID PRIMARY KEY,
    upload_id UUID NOT NULL REFERENCES upload_sessions(upload_id),
    verification_type TEXT NOT NULL, -- 'initial', 're-verification', 'tamper-check'
    verification_status TEXT NOT NULL, -- 'verified', 'failed', 'tampered'
    verifier TEXT NOT NULL,
    verification_method TEXT NOT NULL, -- 'blockchain', 'manual'
    verification_report JSONB NOT NULL,
    created_at TEXT NOT NULL DEFAULT now(),
    UNIQUE(upload_id, verification_type)
);
```

---

**Document Version**: 1.0  
**Last Updated**: 2026-08-23  
**Author**: Lead Architect  
**Status**: Architecture Design Phase
