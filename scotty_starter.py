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
    ("lamp", 650),
    ("bench", 950),
    ("palm", 1300),
    ("lamp", 1700),
    ("whiteboard", 2050),
    ("palm", 2850),
    ("lamp", 3250),
    ("bench", 3550),
]
STUDENT_X = 2450
EXTRA_BENCH_X = 1500
MISSING_PALM_X = 2850

ANOMALIES = [
    "student_watching",   # the student turns to face Scotty, and moves when you're not looking
    "student_eyes",       # the student is taller, with glowing red eyes
    "extra_bench",
    "missing_palm",
    "whiteboard",         # the whiteboard has a message for you
    "frozen_skyline",     # the city in the background stops moving
    "lamps_off",
]
NORMAL_BOARD = None       # draw the whiteboard art as-is
ANOMALY_BOARDS = ["TURN BACK", "SCOTTY\nGO HOME", "WHY ARE YOU\nSTILL HERE", "IT'S BEHIND\nYOU"]

# Corruption 0..1: how dark / wrong the world looks. Rises with every loop.
CORRUPTION_PER_LOOP = 0.11
CORRUPTION_PER_FAIL = 0.05
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
    }


def draw_text(surface, font, text, pos, color=(235, 225, 230), center=False):
    """Text with a dark drop shadow so it reads on both the bright and the dark street."""
    for i, line in enumerate(text.split("\n")):
        shadow = font.render(line, True, (10, 5, 10))
        img = font.render(line, True, color)
        rect = img.get_rect()
        y = pos[1] + i * (font.get_linesize())
        if center:
            rect.midtop = (pos[0], y)
        else:
            rect.topleft = (pos[0], y)
        surface.blit(shadow, rect.move(2, 2))
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

    def draw(self, surface, camera_x):
        img = self.anim.frame(self.facing_right)
        feet_offset = int(SPRITE_FEET_Y * SPRITE_SCALE)
        rect = img.get_rect()
        rect.centerx = int(self.x - camera_x)
        rect.top = int(self.y) - feet_offset
        surface.blit(img, rect)


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
class Street:
    """One loop of the street: what's in it, whether something is wrong, and how far Scotty has got."""

    def __init__(self, decor):
        self.decor = decor
        self.dark_lamp = decor["lamp"].copy()
        self.dark_lamp.fill((70, 60, 75), special_flags=pygame.BLEND_MULT)
        self.sign_font = pygame.font.SysFont(None, int(34 * SPRITE_SCALE * 1.5))
        self.board_font = pygame.font.SysFont(None, int(30 * SPRITE_SCALE * 1.5))
        self.sign_cache = {}
        self.board_cache = {}
        self.scotty_x = START_X
        self.reset()

    def reset(self):
        self.progress = 0          # correct calls in a row
        self.loops = 0             # loops entered so far
        self.fails = 0
        self.corruption = 0.0
        self.anomaly = None
        self.start_loop(self.anomaly)

    # --- loop logic
    def start_loop(self, anomaly):
        self.anomaly = anomaly
        self.student_x = STUDENT_X
        self.board_text = random.choice(ANOMALY_BOARDS) if anomaly == "whiteboard" else NORMAL_BOARD

    def roll_anomaly(self):
        if self.loops <= 1 or random.random() > ANOMALY_CHANCE:   # the first loop is always normal
            return None
        return random.choice(ANOMALIES)

    def progress_if(self, went_forward):
        correct = (self.anomaly is None) == went_forward
        return self.progress + 1 if correct else 0

    def finish_loop(self, went_forward):
        """Judge Scotty's choice and set up the next loop. Returns True if the call was right."""
        new_progress = self.progress_if(went_forward)
        correct = new_progress > 0
        self.progress = new_progress
        if not correct:
            self.fails += 1
        self.loops += 1
        self.start_loop(self.roll_anomaly())
        return correct

    @property
    def target_corruption(self):
        return min(1.0, self.loops * CORRUPTION_PER_LOOP + self.fails * CORRUPTION_PER_FAIL)

    def update(self, dt, scotty, camera_x):
        self.corruption += (self.target_corruption - self.corruption) * min(1.0, dt * 0.6)

        # the watching student only moves while it's off screen
        if self.anomaly == "student_watching":
            screen_x = self.student_x - camera_x
            if not (-60 < screen_x < SCREEN_W + 60):
                gap = scotty.x - self.student_x
                if abs(gap) > 260:
                    self.student_x += math.copysign(110 * dt, gap)
            self.student_x = max(700, min(SEGMENT_LEN - 700, self.student_x))

    def frozen_layers(self):
        return SKYLINE_LAYERS if self.anomaly == "frozen_skyline" else ()

    # --- drawing
    def items(self):
        items = list(STREET_LAYOUT)
        if self.anomaly == "extra_bench":
            items.append(("bench", EXTRA_BENCH_X))
        if self.anomaly == "missing_palm":
            items.remove(("palm", MISSING_PALM_X))
        return items

    def lamp_lights(self, camera_x, t):
        """Screen positions of every lit lamp head (lamps flicker more as corruption rises)."""
        if self.anomaly == "lamps_off":
            return []
        lamp = self.decor["lamp"]
        lights = []
        for tile in (-1, 0, 1):
            for i, (kind, x) in enumerate(STREET_LAYOUT):
                if kind != "lamp":
                    continue
                flicker = math.sin(t * 13 + i * 7) + math.sin(t * 5.3 + i * 3)
                if flicker > 1.95 - self.corruption * 0.9:
                    continue
                sx = x + tile * SEGMENT_LEN - camera_x
                if -LAMP_RADIUS < sx < SCREEN_W + LAMP_RADIUS:
                    lights.append((int(sx), GROUND_Y - lamp.get_height() + int(60 * SPRITE_SCALE)))
        return lights

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

    def draw(self, surface, camera_x):
        # Draw the neighbouring loops too, so the street looks continuous right up to the wrap point.
        # The next loop's sign already shows the number Scotty will get by walking forward.
        for tile in (-1, 0, 1):
            for kind, x in self.items():
                sx = x + tile * SEGMENT_LEN - camera_x
                if not (-300 < sx < SCREEN_W + 300):
                    continue
                if kind == "sign":
                    progress = self.progress_if(True) if tile == 1 else self.progress
                    img = self.sign_image(min(progress, GOAL_LOOPS))
                elif kind == "lamp" and self.anomaly == "lamps_off":
                    img = self.dark_lamp
                elif kind == "whiteboard":
                    img = self.board_image(self.board_text)
                else:
                    img = self.decor[kind]
                self.blit_on_ground(surface, img, sx)
        self.draw_student(surface, camera_x)

    def draw_student(self, surface, camera_x):
        img = self.decor["student"]
        sx = self.student_x - camera_x
        if not (-200 < sx < SCREEN_W + 200):
            return
        facing_right = True
        if self.anomaly == "student_watching":
            facing_right = self.scotty_x > self.student_x
        if self.anomaly == "student_eyes":
            img = pygame.transform.smoothscale(img, (img.get_width(), int(img.get_height() * 1.35)))
        if not facing_right:
            img = pygame.transform.flip(img, True, False)
        self.blit_on_ground(surface, img, sx)
        if self.anomaly == "student_eyes":
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
        self.vignette = make_vignette()
        self.dark = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)

    def light(self, radius):
        key = radius // 8 * 8
        if key not in self.light_cache:
            self.light_cache[key] = pygame.transform.smoothscale(self.base_light, (key * 2, key * 2))
        return self.light_cache[key]

    def apply(self, surface, corruption, scotty_pos, lamp_lights):
        if corruption <= 0.01:
            return
        # colour drains toward a sick red
        tint = tuple(int(255 + (c - 255) * corruption) for c in TINT_FULL)
        surface.fill(tint, special_flags=pygame.BLEND_MULT)

        # darkness with holes for Scotty and the lamps
        self.dark.fill((4, 0, 8, int(DARKNESS_FULL * corruption)))
        r = int(LIGHT_RADIUS[0] + (LIGHT_RADIUS[1] - LIGHT_RADIUS[0]) * corruption)
        lights = [(scotty_pos, r)] + [(p, LAMP_RADIUS) for p in lamp_lights]
        for pos, radius in lights:
            img = self.light(radius)
            self.dark.blit(img, img.get_rect(center=pos), special_flags=pygame.BLEND_RGBA_SUB)
        surface.blit(self.dark, (0, 0))

        self.vignette.set_alpha(int(255 * corruption))
        surface.blit(self.vignette, (0, 0))


