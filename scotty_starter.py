"""
Scotty Game Jam Starter
=======================
A single-file Pygame starter: Scotty the dog runs around Doha / Education City.

Controls
  Left / Right  or  A / D   walk
  Hold Shift                run
  Space / Up / W            jump
  B                         bark
  F1                        toggle debug info
  Esc                       quit

Expected folder layout (assets/ next to this file):
  assets/scotty_frames/<anim>/<anim>_01.png ...   (idle, walking, running, jumping, barking)
  assets/background/01_sky.png ... 04_ground.png

Requires: pip install pygame-ce   (or classic "pygame" on Python <= 3.13)
"""
import os
import sys

import pygame

# ----------------------------------------------------------------------------- config
SCREEN_W, SCREEN_H = 1280, 720
FPS = 60
TITLE = "Scotty Starter"

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
def draw_parallax(surface, layers, camera_x):
    for img, factor in layers:
        w = img.get_width()
        offset = -int(camera_x * factor) % w
        surface.blit(img, (offset - w, 0))
        surface.blit(img, (offset, 0))
        if offset + w < SCREEN_W:      # only needed if the window is wider than the layer
            surface.blit(img, (offset + w, 0))


# ----------------------------------------------------------------------------- main
def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 26)

    layers = load_layers()
    scotty = Scotty(load_animations(), x=SCREEN_W / 2)
    camera_x = 0.0
    debug = False

    while True:
        dt = min(clock.tick(FPS) / 1000, 1 / 20)   # clamp so a hitch doesn't teleport the dog

        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F1:
                debug = not debug
            scotty.handle_event(event)

        scotty.update(dt, pygame.key.get_pressed())

        # camera follows Scotty, keeping a dead zone in the middle third of the screen
        left_edge, right_edge = camera_x + SCREEN_W * 0.35, camera_x + SCREEN_W * 0.65
        if scotty.x < left_edge:
            camera_x -= left_edge - scotty.x
        elif scotty.x > right_edge:
            camera_x += scotty.x - right_edge

        draw_parallax(screen, layers, camera_x)
        scotty.draw(screen, camera_x)

        hint = "A/D move  Shift run  Space jump  B bark  F1 debug"
        screen.blit(font.render(hint, True, (60, 40, 70)), (16, 14))
        if debug:
            info = f"fps {clock.get_fps():.0f}  x {scotty.x:.0f}  cam {camera_x:.0f}  anim {scotty.anim.name}"
            screen.blit(font.render(info, True, (60, 40, 70)), (16, 40))

        pygame.display.flip()


if __name__ == "__main__":
    main()
