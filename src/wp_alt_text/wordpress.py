from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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


@dataclass(frozen=True)
class ContentRecord:
    content_id: int
    content_type: str
    status: str
    slug: str
    link: str
    title: str
    rendered_content: str
    public_html: str = ""

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "ContentRecord":
        return cls(
            content_id=payload["id"],
            content_type=payload.get("type", ""),
            status=payload.get("status", ""),
            slug=payload.get("slug", ""),
            link=payload.get("link", ""),
            title=((payload.get("title") or {}).get("rendered") or "").strip(),
            rendered_content=((payload.get("content") or {}).get("rendered") or ""),
        )


@dataclass(frozen=True)
class MediaContextMatch:
    content_id: int
    content_type: str
    status: str
    slug: str
    link: str
    title: str
    content_source: str
    match_reason: str
    snippet: str


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
    ) -> tuple[list[MediaRecord], dict[str, int | None | list[int]]]:
        records, meta = self._fetch_media_page(
            page=page,
            per_page=per_page,
            media_type=media_type,
        )
        if not missing_alt_only:
            return records, meta

        total_pages = meta["total_pages"] or page
        filtered_records = [record for record in records if not record.alt_text]
        pages_scanned = [page]
        source_records_examined = len(records)

        next_page = page + 1
        while len(filtered_records) < per_page and next_page <= total_pages:
            page_records, _ = self._fetch_media_page(
                page=next_page,
                per_page=per_page,
                media_type=media_type,
            )
            filtered_records.extend(record for record in page_records if not record.alt_text)
            source_records_examined += len(page_records)
            pages_scanned.append(next_page)
            next_page += 1

        meta = {
            **meta,
            "filtered": True,
            "source_pages_scanned": pages_scanned,
            "source_records_examined": source_records_examined,
        }
        return filtered_records[:per_page], meta

    def _fetch_media_page(
        self,
        *,
        page: int,
        per_page: int,
        media_type: str,
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

        headers = response.headers
        meta = {
            "total": _parse_int(headers.get("X-WP-Total")),
            "total_pages": _parse_int(headers.get("X-WP-TotalPages")),
            "page": page,
            "per_page": per_page,
        }
        return records, meta

    def list_content(
        self,
        *,
        endpoint: str,
        page: int = 1,
        per_page: int = 100,
        status: str = "publish",
    ) -> tuple[list[ContentRecord], dict[str, int | None]]:
        params = {
            "page": page,
            "per_page": per_page,
            "status": status,
            "_fields": "id,type,status,slug,link,title,content",
        }
        response = self._request("GET", endpoint, params=params)
        payload = response.json()
        records = [ContentRecord.from_api(item) for item in payload]

        headers = response.headers
        meta = {
            "total": _parse_int(headers.get("X-WP-Total")),
            "total_pages": _parse_int(headers.get("X-WP-TotalPages")),
            "page": page,
            "per_page": per_page,
        }
        return records, meta

    def collect_content(
        self,
        *,
        endpoints: tuple[str, ...] = ("posts", "pages"),
        per_page: int = 100,
        max_pages: int | None = None,
        status: str = "publish",
    ) -> tuple[list[ContentRecord], dict[str, Any]]:
        records: list[ContentRecord] = []
        endpoint_pages: dict[str, int] = {}
        endpoint_totals: dict[str, int | None] = {}
        public_html_fetched = 0
        public_html_failed = 0

        for endpoint in endpoints:
            page = 1
            while True:
                page_records, meta = self.list_content(
                    endpoint=endpoint,
                    page=page,
                    per_page=per_page,
                    status=status,
                )
                enriched_records: list[ContentRecord] = []
                for record in page_records:
                    public_html = self._fetch_public_html(record.link)
                    if public_html:
                        public_html_fetched += 1
                    elif record.link:
                        public_html_failed += 1
                    enriched_records.append(
                        ContentRecord(
                            content_id=record.content_id,
                            content_type=record.content_type,
                            status=record.status,
                            slug=record.slug,
                            link=record.link,
                            title=record.title,
                            rendered_content=record.rendered_content,
                            public_html=public_html,
                        )
                    )
                records.extend(enriched_records)
                endpoint_pages[endpoint] = page
                endpoint_totals[endpoint] = meta["total"]

                total_pages = meta["total_pages"] or 0
                reached_limit = max_pages is not None and page >= max_pages
                if reached_limit or page >= total_pages or not page_records:
                    break
                page += 1

        return records, {
            "endpoints": endpoints,
            "per_page": per_page,
            "max_pages": max_pages,
            "status": status,
            "pages_scanned": endpoint_pages,
            "totals": endpoint_totals,
            "content_items": len(records),
            "public_html_fetched": public_html_fetched,
            "public_html_failed": public_html_failed,
        }

    def match_media_to_content(
        self,
        media_records: list[MediaRecord],
        content_records: list[ContentRecord],
    ) -> dict[int, list[MediaContextMatch]]:
        matches: dict[int, list[MediaContextMatch]] = {}
        for media in media_records:
            media_matches: list[MediaContextMatch] = []
            for content in content_records:
                match = _match_media_in_content(media, content)
                if match:
                    media_matches.append(match)
            matches[media.attachment_id] = media_matches
        return matches

    def _fetch_public_html(self, url: str) -> str:
        if not url:
            return ""
        try:
            response = self.session.get(
                url,
                timeout=self.timeout,
                headers={"Accept": "text/html,application/xhtml+xml"},
            )
        except requests.RequestException:
            return ""

        if response.status_code >= 400:
            return ""
        if "text/html" not in response.headers.get("Content-Type", ""):
            return ""
        return response.text


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _match_media_in_content(
    media: MediaRecord,
    content: ContentRecord,
) -> MediaContextMatch | None:
    for content_source, body in (
        ("rendered_content", content.rendered_content or ""),
        ("public_html", content.public_html or ""),
    ):
        if not body:
            continue

        attachment_patterns = (
            re.compile(rf"\bwp-image-{media.attachment_id}\b"),
            re.compile(rf"\battachment[_-]{media.attachment_id}\b"),
            re.compile(rf"""data-(?:id|image-id|attachment-id)=["']{media.attachment_id}["']"""),
        )
        for pattern in attachment_patterns:
            match = pattern.search(body)
            if match:
                return MediaContextMatch(
                    content_id=content.content_id,
                    content_type=content.content_type,
                    status=content.status,
                    slug=content.slug,
                    link=content.link,
                    title=content.title,
                    content_source=content_source,
                    match_reason="attachment_id",
                    snippet=_extract_snippet(body, match.start()),
                )

        source_url = _normalize_url(media.source_url)
        if source_url:
            source_index = body.find(source_url)
            if source_index >= 0:
                return MediaContextMatch(
                    content_id=content.content_id,
                    content_type=content.content_type,
                    status=content.status,
                    slug=content.slug,
                    link=content.link,
                    title=content.title,
                    content_source=content_source,
                    match_reason="source_url",
                    snippet=_extract_snippet(body, source_index),
                )

    return None


def _extract_snippet(rendered: str, index: int, radius: int = 160) -> str:
    start = max(0, index - radius)
    end = min(len(rendered), index + radius)
    snippet = rendered[start:end]
    snippet = re.sub(r"<[^>]+>", " ", snippet)
    snippet = unescape(snippet)
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
