"""Client for your own YouTube API (Yt-paid-api-bot). No YouTube API key and no third-party service."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx


class APIError(Exception):
    def __init__(self, message: str, code: str = "api_error", status: int = 0, **extra):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.extra = extra


class InvalidAPIKey(APIError):
    """The key is wrong, revoked or missing."""


class DailyLimitReached(APIError):
    """The API key used up its songs for today."""

    @property
    def retry_after(self) -> int:
        return int(self.extra.get("retry_after") or 0)


class NotFound(APIError):
    """Nothing matched the search / the video cannot be played."""


class Unavailable(APIError):
    """The API (or YouTube behind it) is temporarily not answering."""


@dataclass
class Track:
    id: str
    title: str
    duration: int = 0
    thumbnail: str = ""
    channel: str = ""
    link: str = ""
    requested_by: int = 0
    requested_name: str = ""
    video: bool = False

    @classmethod
    def from_api(cls, d: dict) -> "Track":
        vid = str(d.get("id") or "")
        return cls(
            id=vid,
            title=str(d.get("title") or "Unknown title"),
            duration=int(d.get("duration") or 0),
            thumbnail=str(d.get("thumbnail") or (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else "")),
            channel=str(d.get("channel") or ""),
            link=str(d.get("link") or (f"https://www.youtube.com/watch?v={vid}" if vid else "")),
        )


@dataclass
class Stream:
    track: Track
    url: str
    used_today: int = 0
    remaining_today: int = 0
    daily_limit: int = 0
    plan: str = ""
    counted: bool = True


@dataclass
class Usage:
    plan: str = "free"
    daily_limit: int = 0
    used_today: int = 0
    remaining_today: int = 0
    plan_expires_at: str | None = None
    raw: dict = field(default_factory=dict)


class YouTubeAPI:
    """Thin async wrapper. One instance per bot."""

    def __init__(self, base_url: str, api_key: str, *, client: httpx.AsyncClient | None = None, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._own = client is None
        self.http = client or httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=10.0),
            follow_redirects=True,
            trust_env=False,
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )

    async def close(self) -> None:
        if self._own:
            await self.http.aclose()

    # ── plumbing ──────────────────────────────────────────────────────────
    async def _get(self, path: str, params: dict | None = None, *, retries: int = 1) -> dict:
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = await self.http.get(
                    self.base_url + path,
                    params={k: v for k, v in (params or {}).items() if v is not None},
                    headers={"X-API-Key": self.api_key, "Accept": "application/json"},
                )
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = e
                if attempt < retries:
                    await asyncio.sleep(0.8)
                    continue
                raise Unavailable("The music server is not reachable right now.", "unreachable") from e
            if r.status_code in (502, 503, 504) and attempt < retries:
                await asyncio.sleep(0.8)
                continue
            return self._parse(r)
        raise Unavailable("The music server is not reachable right now.", "unreachable") from last

    @staticmethod
    def _parse(r: httpx.Response) -> dict:
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code < 400 and isinstance(body, dict):
            return body
        code = str(body.get("error") or "api_error") if isinstance(body, dict) else "api_error"
        msg = str(body.get("message") or f"The API answered HTTP {r.status_code}.") if isinstance(body, dict) else "Bad answer."
        extra = {k: v for k, v in body.items() if k not in ("error", "message")} if isinstance(body, dict) else {}
        if r.status_code == 429 and code == "daily_limit_reached":
            extra["retry_after"] = r.headers.get("retry-after") or 0
            raise DailyLimitReached(msg, code, 429, **extra)
        if r.status_code == 429:
            raise Unavailable("The music server is busy, try again in a moment.", code, 429, **extra)
        if r.status_code == 401:
            raise InvalidAPIKey("The bot's API key is invalid or revoked. Tell the bot owner.", code, 401)
        if r.status_code in (404, 422):
            raise NotFound(msg, code, r.status_code, **extra)
        raise Unavailable(msg, code, r.status_code, **extra)

    # ── endpoints ─────────────────────────────────────────────────────────
    async def search(self, query: str, limit: int = 5) -> list[Track]:
        data = await self._get("/v1/search", {"q": query, "limit": limit})
        return [Track.from_api(x) for x in data.get("results") or [] if x.get("id")]

    async def track(self, ref: str) -> Track:
        """Metadata only. Does NOT use up a song of the daily limit."""
        data = await self._get("/v1/track", {"q": ref})
        return Track.from_api(data)

    async def track_by_id(self, video_id: str) -> Track:
        data = await self._get("/v1/track", {"id": video_id})
        return Track.from_api(data)

    async def playlist(self, ref: str, limit: int = 25) -> tuple[str, list[Track]]:
        data = await self._get("/v1/playlist", {"url": ref, "limit": limit})
        return str(data.get("title") or "Playlist"), [Track.from_api(x) for x in data.get("tracks") or [] if x.get("id")]

    async def play(self, video_id: str, *, video: bool = False) -> Stream:
        """Resolve a stream link. This is the call that counts toward the daily limit."""
        data = await self._get("/v1/play", {"id": video_id, "type": "video" if video else "audio"}, retries=1)
        url = data.get("stream_url")
        if not url:
            raise Unavailable("The API did not return a stream link.", "no_stream")
        usage = data.get("usage") or {}
        return Stream(
            track=Track.from_api(data),
            url=str(url),
            used_today=int(usage.get("used_today") or 0),
            remaining_today=int(usage.get("remaining_today") or 0),
            daily_limit=int(usage.get("daily_limit") or 0),
            plan=str(usage.get("plan") or ""),
            counted=bool(data.get("counted", True)),
        )

    async def usage(self) -> Usage:
        data = await self._get("/v1/me")
        u, k = data.get("usage") or {}, data.get("key") or {}
        return Usage(
            plan=str(u.get("plan") or k.get("plan") or "free"),
            daily_limit=int(u.get("daily_limit") or 0),
            used_today=int(u.get("used_today") or 0),
            remaining_today=int(u.get("remaining_today") or 0),
            plan_expires_at=k.get("plan_expires_at"),
            raw=data,
        )

    async def health(self) -> bool:
        try:
            r = await self.http.get(self.base_url + "/health", timeout=10)
            return r.status_code == 200
        except httpx.HTTPError:
            return False
