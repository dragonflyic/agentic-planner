"""Workspace sandbox management for attempt execution."""

import asyncio
import shutil
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class DiffStats:
    """Git diff statistics."""

    lines_added: int = 0
    lines_deleted: int = 0
    files_touched: list[str] | None = None

    @property
    def total_lines(self) -> int:
        return self.lines_added + self.lines_deleted

    @property
    def files_count(self) -> int:
        return len(self.files_touched) if self.files_touched else 0


class WorkspaceSandbox:
    """Manages isolated workspace for Claude Code attempt execution."""

    def __init__(
        self,
        path: Path,
        repo_url: str,
        base_branch: str,
        branch_name: str,
    ):
        self.path = path
        self.repo_url = repo_url
        self.base_branch = base_branch
        self.branch_name = branch_name

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        repo_url: str,
        base_branch: str = "main",
        github_pat: str | None = None,
        base_dir: str = "/tmp/workbench-attempts",
    ) -> AsyncGenerator["WorkspaceSandbox", None]:
        """
        Create an isolated workspace with a cloned repository.

        Yields the workspace and cleans up automatically on exit.
        """
        # Ensure base directory exists
        Path(base_dir).mkdir(parents=True, exist_ok=True)

        # Create temporary directory
        temp_dir = tempfile.mkdtemp(dir=base_dir, prefix="attempt_")
        workspace_path = Path(temp_dir)

        try:
            # Prepare clone URL with authentication
            clone_url = cls._add_auth_to_url(repo_url, github_pat)

            # Clone repository (shallow for speed)
            # First try with specified branch, then fallback to default branch
            clone_proc = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--depth",
                "1",
                "-b",
                base_branch,
                clone_url,
                str(workspace_path / "repo"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await clone_proc.communicate()

            # If branch not found, try without specifying branch (use repo default)
            if clone_proc.returncode != 0 and "not found" in stderr.decode().lower():
                clone_proc = await asyncio.create_subprocess_exec(
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    clone_url,
                    str(workspace_path / "repo"),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await clone_proc.communicate()

            if clone_proc.returncode != 0:
                raise RuntimeError(f"Git clone failed: {stderr.decode()}")

            repo_path = workspace_path / "repo"

            # Create working branch for the attempt
            branch_name = f"claude/attempt-{uuid4().hex[:8]}"
            branch_proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(repo_path),
                "checkout",
                "-b",
                branch_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await branch_proc.communicate()

            # Configure git user for commits
            await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(repo_path),
                "config",
                "user.email",
                "workbench@example.com",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(repo_path),
                "config",
                "user.name",
                "Workbench Bot",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            sandbox = cls(
                path=repo_path,
                repo_url=repo_url,
                base_branch=base_branch,
                branch_name=branch_name,
            )

            yield sandbox

        finally:
            # Cleanup workspace
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _add_auth_to_url(url: str, pat: str | None) -> str:
        """Add PAT authentication to git URL."""
        if not pat:
            return url

        # Convert https://github.com/owner/repo to https://PAT@github.com/owner/repo
        if url.startswith("https://github.com/"):
            return url.replace("https://github.com/", f"https://{pat}@github.com/")

        return url

    async def get_diff_stats(self) -> DiffStats:
        """Get git diff statistics for soft gate checks."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(self.path),
            "diff",
            "--numstat",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        stats = DiffStats(files_touched=[])
        for line in stdout.decode().strip().split("\n"):
            if not line or "\t" not in line:
                continue

            parts = line.split("\t")
            if len(parts) >= 3:
                try:
                    additions = int(parts[0]) if parts[0] != "-" else 0
                    deletions = int(parts[1]) if parts[1] != "-" else 0
                    filename = parts[2]

                    stats.lines_added += additions
                    stats.lines_deleted += deletions
                    if stats.files_touched is not None:
                        stats.files_touched.append(filename)
                except ValueError:
                    continue

        return stats

    async def get_diff(self) -> str:
        """Get the full git diff."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(self.path),
            "diff",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode()

    async def commit_changes(self, message: str) -> bool:
        """Stage and commit all changes."""
        # Stage all changes
        add_proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(self.path),
            "add",
            "-A",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await add_proc.communicate()

        # Commit
        commit_proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(self.path),
            "commit",
            "-m",
            message,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await commit_proc.communicate()

        return commit_proc.returncode == 0

    async def push_branch(self, github_pat: str | None = None) -> bool:
        """Push the branch to remote."""
        # Set up remote URL with auth if needed
        if github_pat:
            remote_url = self._add_auth_to_url(self.repo_url, github_pat)
            await asyncio.create_subprocess_exec(
                "git",
                "-C",
                str(self.path),
                "remote",
                "set-url",
                "origin",
                remote_url,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

        # Push the branch
        push_proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(self.path),
            "push",
            "-u",
            "origin",
            self.branch_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await push_proc.communicate()

        return push_proc.returncode == 0
