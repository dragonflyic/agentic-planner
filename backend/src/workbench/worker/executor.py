"""Claude Code SDK executor with budget enforcement."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)


@dataclass
class ExecutionMetrics:
    """Metrics collected during Claude Code execution."""

    tool_call_count: int = 0
    turn_count: int = 0
    commands_run: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class ExecutionResult:
    """Result of a Claude Code execution."""

    success: bool
    output: dict[str, Any]
    metrics: ExecutionMetrics
    final_text: str
    timed_out: bool = False
    budget_exceeded: bool = False
    questions_asked: list[dict[str, Any]] = field(default_factory=list)


class ClaudeCodeExecutor:
    """Execute Claude Code SDK with budget enforcement and output parsing."""

    def __init__(
        self,
        cwd: Path,
        max_turns: int = 50,
        timeout_seconds: int = 1200,
        max_tool_calls: int = 200,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
    ):
        self.cwd = cwd
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self.max_tool_calls = max_tool_calls
        self.allowed_tools = allowed_tools or [
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
            "Bash",
            "AskUserQuestion",
        ]
        self.disallowed_tools = disallowed_tools or ["WebFetch", "WebSearch"]
        self.metrics = ExecutionMetrics()
        self._cancelled = False

    def _build_prompt(
        self,
        signal_title: str,
        signal_body: str | None,
        clarifications: list[dict[str, str]] | None = None,
    ) -> str:
        """Build the prompt for Claude Code."""
        parts = []

        # Main task
        parts.append(f"## Task\n**Title**: {signal_title}\n")
        if signal_body:
            parts.append(f"**Description**:\n{signal_body}\n")

        # Add clarification context if retrying
        if clarifications:
            parts.append("## Previous Clarifications\n")
            for c in clarifications:
                parts.append(f"**Q**: {c.get('question', 'Unknown')}")
                parts.append(f"**A**: {c.get('answer', 'No answer')}\n")

        # Success criteria
        parts.append("""
## Instructions
1. Analyze the task and implement the required changes
2. Run any relevant tests to verify your changes
3. If you encounter blocking issues, use AskUserQuestion to request clarification

## Success Criteria
- Complete the requested task
- Ensure tests pass (if available)
- Keep changes focused and minimal
""")

        return "\n".join(parts)

    def _build_options(self) -> ClaudeCodeOptions:
        """Build Claude Code SDK options."""
        return ClaudeCodeOptions(
            max_turns=self.max_turns,
            cwd=str(self.cwd),
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            permission_mode="acceptEdits",  # Auto-accept file edits
        )

    async def execute(
        self,
        signal_title: str,
        signal_body: str | None = None,
        clarifications: list[dict[str, str]] | None = None,
    ) -> ExecutionResult:
        """
        Execute Claude Code against the signal.

        Returns the execution result with parsed output and metrics.
        """
        prompt = self._build_prompt(signal_title, signal_body, clarifications)
        options = self._build_options()

        self._cancelled = False
        final_text_parts: list[str] = []
        questions_asked: list[dict[str, Any]] = []
        result_message: ResultMessage | None = None
        error_message: str | None = None
        timed_out = False
        budget_exceeded = False

        try:
            async with asyncio.timeout(self.timeout_seconds):
                async for message in query(prompt=prompt, options=options):
                    if self._cancelled:
                        break

                    if isinstance(message, AssistantMessage):
                        self.metrics.turn_count += 1

                        for block in message.content:
                            if isinstance(block, TextBlock):
                                final_text_parts.append(block.text)

                            elif isinstance(block, ToolUseBlock):
                                self.metrics.tool_call_count += 1

                                # Track Bash commands
                                if block.name == "Bash":
                                    cmd = block.input.get("command", "") if isinstance(block.input, dict) else ""
                                    if cmd:
                                        self.metrics.commands_run.append(cmd)

                                # Track AskUserQuestion calls
                                if block.name == "AskUserQuestion":
                                    question_data = block.input if isinstance(block.input, dict) else {}
                                    questions_asked.append({
                                        "id": block.id,
                                        "questions": question_data.get("questions", []),
                                    })

                                # Check tool call budget
                                if self.metrics.tool_call_count >= self.max_tool_calls:
                                    budget_exceeded = True
                                    break

                    elif isinstance(message, ResultMessage):
                        result_message = message

                    if budget_exceeded:
                        break

        except TimeoutError:
            timed_out = True
            error_message = f"Execution timed out after {self.timeout_seconds} seconds"

        except Exception as e:
            error_message = str(e)

        # Extract metrics from result
        if result_message:
            self.metrics.total_cost_usd = result_message.total_cost_usd or 0.0
            self.metrics.turn_count = result_message.num_turns or self.metrics.turn_count

            if result_message.usage:
                self.metrics.input_tokens = result_message.usage.get("input_tokens", 0) or 0
                self.metrics.output_tokens = result_message.usage.get("output_tokens", 0) or 0
                self.metrics.cache_read_tokens = result_message.usage.get("cache_read_input_tokens", 0) or 0
                self.metrics.cache_creation_tokens = result_message.usage.get("cache_creation_input_tokens", 0) or 0

        # Build output dict
        output: dict[str, Any] = {
            "final_text": "\n".join(final_text_parts),
            "questions_asked": questions_asked,
        }

        if error_message:
            output["error"] = error_message

        if result_message:
            output["session_id"] = result_message.session_id
            output["is_error"] = result_message.is_error
            if result_message.duration_ms:
                output["duration_ms"] = result_message.duration_ms
            if result_message.duration_api_ms:
                output["duration_api_ms"] = result_message.duration_api_ms

        # Determine success
        success = (
            not timed_out
            and not budget_exceeded
            and error_message is None
            and (result_message is None or not result_message.is_error)
            and len(questions_asked) == 0  # No unanswered questions
        )

        return ExecutionResult(
            success=success,
            output=output,
            metrics=self.metrics,
            final_text="\n".join(final_text_parts),
            timed_out=timed_out,
            budget_exceeded=budget_exceeded,
            questions_asked=questions_asked,
        )

    async def cancel(self) -> None:
        """Cancel the running execution."""
        self._cancelled = True
