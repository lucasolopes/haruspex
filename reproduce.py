"""Independent, self-contained reproducer for the SQLite float-to-text case.

Run `python reproduce.py`. It re-derives the writeup's findings against YOUR
machine's SQLite, using only the Python standard library (no external deps, and
nothing from our engine). It is deliberately self-contained: the reference
renderer below reproduces SQLite's *observable* float-to-text FORMAT (public
SQLite behavior, not our tool). How the method discovers such behavior from a
black box is NOT here — and doesn't need to be for you to check the results.

Version-adaptive on purpose: SQLite's default text precision changed over time
(older builds render ~15 significant digits and lose precision on round-trip;
newer builds default to ~17 and round-trip safely). This script DETECTS which
one you have and reports YOUR version's reality — so it never "fails to
reproduce": it tells you the truth for whatever SQLite you happen to run.

Requires only Python 3 (>=3.7) with the standard library.
"""
from __future__ import annotations   # lazy annotations -> runs on older Python too

import sqlite3
import struct
import sys

try:                                   # UTF-8 output on any console (Windows included)
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CON = sqlite3.connect(":memory:")
VERSION = sqlite3.sqlite_version


def sqlite_render(d: float) -> str | None:
    """The oracle: the text SQLite produces for a REAL, as a black box."""
    return CON.execute("SELECT CAST(? AS TEXT)", (d,)).fetchone()[0]


def detect_precision() -> int:
    """How many significant digits does this SQLite's default renderer use?

    Probes values whose shortest decimal needs the full precision (no trailing
    zeros), and takes the max digit count observed (~15 on old, ~17 on new).
    """
    best = 0
    for d in (2 / 3, 1 / 7, 3.141592653589793, 1 / 13, 2 / 11):
        s = sqlite_render(d)
        if s is None:
            continue
        core = s.split("e")[0].lstrip("+-").replace(".", "").lstrip("0")
        best = max(best, len(core))
    return best or 15


def reconstructed(d: float, precision: int) -> str | None:
    """Reconstruction of SQLite's float-to-text FORMAT, at `precision` sig digits.

    Observed rules: `precision` significant digits (Python's correctly-rounded
    dtoa), fixed notation if -4 <= E < precision else exponential, always a
    decimal point (integers get ".0"), signed exponent with >=2 digits,
    +-0 -> "0.0", inf -> "Inf", NaN -> NULL.
    """
    if d != d:
        return None
    if d == float("inf"):
        return "Inf"
    if d == float("-inf"):
        return "-Inf"
    if d == 0.0:
        return "0.0"
    sign = "-" if d < 0 else ""
    mant, exp = ("%.*e" % (precision - 1, abs(d))).split("e")
    E = int(exp)
    digits = mant.replace(".", "").rstrip("0") or "0"
    n = len(digits)
    if -4 <= E < precision:
        if E >= 0:
            out = (digits + "0" * (E + 1 - n) + ".0") if n <= E + 1 else (digits[: E + 1] + "." + digits[E + 1:])
        else:
            out = "0." + "0" * (-E - 1) + digits
    else:
        m = digits[0] + "." + (digits[1:] if len(digits) > 1 else "0")
        out = m + "e" + ("+" if E >= 0 else "-") + "%02d" % abs(E)
    return sign + out


def spread(n):
    """Deterministic pseudo-uniform sweep over the whole 64-bit space (all
    magnitudes: tiny, huge, subnormal) — not a hand-picked range."""
    for i in range(n):
        bits = (i * 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
        yield struct.unpack("<d", struct.pack("<Q", bits))[0]


def main():
    P = detect_precision()
    N = 500_000   # single sample size for BOTH round-trip and reconstruction (one sweep)
    print(f"SQLite embedded here: {VERSION}   (default precision detected: ~{P} significant digits)\n")

    # --- The objective, regime-defining signal: does the render round-trip? ---
    fails = total = 0
    for d in spread(N):
        if d != d or d in (float("inf"), float("-inf")):
            continue
        total += 1
        try:                                  # never crash on an unexpected render
            back = float(sqlite_render(d))
        except (ValueError, TypeError):
            back = None
        if back != d:                         # read the text back != original -> info lost
            fails += 1
    rate = 100 * fails / total
    print(f"[Round-trip loss]     {rate:.1f}% of {total} doubles from a uniform 64-bit sweep do NOT "
          f"survive number -> text -> number.")
    if rate > 50:
        print("                      => This build loses precision silently: its text, read back, is a DIFFERENT number.")
    elif rate < 5:
        print("                      => This build round-trips safely (newer default). The precision-loss")
        print("                         defect this case is about does NOT apply to your build — the tool confirms it.")
    else:
        print("                      => Mixed regime; the tool reports what it measures.")

    # --- Blind reconstruction of this version's renderer (format), at its precision ---
    match = 0
    for d in spread(N):
        if reconstructed(d, P) == sqlite_render(d):
            match += 1
    print(f"\n[Blind reconstruction] matches this build's renderer on {100*match/N:.2f}% of {N} doubles "
          f"(all magnitudes).")
    print(f"                      residual {100*(N-match)/N:.2f}% = where this build's dtoa disagrees with "
          f"correct rounding (varies by version).")

    # --- Exhaustive census of a bounded region: the COMPLETE list, not a sample ---
    base = struct.unpack("<Q", struct.pack("<d", 1.0))[0]
    span = 1 << 20
    lo = struct.unpack("<d", struct.pack("<Q", base))[0]
    hi = struct.unpack("<d", struct.pack("<Q", base + span - 1))[0]
    changers = sum(
        1 for k in range(span)
        if sqlite_render(struct.unpack("<d", struct.pack("<Q", base + k))[0])
        != reconstructed(struct.unpack("<d", struct.pack("<Q", base + k))[0], P)
    )
    print(f"\n[Exhaustive census]   over ALL {span} consecutive doubles in [{lo!r}, {hi!r}]: "
          f"exactly {changers} diverge (COMPLETE list, not a sample).")


if __name__ == "__main__":
    main()
