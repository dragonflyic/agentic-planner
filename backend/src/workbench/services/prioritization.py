"""Signal prioritization module.

Rules-based prioritization for signals. Eventually this will be more agentic/smart,
but for now it uses simple weighted rules.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class PriorityConfig:
    """Configuration for priority calculation."""

    # Target repos get a boost, others are heavily downweighted
    priority_repos: list[str] = None
    non_priority_repo_penalty: int = -500

    # Current iteration gets a boost
    current_iteration: str = "Cycle 9"
    current_iteration_boost: int = 200

    # Done/closed items are heavily downweighted
    done_penalty: int = -400
    closed_penalty: int = -400

    # Context richness boost (signals with more context are more actionable)
    # Max context boost is ~115 (50 from comments + 45 from refs + 20 from parent)
    context_multiplier: float = 1.0  # Multiply context_score by this

    # PR activity penalties (signals with PRs are likely already being worked on)
    active_pr_penalty: int = -300  # Open PR = actively being worked
    merged_pr_penalty: int = -200  # Merged PR = likely done/resolved

    # Recency boost (recently active signals are more relevant)
    recency_boost_max: int = 100  # Max boost for very recent activity
    recency_days_for_max: int = 3  # Days within which to get max boost
    recency_days_decay: int = 30  # Days after which no boost is given

    # Base priority from explicit priority field
    base_priority_map: dict[str, int] = None

    def __post_init__(self):
        if self.priority_repos is None:
            self.priority_repos = ["dragonflyic/broker-assist"]

        if self.base_priority_map is None:
            self.base_priority_map = {
                "p0": 100,
                "critical": 100,
                "urgent": 100,
                "p1": 75,
                "high": 75,
                "p2": 50,
                "medium": 50,
                "normal": 50,
                "p3": 25,
                "low": 25,
                "p4": 10,
                "trivial": 10,
            }


# Default configuration
DEFAULT_CONFIG = PriorityConfig()


def calculate_signal_priority(
    repo: str,
    project_fields: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    config: PriorityConfig | None = None,
) -> int:
    """
    Calculate priority score for a signal.

    Higher score = higher priority (should be worked on first).

    Args:
        repo: Repository in format "owner/repo"
        project_fields: GitHub Project fields (Status, Iteration, etc.)
        metadata: Signal metadata (github_state, labels, etc.)
        config: Priority configuration (uses defaults if not provided)

    Returns:
        Integer priority score
    """
    if config is None:
        config = DEFAULT_CONFIG

    if metadata is None:
        metadata = {}

    score = 0

    # Rule 1: Repo prioritization
    if repo in config.priority_repos:
        pass  # No penalty, keep base score
    else:
        score += config.non_priority_repo_penalty

    # Rule 2: Done/Closed penalty
    status = str(project_fields.get("Status", "")).lower()
    github_state = str(metadata.get("github_state", "")).lower()

    if status == "done" or github_state == "closed":
        score += config.done_penalty
    elif github_state == "closed":
        score += config.closed_penalty

    # Rule 3: Current iteration boost
    iteration = str(project_fields.get("Iteration", ""))
    if iteration == config.current_iteration:
        score += config.current_iteration_boost

    # Base priority from explicit priority field
    priority_value = (
        project_fields.get("Priority")
        or project_fields.get("priority")
        or project_fields.get("P")
        or ""
    )
    base_priority = config.base_priority_map.get(str(priority_value).lower(), 0)
    score += base_priority

    # Rule 4: Context richness boost
    context = metadata.get("context", {})
    context_score = context.get("context_score", 0)
    score += int(context_score * config.context_multiplier)

    # Rule 5: PR activity penalty (already being worked on)
    if context.get("has_active_pr"):
        score += config.active_pr_penalty
    elif context.get("has_merged_pr"):
        score += config.merged_pr_penalty

    # Rule 6: Recency boost (recently active signals are more relevant)
    recency_boost = _calculate_recency_boost(metadata, config)
    score += recency_boost

    return score


def _calculate_recency_boost(
    metadata: dict[str, Any],
    config: PriorityConfig,
) -> int:
    """Calculate recency boost based on GitHub updated_at timestamp."""
    github_updated_at = metadata.get("github_updated_at")
    if not github_updated_at:
        return 0

    try:
        # Parse the GitHub timestamp
        updated_at = datetime.fromisoformat(github_updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_ago = (now - updated_at).days

        if days_ago <= config.recency_days_for_max:
            # Within the max boost window
            return config.recency_boost_max
        elif days_ago >= config.recency_days_decay:
            # Too old, no boost
            return 0
        else:
            # Linear decay between max and decay thresholds
            decay_range = config.recency_days_decay - config.recency_days_for_max
            days_into_decay = days_ago - config.recency_days_for_max
            decay_fraction = 1 - (days_into_decay / decay_range)
            return int(config.recency_boost_max * decay_fraction)
    except (ValueError, TypeError):
        return 0


def explain_priority(
    repo: str,
    project_fields: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    config: PriorityConfig | None = None,
) -> dict[str, Any]:
    """
    Explain how priority was calculated for debugging/transparency.

    Returns a dict with the final score and breakdown of components.
    """
    if config is None:
        config = DEFAULT_CONFIG

    if metadata is None:
        metadata = {}

    breakdown = []
    score = 0

    # Rule 1: Repo prioritization
    if repo in config.priority_repos:
        breakdown.append({"rule": "priority_repo", "effect": 0, "detail": f"{repo} is a priority repo"})
    else:
        score += config.non_priority_repo_penalty
        breakdown.append({
            "rule": "non_priority_repo",
            "effect": config.non_priority_repo_penalty,
            "detail": f"{repo} is not in priority repos",
        })

    # Rule 2: Done/Closed penalty
    status = str(project_fields.get("Status", "")).lower()
    github_state = str(metadata.get("github_state", "")).lower()

    if status == "done":
        score += config.done_penalty
        breakdown.append({"rule": "done_status", "effect": config.done_penalty, "detail": "Status is Done"})
    elif github_state == "closed":
        score += config.closed_penalty
        breakdown.append({"rule": "closed_state", "effect": config.closed_penalty, "detail": "GitHub state is closed"})
    else:
        breakdown.append({"rule": "open_status", "effect": 0, "detail": "Issue is open/active"})

    # Rule 3: Current iteration boost
    iteration = str(project_fields.get("Iteration", ""))
    if iteration == config.current_iteration:
        score += config.current_iteration_boost
        breakdown.append({
            "rule": "current_iteration",
            "effect": config.current_iteration_boost,
            "detail": f"In current iteration ({config.current_iteration})",
        })
    elif iteration:
        breakdown.append({"rule": "other_iteration", "effect": 0, "detail": f"In iteration {iteration}"})

    # Base priority
    priority_value = (
        project_fields.get("Priority")
        or project_fields.get("priority")
        or project_fields.get("P")
        or ""
    )
    base_priority = config.base_priority_map.get(str(priority_value).lower(), 0)
    if base_priority > 0:
        score += base_priority
        breakdown.append({
            "rule": "explicit_priority",
            "effect": base_priority,
            "detail": f"Priority field: {priority_value}",
        })

    # Context richness
    context = metadata.get("context", {})
    context_score = context.get("context_score", 0)
    if context_score > 0:
        context_boost = int(context_score * config.context_multiplier)
        score += context_boost
        comment_count = context.get("comment_count", 0)
        reference_count = context.get("reference_count", 0)
        has_parent = context.get("has_parent", False)
        breakdown.append({
            "rule": "context_richness",
            "effect": context_boost,
            "detail": f"{comment_count} comments, {reference_count} refs, parent: {has_parent}",
        })

    # PR activity penalty
    if context.get("has_active_pr"):
        score += config.active_pr_penalty
        open_pr_count = context.get("open_pr_count", 0)
        breakdown.append({
            "rule": "active_pr",
            "effect": config.active_pr_penalty,
            "detail": f"{open_pr_count} open PR(s) - work in progress",
        })
    elif context.get("has_merged_pr"):
        score += config.merged_pr_penalty
        merged_pr_count = context.get("merged_pr_count", 0)
        breakdown.append({
            "rule": "merged_pr",
            "effect": config.merged_pr_penalty,
            "detail": f"{merged_pr_count} merged PR(s) - likely resolved",
        })

    # Recency boost
    recency_boost = _calculate_recency_boost(metadata, config)
    if recency_boost > 0:
        score += recency_boost
        github_updated_at = metadata.get("github_updated_at", "")
        try:
            updated_at = datetime.fromisoformat(github_updated_at.replace("Z", "+00:00"))
            days_ago = (datetime.now(timezone.utc) - updated_at).days
            breakdown.append({
                "rule": "recency",
                "effect": recency_boost,
                "detail": f"Updated {days_ago} days ago",
            })
        except (ValueError, TypeError):
            pass

    return {
        "final_score": score,
        "breakdown": breakdown,
    }
