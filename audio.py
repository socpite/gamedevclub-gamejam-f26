"""
Sound for Scotty: After Hours.

All the WAVs live in assets/sounds/ (regenerate them with assets/sounds/make_sounds.py).
This module watches the game state each frame and plays everything itself, so hooking it up is:

    from audio import GameAudio
    audio = GameAudio(STREET_LAYOUT, SHOP_X, SEGMENT_LEN)        # after pygame.init()
    ...
    audio.update(dt, state, street, scotty)                      # every frame, after street.update()

It reads (never writes): street.anomaly / corruption / loops / progress / last_exit / tiles(),
loop.lamp_index / student_x / storm / tornado_x, and scotty.x / on_ground / barking / vx / walk_dist.
If there is no audio device it quietly does nothing.

What plays:
  always       night drone; wind; dread cluster + glitches rising with corruption
  sound-only   wind_stops: the wind drops dead.  student_murmur: the student with the karak mutters.
  anomalies    cafe_heartbeat: a heartbeat thuds behind the café walls as you pass.
  tornado      the wind keeps rising (gale layer), then a roaring funnel you can hear coming from the
               right; getting caught = whoosh + scare
  Scotty       paw steps, jump, land, bark (a meow when he's the cat; at high corruption the street
               sometimes barks back)
  judgement    forward = faint tape-splice seam, back = boom; right call = chime climbing a scale
               (1..8), wrong call = scare stinger; escaping = major-chord swell
  positional   lamp hum per lamp (none in lamps_off / lamp_missing, sick crackling hum on lamp_red),
               café radio + wall clock (silent in shop_dark, clock runs backwards in shop_clock,
               radio warps in shop_figure), breathing inside the open door (shop_door),
               sub-bass + tinnitus near student_eyes
  one-shots    door creaks open (shop_door), knock on the glass (shop_figure), marker squeaks
               (whiteboard), groaning metal (lamp_tilt)
"""
import math
import os
import random

import pygame

SOUND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "sounds")

MASTER = 0.9
AMB_VOLUME = {"amb_night": 0.45, "amb_wind": 0.3, "amb_dread": 0.75, "gale_loop": 0.9}

# positional loops: sound file, emitter gain, audible radius in world px
EMITTERS = {
    "lamp": ("lamp_hum_loop", 0.22, 520),
    "lamp_bad": ("lamp_hum_bad_loop", 0.5, 650),
    "radio": ("shop_radio_loop", 0.5, 1300),
    "radio_warped": ("shop_radio_warped_loop", 0.55, 1300),
    "clock": ("clock_tick_loop", 0.35, 500),
    "clock_rev": ("clock_tick_reverse_loop", 0.45, 550),
    "inside": ("shop_inside_loop", 0.7, 750),
    "murmur": ("murmur_loop", 0.75, 750),
    "heart": ("heartbeat_loop", 0.95, 950),
    "tornado": ("tornado_loop", 1.0, 1900),
    "eyes": ("eyes_drone_loop", 0.7, 1100),
}
PAN_WIDTH = 700            # world px off-centre for a hard pan
STEP_STRIDE = {False: 64, True: 92}   # px between paw steps walking / running


