"""Tests for ClaudeCodeExecutor."""

from pathlib import Path

from workbench.worker.executor import (
    ClaudeCodeExecutor,
    ExecutionMetrics,
    ExecutionResult,
)


class TestExecutorInit:
    """Tests for executor initialization."""

    def test_default_values(self, tmp_path: Path) -> None:
        """Test default initialization values."""
        executor = ClaudeCodeExecutor(cwd=tmp_path)

        assert executor.cwd == tmp_path
        assert executor.max_turns == 50
        assert executor.timeout_seconds == 1200
        assert executor.max_tool_calls == 200
        assert "Read" in executor.allowed_tools
        assert "WebFetch" in executor.disallowed_tools

    def test_custom_values(self, tmp_path: Path) -> None:
        """Test custom initialization values."""
        executor = ClaudeCodeExecutor(
            cwd=tmp_path,
            max_turns=25,
            timeout_seconds=600,
            max_tool_calls=100,
            allowed_tools=["Read", "Write"],
            disallowed_tools=["Bash"],
        )

        assert executor.max_turns == 25
        assert executor.timeout_seconds == 600
        assert executor.max_tool_calls == 100
        assert executor.allowed_tools == ["Read", "Write"]
        assert executor.disallowed_tools == ["Bash"]


class TestBuildPrompt:
    """Tests for prompt building."""

    def test_basic_prompt(self, tmp_path: Path) -> None:
        """Test basic prompt generation."""
        executor = ClaudeCodeExecutor(cwd=tmp_path)
        prompt = executor._build_prompt("Fix bug", "There's a bug in main.py")

        assert "## Task" in prompt
        assert "Fix bug" in prompt
        assert "There's a bug in main.py" in prompt
        assert "## Instructions" in prompt

    def test_prompt_with_clarifications(self, tmp_path: Path) -> None:
        """Test prompt with clarifications."""
        executor = ClaudeCodeExecutor(cwd=tmp_path)
        clarifications = [
            {"question": "Which file?", "answer": "main.py"},
        ]
        prompt = executor._build_prompt("Fix bug", None, clarifications)

        assert "## Previous Clarifications" in prompt
        assert "Which file?" in prompt
        assert "main.py" in prompt


class TestBuildOptions:
    """Tests for options building."""

    def test_options_structure(self, tmp_path: Path) -> None:
        """Test that options are built correctly."""
        executor = ClaudeCodeExecutor(
            cwd=tmp_path,
            max_turns=30,
            allowed_tools=["Read"],
            disallowed_tools=["WebFetch"],
        )
        options = executor._build_options()

        assert options.max_turns == 30
        assert options.cwd == str(tmp_path)
        assert options.allowed_tools == ["Read"]
        assert options.disallowed_tools == ["WebFetch"]
        assert options.permission_mode == "acceptEdits"


class TestExecutionMetrics:
    """Tests for ExecutionMetrics dataclass."""

    def test_default_values(self) -> None:
        """Test default metrics values."""
        metrics = ExecutionMetrics()

        assert metrics.tool_call_count == 0
        assert metrics.turn_count == 0
        assert metrics.commands_run == []
        assert metrics.total_cost_usd == 0.0
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_default_values(self) -> None:
        """Test default result values."""
        metrics = ExecutionMetrics()
        result = ExecutionResult(
            success=True,
            output={"final_text": "Done"},
            metrics=metrics,
            final_text="Done",
        )

        assert result.success is True
        assert result.timed_out is False
        assert result.budget_exceeded is False
        assert result.questions_asked == []
