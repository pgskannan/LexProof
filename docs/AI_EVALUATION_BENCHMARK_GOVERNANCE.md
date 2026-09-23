# AI Evaluation Benchmark Governance

## Benchmark Tracks

LexProof keeps two benchmark tracks separate:

- `INTERNAL_REVIEW`: internal human review used to validate the evaluation pipeline and provide an initial internal performance signal.
- `INDEPENDENT_REVIEW`: future review by an independently identified legal reviewer. This dataset is not created or finalized in Phase D1.

The tracks must never be merged into one dataset or one blended metric.

## Ground-Truth Independence

Ground truth must be created from the contract/version text and the review protocol. It must not be copied from:

- `risk_findings`
- `evaluation_run_findings`
- `evaluation_matches`
- `evaluation_metrics`

AI findings may be evaluated only after ground truth is finalized.

## AI-Blind Review

Initial review metadata records whether the review was AI-blind. `ai_blind=true` is required for the internal benchmark shell, but it is not a substitute for actual human review. The current minimal workflow provides the service entry point and metadata boundary; a dedicated review UI is intentionally deferred.

## Reviewer Identity and Credentials

The system records `reviewer_id`, `reviewer_type`, and `review_type`. It does not invent or assert legal credentials. `INTERNAL_REVIEWER` does not mean legal expert or independent counsel.

Future independent review must supply a real reviewer identity and separately verified credentials before being described as independently reviewed or expert validated.

## Finalization and Immutability

Ground truth follows `DRAFT -> IN_REVIEW -> APPROVED -> FINALIZED`. Finalized records cannot be mutated or deleted. Corrections create a new record using `supersedes_id`.

Dataset and ground-truth lifecycle actions are auditable through the existing audit-log mechanism when an audit recorder is supplied.

## Evaluator Version

Evaluation outputs retain the deterministic evaluator version, currently `1.0.0`. Historical evaluator versions must remain separate.

## Accuracy Reporting Rules

Before evaluation:

```text
AI accuracy: NOT YET MEASURED
```

After internal evaluation:

```text
Internal benchmark accuracy: [real calculated metric]
Independent benchmark accuracy: NOT YET MEASURED
```

After independent evaluation:

```text
Independent benchmark accuracy: [real calculated metric]
```

Never report an internal benchmark as independently reviewed or expert validated.
