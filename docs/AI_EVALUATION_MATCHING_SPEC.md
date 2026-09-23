# AI Evaluation Matching Specification

## Scope

The Phase C evaluator is a pure, deterministic comparison engine. It accepts finalized ground-truth findings and isolated evaluation-run findings. It does not call an AI provider and does not modify production analysis collections.

The evaluator does not establish real-world AI accuracy until validated expert-reviewed ground truth is supplied.

## Evaluator Version

The current evaluator version is `1.0.0`. Every generated match and metric record stores this version. Changes to matching rules must use a new evaluator version and must not overwrite historical results.

## Matching Inputs

Ground truth uses:

- `contract_id`
- `version_id`
- `finding_category`
- `clause_reference`
- `expected_severity`
- `expected_finding`
- `expected_evidence`
- `expected_recommendation`

Evaluation findings use:

- `contract_id`
- `version_id`
- `finding_category`
- `clause_reference`
- `severity`
- `finding`
- `evidence`
- `recommendation`

Only `FINALIZED` ground truth is eligible for evaluation.

## Deterministic Matching Hierarchy

Candidates are first restricted to the same `contract_id` and `version_id`.

The deterministic score then considers:

1. normalized finding category / clause type equality
2. normalized clause reference / source section equality
3. evidence token overlap and containment
4. finding identity token overlap
5. severity equality as a separate comparison signal

Text is lowercased, punctuation is normalized, whitespace is collapsed, and common stop words are ignored. No embedding model, LLM, or external semantic service is used.

Explicit category conflicts are `UNCERTAIN`. Clause conflicts are `UNCERTAIN` unless corroborated by matching category, evidence, and sufficient finding-token overlap. Evidence is never required for a finding detection match when category and clause identity are strong; it is evaluated separately for grounding.

## Match States

- `MATCHED`: one unique deterministic candidate satisfies the matching rules.
- `MISSED`: a finalized ground-truth finding has no AI candidate.
- `FALSE_POSITIVE`: an AI finding remains after one-to-one assignment.
- `UNCERTAIN`: a candidate is ambiguous or deterministic signals conflict.

The rationale records the actual signal values and overlap score.

## One-to-One Matching

Each ground-truth finding can match at most one evaluation finding. Each evaluation finding can match at most one ground-truth finding. Candidates are sorted by deterministic score and stable finding ID. Ties are marked `UNCERTAIN`; they are not silently treated as correct.

## Adversarial / Conservative Matching Policy

Generic token overlap is insufficient evidence of legal equivalence. Terms such as `agreement`, `party`, `liability`, `termination`, `payment`, `services`, `contract`, and `confidentiality` occur across many unrelated clauses and cannot create a strong match by themselves.

The evaluator is conservative around adversarial cases:

- same category with a different clause reference is `UNCERTAIN` unless corroborating signals are present
- same clause with a conflicting category is `UNCERTAIN`
- legal contrasts such as termination for convenience versus termination for cause are `UNCERTAIN`
- negation conflicts such as no damages versus damages are `UNCERTAIN`, and contradictory evidence is not `VALID`
- numeric differences such as `$1M` versus `$10M` are `UNCERTAIN`
- identical section numbers with different substantive categories are `UNCERTAIN`
- generic evidence overlap does not establish evidence grounding
- recommendation mismatch does not invalidate finding detection, but recommendation correctness is `false`

The evaluator records `UNCERTAIN` instead of awarding credit when deterministic signals conflict or do not establish a unique identity. Ambiguous ties are never resolved arbitrarily.

Assignments are globally sorted by deterministic score, ground-truth ID, and AI finding ID. Output matches are emitted in stable ID order, so shuffling input records does not change logical assignments, states, scores, metrics, or deterministic IDs. Evaluation timestamps use the explicit evaluation timestamp when supplied and a stable pure-engine timestamp otherwise; timestamps never influence scoring or identity.

## Severity

Finding detection and severity correctness are separate.

A finding can be `MATCHED` while `severity_correct=false`. Severity metrics compare `expected_severity` and AI `severity` only for matched detections.

Critical recall uses finalized ground-truth findings whose expected severity is `CRITICAL`. High-risk recall uses expected `CRITICAL` or `HIGH` findings.

## Evidence Grounding

Evidence grounding is recorded independently as:

- `VALID`: expected evidence is contained in or has at least 0.50 normalized token overlap with AI evidence.
- `INVALID`: evidence is present but deterministic overlap is insufficient.
- `UNKNOWN`: expected or AI evidence is unavailable.

This is a deterministic evidence-text check. It does not by itself establish that evidence supports the legal conclusion; validated expert adjudication is required for that stronger claim.

## Recommendation Accuracy

Recommendation accuracy is calculated only where both expected and AI recommendations are present. Otherwise the value is excluded from the denominator and may remain `null` when no comparable recommendations exist.

## Metrics

For matched (`TP`), false-positive (`FP`), and missed (`FN`) records:

- Precision = `TP / (TP + FP)`
- Recall = `TP / (TP + FN)`
- F1 = `2 * precision * recall / (precision + recall)`
- Severity accuracy = correct severities / matched findings
- Critical recall = matched critical findings / finalized critical findings
- High-risk recall = matched high/critical findings / finalized high/critical findings
- Evidence grounding = valid evidence / comparable matched evidence
- Recommendation accuracy = correct recommendations / comparable matched recommendations

Zero denominators return `null` (`NOT YET MEASURED` at presentation time), never 100% and never an invented zero percentage.

## Idempotency

Match and metric IDs are deterministic hashes of the evaluation run, evaluator version, finding IDs, and match state. Persisting the same result twice overwrites the same evaluation documents instead of creating duplicates.

## Tenant and Production Isolation

The engine requires one organization ID for all input records. Cross-organization inputs are rejected. It only persists to evaluation collections:

- `evaluation_matches`
- `evaluation_metrics`

It never modifies `risk_findings`, `contract_versions`, `legal_passports`, `evidence_records`, `redline_proposals`, workflow state, or blockchain data.

## Limitations

The initial evaluator is intentionally deterministic and conservative. It does not perform legal semantic interpretation, use an LLM, or prove that a quote legally supports a conclusion. Uncertain cases require human adjudication. Benchmark claims remain invalid until the dataset contains finalized expert-reviewed ground truth with meaningful denominators.
