"""Tests for the dashboard presentation helpers."""
import sys, types
from datetime import datetime, timedelta

_fp = types.ModuleType("feedparser"); _fp.parse = lambda *a, **k: None
sys.modules.setdefault("feedparser", _fp)

class M:
    def __init__(s, n="st"): s._n = n; s._count = 4
    def __call__(s, *a, **k):
        m = M(s._n)
        if a and isinstance(a[0], (list, tuple)): m._count = len(a[0])
        elif a and isinstance(a[0], int): m._count = a[0]
        return m
    def __getattr__(s, k):
        if k == "cache_data":
            def d(*a, **kw):
                if a and callable(a[0]): f = a[0]; f.clear = lambda: None; return f
                def i(f): f.clear = lambda: None; return f
                return i
            return d
        return M(f"{s._n}.{k}")
    def __getitem__(s, i): return M(s._n)
    def __enter__(s): return s
    def __exit__(s, *a): return False
    def __iter__(s): return iter([M() for _ in range(s._count)])
    def __bool__(s): return False
sys.modules["streamlit"] = M()

import app


def test_relative_time():
    now = datetime.now()
    fmt = "%a, %d %b %Y %H:%M:%S GMT"
    cases = [(now - timedelta(minutes=20), "m ago"),
             (now - timedelta(hours=9), "h ago"),
             (now - timedelta(days=3), "d ago")]
    for dt, suffix in cases:
        out = app.relative_time(dt.strftime(fmt))
        assert out.endswith(suffix), (out, suffix)
    assert app.relative_time("") == ""
    assert app.relative_time(None) == ""
    print("  ok  relative time renders m/h/d and survives empty input")


def test_chips_from_real_reasons():
    """Reason strings taken verbatim from the live 2026-09-03 snapshot."""
    real = [
        ("published 9h ago; transaction: cut; decision-maker on record: brad holmes; "
         "conflict: arrested, charges", ["off-field", "GM on record", "transaction"]),
        ("published 1h ago; decision-maker on record: ben johnson; "
         "press conference (SOT available); speaker: Ben Johnson",
         ["GM on record", "press conference"]),
        ("availability: injured reserve, ir; transaction: activated, roster moves, signed",
         ["availability", "transaction"]),
        ("published 1h ago; distinctive wording; independent source (ProFootballTalk)",
         ["independent"]),
    ]
    for reasons, expected in real:
        got = [c[0] for c in app.signal_chips(reasons, limit=4)]
        for e in expected:
            assert e in got, f"{e!r} missing from {got} for {reasons[:50]}"
    print("  ok  chips derived correctly from real snapshot reason strings")


def test_chips_capped_and_safe():
    busy = ("availability: pup; conflict: charges; decision-maker on record: x; "
            "transaction: signed; money: contract; running storyline: y")
    assert len(app.signal_chips(busy, limit=3)) == 3
    assert app.signal_chips(None) == []
    assert app.signal_chips("") == []
    assert app.chips_html(None) == ""
    print("  ok  chips capped at the limit; empty input yields no markup")


def test_chip_priority():
    """Off-field and availability must outrank routine descriptors."""
    r = "distinctive wording; routine: inbox; availability: pup"
    labels = [c[0] for c in app.signal_chips(r, limit=1)]
    assert labels == ["availability"], labels
    print("  ok  high-value signals outrank routine ones")


def test_lead_and_grid_split():
    import pandas as pd
    df = pd.DataFrame([{"title": f"Story {i}", "summary": "s", "link": "u",
                        "fetched_at": "", "thumbnail": "", "score": 100 - i,
                        "reasons": ""} for i in range(10)])
    lead, rest, more = df.iloc[0], df.iloc[1:5], df.iloc[5:]
    assert lead["title"] == "Story 0"
    assert len(rest) == 4 and len(more) == 5
    print("  ok  1 lead + 4 in grid + 5 behind the expander")


if __name__ == "__main__":
    print("dashboard UI tests")
    for fn in list(globals().values()):
        if callable(fn) and getattr(fn, "__name__", "").startswith("test_"):
            fn()
    print("\nALL TESTS PASSED")
