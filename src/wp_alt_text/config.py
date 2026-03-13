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
