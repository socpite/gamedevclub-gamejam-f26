"""
Scotty: After Hours
===================
A looping-street horror game built on the Scotty starter.

Scotty walks the same Education City street again and again.
  If something is wrong, turn back.
  If nothing is wrong, keep going.
Make the right call 8 times in a row to get out. Every loop the street gets a little darker.

Controls
  Left / Right  or  A / D   walk
  Hold Shift                run
  Space / Up / W            jump
  B                         bark
  M                         mute sound
  F1                        toggle debug info
  F2                        (debug) cycle this loop's anomaly
  Esc                       quit

Expected folder layout (assets/ next to this file):
  assets/scotty_frames/<anim>/<anim>_01.png ...   (idle, walking, running, jumping, barking)
  assets/background/01_sky.png ... 04_ground.png
  assets/decor/*.png, assets/characters/*.png

Requires: pip install pygame-ce   (or classic "pygame" on Python <= 3.13)
"""
import math
import os
import random
import sys

import pygame

from audio import GameAudio

# ----------------------------------------------------------------------------- config
SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
TITLE = "Scotty: After Hours"

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(HERE, "assets")
FRAMES_DIR = os.path.join(ASSETS_DIR, "scotty_frames")
BG_DIR = os.path.join(ASSETS_DIR, "background")

# Background art is 1920x1080; scale everything to fit the window height.
ART_SCALE = SCREEN_H / 1080
GROUND_Y = int(906 * ART_SCALE)      # top of the walkway in the background art

# Sprite frames are 256x256 with the feet at y=230 inside the cell.
SPRITE_SCALE = ART_SCALE
SPRITE_FEET_Y = 230

# (filename, scroll factor) -- 0 = static, 1 = moves with the world
PARALLAX_LAYERS = [
    ("01_sky.png", 0.0),
    ("02_doha_skyline.png", 0.1),
    ("03_education_city.png", 0.35),
    ("04_ground.png", 1.0),
]
SKYLINE_LAYERS = (1, 2)              # layers that freeze during the "frozen_skyline" anomaly

# Animation name -> (frames per second, loops?)
ANIMATIONS = {
    "idle":    (8, True),
    "walking": (12, True),
    "running": (14, True),
    "jumping": (14, False),
    "barking": (12, False),
}

WALK_SPEED = 220     # px/s
RUN_SPEED = 420
JUMP_VELOCITY = -720
GRAVITY = 2000

# ----------------------------------------------------------------------------- street / horror config
# One loop of the street. A multiple of the ground layer width (1280) so the floor tiles seamlessly.
SEGMENT_LEN = 3 * 1280
START_X = 320                        # where Scotty appears at the start of a loop
GOAL_LOOPS = 8                       # correct calls in a row needed to escape
ANOMALY_CHANCE = 0.5

# Decor placement along one loop: (kind, world x of the sprite's centre)
STREET_LAYOUT = [
    ("sign", 150),
    ("palm", 450),
    ("lamp", 650),
    ("bench", 950),
    ("palm", 1300),
    ("lamp", 1700),
    ("whiteboard", 2050),
    ("lamp", 3350),
    ("bench", 3600),
]
LAMP_XS = [x for kind, x in STREET_LAYOUT if kind == "lamp"]
STUDENT_X = 2450
EXTRA_BENCH_X = 1500
MISSING_PALM_X = 1300
SHOP_X = 2950                        # centre of the coffee shop
SHOP_W, SHOP_H = 400, 300

ANOMALIES = [
    "student_watching",   # the student turns to face Scotty, and moves when you're not looking
    "student_eyes",       # the student is taller, with glowing red eyes
    "extra_bench",
    "missing_palm",
    "whiteboard",         # the whiteboard has a message for you
    "frozen_skyline",     # the city in the background stops moving
    # lamps
    "lamps_off",
    "lamp_red",           # one lamp burns red
    "lamp_tall",          # one lamp is taller than the others
    "lamp_tilt",          # one lamp leans
    "lamp_missing",       # one lamp is gone
    # coffee shop: small details
    "shop_sign",          # the shop name is misspelled
    "shop_cups",          # one cup is missing from the window
    "shop_open",          # the door sign is wrong
    "shop_door",          # the door is open, and something is inside
    "shop_figure",        # someone stands in the window, watching
    "shop_dark",          # the shop lights are off
    "shop_clock",         # the clock runs backwards
    "shop_menu",          # the price changed
    # sound only: nothing looks wrong, you have to listen (see audio.py)
    "student_murmur",     # the student with the karak mutters under their breath
    "wind_stops",         # the wind drops dead
    "cafe_heartbeat",     # a heartbeat behind the café walls
]
CAT_CHANCE = 1 / 20       # chance each loop that Scotty is... not Scotty
TORNADO_CHANCE = 1 / 20   # chance each loop that the wind keeps rising until a tornado comes for Scotty
TORNADO_DELAY = 9.0       # seconds of rising wind before it appears
TORNADO_SPEED = 320       # px/s: faster than walking, slower than running
TORNADO_REACH = 70        # px: this close and Scotty is caught
NORMAL_BOARD = None       # draw the whiteboard art as-is
ANOMALY_BOARDS = ["TURN BACK", "SCOTTY\nGO HOME", "WHY ARE YOU\nSTILL HERE", "IT'S BEHIND\nYOU"]
SHOP_SIGN = "KARAK HOUSE"
SHOP_SIGN_TYPOS = ["KARAK HOSUE", "KRAAK HOUSE", "KARAK HOUND", "KARAK HOME"]

