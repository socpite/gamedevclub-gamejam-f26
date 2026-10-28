"""
Procedurally generates every sound effect for Scotty: After Hours.

    python3 assets/sounds/make_sounds.py        (needs numpy)

Writes mono 16-bit 44.1 kHz WAVs next to this file. Everything is synthesised,
so tweak a recipe and re-run rather than editing the WAVs by hand.
Files named amb_* / *_loop are seamless loops.
"""
import os
import wave

import numpy as np

SR = 44100
OUT = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(8)


# ----------------------------------------------------------------------------- building blocks
def secs(d):
    return np.arange(int(d * SR)) / SR


def noise(d):
    return rng.standard_normal(int(d * SR))


def osc(freq, d, shape="sine", phase=0.0):
    """freq may be a number or an array (pitch envelope)."""
    n = int(d * SR)
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    ph = phase + np.cumsum(f) / SR
    if shape == "sine":
        return np.sin(2 * np.pi * ph)
    if shape == "saw":
        return 2 * (ph % 1.0) - 1
    if shape == "square":
        return np.sign(np.sin(2 * np.pi * ph))
    if shape == "tri":
        return 2 * np.abs(2 * (ph % 1.0) - 1) - 1
    raise ValueError(shape)


def spectral(x, gain_fn):
    """Zero-phase filter: multiply the spectrum by gain_fn(freqs)."""
    n = len(x)
    X = np.fft.rfft(x, n * 2)
    f = np.fft.rfftfreq(n * 2, 1 / SR)
    return np.fft.irfft(X * gain_fn(f), n * 2)[:n]


def lp(x, fc, order=2):
    return spectral(x, lambda f: 1 / np.sqrt(1 + (f / fc) ** (2 * order)))


def hp(x, fc, order=2):
    return spectral(x, lambda f: 1 / np.sqrt(1 + (fc / np.maximum(f, 1e-3)) ** (2 * order)))


def bp(x, fc, q=4.0):
    bw = fc / q
    return spectral(x, lambda f: 1 / np.sqrt(1 + ((f - fc) / (bw / 2)) ** 2))


def formants(x, fs, qs=None, gains=None):
    qs = qs or [6] * len(fs)
    gains = gains or [1] * len(fs)
    return sum(g * bp(x, f, q) for f, q, g in zip(fs, qs, gains))


def env_ad(d, attack, decay_curve=4.0):
    t = secs(d)
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    rel = np.clip((t - attack) / max(d - attack, 1e-4), 0, 1)
    return a * np.exp(-decay_curve * rel) * (1 - rel)


def fade(x, fin=0.005, fout=0.02):
    x = x.copy()
    i, o = int(fin * SR), int(fout * SR)
    if i:
        x[:i] *= np.linspace(0, 1, i)
    if o:
        x[-o:] *= np.linspace(1, 0, o)
    return x


def pad(x, d):
    return np.concatenate([x, np.zeros(int(d * SR))])


def place(dst, src, at):
    i = int(at * SR)
    j = min(len(dst), i + len(src))
    dst[i:j] += src[: j - i]
    return dst


def conv(x, ir):
    n = len(x) + len(ir) - 1
    m = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[:n]


def reverb(x, decay=1.6, mix=0.3, bright=4000, predelay=0.02):
    """Exponentially-decaying-noise IR: an empty concrete street at night."""
    t = secs(decay * 1.5)
    ir = rng.standard_normal(len(t)) * np.exp(-6.9 * t / decay)
    ir = lp(ir, bright, 1)
    ir = np.concatenate([np.zeros(int(predelay * SR)), ir])
    ir /= np.sqrt(np.sum(ir ** 2))
    wet = conv(x, ir)
    out = np.concatenate([x, np.zeros(len(wet) - len(x))]) * (1 - mix) + wet * mix
    return out


def loopify(x, xf=1.0):
    """Turn x into a seamless loop of len(x) - xf seconds by crossfading its tail into its head."""
    n = int(xf * SR)
    body, tail = x[:-n].copy(), x[-n:]
    w = np.sin(np.linspace(0, np.pi / 2, n)) ** 2
    body[:n] = body[:n] * w + tail * (1 - w)
    return body


def wrapadd(x, loop_d):
    """Loop for event sequences: fold everything past loop_d (reverb tails, late notes) back onto the start."""
    n = int(loop_d * SR)
    out = x[:n].copy()
    tail = x[n:]
    while len(tail):
        k = min(n, len(tail))
        out[:k] += tail[:k]
        tail = tail[k:]
    return out


