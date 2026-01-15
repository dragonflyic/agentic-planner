"""GitHub Project sync service."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.models import Signal, SignalState
from workbench.services.github_client import GitHubGraphQLClient, ProjectItem
from workbench.services.prioritization import calculate_signal_priority


@dataclass
class SyncStats:
    """Statistics from a sync operation."""

    project_title: str = ""
    items_found: int = 0
    signals_created: int = 0
    signals_updated: int = 0
    signals_skipped: int = 0  # Draft issues, PRs, etc.
    errors: list[str] = field(default_factory=list)


class GitHubSyncService:
    """Service for syncing GitHub Project items to Signals."""

    def __init__(self, db: AsyncSession, github_token: str):
        self.db = db
        self.github_token = github_token

    async def sync_organization_project(
        self,
        org: str,
        project_number: int,
        *,
        since: datetime | None = None,
        force_refresh: bool = False,
        label_filter: list[str] | None = None,
        repo_filter: list[str] | None = None,
    ) -> SyncStats:
        """
        Sync all issues from a GitHub organization project.

        Args:
            org: Organization login (e.g., "dragonflyic")
            project_number: Project number (e.g., 1)
            since: Only sync items updated after this time
            force_refresh: If True, update all fields even if unchanged
            label_filter: Only sync issues with these labels
            repo_filter: Only sync issues from these repos (format: "owner/repo")

        Returns:
            SyncStats with operation results
        """
        stats = SyncStats()

        async with GitHubGraphQLClient(self.github_token) as client:
            # Get project info
            project = await client.get_organization_project(org, project_number)
            stats.project_title = project.title

            print(f"Syncing project: {project.title} ({project.url})")

            # Track existing signals for create vs update detection
            existing_signals = await self._get_existing_signals_map()

            # Iterate over all items
            async for item in client.iter_all_project_items(project.id):
                stats.items_found += 1

                try:
                    result = await self._process_item(
                        item,
                        existing_signals=existing_signals,
                        since=since,
                        force_refresh=force_refresh,
                        label_filter=label_filter,
                        repo_filter=repo_filter,
                    )
                    if result == "created":
                        stats.signals_created += 1
                    elif result == "updated":
                        stats.signals_updated += 1
                    elif result == "skipped":
                        stats.signals_skipped += 1
                except Exception as e:
                    error_msg = f"Item {item.node_id}: {e!s}"
                    stats.errors.append(error_msg)
                    print(f"Error processing item: {error_msg}")

            # Commit all changes
            await self.db.commit()

        print(
            f"Sync complete: {stats.signals_created} created, "
            f"{stats.signals_updated} updated, {stats.signals_skipped} skipped"
        )
        return stats

    async def _get_existing_signals_map(self) -> dict[tuple[str, int], str]:
        """Get map of (repo, issue_number) -> signal_id for existing signals."""
        result = await self.db.execute(
            select(Signal.repo, Signal.issue_number, Signal.id)
        )
        return {(row[0], row[1]): str(row[2]) for row in result.fetchall()}

    async def _process_item(
        self,
        item: ProjectItem,
        *,
        existing_signals: dict[tuple[str, int], str],
        since: datetime | None = None,
        force_refresh: bool = False,
        label_filter: list[str] | None = None,
        repo_filter: list[str] | None = None,
    ) -> str:
        """
        Process a single project item.

        Returns: "created", "updated", or "skipped"
        """
        # Skip non-issues (PRs, drafts)
        if item.content_type != "Issue":
            return "skipped"

        if item.issue_number is None or item.repo_owner is None or item.repo_name is None:
            return "skipped"

        # Build repo string
        repo = f"{item.repo_owner}/{item.repo_name}"

        # Apply repo filter
        if repo_filter and repo not in repo_filter:
            return "skipped"

        # Apply label filter
        if label_filter:
            if not any(label in item.labels for label in label_filter):
                return "skipped"

        # Check if updated since threshold
        if since and item.updated_at:
            item_updated = datetime.fromisoformat(item.updated_at.replace("Z", "+00:00"))
            if item_updated < since:
                return "skipped"

        # Check if exists
        signal_key = (repo, item.issue_number)
        is_existing = signal_key in existing_signals

        # Prepare metadata including context info
        metadata = {
            "github_node_id": item.issue_node_id,
            "project_item_id": item.node_id,
            "labels": item.labels,
            "assignees": item.assignees,
            "github_state": item.state,
            "url": item.url,
            "github_created_at": item.created_at,
            "github_updated_at": item.updated_at,
            "synced_at": datetime.now(timezone.utc).isoformat(),
            # Context information
            "context": {
                "comment_count": item.context.comment_count,
                "reference_count": item.context.reference_count,
                "has_parent": item.context.parent_issue is not None,
                "context_score": item.context.context_score,
                "comments": item.context.comments[:5],  # Store first 5 comments
                "referenced_issues": item.context.referenced_issues[:5],
                "referenced_prs": item.context.referenced_prs[:5],
                "parent_issue": item.context.parent_issue,
                # PR activity tracking
                "open_pr_count": item.context.open_pr_count,
                "merged_pr_count": item.context.merged_pr_count,
                "closed_pr_count": item.context.closed_pr_count,
                "has_active_pr": item.context.has_active_pr,
                "has_merged_pr": item.context.has_merged_pr,
            },
        }

        # Calculate priority using rules-based scoring (includes context)
        priority = self._calculate_priority(item, repo, metadata)

        # Use PostgreSQL upsert for idempotency
        stmt = pg_insert(Signal).values(
            source="github",
            repo=repo,
            issue_number=item.issue_number,
            external_id=item.issue_node_id,
            title=item.title,
            body=item.body,
            metadata_json=metadata,
            project_fields_json=item.field_values,
            state=SignalState.PENDING,
            priority=priority,
        )

        # On conflict, update existing record but preserve workflow state
        stmt = stmt.on_conflict_do_update(
            constraint="uq_signals_repo_issue",
            set_={
                "title": stmt.excluded.title,
                "body": stmt.excluded.body,
                "metadata_json": stmt.excluded.metadata_json,
                "project_fields_json": stmt.excluded.project_fields_json,
                "priority": stmt.excluded.priority,  # Always recalculate priority
                "updated_at": datetime.now(timezone.utc),
                # Don't update state - preserve workflow state
            },
        )

        await self.db.execute(stmt)

        return "updated" if is_existing else "created"

    def _calculate_priority(self, item: ProjectItem, repo: str, metadata: dict) -> int:
        """
        Calculate priority using the prioritization module.

        Uses rules-based scoring that considers:
        - Repository (priority repos get boosted)
        - Status (Done/closed items are downweighted)
        - Iteration (current iteration gets boosted)
        - Explicit priority field values
        """
        return calculate_signal_priority(
            repo=repo,
            project_fields=item.field_values,
            metadata=metadata,
        )