# Corruption 0..1: how dark / wrong the world looks. Only correct calls raise it: it scales with progress,
# from fully lit at Exit 0 to fully dark on the last loop, and a wrong call brings the lights back.
TINT_FULL = (150, 70, 95)            # colour multiplied over the world at full corruption
DARKNESS_FULL = 232                  # alpha of the darkness overlay at full corruption
LIGHT_RADIUS = (420, 190)            # Scotty's light radius at corruption 0 and 1
LAMP_RADIUS = 210


# ----------------------------------------------------------------------------- assets
def load_animations():
    """Load every frame folder in scotty_frames, scaled; returns {name: [right_frames, left_frames]}."""
    anims = {}
    for name in ANIMATIONS:
        folder = os.path.join(FRAMES_DIR, name)
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
        right = []
        for f in files:
            img = pygame.image.load(os.path.join(folder, f)).convert_alpha()
            size = (int(img.get_width() * SPRITE_SCALE), int(img.get_height() * SPRITE_SCALE))
            right.append(pygame.transform.smoothscale(img, size))
        left = [pygame.transform.flip(img, True, False) for img in right]
        anims[name] = (right, left)
    return anims


def load_layers():
    layers = []
    for filename, factor in PARALLAX_LAYERS:
        img = pygame.image.load(os.path.join(BG_DIR, filename)).convert_alpha()
        size = (int(img.get_width() * ART_SCALE), int(img.get_height() * ART_SCALE))
        layers.append((pygame.transform.smoothscale(img, size), factor))
    return layers


def load_image(rel_path, scale=SPRITE_SCALE):
    img = pygame.image.load(os.path.join(ASSETS_DIR, rel_path)).convert_alpha()
    size = (int(img.get_width() * scale), int(img.get_height() * scale))
    return pygame.transform.smoothscale(img, size)


def load_decor():
    return {
        "sign": load_image("decor/signpost_blank.png"),
        "lamp": load_image("decor/street_lamp.png"),
        "bench": load_image("decor/bench.png"),
        "palm": load_image("decor/date_palm.png"),
        "whiteboard": load_image("decor/whiteboard.png"),
        "student": load_image("characters/student_hoodie_karak.png"),
        "cup": load_image("powerups/karak_cup.png", 0.36),
        "dallah": load_image("powerups/dallah_coffee_pot.png", 0.42),
    }


def draw_text(surface, font, text, pos, color=(240, 232, 236), center=False, panel=True):
    """Outlined text on a dark translucent panel, so it stays readable on the bright and the dark street."""
    lines = [(font.render(line, True, color), font.render(line, True, (10, 5, 10))) for line in text.split("\n")]
    lh = font.get_linesize()
    rects = []
    for i, (img, _) in enumerate(lines):
        rect = img.get_rect()
        if center:
            rect.midtop = (pos[0], pos[1] + i * lh)
        else:
            rect.topleft = (pos[0], pos[1] + i * lh)
        rects.append(rect)
    if panel:
        box = rects[0].unionall(rects[1:]).inflate(36, 20)
        bg = pygame.Surface(box.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (8, 4, 12, 170), bg.get_rect(), border_radius=12)
        surface.blit(bg, box)
    for (img, outline), rect in zip(lines, rects):
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (2, 2)):
            surface.blit(outline, rect.move(dx, dy))
        surface.blit(img, rect)


# ----------------------------------------------------------------------------- animation
class Animator:
    def __init__(self, anims):
        self.anims = anims
        self.name = "idle"
        self.time = 0.0
        self.finished = False

    def play(self, name, restart=False):
        if name != self.name or restart:
            self.name = name
            self.time = 0.0
            self.finished = False

    def update(self, dt):
        self.time += dt
        fps, loops = ANIMATIONS[self.name]
        if not loops and self.time * fps >= len(self.anims[self.name][0]):
            self.finished = True

    def frame(self, facing_right):
        frames = self.anims[self.name][0 if facing_right else 1]
        fps, loops = ANIMATIONS[self.name]
        index = int(self.time * fps)
        if loops:
            index %= len(frames)
        return frames[min(index, len(frames) - 1)]


# ----------------------------------------------------------------------------- player
class Scotty:
    def __init__(self, anims, x):
        self.anim = Animator(anims)
        self.x = x                 # world x of the sprite's centre
        self.y = GROUND_Y          # world y of the feet
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.facing_right = True
        self.barking = False
        self.walk_dist = 0.0       # drives the cat's leg cycle

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w) and self.on_ground:
            self.vy = JUMP_VELOCITY
            self.on_ground = False
            self.barking = False
            self.anim.play("jumping", restart=True)
        elif event.key == pygame.K_b and self.on_ground:
            self.barking = True
            self.anim.play("barking", restart=True)

    def update(self, dt, keys):
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]

        direction = right - left
        if self.barking:
            direction = 0
        speed = RUN_SPEED if running else WALK_SPEED
        self.vx = direction * speed
        if direction:
            self.facing_right = direction > 0

        # physics
        self.x += self.vx * dt
        self.walk_dist += abs(self.vx) * dt
        if not self.on_ground:
            self.vy += GRAVITY * dt
            self.y += self.vy * dt
            if self.y >= GROUND_Y:
                self.y = GROUND_Y
                self.vy = 0
                self.on_ground = True

        # pick animation
        if not self.on_ground:
            self.anim.play("jumping")
            # map jump frames onto the arc instead of time: rising -> early frames, falling -> later frames
            n = len(self.anim.anims["jumping"][0])
            t = (self.vy - JUMP_VELOCITY) / (-2 * JUMP_VELOCITY)   # 0 at take-off, 1 at landing
            self.anim.time = max(0.0, min(n - 1, t * n)) / ANIMATIONS["jumping"][0]
        elif self.barking:
            if self.anim.finished:
                self.barking = False
        elif direction:
            self.anim.play("running" if running else "walking")
        else:
            self.anim.play("idle")

        if self.on_ground:
            self.anim.update(dt)

    def draw(self, surface, camera_x, as_cat=False, t=0.0):
        if as_cat:
            draw_cat(surface, (self.x - camera_x, self.y), self.facing_right, self.walk_dist / 14,
                     self.vx != 0, not self.on_ground, t)
            return
        img = self.anim.frame(self.facing_right)
        feet_offset = int(SPRITE_FEET_Y * SPRITE_SCALE)
        rect = img.get_rect()
        rect.centerx = int(self.x - camera_x)
        rect.top = int(self.y) - feet_offset
        surface.blit(img, rect)


