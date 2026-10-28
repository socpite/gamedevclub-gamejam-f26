"""CMU-Q / Qatar themed parallax background for the Scottie sprites.

Layers (each 1920x1080, each tiles seamlessly left-right):
  01_sky.png             static: dusk gradient + sun
  02_doha_skyline.png    far:   West Bay towers, Aspire torch, MIA, sea + dhows
  03_education_city.png  mid:   CMU-Q building, Education City mosque, QNL, desert-rose museum, palms
  04_ground.png          near:  paved walkway with an 8-point-star frieze
"""
import math, os, random
import numpy as np
from PIL import Image, ImageDraw

W, H = 1920, 1080
S = 2                      # supersample
GROUND_Y = 906             # where the dog's feet stand
OUT = "qatar_background"
os.makedirs(OUT, exist_ok=True)
rnd = random.Random(7)

def new():
    return Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))

def sc(pts):
    return [(x * S, y * S) for x, y in pts]

def wrapped(fn, x, *a, **k):
    """draw element at x and its copies one tile left/right so layers loop seamlessly"""
    for off in (-W, 0, W):
        fn(x + off, *a, **k)

def finish(img, name):
    img = img.resize((W, H), Image.LANCZOS)
    img.save(os.path.join(OUT, name), optimize=True)
    return img

# ------------------------------------------------------------------ palette
SKY = [(0.00, (178, 160, 214)), (0.38, (226, 182, 204)), (0.58, (250, 204, 170)), (0.70, (253, 228, 182)), (1.0, (253, 232, 190))]
SUN = (255, 244, 214)
FAR_BACK = (214, 186, 206)
FAR = (188, 158, 192)
SEA = (222, 198, 214)
SEA_LINE = (238, 218, 226)
DHOW = (160, 128, 164)
MID = (170, 124, 140)
MID_DARK = (146, 102, 122)
MID_LIGHT = (210, 168, 170)
MID_GROUND = (190, 144, 140)
MAROON = (138, 21, 56)         # Qatar flag
WHITE = (250, 244, 240)
PAVE = (232, 196, 150)
PAVE_LIP = (247, 222, 182)
PAVE_SEAM = (212, 172, 128)
SAND = (204, 158, 112)
SAND_DARK = (186, 138, 96)

# ------------------------------------------------------------------ 01 sky
def sky():
    t = np.linspace(0, 1, H * S)
    cols = np.zeros((H * S, 3))
    for (t0, c0), (t1, c1) in zip(SKY, SKY[1:]):
        m = (t >= t0) & (t <= t1)
        f = ((t[m] - t0) / (t1 - t0))[:, None]
        cols[m] = np.array(c0) * (1 - f) + np.array(c1) * f
    arr = np.repeat(cols[:, None, :], W * S, axis=1).astype(np.uint8)
    img = Image.fromarray(arr, "RGB").convert("RGBA")
    # sun with soft glow
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    cx, cy, r = 1290 * S, 640 * S, 118 * S
    for i in range(30, 0, -1):
        rr = r + i * 9 * S
        g.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=SUN + (int(5 + (30 - i) * 0.6),))
    img.alpha_composite(glow)
    ImageDraw.Draw(img).ellipse((cx - r, cy - r, cx + r, cy + r), fill=SUN + (255,))
    return img

# ------------------------------------------------------------------ 02 skyline
HORIZON = 712