def crush(x, bits=5, hold=6):
    x = np.repeat(x[::hold], hold)[: len(x)]
    q = 2 ** (bits - 1)
    return np.round(x * q) / q


def norm(x, peak_db=-1.0):
    p = np.max(np.abs(x)) or 1
    return x / p * 10 ** (peak_db / 20)


def save(name, x, peak_db=-1.0):
    x = norm(np.asarray(x, dtype=float), peak_db)
    data = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    print(f"  {name:24s} {len(x) / SR:5.2f}s  peak {peak_db:+.0f} dB")


# ----------------------------------------------------------------------------- ambience
def amb_night():
    """Low city drone: detuned sines, distant traffic rumble. 16 s loop."""
    d = 17
    t = secs(d)
    x = np.zeros(len(t))
    for f, a in [(55, 1), (55.4, 0.8), (82.4, 0.5), (110.2, 0.25), (164.6, 0.08)]:
        x += a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6))
    x *= 0.7 + 0.3 * np.sin(2 * np.pi * t / 8.5)
    rumble = lp(noise(d), 180, 3) * 3
    rumble *= 0.6 + 0.4 * np.sin(2 * np.pi * t / 17 * 2 + 1)
    hiss = bp(noise(d), 1800, 1.2) * 0.04
    return loopify(x * 0.5 + rumble + hiss)


def amb_wind():
    """Night wind through the palms. The frozen_skyline anomaly mutes it. 12 s loop."""
    d = 13
    t = secs(d)
    x = np.zeros(len(t))
    for fc, rate, ph in [(400, 0.13, 0), (900, 0.21, 2), (1700, 0.33, 4)]:
        band = bp(noise(d), fc, 1.5)
        gust = 0.5 + 0.5 * np.sin(2 * np.pi * rate * t + ph) * np.sin(2 * np.pi * rate * 0.37 * t + ph)
        x += band * gust ** 2
    rustle = hp(noise(d), 4000) * (0.3 + 0.7 * (lp(noise(d), 3, 1) * 40).clip(0, 1)) * 0.25
    return loopify(x + rustle)


def amb_dread():
    """Dissonant string cluster that swells with corruption. 16 s loop."""
    d = 17
    t = secs(d)
    x = np.zeros(len(t))
    # minor-second / tritone cluster around A2 and Eb3, slowly beating
    for f in [110, 116.5, 155.6, 164.8, 233.1]:
        for det in (-0.3, 0.3):
            v = osc(f + det, d, "saw", rng.uniform(0, 1))
            x += lp(v, 900) * (0.5 + 0.5 * np.sin(2 * np.pi * t / rng.choice([8.5, 17 / 3]) + rng.uniform(0, 6)))
    # high glassy whine
    whine = np.sin(2 * np.pi * (2960 + 6 * np.sin(2 * np.pi * 0.3 * t)) * t) * 0.03
    sub = np.sin(2 * np.pi * 36.7 * t) * 0.6
    return loopify(reverb(x * 0.15 + whine + sub, 3.0, 0.5)[: len(t)])


# ----------------------------------------------------------------------------- Scotty
def step(i):
    """A small dog's paw on paving stones."""
    d = 0.09
    click = bp(noise(d), 2500 + 600 * i, 2) * env_ad(d, 0.002, 9)
    thump = np.sin(2 * np.pi * (140 - 60 * secs(d) / d) * secs(d)) * env_ad(d, 0.003, 7) * 0.6
    scuff = hp(noise(d), 5000) * env_ad(d, 0.01, 6) * 0.15 * (i % 2)
    return fade(reverb(click + thump + scuff, 0.5, 0.12)[: int(0.4 * SR)], 0.001, 0.15)


def jump():
    d = 0.3
    t = secs(d)
    scuff = bp(noise(d), 3000, 1.5) * env_ad(d, 0.005, 10) * 0.5
    u = t / d
    n = noise(d)
    whoosh = (bp(n, 600, 1.5) * (1 - u) + bp(n, 2100, 1.5) * u) * np.sin(np.pi * u) ** 2 * 0.5
    return fade(scuff + whoosh)


def land():
    d = 0.25
    t = secs(d)
    thud = np.sin(2 * np.pi * (110 - 50 * t / d) * t) * env_ad(d, 0.002, 8)
    grit = bp(noise(d), 2200, 1.5) * env_ad(d, 0.002, 14) * 0.6
    return fade(reverb(thud + grit, 0.6, 0.15))