class GameAudio:
    def __init__(self, street_layout, shop_x, segment_len):
        self.enabled = False
        self.lamp_xs = [x for kind, x in street_layout if kind == "lamp"]
        self.board_x = next((x for kind, x in street_layout if kind == "whiteboard"), None)
        self.shop_x = shop_x
        self.segment_len = segment_len
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            self.sounds = {os.path.splitext(f)[0]: pygame.mixer.Sound(os.path.join(SOUND_DIR, f))
                           for f in os.listdir(SOUND_DIR) if f.endswith(".wav")}
        except (pygame.error, OSError) as e:
            print("audio disabled:", e)
            return
        self.enabled = True

        loop_keys = list(AMB_VOLUME) + list(EMITTERS)
        pygame.mixer.set_num_channels(len(loop_keys) + 24)
        pygame.mixer.set_reserved(len(loop_keys))
        self.loops = {}            # key -> [channel, current (l, r)]
        for i, key in enumerate(loop_keys):
            ch = pygame.mixer.Channel(i)
            snd = self.sounds[key if key in AMB_VOLUME else EMITTERS[key][0]]
            ch.play(snd, loops=-1)
            ch.set_volume(0, 0)
            self.loops[key] = [ch, (0.0, 0.0)]
        # stagger loop start points don't matter much; drone fades in from the title screen
        self.muted = False
        self.time = 0.0
        self.queue = []            # (time, sound, volume, pan) for delayed one-shots
        self.duck = 0.0            # 1 = ambience pulled right down (after a scare / cut to black)
        self._reset_tracking()

    # ------------------------------------------------------------------ public helpers
    def play(self, name, volume=1.0, pan=0.0, delay=0.0):
        """Fire a one-shot. pan is -1 (left) .. 1 (right)."""
        if not self.enabled:
            return
        if delay > 0:
            self.queue.append((self.time + delay, name, volume, pan))
            return
        snd = self.sounds.get(name)
        if snd is None:
            return
        ch = pygame.mixer.find_channel(True)
        if ch is None:
            return
        ch.play(snd)
        ch.set_volume(*self._lr(volume * MASTER * (not self.muted), pan))

    def toggle_mute(self):
        self.muted = not self.muted

    # ------------------------------------------------------------------ internals
    def _reset_tracking(self):
        self.seen_loops = 0
        self.last_step = 0.0
        self.prev_ground = True
        self.prev_bark = False
        self._new_loop()

    def _new_loop(self):
        self.fired = set()         # per-loop one-shots already played
        self.next_repeat = {}      # per-loop repeating one-shots -> next allowed time

    @staticmethod
    def _lr(volume, pan):
        pan = max(-1.0, min(1.0, pan))
        a = (pan + 1) * math.pi / 4
        return volume * math.cos(a), volume * math.sin(a)

    def _spatial(self, dx, radius):
        """(gain, pan) for an emitter dx world px from Scotty."""
        d = abs(dx) / radius
        if d >= 1:
            return 0.0, 0.0
        return (1 - d) ** 2, dx / PAN_WIDTH

    def _set_loop(self, key, volume, pan, dt, speed=4.0):
        ch, (l, r) = self.loops[key]
        tl, tr = self._lr(volume * MASTER * (not self.muted), pan)
        k = min(1.0, dt * speed)
        l, r = l + (tl - l) * k, r + (tr - r) * k
        ch.set_volume(l, r)
        self.loops[key][1] = (l, r)

    def _emitters(self, street):
        """Every positional source in the visible loops: (emitter key, world x)."""
        out = []
        for tile, loop, _ in street.tiles():
            off = tile * self.segment_len
            a = loop.anomaly
            for i, x in enumerate(self.lamp_xs):
                hit = i == loop.lamp_index
                if a == "lamps_off" or (a == "lamp_missing" and hit):
                    continue
                out.append(("lamp_bad" if a == "lamp_red" and hit else "lamp", x + off))
            if a != "shop_dark":
                out.append(("radio_warped" if a == "shop_figure" else "radio", self.shop_x + off))
                out.append(("clock_rev" if a == "shop_clock" else "clock", self.shop_x + off))
            if a == "shop_door":
                out.append(("inside", self.shop_x + off))
            if a == "student_murmur":
                out.append(("murmur", loop.student_x + off))
            if a == "cafe_heartbeat":
                out.append(("heart", self.shop_x + off))
            if tile == 0 and loop.tornado_x is not None:
                out.append(("tornado", loop.tornado_x))
            if a == "student_eyes":
                out.append(("eyes", loop.student_x + off))
        return out

    def _anomaly_oneshots(self, street, sx):
        loop = street.cur
        a = loop.anomaly

        def near(x, radius):
            return abs(x - sx) < radius

        def pan_to(x):
            return (x - sx) / PAN_WIDTH

        def once(tag, x, radius, sound, vol):
            if tag not in self.fired and near(x, radius):
                self.fired.add(tag)
                self.play(sound, vol, pan_to(x))

        def every(tag, x, radius, sound, vol, lo, hi):
            if near(x, radius) and self.time >= self.next_repeat.get(tag, 0):
                self.next_repeat[tag] = self.time + random.uniform(lo, hi)
                dist = 1 - abs(x - sx) / radius
                self.play(sound, vol * (0.4 + 0.6 * dist), pan_to(x))

        if a == "shop_door":
            once("door", self.shop_x, 950, "door_creak", 0.8)
        elif a == "shop_figure":
            once("knock", self.shop_x, 420, "glass_knock", 0.75)
        elif a == "whiteboard" and self.board_x is not None:
            every("board", self.board_x, 750, "marker_squeak", 0.6, 4.5, 8.0)
        elif a == "lamp_tilt":
            every("creak", self.lamp_xs[loop.lamp_index], 800, "lamp_creak", 0.7, 3.5, 7.0)

    def _judge(self, street, state, went_forward):
        c = street.corruption
        if state == "ending":
            self.play("escape", 0.9, delay=0.2)
            return
        if street.last_exit == "caught":
            self.play("tornado_hit", 1.0)
            self.play("wrong", 0.8, delay=0.35)
            self.duck = 1.0
            return
        if went_forward:
            self.play("loop_seam", 0.25 + 0.4 * c)
        else:
            self.play("turn_back", 0.85)
            self.duck = 1.0
        if street.progress > 0:
            self.play(f"chime_{min(street.progress, 8)}", 0.5, delay=0.15 if went_forward else 0.6)
        else:
            self.play("wrong", 1.0, delay=0.0 if went_forward else 0.25)
            self.duck = 1.0

    # ------------------------------------------------------------------ per frame
    def update(self, dt, state, street, scotty):
        if not self.enabled:
            return
        self.time += dt
        c = street.corruption
        sx = scotty.x

        # delayed one-shots
        due = [q for q in self.queue if q[0] <= self.time]
        if due:
            self.queue = [q for q in self.queue if q[0] > self.time]
            for _, name, vol, pan in due:
                self.play(name, vol, pan)

        # new game / loop transitions
        if street.loops < self.seen_loops:
            self._reset_tracking()
        if street.loops > self.seen_loops:
            self._judge(street, state, went_forward=street.last_exit == "forward")
            self.seen_loops = street.loops
            self._new_loop()
            self.last_step = scotty.walk_dist

        # ambience
        self.duck = max(0.0, self.duck - dt * 0.7)
        amb = 1 - 0.75 * self.duck
        playing = state == "playing"
        still = street.anomaly == "wind_stops" and playing
        storm = street.cur.storm if playing else 0.0
        dread = c ** 1.3 if playing else 0.0
        wind = AMB_VOLUME["amb_wind"] * (1 - 0.5 * c) + 0.5 * storm
        self._set_loop("amb_night", AMB_VOLUME["amb_night"] * amb, 0, dt, 1.0)
        self._set_loop("amb_wind", 0.0 if still else wind * amb, 0, dt,
                       12.0 if still else 1.0)       # wind stops dead, comes back gently
        self._set_loop("gale_loop", AMB_VOLUME["gale_loop"] * storm ** 1.5 * amb, 0, dt, 2.0)
        self._set_loop("amb_dread", AMB_VOLUME["amb_dread"] * dread * amb * (1 - 0.6 * storm), 0, dt, 0.5)

        # positional emitters: loudest instance of each kind wins
        targets = {k: (0.0, 0.0) for k in EMITTERS}
        if state != "title":
            for key, x in self._emitters(street):
                _, gain, radius = EMITTERS[key]
                g, p = self._spatial(x - sx, radius)
                if g * gain > targets[key][0]:
                    targets[key] = (g * gain, p)
        for key, (vol, pan) in targets.items():
            self._set_loop(key, vol * amb, pan, dt, 6.0)

        if state != "playing":
            return

        # glitches creep in as the street rots (no ambient heartbeat: that's the cafe_heartbeat anomaly's cue)
        if c > 0.55 and random.random() < dt * 0.06 * c:
            self.play(f"glitch_{random.randint(1, 3)}", 0.15 + 0.2 * c, random.uniform(-0.8, 0.8))

        # Scotty
        cat = street.anomaly == "cat"
        if scotty.on_ground and scotty.vx:
            running = abs(scotty.vx) > 300
            if scotty.walk_dist - self.last_step >= STEP_STRIDE[running]:
                self.last_step = scotty.walk_dist
                vol = (0.45 if running else 0.3) * (0.5 if cat else 1.0)
                self.play(f"step_{random.randint(1, 4)}", vol * random.uniform(0.8, 1.0))
        else:
            self.last_step = scotty.walk_dist - STEP_STRIDE[False] * 0.6   # first step comes quickly
        if self.prev_ground and not scotty.on_ground:
            self.play("jump", 0.5)
        if not self.prev_ground and scotty.on_ground:
            self.play("land", 0.6 * (0.5 if cat else 1.0))
        if scotty.barking and not self.prev_bark:
            if cat:
                self.play("meow_wrong" if c > 0.5 else "meow", 0.8)
            elif c > 0.4 and random.random() < 0.35 * c:
                self.play("bark_wrong_echo", 0.85)
            else:
                self.play(random.choice(("bark_1", "bark_2")), 0.8)
        self.prev_ground = scotty.on_ground
        self.prev_bark = scotty.barking

        self._anomaly_oneshots(street, sx)


if __name__ == "__main__":
    # Audition: python3 audio.py            -> every sound in turn
    #           python3 audio.py bark meow   -> just the sounds whose names contain these words
    import sys

    pygame.mixer.init(44100, -16, 2, 512)
    names = sorted(os.path.splitext(f)[0] for f in os.listdir(SOUND_DIR) if f.endswith(".wav"))
    if sys.argv[1:]:
        names = [n for n in names if any(word in n for word in sys.argv[1:])]
    for name in names:
        snd = pygame.mixer.Sound(os.path.join(SOUND_DIR, name + ".wav"))
        length = min(snd.get_length(), 6.0)
        print(f"{name:26s} {snd.get_length():5.2f}s")
        snd.play(fade_ms=0)
        pygame.time.wait(int(length * 1000) + 300)
        snd.stop()
