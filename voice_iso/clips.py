"""Turning a game's stored voice segments into the sound one SRW64 battle line plays.

Everything here is 16-bit mono numpy.
"""
from __future__ import annotations

import numpy as np

RATE = 22050


def trimmed(a: np.ndarray) -> np.ndarray:
    """A stored segment without the zero padding that fills its last sector."""
    nz = np.flatnonzero(a)
    return a[:nz[-1] + 1] if len(nz) else a


def resampled(a: np.ndarray, rate: int, to: int) -> np.ndarray:
    """A segment stored at another rate than its disc's, brought to the disc's (by its spectrum, so nothing aliases)."""
    n = round(len(a) * to / rate)
    x = np.fft.irfft(np.fft.rfft(a.astype(float))[:n // 2 + 1], n) * n / len(a)
    return np.clip(np.rint(x), -32768, 32767).astype(np.int16)


def speech(a: np.ndarray, rate: int = RATE) -> list[tuple[int, int]]:
    """Voiced spans as sample ranges: 20 ms envelope over 6% of the peak, gaps under 80 ms bridged."""
    w = max(1, min(rate // 50, len(a)))
    e = np.convolve(np.abs(a.astype(float)), np.ones(w) / w, 'same')
    on = np.r_[False, e > max(200, e.max() * 0.06), False]
    edges = np.flatnonzero(np.diff(on.astype(int)))
    spans: list[list[int]] = []
    for s, t in zip(edges[::2], edges[1::2]):
        if spans and s - spans[-1][1] < 0.08 * rate:
            spans[-1][1] = t
        else:
            spans.append([s, t])
    return [(s, t) for s, t in spans if t - s > 0.05 * rate]


def pause_cuts(a: np.ndarray, weights: list[int], rate: int = RATE) -> list[int]:
    """Where a segment's pieces part: for each boundary, the quietest 60 ms near where the text lengths say
    (within half a piece's share either way, and after the boundary before it)."""
    w = rate * 3 // 50
    e = np.convolve(np.abs(a.astype(float)), np.ones(w) / w, 'same')
    lo, hi = int(len(a) * 0.15), int(len(a) * 0.85)
    reach = len(a) // (2 * len(weights))
    cuts: list[int] = []
    for j in range(1, len(weights)):
        guess = int(len(a) * sum(weights[:j]) / sum(weights))
        span = range(max(lo, guess - reach, cuts[-1] + rate // 20 if cuts else 0), min(hi, guess + reach))
        cuts.append(min(span, key=lambda i: (e[i], abs(i - guess))) if len(span) else guess)
    return cuts


def gap_cuts(a: np.ndarray, weights: list[int], rate: int = RATE) -> list[int] | None:
    """Where a stretch of a longer line starts and ends: the pauses between voiced spans whose share of the
    voiced time is nearest the text's (a comma's pause is short, so time spent silent must not count), each cut
    in the middle of its pause. None when the line runs on with no pause where one is needed."""
    spans = speech(a, rate)
    if len(spans) < 2:
        return None
    voiced = np.cumsum([t - s for s, t in spans])   # voiced time up to the end of each span
    cuts: list[int] = []
    last = -1
    for j in range(1, len(weights)):
        want = voiced[-1] * sum(weights[:j]) / sum(weights)
        gaps = [i for i in range(len(spans) - 1) if i > last]
        if not gaps:
            return None
        i = min(gaps, key=lambda i: abs(voiced[i] - want))
        cuts.append((spans[i][1] + spans[i + 1][0]) // 2)
        last = i
    return cuts


def part(a: np.ndarray, which: int, weights: list[int], rate: int = RATE, gaps: bool = False) -> np.ndarray:
    """One of a segment's pieces (two lines of one clip, or with gaps the stretch of a longer line that a shorter
    one says), cut at the pauses, without the silence the cuts leave beside it (the host stops a line's voice when
    the next line opens, so each line needs its own piece)."""
    cuts = (gap_cuts(a, weights, rate) if gaps else None) or pause_cuts(a, weights, rate)
    spans = speech(a, rate)
    k0 = cuts[which - 1] if which > 0 else 0
    k1 = cuts[which] if which < len(cuts) else len(a)
    if which > 0:
        start = min([s for s, t in spans if k0 <= s < k1], default=k0)
        k0 = max(k0, start - rate // 20)
    if which < len(cuts):
        end = max([t for s, t in spans if k0 < t <= k1], default=k1)
        k1 = min(k1, end + rate // 10)
    return a[k0:k1]


# SRW64's battle sound measured from a recorded battle (2026-10-31, 400 ms windows, voices left out):
# median -23.6 dBFS (music under the fight), the loudest 1% -15.5, the loudest moment -11.4.
# IMPACT's voices are mastered far hotter (spoken parts about -9 dBFS, peaks at full scale), so each
# line is brought to the level of SRW64's loud effects, and any peak that then goes over -3 dBFS is turned
# down on its own before encoding (Vorbis overshoots by up to about 3 dB).
TARGET_DBFS = -15.0
PEAK_DBFS = -3.0


def loudness(a: np.ndarray, rate: int = RATE) -> float:
    """dBFS of a line's spoken part: RMS over the 20 ms windows within 20 dB of the loudest."""
    x = a.astype(float) / 32768
    w = max(1, min(rate // 50, len(x)))
    e = np.sqrt(np.convolve(x * x, np.ones(w) / w, 'same'))
    on = e > e.max() * 0.1
    return 20 * np.log10(np.sqrt(np.mean(x[on] ** 2)) + 1e-12)


def limited(x: np.ndarray, peak: float = PEAK_DBFS, rate: int = RATE) -> np.ndarray:
    """Short peaks over the limit turned down, the rest left alone: a gain per 5 ms frame that keeps the frame
    and its neighbours under the limit, eased between frame centres (Alpha's XA voices have sharp transients
    that a single gain for the whole line would let pull every line down)."""
    limit = 32768 * 10 ** (peak / 20)
    w = max(1, rate // 200)
    n = -(-len(x) // w)
    frames = np.pad(np.abs(x), (0, n * w - len(x))).reshape(n, w).max(1)
    g = np.minimum(1.0, limit / np.maximum(frames, 1e-9))
    g = np.minimum(g, np.minimum(np.r_[g[1:], 1.0], np.r_[1.0, g[:-1]]))   # start easing a frame early
    gains = np.interp(np.arange(len(x)), np.arange(n) * w + w / 2, g)
    return np.clip(x * gains, -limit, limit)


def leveled(a: np.ndarray, target: float = TARGET_DBFS, peak: float = PEAK_DBFS, rate: int = RATE) -> np.ndarray:
    """The line at the target loudness, its few peaks over the limit turned down on their own."""
    x = a.astype(float) * 10 ** ((target - loudness(a, rate)) / 20)
    return np.round(limited(x, peak, rate)).astype(np.int16)


def line_sound(clips: list[dict], segment, rate: int = RATE) -> np.ndarray:
    """A line's sound from its voice-map entry: one segment, a piece of one, or several joined.
    segment(n) gives segment n decoded."""
    out = []
    for c in clips:
        a = trimmed(segment(c['clip']))
        out.append(part(a, c['part'], c['weights'], rate, c.get('cut') == 'gaps') if 'part' in c else a)
    return np.concatenate(out)
