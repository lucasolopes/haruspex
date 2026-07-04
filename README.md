# What changes when you upgrade a critical system? I'll tell you — with numbers.

*A real case, reproducible in one line (`python reproduce.py`, included here), against the
real binary — not against theory.*

## The problem

You're about to upgrade a dependency (or rewrite a legacy system) that runs in critical
production. The one question that decides the cutover is simple, and nobody answers it well:
**what changes in behavior?**

- Formal verification compares *idealized models* — it is blind, by design, to what the real
  binary actually does: floating point, overflow, rounding, environment quirks.
- Parallel-run (running old and new side by side) only sees what *traffic* exercises — the
  rare case that breaks next month doesn't show up in today's test.

So you flip the cutover in the dark and find the divergence when a customer complains.

## What I did

I took a public, deterministic target — SQLite's number renderer (`CAST(REAL AS TEXT)`,
which turns a floating-point number into the text you read) — and treated it as a
**black box**: I only ask input → output, **without reading the source**.

I pointed my tool at it two independent ways. Both converged on the same defect, on their own.
And crucially: the tool reports **your** SQLite version's reality — so it never "fails to
reproduce"; it tells you the truth for whatever build you run.

## The findings (run `reproduce.py` to see them for your build)

**1 — Round-trip loss (the objective anchor).** Take the text SQLite emits, read it back as a
number. If the number read back **≠** the original, SQLite lost information. On the
15-significant-digit default (SQLite ≤ ~3.51 — I measured 3.50.4, and confirmed the same on a
clean 3.46.1), this happens for **93.9% of doubles drawn from a uniform 64-bit sweep** (the
same 500k sweep used for the reconstruction below) — the least cherry-picked sample there is
(every representable double equally likely). Short "nice" decimals round-trip fine; any
full-precision or computed double is at risk. It's not opinion — an objective property you
check in a loop, and `reproduce.py` prints the exact rate for your build.

**2 — Blind reconstruction.** Without reading the source, the tool reconstructed the
renderer's behavior and matched it on **99.15%** of a 500k sample drawn by a **deterministic
sweep across the whole 64-bit space** (all magnitudes: tiny, huge, subnormal — not a
hand-picked range). The small residual (**0.85% on 3.50.4**) is **not** my reconstruction
being wrong — it's SQLite's own dtoa **not being correctly rounded** at that version (e.g.,
where the correct value is `…904`, SQLite prints `…905`). This residual **varies by version** —
the tool prints yours. The three versions I ran end to end, same-version pairs:

| SQLite version | round-trip loss | reconstruction residual |
|---|---|---|
| 3.46.1 | 93.9% | 0.01% |
| 3.50.4 | 93.9% | 0.85% |
| 3.51.1 | 93.9% | 0.85% |

Round-trip loss is stable across 15-digit-default builds (it's a function of the digit *count*
— 15 digits simply isn't enough for a double). The residual varies (it's a function of that
build's dtoa *quality*).

**Why 99.15% and 93.9% don't contradict each other** (the obvious skeptical question): they
measure *different things*. 99.15% is how faithfully *I reproduce* SQLite's behavior; 93.9% is
how much *SQLite's behavior* loses information. I reproduce, with high fidelity, a behavior
that is itself lossy. Two orthogonal axes pointing at the same defect by independent paths.

**3 — Exhaustive census (completeness, not a sample).** Over **all 1,048,576 consecutive
doubles starting at 1.0**, the tool hands you the **complete list** of the ones that diverge —
not a sample, a full census of the region. I picked a **dense, well-behaved** band on purpose
so the demo is trivial to verify; the value isn't the band's difficulty — it's that the tool
gives you the **guaranteed-complete list for any region you choose**, including the hard ones.
That's exactly what you get for *your* inputs: what changes, complete, not a guess.

**Version note.** Per SQLite's own docs, **version 3.52.0 (2026-03-06)** changed the renderer
to use up to **17 significant digits** when 15 don't round-trip — so the text now recovers the
exact double — and added `SQLITE_DBCONFIG_FP_DIGITS` to revert to 15
([floatingpoint.html](https://sqlite.org/floatingpoint.html)). Since that algorithm is built
to round-trip, on 3.52.0+ `reproduce.py` shows **near-zero** round-trip loss — the tool
correctly detecting your build already fixed it, **not** a failure to reproduce. (I verified
the 15-digit regime on real 3.46.1 / 3.50.4 / 3.51.1; the 3.52 round-trip guarantee is per the
doc above, not something I re-ran here.)

## Honest framing

I'm not claiming "I found a new bug in SQLite" — this renderer's imprecision is known, and
newer versions changed the default (see above). What I'm claiming is more interesting: **the
tool, pointed at a black box with no specification, rediscovered and quantified the defect on
its own — and told me exactly which inputs it affects.** That's more credible, not less: it
shows the method finds what matters without prior knowledge of the target.

And, in plain words, what I do **not** claim:
- Not a formal proof. It's directed measurement on the real binary.
- "Exhaustive" only where a domain is fully enumerated (the census region above). Elsewhere
  it's sampled measurement — and I state the sample's origin and coverage, I don't hide it.
- The numbers **depend on your SQLite version** — that's the point, not a flaw. The tool
  reports your build's reality.
- Version/clock/environment are hidden state. Before saying "equivalent," the tool
  **deliberately varies clock, environment and call order** to detect hidden state — and if it
  exists, it **warns instead of certifying blind.**

## The offer

This is exactly what I do for your system **before the cutover**: I point at your real
binary/service and hand you **what changes in behavior — with numbers and the exact inputs
that diverge** — covering the blind spot of both formal verification and parallel-run. You
make the go/no-go call with data, not in the dark.
