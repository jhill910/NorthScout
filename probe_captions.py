"""Can we read the captions off a press conference video?

WHY PROBE FIRST
---------------
Every press-conference detail the 9/8 show discussed and the board missed --
Cade Mays hurt, Bartch vs Mahogany at left guard, Stenavich playing coy about
the offensive line, Braxton Jones at left tackle -- was said out loud at a
podium. The clubs post those pressers to YouTube. If the captions are
readable, that content becomes searchable and scorable.

If they are not readable, there is no point building anything on top, and we
find that out in thirty seconds rather than after a day's work. The Bluesky
API taught that lesson: assume nothing about what a host will serve.

    python probe_captions.py

Tests four routes against real presser videos already on your board.
"""

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 20

# Real press conferences detected by the scraper on 2026-09-08.
SAMPLES = [
    ("oUy9gH36eBQ", "Dan Campbell press conference"),
    ("VDJggIy-VA4", "Brad Holmes and Ray Agnew"),
    ("s1sI46zy1wA", "Dennis Allen on the defense"),
]


def _get(url, headers=None):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return type(e).__name__, b""


def route_timedtext(vid):
    """Legacy caption endpoint. Usually empty now, but free to try."""
    url = f"https://www.youtube.com/api/timedtext?v={vid}&lang=en"
    status, body = _get(url)
    if isinstance(status, int) and status == 200 and body.strip():
        return True, f"HTTP 200, {len(body)} bytes"
    return False, f"{status}, {len(body)} bytes"


def route_watch_page(vid):
    """Fetch the watch page and pull the caption track URL out of it.

    This is how the player itself finds captions, so it reflects what is
    actually available rather than what an undocumented endpoint returns.
    """
    status, body = _get(f"https://www.youtube.com/watch?v={vid}")
    if not (isinstance(status, int) and status == 200):
        return False, f"watch page: {status}", None
    html = body.decode("utf-8", "replace")

    m = re.search(r'"captionTracks":(\[.*?\])', html)
    if not m:
        if "captionTracks" in html:
            return False, "captionTracks present but unparseable", None
        return False, "no caption track in the page", None
    try:
        tracks = json.loads(m.group(1))
    except json.JSONDecodeError:
        return False, "caption track JSON malformed", None
    if not tracks:
        return False, "caption list empty (no captions on this video)", None

    langs = [t.get("languageCode") for t in tracks]
    base = None
    for t in tracks:
        if t.get("languageCode", "").startswith("en"):
            base = t.get("baseUrl")
            break
    base = base or tracks[0].get("baseUrl")
    return True, f"{len(tracks)} track(s): {langs}", base


def _extract_text(body, fmt):
    """Pull plain text out of whichever caption format came back."""
    raw = body.decode("utf-8", "replace")
    if fmt == "json3":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        parts = []
        for ev in data.get("events") or []:
            for seg in ev.get("segs") or []:
                parts.append(seg.get("utf8", ""))
        return re.sub(r"\s+", " ", "".join(parts)).strip()
    # srv1/srv3/vtt/ttml are all tagged text
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = re.sub(r"WEBVTT|\d\d:\d\d:\d\d[.,]\d+ --> [^\n]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def route_fetch_track(base_url):
    """Download the caption text.

    A bare baseUrl now returns HTTP 200 with an EMPTY body -- observed on
    2026-09-08 across three club pressers. YouTube requires an explicit
    format parameter; without it the request succeeds and returns nothing,
    which reads like a block but isn't one. Try each format in turn.
    """
    if not base_url:
        return False, "no track url", ""

    attempts = [
        ("json3", base_url + "&fmt=json3"),
        ("srv3", base_url + "&fmt=srv3"),
        ("srv1", base_url + "&fmt=srv1"),
        ("vtt", base_url + "&fmt=vtt"),
        ("bare", base_url),
    ]
    tried = []
    for fmt, url in attempts:
        status, body = _get(url)
        if isinstance(status, int) and status == 200 and body.strip():
            words = _extract_text(body, fmt)
            if words:
                return True, f"fmt={fmt}: {len(words)} chars", words
            tried.append(f"{fmt}:parsed-empty")
        else:
            tried.append(f"{fmt}:{status}/{len(body)}b")
    return False, " ".join(tried), ""


def route_library(vid):
    """youtube-transcript-api, which tracks YouTube's caption protocol.

    The API changed between major versions: older releases exposed a static
    get_transcript(), newer ones want an instance and call it fetch(). The
    first version of this probe assumed the old shape and raised
    AttributeError, which looked like a block but was my bug. Try both.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, "not installed (pip install youtube-transcript-api)"

    attempts = []

    # Newer API: instance .fetch()
    try:
        api = YouTubeTranscriptApi()
        data = api.fetch(vid)
        chunks = getattr(data, "snippets", data)
        words = " ".join(
            (c.text if hasattr(c, "text") else c.get("text", "")) for c in chunks)
        if words.strip():
            return True, f"{len(words)} chars (instance .fetch)", words
        attempts.append("fetch:empty")
    except Exception as e:
        attempts.append(f"fetch:{type(e).__name__}: {str(e)[:70]}")

    # Older API: static get_transcript()
    try:
        tr = YouTubeTranscriptApi.get_transcript(vid)
        words = " ".join(x.get("text", "") for x in tr)
        if words.strip():
            return True, f"{len(words)} chars (static get_transcript)", words
        attempts.append("get_transcript:empty")
    except Exception as e:
        attempts.append(f"get_transcript:{type(e).__name__}: {str(e)[:70]}")

    return False, " | ".join(attempts), ""


def main():
    print("=" * 72)
    print("Press conference caption probe")
    print("=" * 72)

    any_worked = False
    sample_text = ""

    for vid, label in SAMPLES:
        print(f"\n  {label}  ({vid})")

        ok, detail = route_timedtext(vid)
        print(f"     {'WORKS  ' if ok else 'blocked'}  1. legacy timedtext endpoint — {detail}")

        ok2, detail2, base = route_watch_page(vid)
        print(f"     {'WORKS  ' if ok2 else 'blocked'}  2. caption track listed on watch page — {detail2}")

        if ok2:
            ok3, detail3, text = route_fetch_track(base)
            print(f"     {'WORKS  ' if ok3 else 'blocked'}  3. download the caption track — {detail3}")
            if ok3:
                any_worked = True
                if not sample_text:
                    sample_text = text

        r4 = route_library(vid)
        if r4[0] is None:
            print(f"     skipped  4. youtube-transcript-api — {r4[1]}")
        else:
            ok4, detail4 = r4[0], r4[1]
            print(f"     {'WORKS  ' if ok4 else 'blocked'}  4. youtube-transcript-api — {detail4}")
            if ok4:
                any_worked = True
                if not sample_text:
                    sample_text = r4[2]

    print("\n" + "=" * 72)
    if any_worked:
        print("Captions are readable. Here is the first 400 characters:\n")
        print("   " + sample_text[:400].replace("\n", " "))
        print("\nSend this back and I'll build presser transcripts into the board.")
        return 0

    print("No route returned caption text.")
    print()
    print("That likely means YouTube is refusing automated caption access from")
    print("this network, the way Bluesky refused its API. Worth one try on a")
    print("phone hotspot before we conclude it — and if the GitHub Action can't")
    print("read them either, this approach is dead and the honest answer is")
    print("that presser detail stays a human job.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