def draw_cat(surface, feet_pos, facing_right, phase, moving, airborne, t):
    """A black cat in Scotty's silhouette style, wearing his red bandana. Drawn facing right, then flipped."""
    surf = pygame.Surface((240, 180), pygame.SRCALPHA)
    black = (14, 11, 16)
    feet_y = 168
    for i, lx in enumerate((72, 86, 150, 164)):          # back legs, then front legs
        if airborne:
            dx = 12 if lx > 120 else -12
        elif moving:
            dx = math.sin(phase + (0 if i in (0, 3) else math.pi)) * 11
        else:
            dx = 0
        pygame.draw.line(surf, black, (lx, 120), (lx + dx, feet_y - 4), 10)
        pygame.draw.circle(surf, black, (int(lx + dx), feet_y - 4), 6)
    pygame.draw.ellipse(surf, black, (55, 88, 125, 50))
    tail = [(62 - 34 * s + math.sin(s * 3 + t * 2.5) * 10 * s, 104 - 78 * s) for s in (k / 11 for k in range(12))]
    pygame.draw.lines(surf, black, False, tail, 9)
    pygame.draw.circle(surf, black, (int(tail[-1][0]), int(tail[-1][1])), 5)
    pygame.draw.ellipse(surf, black, (145, 70, 40, 50))
    pygame.draw.circle(surf, black, (172, 72), 26)
    pygame.draw.polygon(surf, black, [(150, 62), (154, 28), (172, 50)])
    pygame.draw.polygon(surf, black, [(174, 48), (192, 26), (195, 64)])
    pygame.draw.polygon(surf, (190, 30, 35), [(150, 96), (180, 100), (166, 116)])
    for ex in (178, 191):
        pygame.draw.ellipse(surf, (215, 235, 90), (ex - 3, 63, 7, 11))
        pygame.draw.line(surf, black, (ex, 65), (ex, 71), 2)
    if not facing_right:
        surf = pygame.transform.flip(surf, True, False)
    surface.blit(surf, surf.get_rect(midbottom=(int(feet_pos[0]), int(feet_pos[1]) + 180 - feet_y)))


# ----------------------------------------------------------------------------- background
def draw_parallax(surface, layers, scroll_x, frozen=()):
    for i, (img, factor) in enumerate(layers):
        if i in frozen:
            factor = 0.0
        w = img.get_width()
        offset = -int(scroll_x * factor) % w
        surface.blit(img, (offset - w, 0))
        surface.blit(img, (offset, 0))
        if offset + w < SCREEN_W:      # only needed if the window is wider than the layer
            surface.blit(img, (offset + w, 0))


# ----------------------------------------------------------------------------- street
class Loop:
    """Everything that can differ between two walks down the street."""

    def __init__(self, anomaly=None):
        self.anomaly = anomaly
        self.student_x = float(STUDENT_X)
        self.board_text = random.choice(ANOMALY_BOARDS) if anomaly == "whiteboard" else NORMAL_BOARD
        self.lamp_index = random.randrange(len(LAMP_XS))       # which lamp a lamp_* anomaly hits
        self.lamp_tilt = random.choice((-9, 9))
        self.shop_sign = random.choice(SHOP_SIGN_TYPOS) if anomaly == "shop_sign" else SHOP_SIGN
        self.open_text = random.choice(("CLOSED", "NEPO")) if anomaly == "shop_open" else "OPEN"
        self.storm_time = 0.0                                   # tornado loop: seconds the wind has been rising
        self.tornado_x = None                                   # world x of the tornado once it appears

    @property
    def storm(self):
        """0..1: how far the wind has risen towards the tornado."""
        return min(1.0, self.storm_time / TORNADO_DELAY) if self.anomaly == "tornado" else 0.0

    def shop_key(self):
        """The static look of the coffee shop; one cached image per distinct key."""
        a = self.anomaly
        return (self.shop_sign, 2 if a == "shop_cups" else 3, self.open_text, a != "shop_dark",
                a == "shop_figure", a == "shop_door", "99 QR" if a == "shop_menu" else "1 QR")

    def items(self):
        items = list(STREET_LAYOUT)
        if self.anomaly == "extra_bench":
            items.append(("bench", EXTRA_BENCH_X))
        if self.anomaly == "missing_palm":
            items.remove(("palm", MISSING_PALM_X))
        return items


