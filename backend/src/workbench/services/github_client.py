"""GitHub GraphQL client for Projects V2 API."""

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

GITHUB_GRAPHQL_ENDPOINT = "https://api.github.com/graphql"


@dataclass
class IssueContext:
    """Additional context for an issue."""

    comments: list[dict[str, Any]] = field(default_factory=list)
    referenced_issues: list[dict[str, Any]] = field(default_factory=list)
    referenced_prs: list[dict[str, Any]] = field(default_factory=list)
    parent_issue: dict[str, Any] | None = None
    comment_count: int = 0
    reference_count: int = 0
    # PR activity tracking
    open_pr_count: int = 0
    merged_pr_count: int = 0
    closed_pr_count: int = 0

    @property
    def has_active_pr(self) -> bool:
        """Check if there's an open PR for this issue."""
        return self.open_pr_count > 0

    @property
    def has_merged_pr(self) -> bool:
        """Check if there's a merged PR for this issue."""
        return self.merged_pr_count > 0

    @property
    def context_score(self) -> int:
        """Calculate a context richness score."""
        score = 0
        # Each comment adds context
        score += min(self.comment_count * 10, 50)  # Cap at 50 for comments
        # Each reference adds context
        score += min(self.reference_count * 15, 45)  # Cap at 45 for references
        # Having a parent issue adds context
        if self.parent_issue:
            score += 20
        return score


@dataclass
class ProjectItem:
    """Represents an item from a GitHub Project V2."""

    node_id: str
    content_type: str  # "Issue", "PullRequest", "DraftIssue"
    issue_number: int | None
    issue_node_id: str | None
    repo_owner: str | None
    repo_name: str | None
    title: str
    body: str | None
    state: str | None  # "OPEN", "CLOSED"
    url: str | None
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    field_values: dict[str, Any] = field(default_factory=dict)
    context: IssueContext = field(default_factory=IssueContext)


@dataclass
class ProjectInfo:
    """Metadata about a GitHub Project."""

    id: str
    number: int
    title: str
    url: str
    owner_type: str  # "organization" or "user"
    owner_login: str
    fields: list[dict[str, Any]] = field(default_factory=list)


class GitHubAPIError(Exception):
    """Error from GitHub GraphQL API."""

    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__(f"GitHub API errors: {'; '.join(messages)}")