def bark_voice(f0, f1, d, roughness=0.35, fm=(900, 1700, 3000)):
    """One bark: a falling-pitch buzzy source through dog-ish formants."""
    t = secs(d)
    pitch = f0 + (f1 - f0) * (t / d) ** 0.6
    pitch *= 1 + 0.03 * np.sin(2 * np.pi * 31 * t)
    src = osc(pitch, d, "saw") + roughness * noise(d)
    v = formants(src, list(fm), [5, 6, 7], [1, 0.7, 0.3])
    e = np.clip(t / 0.008, 0, 1) * np.exp(-((t - 0.02).clip(0) / (d * 0.45)) ** 1.6)
    return v * e


def bark(variant=0):
    rng_pitch = [(720, 470), (780, 520)][variant]
    x = bark_voice(*rng_pitch, 0.17)
    if variant == 1:  # "ruff-ruff"
        x = place(pad(x, 0.15), bark_voice(700, 450, 0.15), 0.17)
    return fade(reverb(pad(x, 0.1), 1.4, 0.28)[: int(1.5 * SR)], 0.001, 0.4)


def bark_wrong_echo():
    """The bark, then — far too late — the street barks back, lower."""
    x = pad(bark_voice(720, 470, 0.17), 2.2)
    echo = bark_voice(430, 260, 0.26, 0.6, (600, 1200, 2400))
    echo = lp(echo, 1500) * 0.5
    place(x, echo, 1.25)
    return fade(reverb(x, 2.2, 0.45))


def meow(wrong=False):
    """The cat anomaly: Scotty tries to bark and a meow comes out."""
    d = 0.7 if not wrong else 1.1
    t = secs(d)
    u = t / d
    pitch = 520 + 380 * np.sin(np.pi * u ** 0.8) - 120 * u
    if wrong:
        pitch *= 0.62 * (1 - 0.15 * u)
    src = osc(pitch * (1 + 0.012 * np.sin(2 * np.pi * 6 * t)), d, "saw") + 0.08 * noise(d)
    # "m-ee-ow": formants slide from closed to open to rounded
    f1 = 400 + 600 * np.sin(np.pi * np.clip(u * 1.3, 0, 1))
    out = np.zeros(len(t))
    # time-varying formants via short overlapping blocks
    blk = 1024
    win = np.hanning(blk * 2)
    for s in range(0, len(t) - blk, blk):
        seg = src[s: s + blk * 2]
        if len(seg) < blk * 2:
            seg = np.pad(seg, (0, blk * 2 - len(seg)))
        c = s + blk
        ff1 = f1[min(c, len(t) - 1)]
        y = formants(seg * win, [ff1, ff1 * 2.3, 3300], [5, 7, 8], [1, 0.6, 0.2])
        out[s: s + blk * 2] += y[: len(out) - s]
    e = np.clip(t / 0.04, 0, 1) * np.clip((d - t) / 0.2, 0, 1)
    return fade(reverb(pad(out * e, 0.2), 1.6 if wrong else 1.0, 0.4 if wrong else 0.25))


# ----------------------------------------------------------------------------- loop / judgement cues
def loop_seam():
    """Played as Scotty walks forward into a new loop: a tiny tape-splice tick and breath of air."""
    d = 0.6
    t = secs(d)
    tick = bp(noise(d), 6000, 3) * env_ad(d, 0.001, 30) * 0.5
    air = lp(noise(d), 800) * np.sin(np.pi * t / d) ** 3 * 0.5
    sub = np.sin(2 * np.pi * 48 * t) * np.sin(np.pi * t / d) ** 2 * 0.4
    return fade(tick + air + sub)


def turn_back():
    """The cut to black after turning around: a deep door-slam boom."""
    d = 3.0
    t = secs(d)
    boom = np.sin(2 * np.pi * (70 * np.exp(-t * 1.5) + 28) * t) * np.exp(-t * 2.2)
    hit = lp(noise(d), 400, 2) * env_ad(d, 0.003, 30) * 3
    swell = hp(noise(d), 2000) * np.exp(-((t - 0.0) / 0.03) ** 2) * 0.3
    return fade(reverb(boom + hit + swell, 2.6, 0.4)[: len(t)])