def skyline():
    img = new(); d = ImageDraw.Draw(img)
    base = HORIZON

    def box(x, w, h, col, top="flat"):
        if top == "flat":
            pts = [(x, base), (x, base - h), (x + w, base - h), (x + w, base)]
        elif top == "slant":
            pts = [(x, base), (x, base - h), (x + w, base - h + w * 0.45), (x + w, base)]
        elif top == "point":
            pts = [(x, base), (x, base - h), (x + w / 2, base - h - w * 0.9), (x + w, base - h), (x + w, base)]
        elif top == "step":
            pts = [(x, base), (x, base - h), (x + w * .3, base - h), (x + w * .3, base - h - 26),
                   (x + w * .7, base - h - 26), (x + w * .7, base - h), (x + w, base - h), (x + w, base)]
        d.polygon(sc(pts), fill=col)

    def doha_tower(x, col):          # rounded-top cylinder
        w, h = 66, 360
        d.rectangle(sc([(x, base - h), (x + w, base)]), fill=col)
        d.ellipse(sc([(x, base - h - 40), (x + w, base - h + 40)]), fill=col)
        d.line(sc([(x + w / 2, base - h - 40), (x + w / 2, base - h - 95)]), fill=col, width=4 * S)

    def tornado(x, col):             # hyperboloid
        w, h = 96, 330
        pts_l, pts_r = [], []
        for i in range(41):
            t = i / 40
            hw = w / 2 * (0.72 + 0.28 * (2 * t - 1) ** 2)
            y = base - t * h
            pts_l.append((x + w / 2 - hw, y)); pts_r.append((x + w / 2 + hw, y))
        d.polygon(sc(pts_l + pts_r[::-1]), fill=col)

    def torch(x, col):               # Aspire tower
        h = 430
        d.polygon(sc([(x - 22, base), (x - 13, base - h + 70), (x + 13, base - h + 70), (x + 22, base)]), fill=col)
        d.polygon(sc([(x - 13, base - h + 70), (x - 34, base - h + 22), (x - 26, base - h + 8),
                      (x + 26, base - h + 8), (x + 34, base - h + 22), (x + 13, base - h + 70)]), fill=col)
        d.polygon(sc([(x - 18, base - h + 8), (x, base - h - 60), (x + 18, base - h + 8)]), fill=col)

    def mia(x, col):                 # Museum of Islamic Art, stepped cube
        d.rectangle(sc([(x, base - 46), (x + 230, base)]), fill=col)
        d.rectangle(sc([(x + 45, base - 104), (x + 185, base - 46)]), fill=col)
        d.rectangle(sc([(x + 80, base - 150), (x + 150, base - 104)]), fill=col)
        d.polygon(sc([(x + 92, base - 150), (x + 104, base - 166), (x + 126, base - 166), (x + 138, base - 150)]), fill=col)
        d.ellipse(sc([(x + 106, base - 136), (x + 124, base - 118)]), fill=SKY[2][1])

    # back row (lighter, lower)
    x = 0
    while x < W:
        w = rnd.randint(40, 90); h = rnd.randint(60, 180)
        wrapped(lambda xx: box(xx, w, h, FAR_BACK, rnd.choice(["flat", "slant", "flat"])), x)
        x += w + rnd.randint(-10, 30)
    # West Bay cluster
    cluster = [(210, 70, 230, "slant"), (290, 60, 300, "point"), (360, 80, 260, "flat"),
               (540, 70, 280, "step"), (620, 54, 340, "point"), (684, 54, 340, "point"),
               (760, 90, 210, "flat"), (860, 60, 250, "slant"), (930, 76, 180, "flat"),
               (40, 80, 150, "flat"), (120, 70, 190, "step")]
    for cx, w, h, top in cluster:
        wrapped(lambda xx: box(xx, w, h, FAR, top), cx)
    wrapped(lambda xx: doha_tower(xx, FAR), 450)
    wrapped(lambda xx: tornado(xx, FAR), 1010)
    wrapped(lambda xx: torch(xx, FAR), 1720)
    wrapped(lambda xx: mia(xx, FAR), 1440)

    # sea
    d.rectangle(sc([(0, base), (W, 800)]), fill=SEA)
    for i in range(40):
        y = rnd.uniform(base + 8, 795); x0 = rnd.uniform(0, W); L = rnd.uniform(40, 160)
        wrapped(lambda xx: d.line(sc([(xx, y), (xx + L, y)]), fill=SEA_LINE, width=2 * S), x0)

    def dhow(x, y, s):
        d.polygon(sc([(x - 70 * s, y - 14 * s), (x + 80 * s, y - 20 * s), (x + 55 * s, y), (x - 50 * s, y)]), fill=DHOW)
        d.line(sc([(x, y - 16 * s), (x + 4 * s, y - 120 * s)]), fill=DHOW, width=max(2, int(4 * s)) * S)
        d.polygon(sc([(x - 60 * s, y - 30 * s), (x + 70 * s, y - 130 * s), (x + 8 * s, y - 24 * s)]), fill=DHOW)
    for x, y, s in [(330, 770, 0.55), (1180, 785, 0.75), (1620, 760, 0.45)]:
        wrapped(lambda xx: dhow(xx, y, s), x)
    return img

# ------------------------------------------------------------------ 03 Education City
MID_BASE = 868

