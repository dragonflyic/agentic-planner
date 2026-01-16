"""Outcome classification for Claude Code attempt results."""

import re
from dataclasses import dataclass, field
from typing import Any

from workbench.models import AttemptStatus
from workbench.worker.executor import ExecutionResult
from workbench.worker.sandbox import DiffStats


@dataclass
class QuestionOption:
    """An option for a structured question."""

    label: str
    description: str = ""


@dataclass
class Question:
    """A question extracted from Claude's output."""

    question: str
    why_needed: str = ""
    proposed_default: str | None = None
    evidence: list[str] = field(default_factory=list)
    # Structured question fields (from AskUserQuestion tool)
    options: list[QuestionOption] = field(default_factory=list)
    multi_select: bool = False


@dataclass
class ClassificationResult:
    """Result of attempt classification."""

    status: AttemptStatus
    questions: list[Question] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    pr_url: str | None = None
    what_changed: list[str] = field(default_factory=list)
    error_message: str | None = None


class OutcomeClassifier:
    """Classify Claude Code attempt outcomes."""

    # Patterns that indicate stuck conditions
    STUCK_PATTERNS = {
        "repo_ambiguity": [
            r"which (repo|repository|branch|file)",
            r"unclear (which|what) (to modify|to change)",
            r"multiple (repos|repositories|options)",
        ],
        "semantic_ambiguity": [
            r"could (mean|interpret)",
            r"multiple (interpretations|meanings)",
            r"need clarification",
            r"not sure (if|whether|what)",
            r"unclear (what you mean|intent|requirement)",
        ],
        "missing_decision": [
            r"product decision",
            r"design decision",
            r"(should|would) (I|we|it) (use|choose|prefer)",
            r"which (approach|method|pattern)",
        ],
        "env_blocker": [
            r"(missing|not found|cannot find) (dependency|package|module)",
            r"permission denied",
            r"access denied",
            r"(cannot|couldn't) (connect|access|reach)",
        ],
    }

    # Patterns for extracting PR URLs
    PR_URL_PATTERN = r"https://github\.com/[^/]+/[^/]+/pull/\d+"

    def __init__(
        self,
        max_diff_lines: int = 800,
        max_files_touched: int = 40,
    ):
        self.max_diff_lines = max_diff_lines
        self.max_files_touched = max_files_touched

    def classify(
        self,
        execution_result: ExecutionResult,
        diff_stats: DiffStats,
    ) -> ClassificationResult:
        """
        Classify the outcome of a Claude Code execution.

        Returns a ClassificationResult with status and details.
        """
        # Handle timeout/budget cases first (hard failures)
        if execution_result.timed_out:
            return ClassificationResult(
                status=AttemptStatus.FAILED,
                error_message="Execution timed out",
                risk_flags=["TIMEOUT"],
            )

        if execution_result.budget_exceeded:
            return ClassificationResult(
                status=AttemptStatus.FAILED,
                error_message="Tool call budget exceeded",
                risk_flags=["BUDGET_EXCEEDED"],
            )

        # Extract text content for analysis
        all_text = execution_result.final_text or self._extract_all_text(execution_result.output)

        # Check for AskUserQuestion tool calls (explicit questions)
        # Do this BEFORE checking success - questions don't mean failure
        questions = self._extract_questions_from_result(execution_result)

        # If we have EXPLICIT questions (from AskUserQuestion), it's NEEDS_HUMAN
        if questions:
            print(f"[DEBUG] Returning NEEDS_HUMAN with {len(questions)} explicit questions")
            return ClassificationResult(
                status=AttemptStatus.NEEDS_HUMAN,
                questions=questions,
                assumptions=self._extract_assumptions(all_text),
                what_changed=diff_stats.files_touched or [],
            )

        # Check for implicit stuck patterns ONLY if no work was done
        # (avoids false positives from phrases like "I'm not sure if this is ideal but...")
        if diff_stats.files_count == 0 and execution_result.success:
            implicit_stuck = self._detect_stuck_patterns(all_text)
            if implicit_stuck:
                print(f"[DEBUG] Returning NEEDS_HUMAN with {len(implicit_stuck)} implicit questions (no changes made)")
                return ClassificationResult(
                    status=AttemptStatus.NEEDS_HUMAN,
                    questions=implicit_stuck,
                    assumptions=self._extract_assumptions(all_text),
                    what_changed=[],
                )

        print(f"[DEBUG] No questions found, continuing classification...")

        # Now check for execution errors (after questions, since questions aren't errors)
        if not execution_result.success:
            error_msg = execution_result.output.get("error", "Unknown error")
            return ClassificationResult(
                status=AttemptStatus.FAILED,
                error_message=f"Execution failed: {error_msg}",
                risk_flags=["EXECUTION_ERROR"],
            )

        # Check for PR creation
        pr_url = self._extract_pr_url(all_text)

        # Check soft gates (diff size, files touched)
        risk_flags = []
        if diff_stats.total_lines > self.max_diff_lines:
            risk_flags.append(f"DIFF_SIZE_EXCEEDED:{diff_stats.total_lines}")
        if diff_stats.files_count > self.max_files_touched:
            risk_flags.append(f"FILES_EXCEEDED:{diff_stats.files_count}")

        # Determine final status
        if pr_url:
            status = AttemptStatus.SUCCESS
        elif diff_stats.files_count == 0:
            status = AttemptStatus.NOOP
        else:
            # Changes made but no PR - could be partial success
            status = AttemptStatus.SUCCESS

        return ClassificationResult(
            status=status,
            pr_url=pr_url,
            what_changed=diff_stats.files_touched or [],
            assumptions=self._extract_assumptions(all_text),
            risk_flags=risk_flags,
        )

    def _extract_all_text(self, output: dict[str, Any]) -> str:
        """Extract all text content from Claude's output."""
        texts = []

        # Get final_text (new SDK format)
        if "final_text" in output:
            texts.append(str(output["final_text"]))

        # Get result text (legacy format)
        if "result" in output:
            texts.append(str(output["result"]))

        # Get message content (legacy format)
        messages = output.get("messages", [])
        for msg in messages:
            content = msg.get("content", [])
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))

        return "\n".join(texts)

    def _extract_questions_from_result(self, execution_result: ExecutionResult) -> list[Question]:
        """Extract questions from ExecutionResult.questions_asked (SDK format).

        If interrupted_for_questions is False, the questions were already answered
        during bidirectional communication, so we return an empty list.
        """
        questions = []

        print(f"[DEBUG] Extracting questions from execution_result.questions_asked: {execution_result.questions_asked}")
        print(f"[DEBUG] interrupted_for_questions: {execution_result.interrupted_for_questions}")

        # If questions were answered during execution (bidirectional mode), don't return them
        if not execution_result.interrupted_for_questions and execution_result.questions_asked:
            print(f"[DEBUG] Questions were answered during execution, not returning as NEEDS_HUMAN")
            return []

        for qa in execution_result.questions_asked:
            # qa is a dict with "id" and "questions" (list of question objects)
            q_list = qa.get("questions", [])
            print(f"[DEBUG] Processing qa: {qa}, q_list: {q_list}")
            for q in q_list:
                # Extract options if present (structured AskUserQuestion)
                raw_options = q.get("options", [])
                options = [
                    QuestionOption(
                        label=opt.get("label", ""),
                        description=opt.get("description", ""),
                    )
                    for opt in raw_options
                ]

                questions.append(
                    Question(
                        question=q.get("question", "Unknown question"),
                        why_needed=q.get("header", ""),
                        proposed_default=None,
                        evidence=[],
                        options=options,
                        multi_select=q.get("multiSelect", False),
                    )
                )

        print(f"[DEBUG] Extracted {len(questions)} questions")
        return questions

    def _extract_questions(self, output: dict[str, Any]) -> list[Question]:
        """Extract questions from output dict (legacy format fallback)."""
        questions = []

        # Check for questions_asked in output (new SDK format)
        questions_asked = output.get("questions_asked", [])
        for qa in questions_asked:
            q_list = qa.get("questions", [])
            for q in q_list:
                questions.append(
                    Question(
                        question=q.get("question", "Unknown question"),
                        why_needed=q.get("header", ""),
                        proposed_default=None,
                        evidence=[],
                    )
                )

        return questions

    def _detect_stuck_patterns(self, text: str) -> list[Question]:
        """Detect implicit stuck conditions from text patterns."""
        questions = []

        for category, patterns in self.STUCK_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    questions.append(
                        Question(
                            question=f"Clarification needed ({category})",
                            why_needed=f"Detected {category} pattern in output",
                            evidence=[pattern],
                        )
                    )
                    break  # One match per category

        return questions

    def _extract_pr_url(self, text: str) -> str | None:
        """Extract PR URL from text."""
        match = re.search(self.PR_URL_PATTERN, text)
        return match.group(0) if match else None

    def _extract_assumptions(self, text: str) -> list[str]:
        """Extract assumptions Claude reported."""
        assumptions = []

        patterns = [
            r"(?:I(?:'m| am) assuming|Assumption:|Assumed:)\s*(.+?)(?:\n|$)",
            r"(?:I(?:'ll| will) assume)\s*(.+?)(?:\n|$)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            assumptions.extend(matches)

        return assumptions[:10]  # Limit to 10
