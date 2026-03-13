from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .config import Settings


class WordPressError(RuntimeError):
    """Raised when the WordPress API returns an unexpected response."""


@dataclass(frozen=True)
class MediaRecord:
    attachment_id: int
    date: str
    slug: str
    media_type: str
    mime_type: str
    source_url: str
    alt_text: str
    title: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "MediaRecord":
        return cls(
            attachment_id=payload["id"],
            date=payload.get("date", ""),
            slug=payload.get("slug", ""),
            media_type=payload.get("media_type", ""),
            mime_type=payload.get("mime_type", ""),
            source_url=payload.get("source_url", ""),
            alt_text=(payload.get("alt_text") or "").strip(),
            title=((payload.get("title") or {}).get("rendered") or "").strip(),
        )


class WordPressClient:
    def __init__(self, settings: Settings, timeout: int = 30) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.auth = (settings.wp_username, settings.wp_app_password)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 AltTextGenerator/0.1",
            }
        )
        self.timeout = timeout
        self._api_base_url: str | None = None

    def close(self) -> None:
        self.session.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{self._get_api_base_url()}/{path.lstrip('/')}"
        response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        if response.status_code >= 400:
            detail = self._error_detail(response)
            raise WordPressError(
                f"{method} {url} failed with {response.status_code}: {detail}"
            )
        return response

    def _get_api_base_url(self) -> str:
        if self._api_base_url:
            return self._api_base_url

        root_url = f"{self.settings.wp_site_url.rstrip('/')}/wp-json/"
        response = self.session.get(root_url, timeout=self.timeout)
        if response.status_code >= 400:
            detail = self._error_detail(response)
            raise WordPressError(
                f"GET {root_url} failed with {response.status_code}: {detail}"
            )

        resolved = response.url.rstrip("/")
        if not resolved.endswith("/wp-json"):
            raise WordPressError(
                f"Unexpected REST root URL resolved from {root_url}: {response.url}"
            )

        self._api_base_url = f"{resolved}/wp/v2"
        return self._api_base_url

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text.strip() or "Unknown error"
        if isinstance(payload, dict):
            return str(payload.get("message") or payload)
        return str(payload)

    def auth_check(self) -> dict[str, Any]:
        response = self._request("GET", "users/me")
        payload = response.json()
        return {
            "id": payload.get("id"),
            "name": payload.get("name"),
            "slug": payload.get("slug"),
            "roles": payload.get("roles", []),
        }

    def list_media(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        missing_alt_only: bool = False,
        media_type: str = "image",
    ) -> tuple[list[MediaRecord], dict[str, int | None]]:
        params = {
            "page": page,
            "per_page": per_page,
            "media_type": media_type,
            "_fields": "id,date,slug,media_type,mime_type,source_url,alt_text,title",
        }
        response = self._request("GET", "media", params=params)
        payload = response.json()
        records = [MediaRecord.from_api(item) for item in payload]
        if missing_alt_only:
            records = [record for record in records if not record.alt_text]

        headers = response.headers
        meta = {
            "total": _parse_int(headers.get("X-WP-Total")),
            "total_pages": _parse_int(headers.get("X-WP-TotalPages")),
            "page": page,
            "per_page": per_page,
        }
        return records, meta


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
