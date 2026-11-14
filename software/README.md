# LED Go Board — Python Game Logic

This directory contains the game engine and the command-line driver for the
13×13 Go board.

## Run

```bash
# Automated capture demo (also the default when stdin is not a terminal)
python main.py --demo

# Interactive play
python main.py --interactive
```

Interactive commands:

| Command | Meaning |
| --- | --- |
| `play A1` | Play at a labelled coordinate |
| `play 4 5` | Play at a zero-based `x y` coordinate |
| `up` / `down` / `left` / `right` | Move the joystick cursor |
| `goto A1` | Move the cursor directly |
| `press` | Press the button, playing at the cursor |
| `pass` | Pass the turn |
| `undo` | Undo the most recent move or pass |
| `save FILE` / `load FILE` | Write/read the JSON move list |
| `show` | Redraw the board |
| `quit` | Exit |

The board is drawn with `B` for blue and `R` for red.  The joystick cursor is
shown as `+` on an empty point, or as a lowercase `b`/`r` over a stone.

## Rules implemented

- Alternating blue/red turns
- Group and liberty detection
- Removal of captured stones
- Suicide prevention
- Simple ko
- Passes and game end after two consecutive passes
- Undo of moves and passes

## Test

```bash
cd software
python -m unittest discover -s tests -v
```

## Layout

- `board.py` — board representation and pieces
- `engine.py` — Go rules (groups, liberties, captures, suicide, ko)
- `gamestate.py` — board state, turns, captures, history, undo, save/load
- `game.py` — game facade and joystick/button input controller
- `renderer.py` — text board renderer and LED matrix frame renderer
- `main.py` — demo and interactive command-line entry point