def wrong():
    """Wrong call jump-scare: shrieking cluster, metallic FM screech, sub drop."""
    d = 2.2
    t = secs(d)
    e = np.exp(-t * 2.0) * np.clip(t / 0.004, 0, 1)
    cluster = sum(osc(f * (1 - 0.06 * t), d, "saw") for f in [233, 247, 349, 370, 523, 554])
    cluster = hp(lp(cluster, 4000), 150) * e * 0.35
    mod = np.sin(2 * np.pi * 1373 * t) * (8 * np.exp(-t * 1.5))
    screech = np.sin(2 * np.pi * 1900 * (1 - 0.25 * t) * t + mod) * np.exp(-t * 2.5) * 0.5
    sub = np.sin(2 * np.pi * (90 * np.exp(-t * 3) + 30) * t) * np.exp(-t * 1.2) * 1.2
    burst = hp(noise(d), 1500) * np.exp(-t * 18) * 0.8
    x = cluster + screech + sub + burst
    x = np.tanh(x * 2.2) * 0.8
    return fade(reverb(x, 2.5, 0.35)[: len(t)])


def chime(step_i):
    """A correct call. Notes 1..8 climb a scale; quiet, glassy, a little sad."""
    # D minor-ish scale climbing to the octave
    semis = [0, 2, 3, 5, 7, 8, 10, 12][step_i]
    f = 293.66 * 2 ** (semis / 12)
    d = 2.4
    t = secs(d)
    x = np.zeros(len(t))
    for ratio, a, dec in [(1, 1, 1.4), (2.0, 0.35, 2.2), (2.76, 0.25, 3.0), (5.4, 0.08, 5.0)]:
        x += a * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t * dec)
    x *= np.clip(t / 0.003, 0, 1)
    return fade(reverb(x, 2.4, 0.35)[: len(t)])


def escape():
    """The ending: the street lets go. A warm D major swell resolving out of the drone."""
    d = 7.0
    t = secs(d)
    x = np.zeros(len(t))
    for f in [73.42, 146.83, 220.0, 293.66, 369.99, 440.0]:
        for det in (-0.4, 0.4):
            v = osc(f + det, d, "saw", rng.uniform(0, 1))
            x += (lp(v, 900) * (1 - t / d) + lp(v, 2000) * (t / d)) * 0.12
    x *= np.clip(t / 2.5, 0, 1) ** 2 * np.clip((d - t) / 2.5, 0, 1)
    bells = np.zeros(len(t))
    for i, semis in enumerate([12, 16, 19, 24]):
        f =293.66 * 2 ** (semis / 12)
        tb = secs(3)
        b = np.sin(2 * np.pi * f * tb) * np.exp(-tb * 1.2) + 0.3 * np.sin(2 * np.pi * f * 2.76 * tb) * np.exp(-tb * 2.5)
        place(bells, b * 0.35, 2.2 + i * 0.45)
    return fade(reverb(x + bells, 3.0, 0.4)[: len(t)], 0.01, 0.5)


def heartbeat():
    """One lub-dub; audio.py retriggers it faster as corruption rises."""
    d = 0.75
    t = secs(d)

    def thump(at, f, a):
        tt = (t - at).clip(0)
        return a * np.sin(2 * np.pi * f * (1 - 0.4 * tt / 0.12) * tt) * np.exp(-tt * 28) * (t >= at)

    x = thump(0.0, 62, 1.0) + thump(0.17, 55, 0.7)
    return fade(lp(x, 220, 2), 0.001, 0.05)


def glitch(i):
    """Short digital stutter for when the world tears a little."""
    d = 0.35 + 0.1 * i
    t = secs(d)
    src = osc(220 * (i + 1) * (1 + 0.5 * np.sign(np.sin(2 * np.pi * 23 * t))), d, "square") * 0.4 + noise(d) * 0.4
    gate = (np.sin(2 * np.pi * (17 + 9 * i) * t) > -0.2).astype(float)
    x = crush(src * gate, 3 + i, 5 + 4 * i)
    return fade(bp(x, 1500 + 800 * i, 0.8) * env_ad(d, 0.002, 2))