def education_city():
    img = new(); d = ImageDraw.Draw(img)
    b = MID_BASE

    def mosque(x):
        # low prayer hall + two tall leaning minarets
        d.rounded_rectangle(sc([(x, b - 64), (x + 300, b)]), radius=30 * S, fill=MID)
        d.pieslice(sc([(x + 90, b - 130), (x + 210, b - 10)]), 180, 360, fill=MID)
        for bx, lean in ((x + 40, 26), (x + 262, -26)):
            d.polygon(sc([(bx - 15, b - 40), (bx - 7 + lean, b - 360), (bx + 7 + lean, b - 360), (bx + 15, b - 40)]), fill=MID)
            d.polygon(sc([(bx - 7 + lean, b - 360), (bx + lean, b - 384), (bx + 7 + lean, b - 360)]), fill=MID)
        for i in range(6):
            ax = x + 62 + i * 34
            d.rounded_rectangle(sc([(ax, b - 44), (ax + 16, b - 12)]), radius=8 * S, fill=MID_LIGHT)

    def cmuq(x):
        # long low courtyard building with a taller central atrium block
        d.rectangle(sc([(x, b - 118), (x + 560, b)]), fill=MID)
        d.rectangle(sc([(x - 6, b - 128), (x + 566, b - 116)]), fill=MID_DARK)
        d.rectangle(sc([(x + 200, b - 196), (x + 360, b - 118)]), fill=MID)
        d.rectangle(sc([(x + 194, b - 206), (x + 366, b - 194)]), fill=MID_DARK)
        for i in range(4):  # atrium glazing
            wx = x + 216 + i * 36
            d.rectangle(sc([(wx, b - 182), (wx + 20, b - 126)]), fill=MID_LIGHT)
        for i in range(15):  # tall slot windows
            if 6 <= i <= 8:
                continue
            wx = x + 22 + i * 36
            d.rectangle(sc([(wx, b - 98), (wx + 14, b - 30)]), fill=MID_LIGHT)
        # entrance
        d.rectangle(sc([(x + 240, b - 92), (x + 320, b)]), fill=MID_DARK)

    def library(x):
        # Qatar National Library: one long slab rising to the right over a glass base
        d.polygon(sc([(x + 30, b), (x + 30, b - 22), (x + 410, b - 148), (x + 410, b)]), fill=MID_LIGHT)
        for i in range(9):
            gx = x + 70 + i * 40
            gy = b - 22 - (gx - x - 30) * (126 / 380)
            d.line(sc([(gx, gy), (gx, b)]), fill=MID, width=3 * S)
        d.polygon(sc([(x, b - 30), (x + 430, b - 178), (x + 440, b - 150), (x + 20, b - 8)]), fill=MID)
        d.rectangle(sc([(x, b - 30), (x + 22, b)]), fill=MID)

    def desert_rose(x):
        # National Museum: interlocking tilted discs
        discs = [(0, 0, 120, 26, -12), (60, -40, 100, 22, 18), (-50, -30, 90, 20, -30),
                 (20, -80, 80, 18, 8), (110, 0, 80, 20, 25), (-100, 4, 70, 18, 10)]
        for dx, dy, rx, ry, ang in discs:
            a = math.radians(ang)
            pts = []
            for i in range(48):
                t = 2 * math.pi * i / 48
                px, py = rx * math.cos(t), ry * math.sin(t)
                pts.append((x + dx + px * math.cos(a) - py * math.sin(a), b - 40 + dy + px * math.sin(a) + py * math.cos(a)))
            d.polygon(sc(pts), fill=MID, outline=MID_LIGHT, width=2 * S)
        d.rectangle(sc([(x - 120, b - 30), (x + 160, b)]), fill=MID)

    def palm(x, h, lean, col=MID_DARK):
        pts = []
        for i in range(13):
            t = i / 12
            pts.append((x + lean * t * t, b - h * t))
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            d.line(sc([(x0, y0), (x1, y1)]), fill=col, width=int(10 - 4 * (y0 - b) / -h) * S)
        tx, ty = pts[-1]
        for k in range(8):
            ang = math.radians(-160 + k * 40 + rnd.uniform(-8, 8))
            L = rnd.uniform(60, 82)
            leaf = []
            for i in range(10):
                t = i / 9
                lx = tx + math.cos(ang) * L * t
                ly = ty + math.sin(ang) * L * t * 0.6 + 34 * t * t
                leaf.append((lx, ly))
            top = [(px, py - 7 * math.sin(math.pi * i / 9)) for i, (px, py) in enumerate(leaf)]
            bot = [(px, py + 7 * math.sin(math.pi * i / 9)) for i, (px, py) in enumerate(leaf)]
            d.polygon(sc(top + bot[::-1]), fill=col)

    # rolling ground behind the walkway
    pts = [(0, H)]
    for i in range(0, W + 1, 8):
        pts.append((i, b - 14 + 8 * math.sin(2 * math.pi * i / W * 3) + 4 * math.sin(2 * math.pi * i / W * 7)))
    pts.append((W, H))
    d.polygon(sc(pts), fill=MID_GROUND)

    wrapped(mosque, 90)
    wrapped(cmuq, 560)
    wrapped(library, 1250)
    wrapped(desert_rose, 1780)
    for x, h, lean in [(470, 170, 14), (520, 140, -10), (1150, 190, -16), (1210, 150, 12), (1700, 160, 10), (60, 150, -12)]:
        wrapped(lambda xx: palm(xx, h, lean), x)
    return img

