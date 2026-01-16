"""Application configuration using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://workbench:workbench@localhost:5432/workbench"

    # GitHub
    github_pat: str = ""

    # Worker
    worker_poll_interval_seconds: int = 5
    worker_tmpdir_base: str = "/tmp/workbench-attempts"

    # Claude Code
    claude_code_path: str = "claude"
    claude_default_max_turns: int = 50
    claude_default_timeout_seconds: int = 1200  # 20 minutes
    # Mock mode for testing: "complete", "waiting", "error", or empty for real execution
    claude_mock_scenario: str = ""

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def async_database_url(self) -> str:
        """Convert database URL to async version."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