# ----------------------------------------------------------------------------- lamps
def lamp_hum(bad=False):
    """Sodium street lamp: 100 Hz mains buzz + ballast whine. bad=True is the sick red lamp."""
    d = 6
    t = secs(d)
    base = 100 if not bad else 87
    x = np.zeros(len(t))
    for h, a in [(1, 1), (2, 0.6), (3, 0.45), (4, 0.25), (6, 0.12), (9, 0.06)]:
        x += a * np.sin(2 * np.pi * base * h * t + h)
    x = np.tanh(x * (1.5 if not bad else 3.5)) * 0.5
    whine = np.sin(2 * np.pi * (8200 if not bad else 6100) * t) * 0.02
    sizzle = hp(noise(d), 3000) * 0.04
    if bad:
        # irregular crackle and dropouts
        pops = np.zeros(len(t))
        for at in rng.uniform(0, d - 0.1, 22):
            place(pops, hp(noise(0.02), 1500) * env_ad(0.02, 0.0005, 8) * rng.uniform(0.3, 1), at)
        stutter = 0.65 + 0.35 * np.sign(np.sin(2 * np.pi * 7.3 * t) + np.sin(2 * np.pi * 2.1 * t))
        x = x * stutter + pops * 0.8
    out = x + whine + sizzle
    return loopify(out)  # 5 s: a whole number of 100 / 87 Hz cycles


