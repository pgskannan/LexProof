# LexProof Internal Benchmark Review Protocol

## Purpose

This protocol defines the first internal human-review process for LexProof's evaluation benchmark. It is applied consistently to the three selected contract versions in `LexProof Internal Benchmark v1`.

The internal benchmark validates LexProof's evaluation pipeline and provides an initial internal performance signal. It is not an independently legal-expert-validated benchmark.

## Review Objective

Identify materially relevant legal, commercial, compliance, or operational risks in the contract version from the contract text alone. The reviewer must establish expected findings independently before any AI evaluation output is viewed.

## AI-Blind Review

During initial ground-truth entry, the reviewer must not view:

- production `risk_findings`
- AI analysis results
- `evaluation_run_findings`
- `evaluation_matches`
- `evaluation_metrics`

The dataset metadata records `ai_blind=true`, `review_type=INTERNAL_REVIEW`, `reviewer_type=INTERNAL_REVIEWER`, and `ground_truth_source=INTERNAL_HUMAN_REVIEW`. The current service provides metadata and lifecycle enforcement; it does not yet provide a dedicated review UI.

## Finding Standard

A finding qualifies when the contract contains a specific, supportable provision that creates material legal, commercial, compliance, operational, or negotiation risk for the reviewing party. Generic boilerplate alone is not a finding unless its application creates a material risk.

## Materiality Threshold

Record a finding when the issue could reasonably affect:

- financial exposure
- liability allocation
- termination or renewal rights
- data protection or regulatory obligations
- intellectual property ownership or licensing
- confidentiality or security
- indemnification
- dispute resolution or governing law
- unilateral rights or material operational constraints

Do not record immaterial drafting preferences as findings.

## Severity Definitions

- `CRITICAL`: severe or potentially existential exposure, major regulatory risk, or an unbounded/high-impact obligation.
- `HIGH`: material exposure likely to require negotiation, remediation, or senior approval.
- `MEDIUM`: meaningful but bounded risk or unfavorable term that should be reviewed.
- `LOW`: limited risk, minor asymmetry, or issue worth tracking but unlikely to drive a major decision.

Severity must reflect the contract text and the materiality standard, not any existing AI severity.

## Evidence Requirements

Every finding should cite the exact contract language supporting it. Preserve the smallest useful quote and do not paraphrase as evidence. If exact supporting language is unavailable, record the evidence limitation explicitly rather than inventing a quote.

## Clause and Reference Requirements

Use the contract's section, clause, heading, or page reference when available. If the document has no reliable numbering, use a meaningful heading or record that the reference is unavailable.

## Recommendation Requirements

Recommendations should state a concrete review or negotiation action. Recommendations must be proportionate to the finding and grounded in the cited text. Do not copy an AI recommendation.

## Ambiguous Clauses

If a clause could reasonably be interpreted in multiple ways, record the uncertainty in the finding and explain what additional information or negotiation clarification is needed. Do not convert ambiguity into certainty.

## Missing Information

Do not infer missing schedules, exhibits, policies, side letters, or business facts. Record `UNKNOWN` or describe the missing information when it affects the assessment.

## Boilerplate

Common boilerplate is not automatically a finding. Record it only when the wording is unusually broad, asymmetric, inconsistent with the surrounding agreement, or materially harmful in context.

## Commercially Unfavorable but Legally Acceptable Terms

A term may be commercially unfavorable without being legally defective. Record it when it crosses the materiality threshold, and explain the commercial impact. Do not label a legally acceptable preference as a compliance or legal violation.

## Lifecycle

Ground truth follows:

```text
DRAFT -> IN_REVIEW -> APPROVED -> FINALIZED
```

Finalized records are immutable. Corrections create a new record linked with `supersedes_id`. No evaluation run is created during internal ground-truth entry.
