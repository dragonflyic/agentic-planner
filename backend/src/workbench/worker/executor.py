"""Claude Code SDK executor with budget enforcement."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Awaitable

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_code_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

# Type for log callback: async function that takes (sequence_num, log_entry_dict, is_final)
LogCallback = Callable[[int, dict[str, Any], bool], Awaitable[None]]

# Type for questions callback: async function that saves questions and returns clarification IDs
# Called when AskUserQuestion is detected - should save to DB and return mapping of tool_id -> clarification_ids
QuestionsCallback = Callable[[list[dict[str, Any]]], Awaitable[dict[str, list[str]]]]

# Type for answer polling: async function that checks if all clarifications are answered
# Returns dict mapping question_id to answer, or None if not all answered yet
AnswerPollCallback = Callable[[], Awaitable[dict[str, str] | None]]


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
    prompt: str = ""  # The prompt sent to Claude
    timed_out: bool = False
    budget_exceeded: bool = False
    questions_asked: list[dict[str, Any]] = field(default_factory=list)
    interrupted_for_questions: bool = False


@dataclass
class SignalContext:
    """Full context for a signal."""

    source: str
    repo: str
    issue_number: int | None
    title: str
    body: str | None
    metadata: dict[str, Any] | None = None
    project_fields: dict[str, Any] | None = None
    clarifications: list[dict[str, str]] | None = None


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
        mock_scenario: str | None = None,
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
        self._mock_scenario = mock_scenario

    def _build_prompt(self, signal: SignalContext) -> str:
        """Build the prompt for Claude Code - focused on spec generation."""
        parts = []

        # Signal source context
        parts.append("# Signal Context\n")
        parts.append(f"**Source**: {signal.source}")
        parts.append(f"**Repository**: {signal.repo}")
        if signal.issue_number:
            parts.append(f"**Issue Number**: #{signal.issue_number}")

        # GitHub-specific context
        if signal.source == "github" and signal.metadata:
            if signal.metadata.get("url"):
                parts.append(f"**URL**: {signal.metadata['url']}")
            if signal.metadata.get("labels"):
                parts.append(f"**Labels**: {', '.join(signal.metadata['labels'])}")
            if signal.metadata.get("assignees"):
                parts.append(f"**Assignees**: {', '.join(signal.metadata['assignees'])}")

            # Include comments context
            context = signal.metadata.get("context", {})
            comments = context.get("comments", [])
            if comments:
                parts.append("\n## Discussion Comments")
                for comment in comments[:5]:  # Limit to 5 most recent
                    author = comment.get("author", "unknown")
                    body = comment.get("body", "")
                    parts.append(f"\n**@{author}**:\n{body}")

        # Project fields if available
        if signal.project_fields:
            parts.append("\n## Project Fields")
            for key, value in signal.project_fields.items():
                if value:
                    parts.append(f"**{key}**: {value}")

        # Main task
        parts.append(f"\n# Task\n**Title**: {signal.title}\n")
        if signal.body:
            parts.append(f"**Description**:\n{signal.body}\n")

        # Add clarification context if retrying
        if signal.clarifications:
            parts.append("\n# Previous Clarifications")
            parts.append("These questions were asked in a previous attempt and answered:\n")
            for c in signal.clarifications:
                parts.append(f"**Q**: {c.get('question', 'Unknown')}")
                parts.append(f"**A**: {c.get('answer', 'No answer')}\n")

        # Instructions - focused on spec generation
        parts.append("""
# Your Mission

You are creating a **comprehensive implementation spec** for this task. Your goal is NOT to fully implement the solution, but to:

1. **Understand the codebase** - Explore the repository structure, find relevant files, understand patterns
2. **Analyze the task** - Break down what needs to be done, identify affected areas
3. **Identify unknowns** - What information is missing? What decisions need human input?
4. **Generate a spec** - Document exactly what changes need to be made and how

## Process