class Street:
    """The looping street: the loop Scotty is in, the ones on either side, and how far Scotty has got."""

    def __init__(self, decor):
        self.decor = decor
        lamp = decor["lamp"]
        self.dark_lamp = lamp.copy()
        self.dark_lamp.fill((70, 60, 75), special_flags=pygame.BLEND_RGB_MULT)
        self.red_lamp = lamp.copy()
        self.red_lamp.fill((255, 90, 90), special_flags=pygame.BLEND_RGB_MULT)
        self.tall_lamp = pygame.transform.smoothscale(lamp, (lamp.get_width(), int(lamp.get_height() * 1.35)))
        self.sign_font = pygame.font.SysFont(None, int(34 * SPRITE_SCALE * 1.5))
        self.board_font = pygame.font.SysFont(None, int(30 * SPRITE_SCALE * 1.5))
        self.shop_font = pygame.font.SysFont(None, 38)
        self.small_font = pygame.font.SysFont(None, 21)
        self.sign_cache = {}
        self.board_cache = {}
        self.shop_cache = {}
        self.scotty_x = START_X
        self.reset()

    def reset(self):
        self.progress = 0          # correct calls in a row
        self.loops = 0             # loops entered so far
        self.fails = 0
        self.corruption = 0.0
        self.cur = Loop()
        self.prev = Loop()         # the loop Scotty just left (still visible behind him)
        self.normal = Loop()       # what the next loop looks like from a distance
        self.last_exit = None      # how Scotty left the last loop: "forward", "back" or "caught"

    @property
    def anomaly(self):
        return self.cur.anomaly

    # --- loop logic
    def start_loop(self, anomaly):
        self.prev, self.cur = self.cur, Loop(anomaly)

    def set_anomaly(self, anomaly):
        """Debug: swap the current loop's anomaly in place."""
        self.cur = Loop(anomaly)

    def roll_anomaly(self):
        # Exit 0 is always normal, so the player can (re)learn what the street should look like
        if self.loops <= 1 or self.progress == 0:
            return None
        if random.random() < CAT_CHANCE:
            return "cat"
        if random.random() < TORNADO_CHANCE:
            return "tornado"
        if random.random() > ANOMALY_CHANCE:
            return None
        return random.choice(ANOMALIES)

    def progress_if(self, went_forward):
        correct = (self.anomaly is None) == went_forward
        return self.progress + 1 if correct else 0

    def finish_loop(self, went_forward, caught=False):
        """Judge Scotty's choice and set up the next loop. Returns True if the call was right.
        Being caught by the tornado always counts as a wrong call."""
        new_progress = 0 if caught else self.progress_if(went_forward)
        self.last_exit = "caught" if caught else "forward" if went_forward else "back"
        correct = new_progress > 0
        self.progress = new_progress
        if not correct:
            self.fails += 1
        self.loops += 1
        self.start_loop(self.roll_anomaly())
        return correct

    @property
    def target_corruption(self):
        return min(1.0, self.progress / (GOAL_LOOPS - 1))

    def update(self, dt, scotty, camera_x):
        self.corruption += (self.target_corruption - self.corruption) * min(1.0, dt * 0.6)

        # the watching student only moves while it's off screen
        loop = self.cur
        if loop.anomaly == "student_watching":
            screen_x = loop.student_x - camera_x
            if not (-60 < screen_x < SCREEN_W + 60):
                gap = scotty.x - loop.student_x
                if abs(gap) > 260:
                    loop.student_x += math.copysign(110 * dt, gap)
            loop.student_x = max(700, min(SEGMENT_LEN - 700, loop.student_x))

    def update_tornado(self, dt, scotty, camera_x):
        """Tornado loop: the wind rises, then a tornado sweeps in from the right and chases Scotty.
        Returns True if it caught him."""
        loop = self.cur
        if loop.anomaly != "tornado":
            return False
        loop.storm_time += dt
        if loop.tornado_x is None:
            if loop.storm_time >= TORNADO_DELAY:
                loop.tornado_x = camera_x + SCREEN_W + 160
            return False
        loop.tornado_x += math.copysign(TORNADO_SPEED * dt, scotty.x - loop.tornado_x)
        return abs(scotty.x - loop.tornado_x) < TORNADO_REACH

    def frozen_layers(self):
        return SKYLINE_LAYERS if self.anomaly == "frozen_skyline" else ()

    def tiles(self):
        """(tile offset, loop, number on its sign) for the loop behind, this loop, and the loop ahead.
        The loop ahead already shows the number Scotty will get by walking forward."""
        return ((-1, self.prev, self.progress), (0, self.cur, self.progress), (1, self.normal, self.progress_if(True)))

    # --- lamps
    def lamp_info(self, loop, index, sx):
        """How lamp `index` looks in `loop`: (image, rect, head position or None if unlit, glow colour) or None."""
        a = loop.anomaly
        hit = index == loop.lamp_index
        if a == "lamp_missing" and hit:
            return None
        lamp = self.decor["lamp"]
        h = lamp.get_height()
        head_down = 60 * SPRITE_SCALE                 # lamp head, measured from the top of the image
        glow = None
        if a == "lamp_tilt" and hit:
            angle = math.radians(loop.lamp_tilt)
            img = pygame.transform.rotate(lamp, loop.lamp_tilt)
            # rotate about the foot of the pole rather than the image centre
            cx, cy = sx - h / 2 * math.sin(angle), GROUND_Y + 2 - h / 2 * math.cos(angle)
            arm = h / 2 - head_down
            return img, img.get_rect(center=(cx, cy)), (cx - arm * math.sin(angle), cy - arm * math.cos(angle)), None
        if a == "lamps_off":
            img = self.dark_lamp
        elif a == "lamp_tall" and hit:
            img = self.tall_lamp
            head_down *= 1.35
        elif a == "lamp_red" and hit:
            img, glow = self.red_lamp, (170, 20, 15)
        else:
            img = lamp
        rect = img.get_rect(midbottom=(int(sx), GROUND_Y + 2))
        head = None if a == "lamps_off" else (sx, rect.top + head_down)
        return img, rect, head, glow

    def lights(self, camera_x, t):
        """(screen pos, radius, glow colour) for every lit lamp and shop window (lamps flicker more over time)."""
        lights = []
        for tile, loop, _ in self.tiles():
            for i, x in enumerate(LAMP_XS):
                sx = x + tile * SEGMENT_LEN - camera_x
                if not (-LAMP_RADIUS < sx < SCREEN_W + LAMP_RADIUS):
                    continue
                info = self.lamp_info(loop, i, sx)
                if info is None or info[2] is None:
                    continue
                flicker = math.sin(t * 13 + i * 7) + math.sin(t * 5.3 + i * 3)
                if flicker > 1.95 - self.corruption * 0.9:
                    continue
                lights.append(((int(info[2][0]), int(info[2][1])), LAMP_RADIUS, info[3]))
            shop_left = SHOP_X - SHOP_W // 2 + tile * SEGMENT_LEN - camera_x
            if loop.anomaly != "shop_dark" and -400 < shop_left < SCREEN_W:
                lights.append(((int(shop_left + 117), GROUND_Y + 2 - SHOP_H + 197), 170, None))
        return lights

    # --- coffee shop
    def shop_image(self, loop):
        key = loop.shop_key()
        if key in self.shop_cache:
            return self.shop_cache[key]
        sign, cups, open_text, lit, figure, door_open, price = key
        img = pygame.Surface((SHOP_W, SHOP_H), pygame.SRCALPHA)
        trim, wood, dark_wood = (150, 112, 80), (120, 72, 45), (88, 52, 34)
        glass = (255, 214, 140) if lit else (34, 30, 44)
        black = (12, 10, 14)

        # walls, roof and sign
        pygame.draw.rect(img, (214, 186, 150), (10, 70, 380, 230))
        pygame.draw.rect(img, trim, (10, 70, 380, 230), 3)
        pygame.draw.rect(img, (160, 118, 82), (0, 60, 400, 16))
        pygame.draw.rect(img, dark_wood, (70, 14, 260, 44), border_radius=4)
        pygame.draw.rect(img, (200, 160, 90), (70, 14, 260, 44), 3, border_radius=4)
        label = self.shop_font.render(sign, True, (245, 226, 180))
        img.blit(label, label.get_rect(center=(200, 37)))

        # striped awning with a scalloped edge
        for i in range(9):
            colour = (178, 42, 50) if i % 2 == 0 else (245, 232, 210)
            pygame.draw.rect(img, colour, (20 + i * 40, 80, 40, 34))
            pygame.draw.circle(img, colour, (40 + i * 40, 114), 20, draw_bottom_left=True, draw_bottom_right=True)

        # shop window: someone may be standing behind the shelf, then cups and the dallah on it
        pygame.draw.rect(img, glass, (30, 140, 175, 115))
        if figure:
            img.set_clip((30, 140, 175, 115))
            pygame.draw.ellipse(img, black, (88, 186, 62, 100))
            pygame.draw.circle(img, black, (119, 172), 17)
            for ex in (113, 125):
                pygame.draw.circle(img, (250, 250, 250), (ex, 170), 2)
            img.set_clip(None)
        pygame.draw.rect(img, trim, (34, 216, 167, 6))
        for x in (60, 98, 136)[:cups]:
            img.blit(self.decor["cup"], self.decor["cup"].get_rect(midbottom=(x, 218)))
        img.blit(self.decor["dallah"], self.decor["dallah"].get_rect(midbottom=(176, 218)))
        if lit:
            pygame.draw.line(img, (255, 240, 215), (45, 248), (70, 150), 3)
            pygame.draw.line(img, (255, 240, 215), (58, 248), (80, 160), 2)
        pygame.draw.rect(img, (110, 75, 50), (30, 140, 175, 115), 6)

        # door
        if door_open:
            pygame.draw.rect(img, (6, 4, 8), (225, 140, 80, 160))
            pygame.draw.polygon(img, wood, [(225, 140), (246, 150), (246, 290), (225, 300)])
        else:
            pygame.draw.rect(img, wood, (225, 140, 80, 160))
            pygame.draw.rect(img, glass, (240, 155, 50, 45))
            pygame.draw.circle(img, (220, 180, 80), (292, 228), 5)
            pygame.draw.line(img, (60, 40, 30), (250, 200), (264, 212), 2)
            pygame.draw.line(img, (60, 40, 30), (280, 200), (266, 212), 2)
            pygame.draw.rect(img, (240, 236, 228), (233, 212, 64, 24), border_radius=3)
            text = "OPEN" if open_text == "NEPO" else open_text
            tag = self.small_font.render(text, True, (40, 130, 60) if open_text == "OPEN" else (170, 25, 25))
            if open_text == "NEPO":
                tag = pygame.transform.flip(tag, True, False)
            img.blit(tag, tag.get_rect(center=(265, 224)))
        pygame.draw.rect(img, (90, 52, 32), (225, 140, 80, 160), 5)

        # menu chalkboard and clock face (the hands are drawn live)
        pygame.draw.rect(img, (40, 46, 42), (322, 215, 56, 75))
        pygame.draw.rect(img, trim, (322, 215, 56, 75), 3)
        for i, line in enumerate(("KARAK", price)):
            chalk = self.small_font.render(line, True, (225, 225, 212))
            img.blit(chalk, chalk.get_rect(center=(350, 235 + i * 22)))
        pygame.draw.circle(img, (245, 240, 228), (350, 170), 22)
        pygame.draw.circle(img, dark_wood, (350, 170), 22, 3)

        self.shop_cache[key] = img
        return img

    def draw_shop(self, surface, loop, left, t):
        top = GROUND_Y + 2 - SHOP_H
        surface.blit(self.shop_image(loop), (left, top))
        # clock: normally ticks along, in the anomaly it spins backwards
        minutes = t * (-4 if loop.anomaly == "shop_clock" else 1)
        cx, cy = left + 350, top + 170
        for angle, length, width in ((minutes * 6, 17, 2), (270 + minutes / 2, 11, 3)):
            a = math.radians(angle)
            pygame.draw.line(surface, (30, 20, 20), (cx, cy), (cx + math.sin(a) * length, cy - math.cos(a) * length),
                             width)
        if loop.anomaly == "shop_door" and t % 4 < 3.8:          # something blinks in the doorway
            for ex in (262, 276):
                pygame.draw.circle(surface, (255, 40, 30), (left + ex, top + 205), 3)

    # --- signs and boards
    def sign_image(self, progress):
        if progress not in self.sign_cache:
            img = self.decor["sign"].copy()
            s = SPRITE_SCALE
            for text, centre in ((f"EXIT {progress}", (92, 60)), ("BACK", (92, 116))):
                label = self.sign_font.render(text, True, (85, 50, 30))
                img.blit(label, label.get_rect(center=(int(centre[0] * s), int(centre[1] * s))))
            self.sign_cache[progress] = img
        return self.sign_cache[progress]

    def board_image(self, text):
        if text not in self.board_cache:
            img = self.decor["whiteboard"].copy()
            if text is not None:
                s = SPRITE_SCALE
                pygame.draw.rect(img, (238, 236, 240), (int(18 * s), int(18 * s), int(220 * s), int(122 * s)))
                lines = text.split("\n")
                lh = self.board_font.get_linesize()
                top = int(79 * s) - lh * len(lines) // 2
                for i, line in enumerate(lines):
                    label = self.board_font.render(line, True, (170, 20, 25))
                    img.blit(label, label.get_rect(midtop=(int(128 * s), top + i * lh)))
            self.board_cache[text] = img
        return self.board_cache[text]

    def blit_on_ground(self, surface, img, sx):
        rect = img.get_rect()
        rect.centerx = int(sx)
        rect.bottom = GROUND_Y + 2
        surface.blit(img, rect)

    # --- drawing
    def draw(self, surface, camera_x, t):
        # Draw the neighbouring loops too, so the street looks continuous across the wrap point.
        for tile, loop, sign_progress in self.tiles():
            offset = tile * SEGMENT_LEN - camera_x
            shop_left = SHOP_X - SHOP_W // 2 + offset
            if -SHOP_W < shop_left < SCREEN_W:
                self.draw_shop(surface, loop, shop_left, t)
            for kind, x in loop.items():
                sx = x + offset
                if not (-300 < sx < SCREEN_W + 300):
                    continue
                if kind == "lamp":
                    info = self.lamp_info(loop, LAMP_XS.index(x), sx)
                    if info:
                        surface.blit(info[0], info[1])
                    continue
                if kind == "sign":
                    img = self.sign_image(min(sign_progress, GOAL_LOOPS))
                elif kind == "whiteboard":
                    img = self.board_image(loop.board_text)
                else:
                    img = self.decor[kind]
                self.blit_on_ground(surface, img, sx)
            self.draw_student(surface, loop, offset)

    def draw_tornado(self, surface, camera_x, t):
        """A swirling sand funnel, drawn over the darkness so you can see what's coming."""
        x = self.cur.tornado_x
        if x is None or not (-450 < x - camera_x < SCREEN_W + 450):
            return
        sx = x - camera_x
        top = -60
        layer = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

        def funnel(f):
            """(centre x, width, y) of the funnel at height fraction f (0 ground .. 1 sky)."""
            cx = sx + math.sin(t * 2.6 + f * 5) * 45 * f + math.sin(t * 7 + f * 11) * 8
            return cx, 46 + 380 * f ** 1.7, GROUND_Y - f * (GROUND_Y - top)

        for i in range(36):
            f = i / 35
            cx, w, y = funnel(f)
            shade = 80 + int(45 * (0.5 + 0.5 * math.sin(t * 9 - f * 14)))
            h = 26 + 22 * f
            pygame.draw.ellipse(layer, (shade + 25, shade + 10, shade - 10, 150), (cx - w / 2, y - h / 2, w, h))
        for k in range(44):                          # debris whipping round the funnel
            f = (k * 0.618) % 1
            cx, w, y = funnel(f)
            ang = t * (8 - 4 * f) + k * 2.4
            pygame.draw.rect(layer, (45, 36, 28, 230),
                             (cx + math.cos(ang) * w * 0.45, y + math.sin(ang) * 10, 4 + k % 4, 3 + k % 3))
        for k in range(6):                           # dust kicked up at the base
            r = 60 + k * 26 + 10 * math.sin(t * 5 + k)
            pygame.draw.ellipse(layer, (160, 135, 100, 55), (sx - r, GROUND_Y - r * 0.35, 2 * r, r * 0.7))
        surface.blit(layer, (0, 0))

    def draw_student(self, surface, loop, offset):
        img = self.decor["student"]
        sx = loop.student_x + offset
        if not (-200 < sx < SCREEN_W + 200):
            return
        facing_right = True
        if loop.anomaly == "student_watching":
            facing_right = self.scotty_x > loop.student_x
        if loop.anomaly == "student_eyes":
            img = pygame.transform.smoothscale(img, (img.get_width(), int(img.get_height() * 1.35)))
        if not facing_right:
            img = pygame.transform.flip(img, True, False)
        self.blit_on_ground(surface, img, sx)
        if loop.anomaly == "student_eyes":
            # eyes sit near the front of the head
            head_y = GROUND_Y - img.get_height() + int(62 * SPRITE_SCALE * 1.35)
            for dx in (8, 20):
                ex = int(sx + dx * SPRITE_SCALE * (1 if facing_right else -1))
                pygame.draw.circle(surface, (255, 30, 20), (ex, head_y), 3)


