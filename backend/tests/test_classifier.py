"""Tests for OutcomeClassifier."""


from workbench.models import AttemptStatus
from workbench.worker.classifier import OutcomeClassifier
from workbench.worker.executor import ExecutionMetrics, ExecutionResult
from workbench.worker.sandbox import DiffStats


def make_result(
    success: bool = True,
    final_text: str = "",
    timed_out: bool = False,
    budget_exceeded: bool = False,
    questions_asked: list | None = None,
    output: dict | None = None,
) -> ExecutionResult:
    """Helper to create ExecutionResult."""
    return ExecutionResult(
        success=success,
        output=output or {"final_text": final_text},
        metrics=ExecutionMetrics(),
        final_text=final_text,
        timed_out=timed_out,
        budget_exceeded=budget_exceeded,
        questions_asked=questions_asked or [],
    )


def make_diff_stats(
    lines_added: int = 0,
    lines_deleted: int = 0,
    files_touched: list | None = None,
) -> DiffStats:
    """Helper to create DiffStats."""
    return DiffStats(
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        files_touched=files_touched or [],
    )


class TestClassifierBasics:
    """Basic classification tests."""

    def test_timeout_returns_failed(self) -> None:
        """Timed out execution should return FAILED."""
        classifier = OutcomeClassifier()
        result = make_result(success=False, timed_out=True)
        diff_stats = make_diff_stats()

        classification = classifier.classify(result, diff_stats)

        assert classification.status == AttemptStatus.FAILED
        assert "TIMEOUT" in classification.risk_flags
        assert classification.error_message == "Execution timed out"

    def test_budget_exceeded_returns_failed(self) -> None:
        """Budget exceeded should return FAILED."""
        classifier = OutcomeClassifier()
        result = make_result(success=False, budget_exceeded=True)
        diff_stats = make_diff_stats()

        classification = classifier.classify(result, diff_stats)

        assert classification.status == AttemptStatus.FAILED
        assert "BUDGET_EXCEEDED" in classification.risk_flags

    def test_execution_error_returns_failed(self) -> None:
        """Execution error should return FAILED."""
        classifier = OutcomeClassifier()
        result = make_result(
            success=False,
            output={"error": "Something went wrong"},
        )
        diff_stats = make_diff_stats()

        classification = classifier.classify(result, diff_stats)

        assert classification.status == AttemptStatus.FAILED
        assert "EXECUTION_ERROR" in classification.risk_flags
        assert "Something went wrong" in classification.error_message

    def test_no_changes_returns_noop(self) -> None:
        """No file changes should return NOOP."""
        classifier = OutcomeClassifier()
        result = make_result(success=True, final_text="No changes needed")
        diff_stats = make_diff_stats()  # No files touched

        classification = classifier.classify(result, diff_stats)

        assert classification.status == AttemptStatus.NOOP

    def test_changes_without_pr_returns_success(self) -> None:
        """Changes without PR URL should return SUCCESS."""
        classifier = OutcomeClassifier()
        result = make_result(success=True, final_text="Fixed the bug")
        diff_stats = make_diff_stats(lines_added=10, files_touched=["a.py", "b.py"])

        classification = classifier.classify(result, diff_stats)

        assert classification.status == AttemptStatus.SUCCESS
        assert classification.what_changed == ["a.py", "b.py"]

    def test_pr_url_extraction(self) -> None:
        """PR URL should be extracted from text."""
        classifier = OutcomeClassifier()
        result = make_result(
            success=True,
            final_text="Created PR: https://github.com/org/repo/pull/123",
        )
        diff_stats = make_diff_stats(lines_added=5, files_touched=["a.py"])

        classification = classifier.classify(result, diff_stats)

        assert classification.status == AttemptStatus.SUCCESS
        assert classification.pr_url == "https://github.com/org/repo/pull/123"


class TestQuestionsDetection:
    """Tests for question detection."""

    def test_questions_asked_returns_needs_human(self) -> None:
        """Questions in execution result should return NEEDS_HUMAN."""
        classifier = OutcomeClassifier()
        result = make_result(
            success=True,
            questions_asked=[
                {
                    "id": "q1",
                    "questions": [
                        {"question": "Which approach?", "header": "approach"}
                    ],
                }
            ],
        )
        diff_stats = make_diff_stats()

        classification = classifier.classify(result, diff_stats)

        assert classification.status == AttemptStatus.NEEDS_HUMAN
        assert len(classification.questions) == 1
        assert classification.questions[0].question == "Which approach?"


class TestRiskFlags:
    """Tests for risk flag detection."""

    def test_large_diff_adds_risk_flag(self) -> None:
        """Large diffs should add risk flag."""
        classifier = OutcomeClassifier(max_diff_lines=100)
        result = make_result(success=True)
        diff_stats = make_diff_stats(lines_added=300, lines_deleted=200, files_touched=["a.py"])

        classification = classifier.classify(result, diff_stats)

        assert any("DIFF_SIZE_EXCEEDED" in f for f in classification.risk_flags)

    def test_many_files_adds_risk_flag(self) -> None:
        """Many files touched should add risk flag."""
        classifier = OutcomeClassifier(max_files_touched=10)
        result = make_result(success=True)
        # Create 50 files touched
        files = [f"file{i}.py" for i in range(50)]
        diff_stats = make_diff_stats(lines_added=50, lines_deleted=50, files_touched=files)

        classification = classifier.classify(result, diff_stats)

        assert any("FILES_EXCEEDED" in f for f in classification.risk_flags)
