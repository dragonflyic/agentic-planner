"""Handler for SYNC_SIGNALS jobs."""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from workbench.config import get_settings
from workbench.models import Job
from workbench.services.github_sync import GitHubSyncService


async def handle_sync_signals(db: AsyncSession, job: Job) -> dict[str, Any]:
    """
    Handle a SYNC_SIGNALS job.

    Expected payload:
    {
        "org": "dragonflyic",
        "project_number": 1,
        "since": "2025-01-01T00:00:00Z",  # optional
        "force_refresh": false,  # optional
        "label_filter": ["good-first-issue"],  # optional
        "repo_filter": ["owner/repo"],  # optional
    }
    """
    settings = get_settings()
    payload = job.payload

    org = payload.get("org")
    project_number = payload.get("project_number")

    if not org or not project_number:
        raise ValueError("Missing required fields: org, project_number")

    if not settings.github_pat:
        raise ValueError("GITHUB_PAT not configured")

    since = None
    if payload.get("since"):
        since = datetime.fromisoformat(payload["since"])

    sync_service = GitHubSyncService(db, settings.github_pat)

    stats = await sync_service.sync_organization_project(
        org=org,
        project_number=project_number,
        since=since,
        force_refresh=payload.get("force_refresh", False),
        label_filter=payload.get("label_filter"),
        repo_filter=payload.get("repo_filter"),
    )

    return {
        "success": len(stats.errors) == 0,
        "project_title": stats.project_title,
        "items_found": stats.items_found,
        "signals_created": stats.signals_created,
        "signals_updated": stats.signals_updated,
        "signals_skipped": stats.signals_skipped,
        "errors": stats.errors[:10],  # Limit error list
        "error_count": len(stats.errors),
    }