# ----------------------------------------------------------------------------- main
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 26)
    big_font = pygame.font.SysFont(None, 72)
    mid_font = pygame.font.SysFont(None, 36)

    canvas = pygame.Surface((SCREEN_W, SCREEN_H))
    layers = load_layers()
    anims = load_animations()
    street = Street(load_decor())
    effects = Effects()

    def new_game():
        street.reset()
        return Scotty(anims, x=START_X), START_X - SCREEN_W / 2

    scotty, camera_x = new_game()
    scroll_x = camera_x            # parallax scroll; unlike camera_x it never jumps when the loop wraps
    state = "title"                # title -> playing -> ending
    debug = False
    fade = 0.0                     # black fade after turning back
    scare = 0.0                    # red flash + shake after a wrong call
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
                elif event.key == pygame.K_F2:
                    options = [None] + ANOMALIES
                    street.start_loop(options[(options.index(street.anomaly) + 1) % len(options)])
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

            # leaving the loop: forward wraps seamlessly, backward cuts to black
            if scotty.x > SEGMENT_LEN or scotty.x < 0:
                went_forward = scotty.x > SEGMENT_LEN
                correct = street.finish_loop(went_forward)
                if went_forward:
                    scotty.x -= SEGMENT_LEN
                    camera_x -= SEGMENT_LEN
                else:
                    scotty.x = START_X
                    scotty.facing_right = True
                    camera_x = START_X - SCREEN_W / 2
                    fade = 1.0
                if not correct:
                    scare = 0.6
                if street.progress >= GOAL_LOOPS:
                    state = "ending"

        street.scotty_x = scotty.x
        street.update(dt, scotty, camera_x)
        if state == "ending":
            street.corruption += (0.0 - street.corruption) * min(1.0, dt * 0.8)

        # ---- draw the world
        draw_parallax(canvas, layers, scroll_x, street.frozen_layers())
        street.draw(canvas, camera_x)
        scotty.draw(canvas, camera_x)
        scotty_pos = (int(scotty.x - camera_x), int(scotty.y - 60 * SPRITE_SCALE))
        effects.apply(canvas, street.corruption, scotty_pos, street.lamp_lights(camera_x, t))

        if fade > 0:
            fade = max(0.0, fade - dt * 1.4)
            veil = pygame.Surface((SCREEN_W, SCREEN_H))
            veil.set_alpha(int(255 * min(1.0, fade * 1.5)))
            canvas.blit(veil, (0, 0))
        shake = (0, 0)
        if scare > 0:
            scare = max(0.0, scare - dt)
            flash = pygame.Surface((SCREEN_W, SCREEN_H))
            flash.fill((180, 0, 0))
            flash.set_alpha(int(220 * scare / 0.6))
            canvas.blit(flash, (0, 0))
            shake = (random.randint(-14, 14), random.randint(-10, 10))

        # ---- text
        if state == "title":
            draw_text(canvas, big_font, "SCOTTY: AFTER HOURS", (SCREEN_W // 2, 170), center=True)
            draw_text(canvas, mid_font,
                      "Walk the street.\nIf something is wrong, turn back.\nIf nothing is wrong, keep going.\n\n"
                      f"Make the right call {GOAL_LOOPS} times to get out.",
                      (SCREEN_W // 2, 260), center=True)
            draw_text(canvas, font, "Press Space to start", (SCREEN_W // 2, 520), center=True)
        elif state == "ending":
            draw_text(canvas, big_font, "EXIT 8", (SCREEN_W // 2, 190), center=True)
            draw_text(canvas, mid_font, "The street lets Scotty go.\n...for tonight.", (SCREEN_W // 2, 280),
                      center=True)
            draw_text(canvas, font, "Press R to walk again   Esc to quit", (SCREEN_W // 2, 400), center=True)
        elif street.loops == 0:
            draw_text(canvas, font, "A/D move  Shift run  Space jump  B bark", (16, 14))

        if debug:
            info = (f"fps {clock.get_fps():.0f}  x {scotty.x:.0f}  cam {camera_x:.0f}  loop {street.loops}  "
                    f"progress {street.progress}  anomaly {street.anomaly}  corruption {street.corruption:.2f}  "
                    f"(F2 cycles anomaly)")
            draw_text(canvas, font, info, (16, 40))

        screen.fill((0, 0, 0))
        screen.blit(canvas, shake)
        pygame.display.flip()


if __name__ == "__main__":
    main()
