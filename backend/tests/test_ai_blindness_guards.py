"""AI-blindness source guards for the benchmark/evaluation boundary.

The finalized human benchmark is the answer key for evaluation and must be
invisible to the AI that is being measured. These guards assert that boundary at
the source level so a future change cannot quietly wire the production analysis
path (or the evaluator) to the answer key:

* the AI analysis path may not reference any evaluation collection or GT field,
* the evaluator is the only consumer of ground truth and it must require
  FINALIZED records,
* neither side may write the other side's collections.

Read-only: the guards only read source files.
"""

from pathlib import Path

SERVICES = Path(__file__).resolve().parents[1] / "app" / "lexproof" / "services"

EVALUATION_COLLECTIONS = (
    "evaluation_ground_truth_findings",
    "evaluation_dataset_members",
    "evaluation_matches",
    "evaluation_metrics",
    "evaluation_run_findings",
    "evaluation_runs",
)

GROUND_TRUTH_FIELDS = (
    "ground_truth_id",
    "expected_finding",
    "expected_evidence",
    "expected_recommendation",
    "expected_severity",
    "review_status",
)

PRODUCTION_COLLECTIONS = (
    "risk_findings",
    "legal_passports",
    "evidence_records",
    "evidence_anchors",
)

PRODUCTION_WRITE_COLLECTIONS = (
    *PRODUCTION_COLLECTIONS,
    "notifications",
    "audit_events",
    "contract_versions",
)

AI_PROVIDER_MARKERS = ("vertexai", "VertexGeminiProvider", "generate_content", "generative_models")


def source(name: str) -> str:
    return (SERVICES / name).read_text(encoding="utf-8")


def code_only(name: str) -> str:
    """Module source with the leading docstring and ``#`` comments removed.

    Docstrings are allowed to *describe* what a module must not do; executable
    code is not. Guarding against the former would be noise.
    """
    lines = source(name).splitlines()
    body: list[str] = []
    in_docstring = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('"""') and (stripped.endswith('"""') and len(stripped) > 3):
            continue
        if stripped.startswith('"""'):
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        body.append(line)
    return "\n".join(body)


def test_ai_analysis_path_cannot_see_the_answer_key():
    for name in ("version_analysis.py", "analysis_prompt.py", "vertex_ai.py"):
        text = source(name)
        for marker in (*EVALUATION_COLLECTIONS, *GROUND_TRUTH_FIELDS):
            assert marker not in text, f"{name} must not reference {marker}"


def test_analysis_prompt_module_is_the_only_prompt_source():
    prompt_text = source("analysis_prompt.py")
    assert 'ANALYSIS_PROMPT_VERSION = "analysis-1.0"' in prompt_text
    assert "def build_analysis_prompt(" in prompt_text
    assert "def parse_structured_analysis(" in prompt_text
    assert '"\\n\\nContract:\\n"' in prompt_text

    # Production analysis must delegate to the shared builder instead of keeping
    # a second, drift-prone copy of the prompt.
    version_text = source("version_analysis.py")
    assert "from .analysis_prompt import" in version_text
    assert "build_analysis_prompt(document_text, playbook_text)" in version_text
    assert '"\\n\\nContract:\\n"' not in version_text
    assert "evaluation" not in version_text.lower()


def test_analysis_prompt_module_has_no_provider_or_evaluation_dependencies():
    prompt_text = source("analysis_prompt.py")
    for marker in (*AI_PROVIDER_MARKERS, *EVALUATION_COLLECTIONS, *GROUND_TRUTH_FIELDS):
        assert marker not in prompt_text, f"analysis_prompt.py must not reference {marker}"
    code = code_only("analysis_prompt.py")
    for forbidden in ("from .evaluation", "from .vertex_ai", "evaluation_engine", "repository"):
        assert forbidden not in code, f"analysis_prompt.py must stay dependency-free ({forbidden})"


def test_only_the_evaluator_reads_ground_truth_and_it_requires_finalized():
    text = source("evaluation_engine.py")
    assert "require_finalized" in text
    assert "Evaluation requires finalized ground-truth findings" in text
    # The evaluator is pure: no AI provider, no network client of its own.
    for marker in AI_PROVIDER_MARKERS:
        assert marker not in text, f"evaluation_engine.py must not contain {marker}"


def test_evaluator_cannot_write_production_collections():
    text = source("evaluation_engine.py")
    for collection in PRODUCTION_COLLECTIONS:
        assert collection not in text, f"evaluation_engine.py must not write {collection}"


def test_evaluation_service_never_analyses_contracts():
    text = source("evaluation.py")
    for marker in AI_PROVIDER_MARKERS:
        assert marker not in text, f"evaluation.py must not contain {marker}"
    assert "VersionAnalysisService" not in text


# ------------------------------------------------------------- benchmark runner
def test_runner_ai_phase_never_reads_ground_truth():
    """Ground truth may only be touched in the evaluation step, after the AI ran."""
    text = source("benchmark_runner.py")
    ai_phase = text.split("async def evaluate_run(")[0]
    assert "ground_truth" not in ai_phase
    assert "GroundTruth" not in ai_phase
    assert "self.evaluator.evaluate(" not in ai_phase


def test_runner_only_touches_the_evaluator_after_collecting_ai_findings():
    text = source("benchmark_runner.py")
    assert "self.evaluation.list_ground_truth_findings(" in text
    assert "self.evaluator.evaluate(" in text
    assert "self.evaluator.persist(" in text
    # The runner scores nothing itself and stores no answer-key fields.
    for field in GROUND_TRUTH_FIELDS:
        assert field not in code_only("benchmark_runner.py"), f"runner must not handle {field}"


def test_runner_writes_no_production_artifacts():
    code = code_only("benchmark_runner.py")
    assert ".set(" not in code
    assert ".delete(" not in code
    assert ".update(" not in code
    for collection in PRODUCTION_WRITE_COLLECTIONS:
        assert collection not in code, f"benchmark_runner.py must not write {collection}"
    assert "analysis_status" not in code
    assert "analysis_snapshot" not in code


def test_runner_does_not_reuse_the_production_analysis_or_anchor_services():
    code = code_only("benchmark_runner.py")
    for forbidden in ("version_analysis", "VersionAnalysisService", "PassportService", "ethereum_anchor", "EvidenceAnchor"):
        assert forbidden not in code, f"benchmark_runner.py must not use {forbidden}"


def test_runner_reuses_the_production_prompt_and_the_deterministic_evaluator():
    code = code_only("benchmark_runner.py")
    assert "build_analysis_prompt(document_text, playbook_text)" in code
    assert "ANALYSIS_PROMPT_VERSION" in code
    assert "from .evaluation_engine import DeterministicEvaluationEngine" in code
    # One prompt builder and one evaluator version for AI and benchmark alike.
    assert "ANALYSIS_PROMPT_VERSION =" not in code
    assert "EVALUATOR_VERSION" not in code

