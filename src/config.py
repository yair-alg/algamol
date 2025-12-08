"""Configuration management for Algamol."""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import yaml
from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    path: str = "./data/algamol.db"


class SourceConfig(BaseModel):
    enabled: bool = True
    tier: int = 1
    rate_limit_per_second: float = 1.0
    email: Optional[str] = None
    mailto: Optional[str] = None


class PDFRetrievalConfig(BaseModel):
    enabled: bool = True
    unpaywall_email: str = "user@example.com"
    timeout_seconds: int = 30
    max_file_size_mb: int = 50
    user_agent: str = "Algamol/1.0"


class SearchDefaultsConfig(BaseModel):
    max_results_per_source: int = 100
    year_range_start: int = 2000
    year_range_end: int = 2025
    include_tier_3: bool = False


class RetryConfig(BaseModel):
    max_attempts: int = 3
    initial_wait_seconds: int = 2
    max_wait_seconds: int = 16


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "./data/algamol.log"


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class Config(BaseModel):
    data_dir: str = "./data"
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    sources: Dict[str, SourceConfig] = Field(default_factory=dict)
    pdf_retrieval: PDFRetrievalConfig = Field(default_factory=PDFRetrievalConfig)
    search_defaults: SearchDefaultsConfig = Field(default_factory=SearchDefaultsConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    api: APIConfig = Field(default_factory=APIConfig)

    @classmethod
    def from_yaml(cls, config_path: str = "config.yaml") -> "Config":
        """Load configuration from YAML file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        return cls(**data)

    def get_data_dir(self) -> Path:
        """Get the data directory as a Path object."""
        return Path(self.data_dir).resolve()

    def get_db_path(self) -> Path:
        """Get the database path as a Path object."""
        return Path(self.database.path).resolve()

    def ensure_directories(self):
        """Ensure all required directories exist."""
        data_dir = self.get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "papers").mkdir(parents=True, exist_ok=True)

        # Ensure log directory exists
        log_path = Path(self.logging.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)


# Global configuration instance
_config: Optional[Config] = None


def load_config(config_path: str = "config.yaml") -> Config:
    """Load and cache the global configuration."""
    global _config
    _config = Config.from_yaml(config_path)
    _config.ensure_directories()
    return _config


def get_config() -> Config:
    """Get the cached configuration, loading it if necessary."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
