"""The now-playing picture: blurred cover as backdrop, rounded cover art, big readable title."""

from __future__ import annotations

import asyncio
import io
import logging
import unicodedata
from collections import OrderedDict
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..api import Track

log = logging.getLogger("bot.card")

W, H = 1280, 720
ACCENT = (124, 92, 255)

FONT_DIRS = [
    Path(__file__).resolve().parents[2] / "assets" / "fonts",
    Path("/usr/share/fonts/truetype/google-fonts"),
    Path("/usr/share/fonts/truetype/poppins"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/freefont"),
    Path("/usr/share/fonts/truetype/wqy"),
    Path("/usr/share/fonts/opentype/noto"),
]
# preferred font files per script, best first
FONTS = {
    "latin": {True: ["Poppins-Bold.ttf", "NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
              False: ["Poppins-Medium.ttf", "NotoSans-Regular.ttf", "DejaVuSans.ttf"]},
    "indic": {True: ["Poppins-Bold.ttf", "NotoSansDevanagari-Bold.ttf"],
              False: ["Poppins-Medium.ttf", "NotoSansDevanagari-Regular.ttf"]},
    "cjk": {True: ["NotoSansCJK-Bold.ttc", "wqy-zenhei.ttc"], False: ["NotoSansCJK-Regular.ttc", "wqy-zenhei.ttc"]},
    "other": {True: ["NotoSans-Bold.ttf", "DejaVuSans-Bold.ttf"], False: ["NotoSans-Regular.ttf", "DejaVuSans.ttf"]},
}


def script_of(text: str) -> str:
    kind = "latin"
    for ch in text:
        o = ord(ch)
        if 0x0900 <= o <= 0x097F:  # Devanagari (Hindi, Marathi...)
            kind = "indic" if kind == "latin" else kind
        elif 0x3040 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF:
            return "cjk"
        elif o > 0x24F and not unicodedata.category(ch).startswith(("P", "S", "Z")):
            return "other"
    return kind


_font_cache: dict = {}


def load_font(size: int, bold: bool, text: str = "") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    script = script_of(text)
    key = (script, bold, size)
    if key in _font_cache:
        return _font_cache[key]
    font = None
    for name in FONTS[script][bold]:
        for d in FONT_DIRS:
            p = d / name
            if p.exists():
                try:
                    font = ImageFont.truetype(str(p), size)
                    break
                except OSError:
                    continue
        if font:
            break
    if font is None:
        try:
            font = ImageFont.load_default(size)
        except TypeError:  # very old Pillow
            font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def wrap(text: str, font, max_width: int, max_lines: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for i, w in enumerate(words):
        trial = f"{cur} {w}".strip()
        if font.getlength(trial) <= max_width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = w
        while font.getlength(cur) > max_width and len(cur) > 1:  # one huge word
            cut = len(cur)
            while cut > 1 and font.getlength(cur[:cut]) > max_width:
                cut -= 1
            lines.append(cur[:cut])
            cur = cur[cut:]
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    consumed = " ".join(lines)
    if len(lines) == max_lines and len(consumed) < len((text or "").strip()):
        last = lines[-1]
        while last and font.getlength(last + "…") > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines or [""]


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def _fallback_cover(seed: str) -> Image.Image:
    h = sum(ord(c) for c in seed) % 360
    img = Image.new("RGB", (640, 360))
    px = ImageDraw.Draw(img)
    for y in range(360):
        r = int(60 + 90 * y / 360)
        px.line([(0, y), (640, y)], fill=(r, 40 + (h % 80), 160 - int(60 * y / 360)))
    d = ImageDraw.Draw(img)
    d.ellipse([260, 100, 380, 220], outline=(255, 255, 255), width=8)
    d.polygon([(305, 130), (305, 190), (355, 160)], fill=(255, 255, 255))
    return img


def _crop_16x9(img: Image.Image) -> Image.Image:
    w, h = img.size
    target = 16 / 9
    if abs(w / h - 4 / 3) < 0.05:  # YouTube's 4:3 thumbnails have black bars above and below
        bar = int(h * 0.125)
        img = img.crop((0, bar, w, h - bar))
        w, h = img.size
    if w / h > target:
        nw = int(h * target)
        return img.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
    nh = int(w / target)
    return img.crop((0, (h - nh) // 2, w, (h + nh) // 2))


def compose(track: Track, cover: Image.Image | None, bot_name: str = "Shubh Music", requested_by: str = "") -> bytes:
    cover = _crop_16x9((cover or _fallback_cover(track.id)).convert("RGB"))
    bg = ImageOps.fit(cover, (W, H)).filter(ImageFilter.GaussianBlur(38))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (10, 10, 18)), 0.62)
    canvas = bg.convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for x in range(W):  # darker toward the right so text stays readable
        sd.line([(x, 0), (x, H)], fill=(0, 0, 0, int(110 * x / W)))
    canvas = Image.alpha_composite(canvas, shade)

    art_w, art_h = 560, 315
    art = _rounded(cover.resize((art_w, art_h), Image.LANCZOS), 28)
    x0, y0 = 70, (H - art_h) // 2 - 10
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).rounded_rectangle([x0 - 4, y0 + 18, x0 + art_w + 4, y0 + art_h + 30], 34, fill=(0, 0, 0, 170))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(26)))
    canvas.alpha_composite(art, (x0, y0))

    d = ImageDraw.Draw(canvas)
    tx = x0 + art_w + 60
    tw = W - tx - 60
    label_font = load_font(26, True, "NOW PLAYING")
    d.rounded_rectangle([tx, 150, tx + 232, 192], 21, fill=ACCENT + (255,))
    d.text((tx + 22, 156), "NOW PLAYING", font=label_font, fill=(255, 255, 255))

    title_font = load_font(52, True, track.title)
    y = 224
    for line in wrap(track.title, title_font, tw, 3):
        d.text((tx, y), line, font=title_font, fill=(255, 255, 255))
        y += 70
    chan_font = load_font(32, False, track.channel)
    d.text((tx, y + 8), wrap(track.channel or "Unknown artist", chan_font, tw, 1)[0], font=chan_font, fill=(205, 205, 220))

    info_font = load_font(28, False, "0123")
    dur = _fmt(track.duration) if track.duration else "LIVE"
    chips = [dur, "VIDEO" if track.video else "AUDIO"]
    cx, cy = tx, y + 78
    for chip in chips:
        wchip = int(info_font.getlength(chip)) + 40
        d.rounded_rectangle([cx, cy, cx + wchip, cy + 46], 23, outline=(255, 255, 255, 150), width=2)
        d.text((cx + 20, cy + 6), chip, font=info_font, fill=(255, 255, 255))
        cx += wchip + 16
    if requested_by:
        rf = load_font(26, False, requested_by)
        d.text((tx, cy + 70), "Requested by " + wrap(requested_by, rf, tw - 200, 1)[0], font=rf, fill=(170, 170, 190))

    brand = load_font(28, True, bot_name)
    bw = int(brand.getlength(bot_name))
    d.text((W - bw - 56, H - 66), bot_name, font=brand, fill=(255, 255, 255, 220))
    d.ellipse([W - bw - 90, H - 56, W - bw - 70, H - 36], fill=ACCENT + (255,))

    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


