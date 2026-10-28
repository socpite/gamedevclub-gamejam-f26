# Scotty Starter

A one-file Pygame starter game. You play Scotty, who walks, runs, jumps and barks in front of a scrolling Doha / Education City background.

## Run it

1. Install Python 3.
2. Install pygame-ce:
   ```
   pip install pygame-ce
   ```
   On Python 3.14, the classic `pygame` package can't load PNGs, so use `pygame-ce`. Your code still says `import pygame`.
3. Run the game from this folder:
   ```
   python3 scotty_starter.py
   ```

Keep `scotty_starter.py` and the `assets/` folder together in the same folder.

## Controls

| Key | Action |
| --- | --- |
| A / D or ← / → | Walk |
| Hold Shift | Run |
| Space / W / ↑ | Jump |
| B | Bark |
| F1 | Debug info |
| Esc | Quit |

## Making it your own

- Speeds, gravity, jump strength, window size and layer scroll speeds are constants at the top of `scotty_starter.py`.
- Load any other asset with `os.path.join(ASSETS_DIR, "platforms", "crate.png")`. The assets are sorted into folders: platforms, collectibles, hazards, powerups, characters, decor and ui.
