# LexProof Internal Benchmark v1

## Status

This is an internal benchmark shell only. It is `DRAFT` and has no ground-truth findings yet.

```text
dataset_version_id: 9106833f-43df-4e0c-a78e-195ce30277af
name: LexProof Internal Benchmark v1
version_label: v1
org_id: lexproof-demo
classification: INTERNAL_REVIEW
review_type: INTERNAL_REVIEW
reviewer_type: INTERNAL_REVIEWER
reviewer_id: VJEexqdPVwYJ73D6vShQ75DSGdZ2
ai_blind: true
ground_truth_source: INTERNAL_HUMAN_REVIEW
status: DRAFT
created_at: 2026-09-14T19:42:43.889341Z
planned_evaluator_version: 1.0.0
```

The reviewer identity is recorded as the signed-in internal organization member. No legal credentials are asserted.

## Selected contract versions

Exactly three existing complete contract versions were selected for diversity of contract type and risk structure. Selection was based on readable source text and coverage diversity, not existing AI finding count.

| Contract | Version | Rationale |
|---|---|---|
| `645a2cd6-f436-4e6f-8b14-ac6240d6606a` (`CONTRACT_02_MSA_MediumRisk.docx`) | `b4193b13-b8bb-4f43-857e-ea4a3023e3c0` | MSA structure with medium-risk commercial allocation and 3,794 characters of readable source text. |
| `50712c6d-cd84-408e-aac0-9c28ed09f2fe` (`CONTRACT_06_DPA_ComplianceIssues.docx`) | `3fb395b9-b431-4196-ad8c-c4955a8d486d` | DPA/compliance-focused clauses with 3,310 characters of readable source text. |
| `897c9b37-b5a0-4853-b1c6-c42d2cdf1a18` (`CONTRACT_08_JointVenture_ExecApproval.docx`) | `0c6318be-76b0-4dfb-8c3b-0d56241a5fa6` | Joint-venture and executive-approval structure with 3,503 characters of readable source text. |

Dataset membership contains only these existing `contract_id`/`version_id` references. Contract documents were not copied or modified.

## Review method

The reviewer must apply [AI_EVALUATION_INTERNAL_REVIEW_PROTOCOL.md](AI_EVALUATION_INTERNAL_REVIEW_PROTOCOL.md) independently from AI findings. The service supports direct human ground-truth entry through `create_ground_truth()` and the existing lifecycle:

```text
DRAFT -> IN_REVIEW -> APPROVED -> FINALIZED
```

No AI findings, evaluation-run findings, matches, or metrics were used to populate the shell.

## Counts

```text
contracts: 3
members: 3
ground-truth findings: 0
finalized findings: 0
evaluation runs: 0
metrics: not measured
```

## Limitations

- Internal human ground truth is still required before finalization.
- This is not an independently reviewed or legal-expert-validated benchmark.
- No AI evaluation has been run.
- No accuracy, precision, recall, or F1 result exists for this dataset.
- Independent benchmark data is not created in this phase.
