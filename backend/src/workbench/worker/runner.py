"""Main worker process for processing attempt jobs."""

import asyncio
import json
import signal
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, update

from workbench.config import get_settings
from workbench.db.session import AsyncSessionLocal
from workbench.models import Artifact, ArtifactType, Attempt, AttemptStatus, Clarification, Job, JobType
from workbench.services.job_service import JobService
from workbench.worker.executor import ClaudeCodeExecutor, SignalContext
from workbench.worker.sandbox import WorkspaceSandbox


class AttemptWorker:
    """Worker that processes attempt jobs from the queue."""

    def __init__(self):
        self.settings = get_settings()
        self._shutdown = False
        self._current_job: Job | None = None

    async def run(self) -> None:
        """Main worker loop."""
        print(f"Worker starting... (poll interval: {self.settings.worker_poll_interval_seconds}s)")

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown)

        while not self._shutdown:
            try:
                await self._process_next_job()
            except Exception as e:
                print(f"Worker error: {e}")
                await asyncio.sleep(self.settings.worker_poll_interval_seconds)

        print("Worker shutting down...")

    def _handle_shutdown(self) -> None:
        """Handle shutdown signal."""
        print("Received shutdown signal...")
        self._shutdown = True

    async def _process_next_job(self) -> None:
        """Try to claim and process the next job."""
        async with AsyncSessionLocal() as db:
            job_service = JobService(db)

            # Try to claim a job
            job = await job_service.claim_job(
                job_types=[JobType.RUN_ATTEMPT, JobType.RETRY_ATTEMPT, JobType.SYNC_SIGNALS]
            )

            if job is None:
                # No jobs available, wait before polling again
                await asyncio.sleep(self.settings.worker_poll_interval_seconds)
                return

            self._current_job = job
            print(f"Claimed job {job.id} (type: {job.type})")

            try:
                # Mark as running
                await job_service.start_job(job.id)
                await db.commit()

                # Process the job based on type
                if job.type == JobType.SYNC_SIGNALS:
                    from workbench.worker.sync_handler import handle_sync_signals

                    result = await handle_sync_signals(db, job)
                else:
                    result = await self._execute_attempt(db, job)

                # Mark job as complete
                await job_service.complete_job(job.id, result)
                await db.commit()
                print(f"Completed job {job.id}")

            except Exception as e:
                print(f"Job {job.id} failed: {e}")
                await db.rollback()

                # Mark job as failed
                async with AsyncSessionLocal() as fail_db:
                    fail_service = JobService(fail_db)
                    await fail_service.fail_job(job.id, str(e))
                    await fail_db.commit()

            finally:
                self._current_job = None

    async def _execute_attempt(
        self,
        db: AsyncSessionLocal,
        job: Job,
    ) -> dict[str, Any]:
        """Execute a Claude Code attempt."""
        payload = job.payload
        attempt_id = payload.get("attempt_id")
        signal_id = payload.get("signal_id")

        # Build full signal context
        signal_context = SignalContext(
            source=payload.get("source", "unknown"),
            repo=payload.get("repo"),
            issue_number=payload.get("issue_number"),
            title=payload.get("title"),
            body=payload.get("body"),
            metadata=payload.get("metadata"),
            project_fields=payload.get("project_fields"),
            clarifications=payload.get("clarifications", []),
        )

        # Update attempt status to RUNNING
        await db.execute(
            update(Attempt)
            .where(Attempt.id == attempt_id)
            .values(
                status=AttemptStatus.RUNNING,
                started_at=datetime.now(UTC),
            )
        )
        await db.commit()

        # Build repo URL
        repo_url = f"https://github.com/{signal_context.repo}.git"

        # Track sequence number for logs
        sequence_num = 0

        # Create log callback to write artifacts
        async def log_callback(seq: int, log_entry: dict[str, Any], is_final: bool) -> None:
            """Write log entry as an artifact."""
            artifact = Artifact(
                attempt_id=UUID(attempt_id) if isinstance(attempt_id, str) else attempt_id,
                type=ArtifactType.LOG,
                name=f"log_{seq:04d}",
                sequence_num=seq,
                is_final=is_final,
                content_text=json.dumps(log_entry),
            )
            db.add(artifact)
            await db.commit()

        async def log_event(event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
            """Log a timeline event."""
            nonlocal sequence_num
            sequence_num += 1
            await log_callback(sequence_num, {
                "type": "event",
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event_type,
                "message": message,
                "details": details,
            }, is_final=False)

        # Log attempt start
        await log_event("attempt_started", f"Starting attempt for signal: {signal_context.title[:50]}...")

        # Log repo clone
        await log_event("cloning_repo", f"Cloning repository: {signal_context.repo}", {
            "repo_url": repo_url,
        })

        # Create workspace and run Claude Code
        async with WorkspaceSandbox.create(
            repo_url=repo_url,
            github_pat=self.settings.github_pat or None,
            base_dir=self.settings.worker_tmpdir_base,
        ) as sandbox:
            await log_event("workspace_ready", f"Workspace created at {sandbox.path}", {
                "branch": sandbox.branch_name,
                "path": str(sandbox.path),
            })

            # Create executor (with optional mock mode for testing)
            mock_scenario = self.settings.claude_mock_scenario or None
            if mock_scenario:
                print(f"[RUNNER] Using MOCK mode with scenario: {mock_scenario}")

            executor = ClaudeCodeExecutor(
                cwd=sandbox.path,
                max_turns=self.settings.claude_default_max_turns,
                timeout_seconds=self.settings.claude_default_timeout_seconds,
                mock_scenario=mock_scenario,
            )

            # Log execution start
            await log_event("execution_starting", "Starting Claude Code execution")

            # Create executor log callback that tracks sequence numbers
            async def executor_log_callback(seq: int, log_entry: dict[str, Any], is_final: bool) -> None:
                nonlocal sequence_num
                sequence_num += 1
                await log_callback(sequence_num, log_entry, is_final)

            # Track clarification IDs created during this execution
            created_clarification_ids: list[str] = []

            # Callback to save questions when AskUserQuestion is detected
            async def on_questions_asked(questions_list: list[dict[str, Any]]) -> dict[str, list[str]]:
                """Save questions as clarifications and return mapping."""
                nonlocal created_clarification_ids
                result_mapping: dict[str, list[str]] = {}

                for qa in questions_list:
                    tool_id = qa.get("id", "unknown")
                    questions = qa.get("questions", [])
                    clarification_ids = []

                    for i, q in enumerate(questions):
                        # Build anchors_json with options for structured questions
                        anchors: dict[str, Any] = {"evidence": []}
                        options = q.get("options", [])
                        if options:
                            anchors["options"] = options
                            anchors["multi_select"] = q.get("multiSelect", False)

                        clarification = Clarification(
                            attempt_id=attempt_id,
                            question_id=f"{tool_id}_{i}",
                            question_text=q.get("question", "Unknown question"),
                            question_context=q.get("header", ""),
                            default_answer=None,
                            anchors_json=anchors,
                        )
                        db.add(clarification)
                        await db.flush()
                        clarification_ids.append(str(clarification.id))
                        created_clarification_ids.append(str(clarification.id))

                    result_mapping[tool_id] = clarification_ids

                await db.commit()
                print(f"[RUNNER] Saved {len(created_clarification_ids)} clarifications")
                return result_mapping

            # Callback to poll for answers
            async def poll_for_answers() -> dict[str, str] | None:
                """Check if all clarifications are answered. Returns answers or None."""
                if not created_clarification_ids:
                    return {}

                # Query all created clarifications
                from sqlalchemy import select
                query = select(Clarification).where(
                    Clarification.id.in_([UUID(cid) for cid in created_clarification_ids])
                )
                result = await db.execute(query)
                clarifications = result.scalars().all()

                # Check if all are answered
                answers = {}
                for c in clarifications:
                    if not c.is_answered:
                        return None  # Not all answered yet
                    answers[c.question_id] = c.effective_answer or ""

                return answers

            # Execute Claude Code with bidirectional communication
            execution_result = await executor.execute(
                signal=signal_context,
                log_callback=executor_log_callback,
                on_questions_asked=on_questions_asked,
                poll_for_answers=poll_for_answers,
                answer_poll_interval=5.0,
            )

            # Save the prompt as a separate artifact for easy access
            sequence_num += 1
            prompt_artifact = Artifact(
                attempt_id=UUID(attempt_id) if isinstance(attempt_id, str) else attempt_id,
                type=ArtifactType.LOG,
                name="prompt",
                sequence_num=0,  # Always first
                is_final=False,
                content_text=json.dumps({
                    "type": "prompt",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "content": execution_result.prompt,
                }),
            )
            db.add(prompt_artifact)
            await db.commit()

            # Log execution complete
            await log_event("execution_complete", f"Claude Code execution finished", {
                "turns": execution_result.metrics.turn_count,
                "tool_calls": execution_result.metrics.tool_call_count,
                "cost_usd": execution_result.metrics.total_cost_usd,
                "interrupted": execution_result.interrupted_for_questions,
            })

            # Get diff stats
            diff_stats = await sandbox.get_diff_stats()

            # Determine status directly (simple logic)
            error_message: str | None = None
            if execution_result.timed_out:
                status = AttemptStatus.ERROR
                error_message = "Execution timed out"
            elif execution_result.budget_exceeded:
                status = AttemptStatus.ERROR
                error_message = "Tool call budget exceeded"
            elif not execution_result.success:
                status = AttemptStatus.ERROR
                error_message = execution_result.output.get("error", "Unknown error")
            elif execution_result.interrupted_for_questions:
                status = AttemptStatus.WAITING
            else:
                status = AttemptStatus.COMPLETE

            # Extract PR URL if present
            import re
            pr_url_pattern = r"https://github\.com/[^/]+/[^/]+/pull/\d+"
            all_text = execution_result.final_text or ""
            pr_match = re.search(pr_url_pattern, all_text)
            pr_url = pr_match.group(0) if pr_match else None

            # Build summary
            summary = {
                "status": status.value,
                "what_changed": diff_stats.files_touched or [],
                "metrics": {
                    "tool_calls": execution_result.metrics.tool_call_count,
                    "turns": execution_result.metrics.turn_count,
                    "commands_run": execution_result.metrics.commands_run,
                    "cost_usd": execution_result.metrics.total_cost_usd,
                },
            }

            # Update attempt with results
            update_values: dict[str, Any] = {
                "status": status,
                "finished_at": datetime.now(UTC),
                "summary_json": summary,
                "runner_metadata_json": {
                    "timed_out": execution_result.timed_out,
                    "budget_exceeded": execution_result.budget_exceeded,
                    "interrupted_for_questions": execution_result.interrupted_for_questions,
                    "session_id": execution_result.output.get("session_id"),
                },
            }

            if error_message:
                update_values["error_message"] = error_message

            if pr_url:
                update_values["pr_url"] = pr_url
                update_values["branch_name"] = sandbox.branch_name

            await db.execute(
                update(Attempt).where(Attempt.id == attempt_id).values(**update_values)
            )
            await db.commit()

            return summary


async def main() -> None:
    """Entry point for the worker process."""
    worker = AttemptWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
