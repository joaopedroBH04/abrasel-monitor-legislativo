"""Configuracoes centrais do Abrasel Monitor Legislativo."""

from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # AWS
    aws_region: str = "sa-east-1"
    s3_bucket_bronze: str = "abrasel-monitor-bronze"
    s3_bucket_silver: str = "abrasel-monitor-silver"

    # Database
    database_url: str = "postgresql+asyncpg://abrasel:abrasel@localhost:5432/monitor_legislativo"

    # DynamoDB
    dynamodb_table_checkpoints: str = "abrasel-monitor-checkpoints"

    # Alertas
    slack_webhook_url: str = ""
    slack_channel: str = "#monitor-legislativo"
    ses_sender_email: str = "monitor@abrasel.com.br"
    ses_recipient_emails: str = "relacoes.institucionais@abrasel.com.br"

    # Rate Limiting (requests por segundo)
    camara_rate_limit_rps: float = 1.0
    senado_rate_limit_rps: float = 1.0
    assembleia_rate_limit_rps: float = 0.5

    # Configuracao
    keywords_config_path: str = "config/keywords.yaml"
    log_level: str = "INFO"

    # MCP Brasil
    anthropic_api_key: str = ""
    mcp_brasil_tool_search: str = "bm25"

    # Timeouts
    http_timeout_seconds: int = 30
    http_max_retries: int = 3

    # Scoring
    score_keyword_primary: int = 3
    score_keyword_secondary: int = 1
    score_theme: int = 2
    score_allied_author: int = 2
    score_threshold_high: int = 5
    score_threshold_medium: int = 3
    score_threshold_low: int = 1

    # Alertas timing
    alert_voting_window_hours: int = 72

    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent.parent

    @property
    def ses_recipients_list(self) -> list[str]:
        return [e.strip() for e in self.ses_recipient_emails.split(",") if e.strip()]


settings = Settings()
