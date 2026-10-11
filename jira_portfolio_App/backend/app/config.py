from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_name: str = "Jira Executive Portfolio Intelligence"
    database_url: str = "sqlite:///./jira_portfolio.db"
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = Field(default=None, repr=False)
    jira_max_retries: int = 3
    jira_timeout_seconds: float = 20
    cors_origins: list[str] = ["http://localhost:5173"]
    log_level: str = "INFO"

    @field_validator("jira_base_url")
    @classmethod
    def normalize_url(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def jira_is_configured(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
