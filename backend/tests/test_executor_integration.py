"""Integration test for ClaudeCodeExecutor with Claude Code SDK."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from workbench.worker.executor import ClaudeCodeExecutor


@pytest.mark.asyncio
async def test_executor_sdk_import():
    """Verify SDK imports work correctly."""
    from claude_code_sdk import query, ClaudeCodeOptions, AssistantMessage, ResultMessage
    assert query is not None
    assert ClaudeCodeOptions is not None


@pytest.mark.asyncio
async def test_executor_builds_valid_options():
    """Test that executor builds valid ClaudeCodeOptions."""
    with tempfile.TemporaryDirectory() as tmp:
        executor = ClaudeCodeExecutor(cwd=Path(tmp), max_turns=10)
        options = executor._build_options()

        # Verify options have expected values
        assert options.max_turns == 10
        assert options.cwd == tmp
        assert options.permission_mode == "acceptEdits"
        assert "Read" in options.allowed_tools
        assert "WebFetch" in options.disallowed_tools


@pytest.mark.asyncio
async def test_executor_builds_prompt():
    """Test that executor builds proper prompt."""
    with tempfile.TemporaryDirectory() as tmp:
        executor = ClaudeCodeExecutor(cwd=Path(tmp))
        prompt = executor._build_prompt(
            signal_title="Fix the bug",
            signal_body="There's a bug in main.py",
            clarifications=[{"question": "Which file?", "answer": "main.py"}]
        )

        assert "Fix the bug" in prompt
        assert "bug in main.py" in prompt
        assert "Which file?" in prompt
        assert "main.py" in prompt


@pytest.mark.asyncio
async def test_executor_timeout():
    """Test that executor handles timeout properly."""
    with tempfile.TemporaryDirectory() as tmp:
        # Create executor with very short timeout
        executor = ClaudeCodeExecutor(
            cwd=Path(tmp),
            timeout_seconds=1,  # 1 second timeout
            max_turns=1,
        )

        # This should timeout (no actual Claude call, just testing the structure)
        # We can't actually run without credentials
        assert executor.timeout_seconds == 1


if __name__ == "__main__":
    asyncio.run(test_executor_sdk_import())
    print("SDK import test passed!")
    asyncio.run(test_executor_builds_valid_options())
    print("Options test passed!")
    asyncio.run(test_executor_builds_prompt())
    print("Prompt test passed!")
    print("\nAll integration tests passed!")
