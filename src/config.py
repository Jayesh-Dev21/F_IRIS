"""Configuration management for IRIS Security Agent."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class CameraConfig(BaseModel):
    """Camera configuration."""

    device_id: int = 0
    fps: int = 30
    resolution: list[int] = [1280, 720]
    flip_horizontal: bool = False
    warmup_frames: int = 30


class MonitoringConfig(BaseModel):
    """Monitoring configuration."""

    active: bool = True
    motion_threshold: int = 25
    min_motion_area: int = 500
    cooldown_seconds: int = 5


class IntelligenceConfig(BaseModel):
    """LLM intelligence configuration."""

    provider: str = "openai"
    model: str = "gpt-4o"
    max_tokens: int = 300
    temperature: float = 0.3
    include_recent_context: bool = True
    context_window: int = 5


class TelegramConfig(BaseModel):
    """Telegram alert configuration."""

    enabled: bool = True
    alert_on_threat_level: str = "medium"
    include_snapshot: bool = True


class AlertsConfig(BaseModel):
    """Alerts configuration."""

    enabled: bool = True
    telegram: TelegramConfig = TelegramConfig()


class StorageConfig(BaseModel):
    """Storage configuration."""

    db_path: str = "data/events.db"
    snapshots_dir: str = "data/snapshots"
    max_snapshot_age_days: int = 30
    snapshot_quality: int = 85


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    file: str = "data/iris.log"
    console: bool = True


class Settings(BaseSettings):
    """Main settings class."""

    # API Keys from environment
    openai_api_key: Optional[str] = Field(None, alias="OPENAI_API_KEY")
    telegram_bot_token: Optional[str] = Field(None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, alias="TELEGRAM_CHAT_ID")
    anthropic_api_key: Optional[str] = Field(None, alias="ANTHROPIC_API_KEY")

    # Configuration sections
    camera: CameraConfig = CameraConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    intelligence: IntelligenceConfig = IntelligenceConfig()
    alerts: AlertsConfig = AlertsConfig()
    storage: StorageConfig = StorageConfig()
    logging: LoggingConfig = LoggingConfig()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def load_settings(config_path: Optional[str] = None) -> Settings:
    """
    Load settings from YAML config and environment variables.

    Args:
        config_path: Path to YAML config file. Defaults to config/settings.yaml

    Returns:
        Settings object with loaded configuration
    """
    if config_path is None:
        config_path = os.getenv("CONFIG_PATH", "config/settings.yaml")

    config_file = Path(config_path)

    # Load YAML config if it exists
    config_data = {}
    if config_file.exists():
        with open(config_file, "r") as f:
            config_data = yaml.safe_load(f) or {}

    # Create settings, environment variables will override YAML
    settings = Settings(**config_data)

    return settings


def get_prompt(prompt_name: str = "security") -> str:
    """
    Load a prompt template from the prompts directory.

    Args:
        prompt_name: Name of the prompt file (without .txt extension)

    Returns:
        Prompt text as string
    """
    prompt_path = Path(f"config/prompts/{prompt_name}.txt")

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    with open(prompt_path, "r") as f:
        return f.read().strip()


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