# ----------------------------------------------------------------------------- effects
def make_light(radius):
    """Radial alpha gradient used to cut light out of the darkness overlay."""
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -2):
        a = int(255 * min(1.0, (1 - r / radius) * 1.7))
        pygame.draw.circle(surf, (a, a, a, a), (radius, radius), r)
    return surf


def make_vignette():
    small = pygame.Surface((64, 36), pygame.SRCALPHA)
    for y in range(36):
        for x in range(64):
            d = math.hypot((x - 31.5) / 32, (y - 17.5) / 18)
            small.set_at((x, y), (0, 0, 0, int(255 * max(0.0, min(1.0, (d - 0.55) * 1.6)))))
    return pygame.transform.smoothscale(small, (SCREEN_W, SCREEN_H))


class Effects:
    def __init__(self):
        self.base_light = make_light(256)
        self.light_cache = {}
        self.glow_cache = {}
        self.vignette = make_vignette()
        self.dark = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

    def light(self, radius):
        key = radius // 8 * 8
        if key not in self.light_cache:
            self.light_cache[key] = pygame.transform.smoothscale(self.base_light, (key * 2, key * 2))
        return self.light_cache[key]

    def glow(self, radius, colour):
        key = (radius // 8 * 8, colour)
        if key not in self.glow_cache:
            img = self.light(radius).copy()
            img.fill(colour, special_flags=pygame.BLEND_RGB_MULT)
            self.glow_cache[key] = img
        return self.glow_cache[key]

    def apply(self, surface, corruption, scotty_pos, lights):
        """lights: (screen pos, radius, glow colour or None) for every lamp / window."""
        if corruption > 0.01:
            # colour drains toward a sick red
            tint = tuple(int(255 + (c - 255) * corruption) for c in TINT_FULL)
            surface.fill(tint, special_flags=pygame.BLEND_MULT)

            # darkness with holes for Scotty and the lights
            self.dark.fill((4, 0, 8, int(DARKNESS_FULL * corruption)))
            r = int(LIGHT_RADIUS[0] + (LIGHT_RADIUS[1] - LIGHT_RADIUS[0]) * corruption)
            for pos, radius, _ in [(scotty_pos, r, None)] + lights:
                img = self.light(radius)
                self.dark.blit(img, img.get_rect(center=pos), special_flags=pygame.BLEND_RGBA_SUB)
            surface.blit(self.dark, (0, 0))

            self.vignette.set_alpha(int(255 * corruption))
            surface.blit(self.vignette, (0, 0))

        for pos, radius, colour in lights:
            if colour:
                img = self.glow(radius, colour)
                surface.blit(img, img.get_rect(center=pos), special_flags=pygame.BLEND_RGB_ADD)


# ----------------------------------------------------------------------------- main
def main():
    pygame.mixer.pre_init(44100, -16, 2, 512)   # small buffer so barks and steps feel instant
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 30)
    big_font = pygame.font.SysFont(None, 88)
    mid_font = pygame.font.SysFont(None, 40)

    canvas = pygame.Surface((SCREEN_W, SCREEN_H))
    layers = load_layers()
    anims = load_animations()
    street = Street(load_decor())
    effects = Effects()
    audio = GameAudio(STREET_LAYOUT, SHOP_X, SEGMENT_LEN)

    def new_game():
        street.reset()
        return Scotty(anims, x=START_X), START_X - SCREEN_W / 2

    scotty, camera_x = new_game()
    scroll_x = camera_x            # parallax scroll; unlike camera_x it never jumps when the loop wraps
    state = "title"                # title -> playing -> ending
    debug = False
    fade = 0.0                     # black fade after turning back
    flash = 0.0                    # colour flash after every call: green if right, red (+ shake) if wrong
    flash_colour = (0, 0, 0)
    FLASH_TIME = 0.6
    t = 0.0

    while True:
        dt = min(clock.tick(FPS) / 1000, 1 / 20)   # clamp so a hitch doesn't teleport the dog
        t += dt

        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F1:
                    debug = not debug
                elif event.key == pygame.K_m:
                    audio.toggle_mute()
                elif event.key == pygame.K_F2:
                    options = [None, "cat", "tornado"] + ANOMALIES
                    street.set_anomaly(options[(options.index(street.anomaly) + 1) % len(options)])
                elif state == "title" and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    state = "playing"
                    continue
                elif state == "ending" and event.key == pygame.K_r:
                    scotty, camera_x = new_game()
                    state = "playing"
                    continue
            if state == "playing":
                scotty.handle_event(event)

        if state == "playing":
            old_cam = camera_x
            scotty.update(dt, pygame.key.get_pressed())

            # camera follows Scotty, keeping a dead zone in the middle third of the screen
            left_edge, right_edge = camera_x + SCREEN_W * 0.35, camera_x + SCREEN_W * 0.65
            if scotty.x < left_edge:
                camera_x -= left_edge - scotty.x
            elif scotty.x > right_edge:
                camera_x += scotty.x - right_edge
            scroll_x += camera_x - old_cam

            # leaving the loop: forward wraps seamlessly, backward (or the tornado catching you) cuts to black
            caught = street.update_tornado(dt, scotty, camera_x)
            if caught or scotty.x > SEGMENT_LEN or scotty.x < 0:
                went_forward = scotty.x > SEGMENT_LEN and not caught
                correct = street.finish_loop(went_forward, caught)
                if went_forward:
                    scotty.x -= SEGMENT_LEN
                    camera_x -= SEGMENT_LEN
                else:
                    scotty.x = START_X
                    scotty.facing_right = True
                    camera_x = START_X - SCREEN_W / 2
                    fade = 1.0
                flash = FLASH_TIME
                flash_colour = (30, 190, 70) if correct else (180, 0, 0)
                if street.progress >= GOAL_LOOPS:
                    state = "ending"

        street.scotty_x = scotty.x
        street.update(dt, scotty, camera_x)
        audio.update(dt, state, street, scotty)
        if state == "ending":
            street.corruption += (0.0 - street.corruption) * min(1.0, dt * 0.8)

        # ---- draw the world
        draw_parallax(canvas, layers, scroll_x, street.frozen_layers())
        street.draw(canvas, camera_x, t)
        scotty.draw(canvas, camera_x, as_cat=street.anomaly == "cat", t=t)
        scotty_pos = (int(scotty.x - camera_x), int(scotty.y - 60 * SPRITE_SCALE))
        effects.apply(canvas, street.corruption, scotty_pos, street.lights(camera_x, t))
        street.draw_tornado(canvas, camera_x, t)

        if fade > 0:
            fade = max(0.0, fade - dt * 1.4)
            veil = pygame.Surface((SCREEN_W, SCREEN_H))
            veil.set_alpha(int(255 * min(1.0, fade * 1.5)))
            canvas.blit(veil, (0, 0))
        shake = (0, 0)
        if street.cur.tornado_x is not None and state == "playing":     # the ground shakes as it closes in
            k = int(12 * max(0.0, 1 - abs(street.cur.tornado_x - scotty.x) / 900))
            if k:
                shake = (random.randint(-k, k), random.randint(-k, k))
        if flash > 0:
            flash = max(0.0, flash - dt)
            veil = pygame.Surface((SCREEN_W, SCREEN_H))
            veil.fill(flash_colour)
            veil.set_alpha(int(170 * flash / FLASH_TIME))
            canvas.blit(veil, (0, 0))
            if flash_colour[0] > flash_colour[1]:      # wrong call: shake too
                shake = (random.randint(-14, 14), random.randint(-10, 10))

        # ---- text
        if state == "title":
            draw_text(canvas, big_font, "SCOTTY: AFTER HOURS", (SCREEN_W // 2, 60), center=True)
            draw_text(canvas, mid_font,
                      "Walk the street.\nIf something is wrong, turn back.\nIf nothing is wrong, keep going.\n"
                      f"Make the right call {GOAL_LOOPS} times to get out.",
                      (SCREEN_W // 2, 170), center=True)
            draw_text(canvas, mid_font, "Turn your sound on. Some things can only be heard.",
                      (SCREEN_W // 2, 340), color=(255, 215, 120), center=True)
            draw_text(canvas, font, "Press Space to start", (SCREEN_W // 2, 405), center=True)
        elif state == "ending":
            draw_text(canvas, big_font, "EXIT 8", (SCREEN_W // 2, 190), center=True)
            draw_text(canvas, mid_font, "The street lets Scotty go.\n...for tonight.", (SCREEN_W // 2, 280),
                      center=True)
            draw_text(canvas, font, "Press R to walk again   Esc to quit", (SCREEN_W // 2, 400), center=True)
        elif street.progress == 0:
            if street.loops == 0:
                draw_text(canvas, font, "A/D move  Shift run  Space jump  B bark  M mute", (16, 14))
            hint = "This is how the street should look. Remember it." if street.fails == 0 else \
                "Back to the start. Nothing is wrong here... remember it."
            draw_text(canvas, mid_font, hint, (SCREEN_W // 2, 80), center=True)

        if debug:
            info = (f"fps {clock.get_fps():.0f}  x {scotty.x:.0f}  cam {camera_x:.0f}  loop {street.loops}  "
                    f"progress {street.progress}  anomaly {street.anomaly}  corruption {street.corruption:.2f}  "
                    f"(F2 cycles anomaly)")
            draw_text(canvas, font, info, (16, SCREEN_H - 40))

        screen.fill((0, 0, 0))
        screen.blit(canvas, shake)
        pygame.display.flip()


if __name__ == "__main__":
    main()
