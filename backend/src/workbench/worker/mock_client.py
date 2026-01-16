"""Mock Claude SDK Client for testing the executor's message handling logic."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from uuid import uuid4

# Import real SDK types so isinstance checks work
from claude_code_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)


@dataclass
class MockScenario:
    """Defines what messages the mock client should yield."""

    name: str
    # List of messages to yield in order (before AskUserQuestion)
    messages: list[Any] = field(default_factory=list)
    # Messages to yield after receiving answer to AskUserQuestion
    continuation_messages: list[Any] = field(default_factory=list)
    # Delay between messages (seconds)
    message_delay: float = 0.1


def create_ask_user_question_scenario() -> MockScenario:
    """Create a scenario that triggers AskUserQuestion handling with continuation."""
    tool_id = f"toolu_{uuid4().hex[:12]}"
    tool_id_1 = f"toolu_{uuid4().hex[:12]}"
    tool_id_2 = f"toolu_{uuid4().hex[:12]}"

    return MockScenario(
        name="ask_user_question",
        messages=[
            SystemMessage(subtype="init", data={}),
            # First turn: exploration
            AssistantMessage(
                content=[
                    TextBlock(text="Let me explore the codebase first."),
                    ToolUseBlock(
                        id=tool_id_1,
                        name="Glob",
                        input={"pattern": "**/*.py"},
                    ),
                ],
                model="claude-sonnet-4-20250514",
            ),
            UserMessage(content=[
                ToolResultBlock(
                    tool_use_id=tool_id_1,
                    content="src/main.py\nsrc/utils.py\ntests/test_main.py",
                ),
            ]),
            # Second turn: read a file
            AssistantMessage(
                content=[
                    TextBlock(text="Let me read the main file."),
                    ToolUseBlock(
                        id=tool_id_2,
                        name="Read",
                        input={"file_path": "src/main.py"},
                    ),
                ],
                model="claude-sonnet-4-20250514",
            ),
            UserMessage(content=[
                ToolResultBlock(
                    tool_use_id=tool_id_2,
                    content="def main():\n    print('Hello')",
                ),
            ]),
            # Third turn: AskUserQuestion
            AssistantMessage(
                content=[
                    TextBlock(text="I have some questions before proceeding with the implementation."),
                    ToolUseBlock(
                        id=tool_id,
                        name="AskUserQuestion",
                        input={
                            "questions": [
                                {
                                    "question": "Which database should I use for storing user data?",
                                    "header": "Database",
                                    "options": [
                                        {"label": "PostgreSQL", "description": "Relational database with strong consistency"},
                                        {"label": "MongoDB", "description": "Document database with flexible schema"},
                                        {"label": "SQLite", "description": "Lightweight file-based database"},
                                    ],
                                    "multiSelect": False,
                                },
                                {
                                    "question": "Should the API require authentication?",
                                    "header": "Auth",
                                    "options": [
                                        {"label": "Yes, JWT tokens", "description": "Secure with JSON Web Tokens"},
                                        {"label": "Yes, API keys", "description": "Simple API key authentication"},
                                        {"label": "No auth needed", "description": "Public API"},
                                    ],
                                    "multiSelect": False,
                                },
                            ],
                        },
                    ),
                ],
                model="claude-sonnet-4-20250514",
            ),
            # Note: Messages stop here - executor will poll for answers, then call query() with answers
        ],
        # These messages are yielded AFTER the executor sends the answers via query()
        continuation_messages=[
            AssistantMessage(
                content=[
                    TextBlock(text="Thank you for the clarifications! Based on your answers, here's my implementation spec:\n\n## Summary\nI will implement the feature using the database and authentication approach you specified.\n\n## Files to Modify\n- src/main.py\n- src/database.py (new)\n- src/auth.py (new)\n\n## Implementation Steps\n1. Set up database connection\n2. Add authentication middleware\n3. Update main module to use new components"),
                ],
                model="claude-sonnet-4-20250514",
            ),
            ResultMessage(
                subtype="success",
                session_id=f"mock_{uuid4().hex[:8]}",
                is_error=False,
                num_turns=4,
                total_cost_usd=0.08,
                duration_ms=2000,
                duration_api_ms=1600,
                usage={"input_tokens": 2000, "output_tokens": 800},
            ),
        ],
    )


def create_success_scenario() -> MockScenario:
    """Create a scenario that completes successfully."""
    tool_id_1 = f"toolu_{uuid4().hex[:12]}"

    return MockScenario(
        name="success",
        messages=[
            SystemMessage(subtype="init", data={}),
            AssistantMessage(
                content=[
                    TextBlock(text="Let me analyze the task and explore the codebase."),
                    ToolUseBlock(
                        id=tool_id_1,
                        name="Glob",
                        input={"pattern": "**/*.py"},
                    ),
                ],
                model="claude-sonnet-4-20250514",
            ),
            UserMessage(content=[
                ToolResultBlock(
                    tool_use_id=tool_id_1,
                    content="src/main.py\ntests/test_main.py",
                ),
            ]),
            AssistantMessage(
                content=[
                    TextBlock(text="Based on my analysis, here's the implementation spec:\n\n## Summary\nThis task requires updating the main module.\n\n## Files to Modify\n- src/main.py"),
                ],
                model="claude-sonnet-4-20250514",
            ),
            ResultMessage(
                subtype="success",
                session_id=f"mock_{uuid4().hex[:8]}",
                is_error=False,
                num_turns=2,
                total_cost_usd=0.05,
                duration_ms=1000,
                duration_api_ms=800,
                usage={"input_tokens": 1000, "output_tokens": 500},
            ),
        ],
    )


def create_error_scenario() -> MockScenario:
    """Create a scenario that results in an error."""
    tool_id_1 = f"toolu_{uuid4().hex[:12]}"

    return MockScenario(
        name="error",
        messages=[
            SystemMessage(subtype="init", data={}),
            AssistantMessage(
                content=[
                    TextBlock(text="Let me check the repository."),
                    ToolUseBlock(
                        id=tool_id_1,
                        name="Bash",
                        input={"command": "git status"},
                    ),
                ],
                model="claude-sonnet-4-20250514",
            ),
            UserMessage(content=[
                ToolResultBlock(
                    tool_use_id=tool_id_1,
                    content="fatal: not a git repository",
                ),
            ]),
            ResultMessage(
                subtype="error",
                session_id=f"mock_{uuid4().hex[:8]}",
                is_error=True,
                num_turns=1,
                total_cost_usd=0.01,
                duration_ms=500,
                duration_api_ms=400,
                usage={"input_tokens": 500, "output_tokens": 100},
            ),
        ],
    )


# Registry of available scenarios
MOCK_SCENARIOS = {
    "success": create_success_scenario,
    "ask_user_question": create_ask_user_question_scenario,
    "needs_human": create_ask_user_question_scenario,  # Alias
    "error": create_error_scenario,
}


class MockClaudeSDKClient:
    """
    Mock client that yields predefined messages for testing.

    Implements the same interface as ClaudeSDKClient from claude_code_sdk.
    Supports bidirectional communication: after AskUserQuestion, executor
    can send answers via query() and continue receiving messages.
    """

    def __init__(self, options: Any = None, scenario: str = "success"):
        self.options = options
        self.scenario_name = scenario
        self._scenario: MockScenario | None = None
        self._message_index = 0
        self._interrupted = False
        self._connected = False
        self._query_count = 0
        self._pending_continuation = False

    async def connect(self) -> None:
        """Simulate connection."""
        self._connected = True
        # Load scenario
        scenario_factory = MOCK_SCENARIOS.get(self.scenario_name, MOCK_SCENARIOS["success"])
        self._scenario = scenario_factory()
        print(f"[MOCK CLIENT] Connected, using scenario: {self._scenario.name}")

    async def query(self, prompt: str) -> None:
        """Simulate sending a query (initial or follow-up with answers)."""
        self._query_count += 1
        print(f"[MOCK CLIENT] Received query #{self._query_count} ({len(prompt)} chars)")

        if self._query_count > 1:
            # This is a follow-up query (answers to questions)
            print(f"[MOCK CLIENT] Follow-up query received - will yield continuation messages")
            self._pending_continuation = True

    async def receive_messages(self) -> AsyncIterator[Any]:
        """Yield mock messages according to the scenario."""
        if not self._scenario:
            return

        # Yield initial messages
        for message in self._scenario.messages:
            if self._interrupted:
                print("[MOCK CLIENT] Interrupted, stopping message stream")
                return

            await asyncio.sleep(self._scenario.message_delay)

            msg_type = type(message).__name__
            print(f"[MOCK CLIENT] Yielding {msg_type}")

            # Debug: if it's an AssistantMessage with AskUserQuestion, log it
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock) and block.name == "AskUserQuestion":
                        print(f"[MOCK CLIENT] AskUserQuestion block.input: {block.input}")

            yield message

        # After yielding all initial messages, wait for continuation signal
        # The executor will call query() with answers, then call receive_messages() again
        # But since we're in an async generator, we need to handle continuation here
        while not self._interrupted:
            if self._pending_continuation and self._scenario.continuation_messages:
                print(f"[MOCK CLIENT] Yielding continuation messages...")
                self._pending_continuation = False

                for message in self._scenario.continuation_messages:
                    if self._interrupted:
                        print("[MOCK CLIENT] Interrupted during continuation")
                        return

                    await asyncio.sleep(self._scenario.message_delay)
                    msg_type = type(message).__name__
                    print(f"[MOCK CLIENT] Yielding continuation {msg_type}")
                    yield message

                # After continuation, we're done
                return

            # Wait a bit before checking again
            await asyncio.sleep(0.1)

    async def interrupt(self) -> None:
        """Simulate interruption."""
        print("[MOCK CLIENT] Interrupt called")
        self._interrupted = True

    async def disconnect(self) -> None:
        """Simulate disconnection."""
        print("[MOCK CLIENT] Disconnected")
        self._connected = False