# ------------------------------------------------------------------ 04 ground
def ground():
    img = new(); d = ImageDraw.Draw(img)
    y0 = GROUND_Y
    d.rectangle(sc([(0, y0), (W, H)]), fill=SAND)
    d.rectangle(sc([(0, y0), (W, y0 + 52)]), fill=PAVE)
    d.rectangle(sc([(0, y0), (W, y0 + 7)]), fill=PAVE_LIP)
    for x in range(0, W, 96):                    # paving seams (20 per tile -> seamless)
        d.line(sc([(x, y0 + 8), (x, y0 + 52)]), fill=PAVE_SEAM, width=3 * S)
    d.rectangle(sc([(0, y0 + 52), (W, y0 + 58)]), fill=PAVE_SEAM)

    # 8-point star frieze (two overlapping squares), 16 per tile
    fy = y0 + 104
    for i in range(16):
        cx = 60 + i * 120
        for rot in (0, 45):
            pts = []
            for k in range(4):
                a = math.radians(rot + 45 + 90 * k)
                pts.append((cx + 26 * math.cos(a), fy + 26 * math.sin(a)))
            d.polygon(sc(pts), fill=SAND_DARK)
        d.ellipse(sc([(cx - 9, fy - 9), (cx + 9, fy + 9)]), fill=SAND)
        d.polygon(sc([(cx + 50, fy), (cx + 60, fy - 10), (cx + 70, fy), (cx + 60, fy + 10)]), fill=SAND_DARK)
    d.rectangle(sc([(0, fy + 48), (W, fy + 54)]), fill=SAND_DARK)
    d.rectangle(sc([(0, fy - 54), (W, fy - 48)]), fill=SAND_DARK)
    return img

# ------------------------------------------------------------------ build
L = {
    "sky": finish(sky(), "01_sky.png"),
    "far": finish(skyline(), "02_doha_skyline.png"),
    "mid": finish(education_city(), "03_education_city.png"),
    "near": finish(ground(), "04_ground.png"),
}

# preview: composite + dog standing on the walkway
dog_dir = "scottie_frames"
def dog(name, i):
    return Image.open(os.path.join(dog_dir, name, f"{name}_{i:02d}.png")).convert("RGBA")

comp = L["sky"].copy()
for k in ("far", "mid", "near"):
    comp.alpha_composite(L[k])
DOG_SCALE = 1.0
CELL_GROUND = 230
comp.alpha_composite(dog("idle", 1), (700, GROUND_Y - CELL_GROUND))
comp.convert("RGB").save(os.path.join(OUT, "preview.png"))

# scrolling parallax GIF with the dog walking
SPEEDS = {"far": 1, "mid": 4, "near": 12}   # px per frame at 1920 wide
frames = []
N = 112
for f in range(N):
    fr = L["sky"].copy()
    for k in ("far", "mid", "near"):
        off = (f * SPEEDS[k]) % W
        fr.alpha_composite(L[k], (-off, 0))
        fr.alpha_composite(L[k], (W - off, 0))
    name, n = ("running", 6) if f >= N // 2 else ("walking", 8)
    fr.alpha_composite(dog(name, f % n + 1), (700, GROUND_Y - CELL_GROUND))
    frames.append(fr.resize((800, 450), Image.LANCZOS).convert("RGB").quantize(128))
frames[0].save(os.path.join(OUT, "parallax_preview.gif"), save_all=True, append_images=frames[1:], duration=70, loop=0)
print("done")