def lamp_creak():
    """The leaning lamp: a slow metal groan (stick-slip pulse train through resonances)."""
    d = 1.8
    t = secs(d)
    rate = 34 + 22 * np.sin(np.pi * t / d) + 6 * np.sin(2 * np.pi * 3.1 * t)
    ph = np.cumsum(rate) / SR
    pulses = (np.diff(np.floor(ph), prepend=0) > 0).astype(float)
    pulses *= rng.uniform(0.5, 1.0, len(t))
    body = formants(pulses, [420, 1130, 2260, 3900], [18, 22, 25, 25], [1, 0.8, 0.5, 0.25])
    body *= np.sin(np.pi * t / d) ** 0.7
    return fade(reverb(body, 1.6, 0.3)[: len(t) + SR // 2])


def lamp_die():
    """Optional: a lamp powering down (falling ballast whine + clunk)."""
    d = 1.5
    t = secs(d)
    whine = np.sin(2 * np.pi * np.cumsum(1500 * np.exp(-t * 2.5) + 60) / SR) * np.exp(-t * 2) * 0.4
    clunk = lp(noise(d), 600) * env_ad(d, 0.002, 40) * 2
    return fade(reverb(whine + clunk, 1.2, 0.3)[: len(t)])


# ----------------------------------------------------------------------------- coffee shop
HIJAZ_D = [0, 1, 4, 5, 7, 8, 10, 12]


def pluck(f, d=0.9, bright=1.0):
    """Karplus-Strong-ish oud pluck."""
    n = int(d * SR)
    period = max(2, int(SR / f))
    buf = rng.uniform(-1, 1, period)
    out = np.empty(n)
    damp = 0.996 - 0.004 * (1 - bright)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = damp * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    return out


def shop_radio(warped=False):
    """Muffled oud tune heard through the café glass, in maqam Hijaz on D. 16 s loop."""
    beat = 0.5
    d = 16
    x = np.zeros(int((d + 2.5) * SR))
    melody = [0, 1, 4, 5, 4, 1, 0, -1, 0, 4, 5, 7, 8, 7, 5, 4, 5, 4, 1, 0, 1, 4, 1, 0,
              7, 8, 10, 8, 7, 5, 4, 1]
    for i, deg in enumerate(melody):
        octave, k = divmod(deg, 7)
        semis = HIJAZ_D[k] + 12 * octave
        f = 293.66 * 2 ** (semis / 12)
        place(x, pluck(f, 0.8) * 0.6, i * beat)
        if i % 4 == 0:  # bass drone on D/A
            place(x, pluck(73.42 if i % 8 == 0 else 110.0, 1.6) * 0.5, i * beat)
        if i % 2 == 1:  # soft frame-drum tak
            place(x, bp(noise(0.06), 2500, 2) * env_ad(0.06, 0.001, 10) * 0.25, i * beat)
        if i % 4 == 0:  # dum
            tt = secs(0.25)
            place(x, np.sin(2 * np.pi * (90 - 40 * tt) * tt) * np.exp(-tt * 14) * 0.6, i * beat)
    # through the window: lowpass, a touch of room
    x = lp(hp(x, 120), 1300, 2)
    x = wrapadd(reverb(x, 0.8, 0.2), d)
    if warped:
        # tape wow: a slow, wobbling read head running ~12% slow, then darker still
        src = np.tile(x, 3)
        out_n = int(d / 0.88 * SR)
        tt = np.arange(out_n + SR) / SR
        speed = 0.88 + 0.05 * np.sin(2 * np.pi * tt / (d / 0.88) * 7) + 0.02 * np.sin(2 * np.pi * 2.3 * tt)
        pos = np.cumsum(speed)
        x = np.interp(pos, np.arange(len(src)), src)
        x = loopify(lp(x, 800, 2), 1.0)
    return x


def clock_tick(reverse=False):
    """Café wall clock, one tick per second (2 s loop). reverse=True plays every tick backwards."""
    d = 2.0
    x = np.zeros(int(d * SR))
    for i, fc in enumerate([3200, 2600]):
        tk = bp(noise(0.05), fc, 6) * env_ad(0.05, 0.0005, 16)
        tk += np.sin(2 * np.pi * 900 * secs(0.05)) * env_ad(0.05, 0.0005, 25) * 0.3
        if reverse:
            tk = tk[::-1] * np.linspace(0.3, 1, len(tk)) ** 2
        place(x, tk, i * 1.0 + (0.9 if reverse else 0.02))
    if reverse:
        return wrapadd(reverb(x[::-1], 0.6, 0.25), d)[::-1]
    return wrapadd(reverb(x, 0.6, 0.15), d)


def door_creak():
    """The shop door swinging open on its own."""
    d = 2.6
    t = secs(d)
    rate = 14 + 70 * (t / d) ** 1.5 + 8 * np.sin(2 * np.pi * 1.7 * t)
    ph = np.cumsum(rate) / SR
    pulses = (np.diff(np.floor(ph), prepend=0) > 0).astype(float) * rng.uniform(0.4, 1, len(t))
    body = formants(pulses, [310, 760, 1650, 2900], [14, 16, 20, 20], [1, 0.9, 0.6, 0.3])
    body *= np.sin(np.pi * np.clip(t / d * 1.1, 0, 1)) ** 0.5
    knock = lp(noise(0.3), 300) * env_ad(0.3, 0.002, 12) * 2
    place(body, knock, d - 0.3)
    return fade(reverb(body, 1.8, 0.3))


def shop_inside():
    """Something breathing in the dark doorway. 7.2 s loop."""
    d = 7.2
    t = secs(d + 2.2)
    x = np.zeros(len(t))
    for start in np.arange(0, d, 2.4):
        dur = 2.1
        tt = secs(dur)
        inhale = np.sin(np.pi * np.clip(tt / 0.9, 0, 1)) ** 2 * (tt < 0.9)
        exhale = np.sin(np.pi * np.clip((tt - 1.0) / 1.1, 0, 1)) ** 2 * (tt >= 1.0)
        br = formants(noise(dur), [500, 1100, 2300], [3, 4, 5], [1, 0.6, 0.3])
        growl = osc(52 + 4 * rng.uniform(), dur, "saw") * exhale * 0.25
        place(x, br * (inhale * 0.6 + exhale) + lp(growl, 300), start)
    return wrapadd(lp(x, 2500), 7.2)


def glass_knock():
    """Three slow knocks on the café window from the inside."""
    x = np.zeros(int(2.4 * SR))
    for i, at in enumerate([0.0, 0.55, 1.1]):
        d = 0.3
        t = secs(d)
        k = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * dec)
                for f, a, dec in [(240, 1, 30), (1830, 0.4, 40), (3170, 0.25, 50), (4600, 0.1, 60)])
        k += lp(noise(d), 1200) * env_ad(d, 0.001, 30) * 0.5
        place(x, k * (1 - 0.1 * i), at)
    return fade(reverb(x, 0.9, 0.2)[: len(x)])


# ----------------------------------------------------------------------------- street anomalies
def whisper():
    """student_watching: breathy, unintelligible whispering. 6 s loop."""
    d = 6
    t = secs(d + 1)
    x = np.zeros(len(t))
    pos = 0.1
    vowels = [(300, 2300), (700, 1200), (500, 900), (400, 2000), (600, 1700)]
    while pos < d - 0.4:
        sd = rng.uniform(0.12, 0.3)
        f1, f2 = vowels[rng.integers(len(vowels))]
        syl = formants(noise(sd), [f1, f2, 2800], [4, 6, 6], [1, 0.8, 0.4])
        if rng.random() < 0.4:  # sibilant consonant
            syl = np.concatenate([hp(noise(0.08), 4500) * 0.6, syl])
        e = np.sin(np.pi * np.linspace(0, 1, len(syl))) ** 1.5
        place(x, syl * e * rng.uniform(0.4, 1), pos)
        pos += len(syl) / SR + rng.uniform(0.02, 0.4 if rng.random() < 0.8 else 1.0)
    return wrapadd(reverb(x, 0.7, 0.2), d)