1. First, explore the codebase to understand the relevant parts
2. Read key files that relate to this task
3. Identify any ambiguities, missing information, or decisions that require human input
4. If you have questions, use `AskUserQuestion` to gather ALL your questions at once
   - **IMPORTANT**: Aggregate all your questions into a SINGLE AskUserQuestion call
   - Do not ask questions one at a time - batch them together
   - Include context for why each question matters

## Output

At the end, provide a structured spec that includes:
- **Summary**: One paragraph overview of what needs to be done
- **Files to Modify**: List of files that need changes
- **Implementation Steps**: Detailed steps to implement the solution
- **Risks/Considerations**: Any potential issues or edge cases
- **Open Questions**: Any remaining uncertainties (if you couldn't get answers)

## Guidelines

- You MAY make exploratory changes to understand the codebase better
- You MAY run tests or builds to verify your understanding
- Keep your exploration focused and efficient
- If the task is ambiguous, ASK rather than assume
""")

        return "\n".join(parts)

    def _build_options(
        self,
        can_use_tool: Callable[[str, dict[str, Any], ToolPermissionContext], Awaitable[PermissionResultAllow | PermissionResultDeny]] | None = None,
    ) -> ClaudeCodeOptions:
        """Build Claude Code SDK options."""
        return ClaudeCodeOptions(
            max_turns=self.max_turns,
            cwd=str(self.cwd),
            allowed_tools=self.allowed_tools,
            disallowed_tools=self.disallowed_tools,
            permission_mode="bypassPermissions",
            can_use_tool=can_use_tool,
        )

    async def execute(
        self,
        signal: SignalContext,
        log_callback: LogCallback | None = None,
        on_questions_asked: QuestionsCallback | None = None,
        poll_for_answers: AnswerPollCallback | None = None,
        answer_poll_interval: float = 5.0,
    ) -> ExecutionResult:
        """
        Execute Claude Code against the signal.

        Uses ClaudeSDKClient for bidirectional communication. When AskUserQuestion
        is detected, saves the questions via callback and polls for answers.
        Once answers are available, sends them back to Claude and continues.

        Args:
            signal: Full signal context
            log_callback: Optional async callback for streaming logs.
            on_questions_asked: Callback to save questions when AskUserQuestion is detected.
                Should save to DB and return mapping of tool_id -> list of clarification IDs.
            poll_for_answers: Callback to check if all clarifications are answered.
                Returns dict mapping question_id to answer, or None if not ready.
            answer_poll_interval: How often to poll for answers (seconds).

        Returns the execution result with parsed output and metrics.
        """
        prompt = self._build_prompt(signal)

        self._cancelled = False
        final_text_parts: list[str] = []
        questions_asked: list[dict[str, Any]] = []
        result_message: ResultMessage | None = None
        error_message: str | None = None
        timed_out = False
        budget_exceeded = False
        interrupted_for_questions = False
        sequence_num = 0
        # Lock to serialize database operations (control handler runs concurrently)
        db_lock = asyncio.Lock()

        async def write_log(log_entry: dict[str, Any], is_final: bool = False) -> None:
            """Write a log entry if callback is provided."""
            nonlocal sequence_num
            if log_callback:
                async with db_lock:
                    sequence_num += 1
                    await log_callback(sequence_num, log_entry, is_final)

        # Create can_use_tool callback for handling AskUserQuestion
        async def can_use_tool_handler(
            tool_name: str,
            input_data: dict[str, Any],
            context: ToolPermissionContext,
        ) -> PermissionResultAllow | PermissionResultDeny:
            """Handle tool permission requests, especially AskUserQuestion."""
            nonlocal questions_asked, interrupted_for_questions

            if tool_name == "AskUserQuestion":
                print(f"[DEBUG] can_use_tool: AskUserQuestion detected!")
                print(f"[DEBUG] can_use_tool input_data: {input_data}")

                questions_list = input_data.get("questions", [])
                current_questions = {
                    "id": f"auq_{len(questions_asked)}",  # Generate unique ID
                    "questions": questions_list,
                }
                questions_asked.append(current_questions)

                # If we have callbacks for bidirectional mode, poll for answers
                if on_questions_asked and poll_for_answers:
                    # Build a readable summary of questions for the log
                    question_texts = [q.get("question", "?")[:80] for q in questions_list]
                    questions_summary = "; ".join(question_texts)
                    await write_log({
                        "type": "event",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "event": "waiting_for_human",
                        "message": f"Waiting for human input on {len(questions_list)} question(s): {questions_summary}",
                        "details": {"questions_count": len(questions_list), "questions": questions_list},
                    })

                    # Save questions to DB (with lock to avoid concurrent commits)
                    async with db_lock:
                        await on_questions_asked([current_questions])
                    print(f"[DEBUG] Questions saved, polling for answers...")

                    # Poll for answers
                    answers = None
                    while answers is None:
                        await asyncio.sleep(answer_poll_interval)
                        async with db_lock:
                            answers = await poll_for_answers()
                        if answers is None:
                            print(f"[DEBUG] Answers not ready, polling again in {answer_poll_interval}s...")

                    print(f"[DEBUG] Got answers: {answers}")

                    # Build a readable summary of answers for the log message
                    answer_summary = "; ".join(
                        f"{qid}: {ans[:50]}{'...' if len(ans) > 50 else ''}"
                        for qid, ans in answers.items()
                    )
                    await write_log({
                        "type": "event",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "event": "human_answered",
                        "message": f"Human provided {len(answers)} answer(s): {answer_summary}",
                        "details": {"answers": answers},
                    })

                    # Build the answers in the format expected by AskUserQuestion tool
                    # The answers dict maps question_id to answer (e.g., "auq_0_0" -> "answer text")
                    # We need to map question TEXT to answer for the SDK
                    formatted_answers = {}
                    tool_id = current_questions["id"]  # e.g., "auq_0"
                    for i, q in enumerate(questions_list):
                        q_text = q.get("question", "")
                        question_id = f"{tool_id}_{i}"  # e.g., "auq_0_0"
                        if question_id in answers:
                            formatted_answers[q_text] = answers[question_id]
                            print(f"[DEBUG] Mapped {question_id} -> '{q_text[:50]}...' = '{answers[question_id]}'")
                        else:
                            print(f"[DEBUG] No answer found for question_id {question_id}")

                    print(f"[DEBUG] Formatted answers for SDK: {formatted_answers}")

                    # Return answers in the proper format per docs
                    return PermissionResultAllow(
                        behavior="allow",
                        updated_input={
                            "questions": questions_list,
                            "answers": formatted_answers,
                        },
                    )
                else:
                    # No callbacks - deny and interrupt (old behavior)
                    interrupted_for_questions = True
                    return PermissionResultDeny(
                        behavior="deny",
                        message="AskUserQuestion requires human input but no callback provided",
                        interrupt=True,
                    )

            # For all other tools, allow with original input (bypass mode)
            return PermissionResultAllow(
                behavior="allow",
                updated_input=input_data,
            )

        # Build options with the can_use_tool callback
        options = self._build_options(can_use_tool=can_use_tool_handler if (on_questions_asked and poll_for_answers) else None)

        # Use mock client if scenario is specified (for testing)
        if self._mock_scenario:
            from workbench.worker.mock_client import MockClaudeSDKClient
            client = MockClaudeSDKClient(options=options, scenario=self._mock_scenario)
            print(f"[EXECUTOR] Using MOCK client with scenario: {self._mock_scenario}")
        else:
            client = ClaudeSDKClient(options=options)

        try:
            async with asyncio.timeout(self.timeout_seconds):
                await client.connect()
                await client.query(prompt)

                async for message in client.receive_messages():
                    if self._cancelled:
                        await client.interrupt()
                        break

                    if isinstance(message, SystemMessage):
                        # Log system message but don't process further
                        await write_log({
                            "type": "system",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "content": {"text": str(message.content) if hasattr(message, 'content') else "System initialized"},
                        })

                    elif isinstance(message, AssistantMessage):
                        self.metrics.turn_count += 1

                        # Build log entry for this assistant message
                        text_parts = []
                        tool_calls = []

                        for block in message.content:
                            if isinstance(block, TextBlock):
                                final_text_parts.append(block.text)
                                text_parts.append(block.text)

                            elif isinstance(block, ToolUseBlock):
                                self.metrics.tool_call_count += 1
                                tool_calls.append({
                                    "id": block.id,
                                    "name": block.name,
                                    "input": block.input if isinstance(block.input, dict) else {},
                                })

                                # Track Bash commands
                                if block.name == "Bash":
                                    cmd = block.input.get("command", "") if isinstance(block.input, dict) else ""
                                    if cmd:
                                        self.metrics.commands_run.append(cmd)

                                # Note: AskUserQuestion is now handled via can_use_tool callback
                                # The callback saves questions, polls for answers, and returns them properly

                                # Check tool call budget
                                if self.metrics.tool_call_count >= self.max_tool_calls:
                                    budget_exceeded = True
                                    await client.interrupt()
                                    break

                        # Write assistant message log (if not already written due to interrupt)
                        if not interrupted_for_questions:
                            await write_log({
                                "type": "assistant",
                                "timestamp": datetime.now(UTC).isoformat(),
                                "turn": self.metrics.turn_count,
                                "content": {
                                    "text": "\n".join(text_parts) if text_parts else None,
                                    "tool_calls": tool_calls if tool_calls else None,
                                },
                            })

                    elif isinstance(message, UserMessage):
                        # Tool results come back as UserMessage
                        tool_results = []
                        for block in message.content:
                            if isinstance(block, ToolResultBlock):
                                # Truncate very long tool results for logging
                                content = block.content
                                if isinstance(content, str) and len(content) > 5000:
                                    content = content[:5000] + "\n... (truncated)"
                                tool_results.append({
                                    "tool_use_id": block.tool_use_id,
                                    "content": content,
                                })

                        if tool_results:
                            await write_log({
                                "type": "tool_result",
                                "timestamp": datetime.now(UTC).isoformat(),
                                "content": {
                                    "tool_results": tool_results,
                                },
                            })

                    elif isinstance(message, ResultMessage):
                        result_message = message
                        # Write final result log
                        await write_log({
                            "type": "result",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "content": {
                                "session_id": message.session_id,
                                "is_error": message.is_error,
                                "duration_ms": message.duration_ms,
                                "cost_usd": message.total_cost_usd,
                                "turns": message.num_turns,
                                "usage": message.usage,
                            },
                        }, is_final=True)
                        # ResultMessage means execution is complete
                        break

                    if budget_exceeded or interrupted_for_questions:
                        break

        except TimeoutError:
            timed_out = True
            error_message = f"Execution timed out after {self.timeout_seconds} seconds"

        except Exception as e:
            # Capture full error details including stderr for ProcessError
            error_message = str(e)
            if hasattr(e, 'stderr') and e.stderr:
                error_message = f"{error_message}\nstderr: {e.stderr}"

        finally:
            try:
                await client.disconnect()
            except Exception:
                pass  # Ignore disconnect errors

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
        # - If interrupted for questions, it's not a failure, just needs human input
        # - Questions are handled by the classifier as NEEDS_HUMAN
        success = (
            not timed_out
            and not budget_exceeded
            and error_message is None
            and (result_message is None or not result_message.is_error)
        )

        return ExecutionResult(
            success=success,
            output=output,
            metrics=self.metrics,
            final_text="\n".join(final_text_parts),
            prompt=prompt,
            timed_out=timed_out,
            budget_exceeded=budget_exceeded,
            questions_asked=questions_asked,
            interrupted_for_questions=interrupted_for_questions,
        )

    async def cancel(self) -> None:
        """Cancel the running execution."""
        self._cancelled = True
