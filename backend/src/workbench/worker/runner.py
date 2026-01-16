"""Main worker process for processing attempt jobs."""

import asyncio
import json
import signal
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update

from workbench.config import get_settings
from workbench.db.session import AsyncSessionLocal
from workbench.models import Artifact, ArtifactType, Attempt, AttemptStatus, Clarification, Job, JobType, Signal
from workbench.services.job_service import JobService
from workbench.worker.classifier import OutcomeClassifier
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

            # Create executor
            executor = ClaudeCodeExecutor(
                cwd=sandbox.path,
                max_turns=self.settings.claude_default_max_turns,
                timeout_seconds=self.settings.claude_default_timeout_seconds,
            )

            # Log execution start
            await log_event("execution_starting", "Starting Claude Code execution")

            # Create executor log callback that tracks sequence numbers
            async def executor_log_callback(seq: int, log_entry: dict[str, Any], is_final: bool) -> None:
                nonlocal sequence_num
                sequence_num += 1
                await log_callback(sequence_num, log_entry, is_final)

            # Execute Claude Code with log streaming
            execution_result = await executor.execute(
                signal=signal_context,
                log_callback=executor_log_callback,
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

            # Classify outcome
            classifier = OutcomeClassifier()
            classification = classifier.classify(execution_result, diff_stats)

            # Build summary
            summary = {
                "status": classification.status.value,
                "what_changed": classification.what_changed,
                "assumptions": classification.assumptions,
                "risk_flags": classification.risk_flags,
                "metrics": {
                    "tool_calls": execution_result.metrics.tool_call_count,
                    "turns": execution_result.metrics.turn_count,
                    "commands_run": execution_result.metrics.commands_run,
                    "cost_usd": execution_result.metrics.total_cost_usd,
                },
            }

            # Update attempt with results
            update_values: dict[str, Any] = {
                "status": classification.status,
                "finished_at": datetime.now(UTC),
                "summary_json": summary,
                "runner_metadata_json": {
                    "timed_out": execution_result.timed_out,
                    "budget_exceeded": execution_result.budget_exceeded,
                    "interrupted_for_questions": execution_result.interrupted_for_questions,
                    "session_id": execution_result.output.get("session_id"),
                },
            }

            if classification.error_message:
                update_values["error_message"] = classification.error_message

            if classification.pr_url:
                update_values["pr_url"] = classification.pr_url
                update_values["branch_name"] = sandbox.branch_name

            await db.execute(
                update(Attempt).where(Attempt.id == attempt_id).values(**update_values)
            )

            # If NEEDS_HUMAN, create clarification records
            if classification.status == AttemptStatus.NEEDS_HUMAN:
                for i, q in enumerate(classification.questions):
                    clarification = Clarification(
                        attempt_id=attempt_id,
                        question_id=f"q_{i}",
                        question_text=q.question,
                        question_context=q.why_needed,
                        default_answer=q.proposed_default,
                        anchors_json={"evidence": q.evidence},
                    )
                    db.add(clarification)

                # Update signal state to blocked
                await db.execute(
                    update(Signal)
                    .where(Signal.id == signal_id)
                    .values(state="blocked")
                )

            elif classification.status == AttemptStatus.SUCCESS:
                # Update signal state to completed
                await db.execute(
                    update(Signal)
                    .where(Signal.id == signal_id)
                    .values(state="completed")
                )

            elif classification.status == AttemptStatus.FAILED:
                # Reset signal to pending state for potential retry
                await db.execute(
                    update(Signal)
                    .where(Signal.id == signal_id)
                    .values(state="pending")
                )

            await db.commit()

            return summary


async def main() -> None:
    """Entry point for the worker process."""
    worker = AttemptWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