def eyes_drone():
    """student_eyes: sub-bass pressure and a tinnitus whine. 8 s loop."""
    d = 9
    t = secs(d)
    sub = np.sin(2 * np.pi * 31 * t) * (0.7 + 0.3 * np.sin(2 * np.pi * t / 4))
    growl = lp(osc(46.25, d, "saw") * (0.5 + 0.5 * np.sin(2 * np.pi * 0.75 * t)), 220) * 0.6
    tinnitus = np.sin(2 * np.pi * (7040 + 30 * np.sin(2 * np.pi * 0.2 * t)) * t) * 0.05
    return loopify(sub + growl + tinnitus)


def marker_squeak():
    """whiteboard: someone you can't see is writing on it."""
    d = 2.8
    x = np.zeros(int(d * SR))
    at = 0.0
    while at < d - 0.4:
        sd = rng.uniform(0.08, 0.35)
        t = secs(sd)
        f = rng.uniform(1300, 2400) * (1 + 0.25 * np.sin(2 * np.pi * rng.uniform(2, 8) * t))
        tone = osc(f, sd, "saw") * 0.3 + bp(noise(sd), 3500, 2) * 0.5
        stick = (np.sin(2 * np.pi * rng.uniform(30, 60) * t) > 0.3).astype(float) * 0.6 + 0.4
        place(x, lp(tone * stick, 5000) * np.sin(np.pi * t / sd) ** 0.5, at)
        at += sd + rng.uniform(0.04, 0.25)
    return fade(reverb(x, 0.7, 0.15)[: len(x)])


# ----------------------------------------------------------------------------- sound-only anomalies
def heartbeat_loop():
    """cafe_heartbeat: a big slow heart somewhere inside the café walls. 3 beats, 2.7 s loop."""
    d = 2.7
    x = np.zeros(int((d + 1.5) * SR))
    for i in range(3):
        place(x, heartbeat() * (1 - 0.08 * i), i * 0.9)
    x = lp(x, 160, 2) * 2 + lp(x, 900, 1) * 0.2     # felt through a wall more than heard
    return wrapadd(reverb(x, 0.9, 0.3), d)


def murmur_loop():
    """student_murmur: the student mumbles under their breath, half voice, half whisper. 6.5 s loop."""
    d = 6.5
    t = secs(d + 1)
    x = np.zeros(len(t))
    pos = 0.15
    vowels = [(350, 900), (600, 1100), (450, 1700), (300, 2100), (650, 1300)]
    while pos < d - 0.3:
        sd = rng.uniform(0.15, 0.35)
        tt = secs(sd)
        f1, f2 = vowels[rng.integers(len(vowels))]
        voice = osc(105 * (1 + 0.08 * np.sin(2 * np.pi * rng.uniform(1, 3) * tt) - 0.1 * tt / sd), sd, "saw")
        src = voice * 0.5 + noise(sd) * 0.6
        syl = formants(src, [f1, f2, 2600], [5, 7, 7], [1, 0.7, 0.25])
        if rng.random() < 0.35:
            syl = np.concatenate([hp(noise(0.07), 4200) * 0.5, syl])
        place(x, syl * np.sin(np.pi * np.linspace(0, 1, len(syl))) ** 1.2 * rng.uniform(0.5, 1), pos)
        pos += len(syl) / SR + (rng.uniform(0.02, 0.15) if rng.random() < 0.75 else rng.uniform(0.5, 1.1))
    return wrapadd(reverb(lp(x, 3500), 0.6, 0.15), d)


def gale_loop():
    """The rising storm before the tornado: howling, gusting wind. 10 s loop."""
    d = 11
    t = secs(d)
    x = np.zeros(len(t))
    for fc, rate, ph, a in [(250, 0.3, 0, 1.2), (700, 0.45, 1, 1), (1400, 0.7, 3, 0.7), (3000, 1.1, 5, 0.3)]:
        gust = 0.55 + 0.45 * np.sin(2 * np.pi * rate * t + ph) * np.sin(2 * np.pi * rate * 0.61 * t + ph * 2)
        x += bp(noise(d), fc, 1.2) * gust * a
    # howl: narrow resonances sliding around
    for base in (420, 610):
        howl_f = base * (1 + 0.15 * np.sin(2 * np.pi * 0.23 * t + base))
        howl = np.zeros(len(t))
        n = noise(d)
        for k in range(0, len(t), 4096):  # piecewise narrow band
            seg = n[k: k + 8192]
            howl[k: k + len(seg)] += bp(seg * np.hanning(len(seg)), howl_f[k], 25)[: len(t) - k]
        x += howl * 1.5
    x += lp(noise(d), 90, 3) * 4
    return loopify(x)