def _fmt(seconds: int) -> str:
    h, rem = divmod(max(0, int(seconds)), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class CardMaker:
    """Downloads the cover (never fatal), renders in a thread, keeps the last renders in memory."""

    def __init__(self, bot_name: str, http: httpx.AsyncClient | None = None, cache_size: int = 64):
        self.bot_name = bot_name
        self.http = http or httpx.AsyncClient(timeout=10, follow_redirects=True, trust_env=False)
        self._own = http is None
        self._cache: OrderedDict[tuple, bytes] = OrderedDict()
        self._size = cache_size

    async def close(self) -> None:
        if self._own:
            await self.http.aclose()

    async def _cover(self, url: str) -> Image.Image | None:
        if not url.startswith("https://"):
            return None
        try:
            r = await self.http.get(url)
            if r.status_code != 200 or len(r.content) > 8_000_000:
                return None
            img = Image.open(io.BytesIO(r.content))
            img.load()
            return img
        except Exception as e:
            log.info("cover download failed (%s): %s", url, e)
            return None

    async def make(self, track: Track, requested_by: str = "") -> bytes | None:
        key = (track.id, track.video, requested_by, self.bot_name)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        try:
            cover = await self._cover(track.thumbnail)
            data = await asyncio.get_running_loop().run_in_executor(None, compose, track, cover, self.bot_name, requested_by)
        except Exception:
            log.exception("card rendering failed")
            return None
        self._cache[key] = data
        while len(self._cache) > self._size:
            self._cache.popitem(last=False)
        return data
