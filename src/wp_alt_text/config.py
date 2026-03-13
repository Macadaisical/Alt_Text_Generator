from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    wp_site_url: str
    wp_username: str
    wp_app_password: str

    @property
    def api_base_url(self) -> str:
        return f"{self.wp_site_url.rstrip('/')}/wp-json/wp/v2"


@dataclass(frozen=True)
class OpenAISettings:
    openai_api_key: str
    openai_model: str = "gpt-4.1-mini"


def load_settings(env_path: Path | None = None) -> Settings:
    root = Path.cwd()
    resolved_env = env_path or (root / ".env")
    load_dotenv(resolved_env)

    site_url = os.getenv("WP_SITE_URL", "").strip()
    username = os.getenv("WP_USERNAME", "").strip()
    app_password = os.getenv("WP_APP_PASSWORD", "").strip()

    missing = [
        name
        for name, value in (
            ("WP_SITE_URL", site_url),
            ("WP_USERNAME", username),
            ("WP_APP_PASSWORD", app_password),
        )
        if not value
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing required environment variables: {joined}")

    return Settings(
        wp_site_url=site_url,
        wp_username=username,
        wp_app_password=app_password,
    )


def load_openai_settings(env_path: Path | None = None) -> OpenAISettings:
    root = Path.cwd()
    resolved_env = env_path or (root / ".env")
    load_dotenv(resolved_env)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip() or "gpt-4.1-mini"

    if not api_key:
        raise ValueError("Missing required environment variable: OPENAI_API_KEY")

    return OpenAISettings(
        openai_api_key=api_key,
        openai_model=model,
    )