def tornado_loop():
    """The tornado itself: a roaring, churning wall of air and grit. 6 s loop."""
    d = 7
    t = secs(d)
    roar = lp(noise(d), 300, 2) * 5 * (0.8 + 0.2 * np.sin(2 * np.pi * 3.1 * t))
    churn = bp(noise(d), 900, 1) * (0.6 + 0.4 * np.sin(2 * np.pi * 5.3 * t) ** 2) * 1.5
    hiss = hp(noise(d), 3000) * 0.5
    rumble = osc(31 + 3 * np.sin(2 * np.pi * 0.5 * t), d, "saw")
    rumble = lp(rumble, 120) * 1.5
    grit = np.zeros(len(t))
    for at in rng.uniform(0, d - 0.05, 260):   # debris and sand pelting
        place(grit, bp(noise(0.015), rng.uniform(1500, 5000), 3) * env_ad(0.015, 0.0005, 10) * rng.uniform(0.2, 1), at)
    x = np.tanh((roar + churn + hiss + rumble + grit * 1.5) * 0.7)
    return loopify(x)


def tornado_hit():
    """Caught: swallowed by the storm, then torn away."""
    d = 2.6
    t = secs(d)
    swell = lp(noise(d), 1500) * np.exp(-t * 1.6) * 3
    whoosh = (bp(noise(d), 500, 1) * (t < 0.4) + bp(noise(d), 1800, 1) * (t >= 0.4)) * np.exp(-t * 2) * 2
    thud = np.sin(2 * np.pi * (60 * np.exp(-t * 4) + 25) * t) * np.exp(-t * 2.5) * 1.5
    x = np.tanh((swell + whoosh + thud) * 0.9) * np.clip(t / 0.02, 0, 1)
    return fade(reverb(x, 2.0, 0.35)[: len(t)])


# ----------------------------------------------------------------------------- build
def main():
    print("writing to", OUT)
    save("amb_night", amb_night(), -3)
    save("amb_wind", amb_wind(), -3)
    save("amb_dread", amb_dread(), -3)
    for i in range(4):
        save(f"step_{i + 1}", step(i), -6)
    save("jump", jump(), -8)
    save("land", land(), -6)
    save("bark_1", bark(0), -2)
    save("bark_2", bark(1), -2)
    save("bark_wrong_echo", bark_wrong_echo(), -2)
    save("meow", meow(), -3)
    save("meow_wrong", meow(True), -3)
    save("loop_seam", loop_seam(), -10)
    save("turn_back", turn_back(), -1)
    save("wrong", wrong(), -0.5)
    for i in range(8):
        save(f"chime_{i + 1}", chime(i), -6)
    save("escape", escape(), -2)
    save("heartbeat", heartbeat(), -2)
    for i in range(3):
        save(f"glitch_{i + 1}", glitch(i), -6)
    save("lamp_hum_loop", lamp_hum(), -6)
    save("lamp_hum_bad_loop", lamp_hum(True), -6)
    save("lamp_creak", lamp_creak(), -3)
    save("lamp_die", lamp_die(), -4)
    save("shop_radio_loop", shop_radio(), -4)
    save("shop_radio_warped_loop", shop_radio(True), -4)
    save("clock_tick_loop", clock_tick(), -6)
    save("clock_tick_reverse_loop", clock_tick(True), -6)
    save("door_creak", door_creak(), -3)
    save("shop_inside_loop", shop_inside(), -4)
    save("glass_knock", glass_knock(), -3)
    save("whisper_loop", whisper(), -4)
    save("eyes_drone_loop", eyes_drone(), -3)
    save("marker_squeak", marker_squeak(), -5)
    save("heartbeat_loop", heartbeat_loop(), -2)
    save("murmur_loop", murmur_loop(), -4)
    save("gale_loop", gale_loop(), -3)
    save("tornado_loop", tornado_loop(), -2)
    save("tornado_hit", tornado_hit(), -1)


if __name__ == "__main__":
    main()