class GitHubGraphQLClient:
    """Client for GitHub GraphQL API with Projects V2 support."""

    def __init__(self, token: str):
        self.token = token
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GitHubGraphQLClient":
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=60.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def _execute(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL query."""
        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        response = await self._client.post(
            GITHUB_GRAPHQL_ENDPOINT,
            json={"query": query, "variables": variables or {}},
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            raise GitHubAPIError(data["errors"])

        return data.get("data", {})

    async def get_organization_project(
        self,
        org: str,
        project_number: int,
    ) -> ProjectInfo:
        """Fetch project metadata including custom field definitions."""
        query = """
        query GetProject($org: String!, $number: Int!) {
          organization(login: $org) {
            projectV2(number: $number) {
              id
              number
              title
              url
              fields(first: 50) {
                nodes {
                  ... on ProjectV2Field {
                    id
                    name
                    dataType
                  }
                  ... on ProjectV2SingleSelectField {
                    id
                    name
                    dataType
                    options {
                      id
                      name
                    }
                  }
                  ... on ProjectV2IterationField {
                    id
                    name
                    dataType
                  }
                }
              }
            }
          }
        }
        """

        data = await self._execute(query, {"org": org, "number": project_number})

        project_data = data.get("organization", {}).get("projectV2")
        if not project_data:
            raise GitHubAPIError(
                [{"message": f"Project {project_number} not found in organization {org}"}]
            )

        return ProjectInfo(
            id=project_data["id"],
            number=project_data["number"],
            title=project_data["title"],
            url=project_data["url"],
            owner_type="organization",
            owner_login=org,
            fields=project_data.get("fields", {}).get("nodes", []),
        )

    async def get_project_items(
        self,
        project_id: str,
        after_cursor: str | None = None,
        page_size: int = 100,
    ) -> tuple[list[ProjectItem], str | None, bool]:
        """
        Fetch items from a project with pagination.

        Returns: (items, next_cursor, has_more)
        """
        query = """
        query GetProjectItems($projectId: ID!, $after: String, $first: Int!) {
          node(id: $projectId) {
            ... on ProjectV2 {
              items(first: $first, after: $after) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  id
                  fieldValues(first: 20) {
                    nodes {
                      ... on ProjectV2ItemFieldTextValue {
                        text
                        field { ... on ProjectV2Field { name } }
                      }
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        field { ... on ProjectV2SingleSelectField { name } }
                      }
                      ... on ProjectV2ItemFieldNumberValue {
                        number
                        field { ... on ProjectV2Field { name } }
                      }
                      ... on ProjectV2ItemFieldDateValue {
                        date
                        field { ... on ProjectV2Field { name } }
                      }
                      ... on ProjectV2ItemFieldIterationValue {
                        title
                        field { ... on ProjectV2IterationField { name } }
                      }
                    }
                  }
                  content {
                    ... on Issue {
                      id
                      number
                      title
                      body
                      state
                      url
                      repository {
                        owner { login }
                        name
                      }
                      labels(first: 20) {
                        nodes { name }
                      }
                      assignees(first: 10) {
                        nodes { login }
                      }
                      createdAt
                      updatedAt
                      comments(first: 10) {
                        totalCount
                        nodes {
                          body
                          author { login }
                          createdAt
                        }
                      }
                      timelineItems(first: 20, itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT, MARKED_AS_DUPLICATE_EVENT]) {
                        nodes {
                          ... on CrossReferencedEvent {
                            source {
                              __typename
                              ... on Issue {
                                number
                                title
                                state
                                repository { nameWithOwner }
                              }
                              ... on PullRequest {
                                number
                                title
                                state
                                repository { nameWithOwner }
                              }
                            }
                          }
                          ... on ConnectedEvent {
                            subject {
                              __typename
                              ... on Issue {
                                number
                                title
                                repository { nameWithOwner }
                              }
                            }
                          }
                        }
                      }
                      trackedInIssues(first: 5) {
                        nodes {
                          number
                          title
                          state
                          repository { nameWithOwner }
                        }
                      }
                    }
                    ... on PullRequest {
                      id
                      number
                      title
                      body
                      state
                      url
                      repository {
                        owner { login }
                        name
                      }
                      createdAt
                      updatedAt
                    }
                    ... on DraftIssue {
                      title
                      body
                      createdAt
                      updatedAt
                    }
                  }
                }
              }
            }
          }
        }
        """

        data = await self._execute(
            query,
            {"projectId": project_id, "after": after_cursor, "first": page_size},
        )

        node = data.get("node", {})
        items_data = node.get("items", {})
        page_info = items_data.get("pageInfo", {})
        nodes = items_data.get("nodes", [])

        items = []
        for node_item in nodes:
            item = self._parse_project_item(node_item)
            if item:
                items.append(item)

        return (
            items,
            page_info.get("endCursor"),
            page_info.get("hasNextPage", False),
        )

    def _parse_project_item(self, node: dict[str, Any]) -> ProjectItem | None:
        """Parse a project item node from GraphQL response."""
        content = node.get("content")
        if not content:
            return None

        # Determine content type
        if "number" in content and "repository" in content:
            if "state" in content:
                content_type = "Issue" if content.get("state") in ("OPEN", "CLOSED") else "PullRequest"
            else:
                content_type = "Issue"
        elif "number" in content:
            content_type = "PullRequest"
        else:
            content_type = "DraftIssue"

        # Extract repository info
        repo = content.get("repository", {})
        repo_owner = repo.get("owner", {}).get("login")
        repo_name = repo.get("name")

        # Extract labels
        labels = [
            label["name"]
            for label in content.get("labels", {}).get("nodes", [])
            if label and "name" in label
        ]

        # Extract assignees
        assignees = [
            assignee["login"]
            for assignee in content.get("assignees", {}).get("nodes", [])
            if assignee and "login" in assignee
        ]

        # Parse field values
        field_values = {}
        for fv in node.get("fieldValues", {}).get("nodes", []):
            if not fv:
                continue
            field_name = fv.get("field", {}).get("name")
            if not field_name:
                continue

            # Extract value based on type
            if "text" in fv:
                field_values[field_name] = fv["text"]
            elif "name" in fv:
                field_values[field_name] = fv["name"]
            elif "number" in fv:
                field_values[field_name] = fv["number"]
            elif "date" in fv:
                field_values[field_name] = fv["date"]
            elif "title" in fv:
                field_values[field_name] = fv["title"]

        # Parse context for issues
        context = self._parse_issue_context(content) if content_type == "Issue" else IssueContext()

        return ProjectItem(
            node_id=node["id"],
            content_type=content_type,
            issue_number=content.get("number"),
            issue_node_id=content.get("id"),
            repo_owner=repo_owner,
            repo_name=repo_name,
            title=content.get("title", ""),
            body=content.get("body"),
            state=content.get("state"),
            url=content.get("url"),
            labels=labels,
            assignees=assignees,
            created_at=content.get("createdAt"),
            updated_at=content.get("updatedAt"),
            field_values=field_values,
            context=context,
        )

    def _parse_issue_context(self, content: dict[str, Any]) -> IssueContext:
        """Parse context information from issue content."""
        # Parse comments
        comments_data = content.get("comments", {})
        comment_count = comments_data.get("totalCount", 0)
        comments = [
            {
                "body": c.get("body", "")[:500],  # Truncate long comments
                "author": c.get("author", {}).get("login"),
                "created_at": c.get("createdAt"),
            }
            for c in comments_data.get("nodes", [])
            if c
        ]

        # Parse timeline items for cross-references
        referenced_issues = []
        referenced_prs = []
        open_pr_count = 0
        merged_pr_count = 0
        closed_pr_count = 0
        timeline_items = content.get("timelineItems", {}).get("nodes", [])

        for item in timeline_items:
            if not item:
                continue

            # Handle CrossReferencedEvent
            source = item.get("source", {})
            if source:
                source_type = source.get("__typename")
                state = source.get("state")
                ref_data = {
                    "number": source.get("number"),
                    "title": source.get("title"),
                    "state": state,
                    "repo": source.get("repository", {}).get("nameWithOwner"),
                    "type": source_type,
                }
                # Use __typename to distinguish PRs from issues
                if source_type == "PullRequest":
                    referenced_prs.append(ref_data)
                    if state == "OPEN":
                        open_pr_count += 1
                    elif state == "MERGED":
                        merged_pr_count += 1
                    elif state == "CLOSED":
                        closed_pr_count += 1
                elif source_type == "Issue":
                    referenced_issues.append(ref_data)

            # Handle ConnectedEvent (parent/child relationships)
            subject = item.get("subject", {})
            if subject and subject.get("number"):
                ref_data = {
                    "number": subject.get("number"),
                    "title": subject.get("title"),
                    "repo": subject.get("repository", {}).get("nameWithOwner"),
                }
                referenced_issues.append(ref_data)

        # Parse parent issues (trackedInIssues)
        parent_issue = None
        tracked_in = content.get("trackedInIssues", {}).get("nodes", [])
        if tracked_in:
            first_parent = tracked_in[0]
            if first_parent:
                parent_issue = {
                    "number": first_parent.get("number"),
                    "title": first_parent.get("title"),
                    "state": first_parent.get("state"),
                    "repo": first_parent.get("repository", {}).get("nameWithOwner"),
                }

        return IssueContext(
            comments=comments,
            referenced_issues=referenced_issues,
            referenced_prs=referenced_prs,
            parent_issue=parent_issue,
            comment_count=comment_count,
            reference_count=len(referenced_issues) + len(referenced_prs),
            open_pr_count=open_pr_count,
            merged_pr_count=merged_pr_count,
            closed_pr_count=closed_pr_count,
        )

    async def iter_all_project_items(
        self,
        project_id: str,
        page_size: int = 100,
    ) -> AsyncIterator[ProjectItem]:
        """Iterate over all project items with automatic pagination."""
        cursor = None
        while True:
            items, cursor, has_more = await self.get_project_items(
                project_id, after_cursor=cursor, page_size=page_size
            )
            for item in items:
                yield item
            if not has_more:
                break
