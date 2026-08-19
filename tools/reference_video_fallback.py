#!/usr/bin/env python3
"""Fetch public YouTube reference video through federated frontends.

This is a fallback for environments where YouTube blocks datacenter IPs.
It never executes downloaded content. It only retrieves JSON metadata,
progressive media bytes, and optional English captions into a working folder.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"

PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.tokhmi.xyz",
    "https://pipedapi.moomoo.me",
    "https://pipedapi.syncpundit.io",
    "https://api-piped.mha.fi",
    "https://piped-api.garudalinux.org",
    "https://pipedapi.rivo.lol",
]

INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yt.chocolatemoo53.com",
]


def video_id_from_url(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    if "youtu.be" in host:
        candidate = parsed.path.strip("/").split("/")[0]
    elif "youtube.com" in host:
        if parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
            parts = [p for p in parsed.path.split("/") if p]
            candidate = parts[1] if len(parts) > 1 else ""
        else:
            from urllib.parse import parse_qs
            candidate = parse_qs(parsed.query).get("v", [""])[0]
    else:
        candidate = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        raise ValueError(f"Could not extract a YouTube video ID from: {value}")
    return candidate


def get_json(url: str, timeout: float = 20.0) -> dict:
    req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return json.loads(r.read().decode("utf-8", "replace"))


def download(url: str, dest: Path, timeout: float = 40.0) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    total = 0
    with urlopen(req, timeout=timeout) as r, dest.open("wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    if total < 100_000:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file is suspiciously small ({total} bytes)")
    return total


def height_of(stream: dict) -> int:
    value = stream.get("height")
    if isinstance(value, int):
        return value
    quality = str(stream.get("quality") or stream.get("qualityLabel") or "")
    m = re.search(r"(\d{3,4})p", quality)
    return int(m.group(1)) if m else 0


def select_progressive(streams: list[dict]) -> dict | None:
    candidates = []
    for s in streams or []:
        if s.get("videoOnly") is True:
            continue
        mime = str(s.get("mimeType") or s.get("type") or "").lower()
        fmt = str(s.get("format") or "").lower()
        if "video/mp4" not in mime and "mpeg_4" not in fmt and "mp4" not in fmt:
            continue
        if not s.get("url"):
            continue
        h = height_of(s)
        # Prefer <=720p for analysis reliability, then the highest available.
        score = (1 if 0 < h <= 720 else 0, min(h, 2160))
        candidates.append((score, s))
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def save_caption(url: str, dest: Path) -> None:
    try:
        req = Request(url, headers={"User-Agent": UA, "Accept": "text/vtt,text/plain,*/*"})
        with urlopen(req, timeout=20) as r:
            data = r.read()
        if data:
            dest.write_bytes(data)
    except Exception as exc:
        print(f"caption warning: {exc}", file=sys.stderr)


def try_piped(video_id: str, out: Path) -> bool:
    for api in PIPED_INSTANCES:
        try:
            print(f"Piped: {api}", flush=True)
            data = get_json(f"{api}/streams/{video_id}")
            stream = select_progressive(data.get("videoStreams", []))
            if not stream:
                raise RuntimeError("no progressive MP4 stream")
            stream_url = str(stream["url"])
            if stream_url.startswith("/"):
                stream_url = urljoin(str(data.get("proxyUrl") or api), stream_url)
            size = download(stream_url, out / "source.mp4")
            (out / "federated-info.json").write_text(
                json.dumps({"provider": "piped", "api": api, "stream": stream, "metadata": data}, indent=2),
                encoding="utf-8",
            )
            for cap in data.get("subtitles", []) or []:
                code = str(cap.get("code") or cap.get("languageCode") or "").lower()
                if code.startswith("en") and cap.get("url"):
                    cap_url = str(cap["url"])
                    if cap_url.startswith("/"):
                        cap_url = urljoin(str(data.get("proxyUrl") or api), cap_url)
                    save_caption(cap_url, out / "source.en.vtt")
                    break
            print(f"Piped success: {api} ({size} bytes)", flush=True)
            return True
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            print(f"Piped failed: {api}: {exc}", file=sys.stderr, flush=True)
            time.sleep(0.2)
    return False


def try_invidious(video_id: str, out: Path) -> bool:
    for api in INVIDIOUS_INSTANCES:
        try:
            print(f"Invidious: {api}", flush=True)
            data = get_json(f"{api}/api/v1/videos/{video_id}")
            streams = data.get("formatStreams", []) or []
            stream = select_progressive(streams)
            if not stream:
                # Invidious formatStreams are progressive by definition on many instances;
                # be less strict if the instance omits mime metadata.
                usable = [s for s in streams if s.get("url")]
                if usable:
                    stream = max(usable, key=height_of)
            if not stream:
                raise RuntimeError("no progressive stream")
            stream_url = str(stream["url"])
            if stream_url.startswith("/"):
                stream_url = urljoin(api, stream_url)
            size = download(stream_url, out / "source.mp4")
            (out / "federated-info.json").write_text(
                json.dumps({"provider": "invidious", "api": api, "stream": stream, "metadata": data}, indent=2),
                encoding="utf-8",
            )
            for cap in data.get("captions", []) or []:
                code = str(cap.get("languageCode") or cap.get("label") or "").lower()
                if (code.startswith("en") or "english" in code) and cap.get("url"):
                    save_caption(urljoin(api, str(cap["url"])), out / "source.en.vtt")
                    break
            print(f"Invidious success: {api} ({size} bytes)", flush=True)
            return True
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            print(f"Invidious failed: {api}: {exc}", file=sys.stderr, flush=True)
            time.sleep(0.2)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--output", default="fetched")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    video_id = video_id_from_url(args.url)
    if try_piped(video_id, out) or try_invidious(video_id, out):
        return 0
    print("All federated instances failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
