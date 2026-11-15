# LED Go Board — Python Game Logic

This directory contains the game engine, a KataGo opponent, and the
command-line driver for the 13×13 Go board.

## Run

```bash
# Automated capture demo (also the default when stdin is not a terminal)
python main.py --demo

# Interactive play
python main.py --interactive

# Play against KataGo (red by default)
python main.py --vs-katago

# Let KataGo play blue and open the game
python main.py --vs-katago --ai-color blue --visits 200
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
| `engine` | Ask KataGo to move (when it is its turn) |
| `undo` | Undo the most recent move or pass |
| `save FILE` / `load FILE` | Write/read the JSON move list |
| `show` | Redraw the board |
| `quit` | Exit |

The board is drawn with `B` for blue and `R` for red.  The joystick cursor is
shown as `+` on an empty point, or as a lowercase `b`/`r` over a stone.

## Joystick

With `--led-serial`, the firmware reports the analog stick and button over the
same serial connection.  The stick axes are read on **A4 (X)** and **A5 (Y)**.
The button may be wired to **A4**, **D11**, **D12**, or **D13**; on this board
the button shares A4 with the X axis and pulls it to the top rail when pressed.

- Tilting the stick moves the cursor one intersection immediately.
- Holding a direction repeats after 0.35 s at about seven steps per second.
- Pressing the button plays at the cursor and, against KataGo, immediately
  starts the engine reply.
- Use `--no-joystick` to disable hardware input.

Only the cursor changes are sent while the stick moves, so movement stays
responsive even on a full board.

## Playing KataGo

KataGo is driven over GTP in a subprocess.  Before every engine move the full
move history is replayed into the engine, so `undo`, `load`, and human/engine
alternation cannot desynchronise it.

First-time setup (user-local, no sudo needed for the model):

```bash
software/scripts/install_katago.sh
```

The script checks for the `katago` executable, downloads a b18c384nbt network
to `~/.katago/default_model.bin.gz`, copies a GTP config to
`~/.katago/default_gtp.cfg`, and installs `pyserial` for LED output.  If
KataGo itself is missing it prints the system package command instead of
running `sudo`.

Options:

| Option | Meaning |
| --- | --- |
| `--vs-katago` | Enable the engine opponent |
| `--ai-color blue\|red` | Engine colour (default: red) |
| `--visits N` | Search visits per move (default: 100) |
| `--komi N` | Komi passed to KataGo (default: 7.5) |
| `--katago PATH` | KataGo executable |
| `--model PATH` | `.bin.gz` neural network |
| `--config PATH` | GTP config file |

Environment overrides are also supported: `KATAGO_BIN`, `KATAGO_MODEL`,
`KATAGO_CONFIG`, and `KATAGO_LOG_DIR`.

KataGo uses standard GTP coordinates, which skip the letter `I` (`A B C D E
F G H J K ...`).  The text renderer uses spreadsheet-style labels (`A B C ...
M`), so for columns at or after `J` the two labels differ by one.  Moves are
converted internally; use the labels shown by the board when typing moves.

## LED panel

The 32×32 panel is driven from the firmware's serial port.  Connect the board
and pass the port explicitly:

```bash
python main.py --vs-katago --led-serial /dev/ttyACM0
python main.py --vs-katago --led-serial /dev/ttyUSB0 --led-baud 115200
python main.py --vs-katago --led-serial /dev/ttyACM0 --led-brightness 3
```

On Linux the user normally needs membership in the `dialout` (Debian/Ubuntu)
or `uucp` (Arch) group to open the port.  Brightness is `1` (dimmest,
battery-safe) through `7` (brightest).  The cursor blinks at about 2 Hz; use
`--no-led-blink` to keep it steady.

### Serial protocol

The firmware listens for newline-terminated text commands and replies `OK`:

| Command | Meaning |
| --- | --- |
| `P x y r g b` | Draw one pixel (colour channels `0`–`7`) |
| `X x y` | Clear one pixel |
| `C` | Clear the panel |
| `L x0 y0 x1 y1 r g b` | Draw a line |
| `S x y size r g b [fill]` | Draw a square, filled by default |
| `T x0 y0 x1 y1 x2 y2 r g b [fill]` | Draw a triangle |
| `B n` | Set brightness (`1`–`7`) |
| `J` | Return joystick state: `J <U\|D\|L\|R\|0> <0\|1>` |
| `K` | Return raw joystick diagnostics: `K <x> <y> <button bits>` |
| `?` | Return `READY` |

For each board update the Python transport sends `B`, then `C`, then one
filled `S` command per stone or cursor.  Each intersection is a centred tile,
so a 13×13 board becomes 2×2 blocks on the 32×32 panel.  The layout is shifted
by one pixel when needed so no tile straddles the seam between the panel's two
16-row halves.  The cursor is a grey tile on an empty point, or a white pixel
on top of a stone.  Upload the firmware with PlatformIO:

```bash
cd firmware
pio run --target upload
```

Frames also work over any transport with a `send(board, cursor)` method; the
renderer accepts one via `LEDRenderer(transport=...)`.

## Rules implemented

- Alternating blue/red turns
- Group and liberty detection
- Removal of captured stones
- Suicide prevention
- Simple ko
- Passes and game end after two consecutive passes
- Resignation (engine or player) and undo
- Undo of moves and passes

## Test

```bash
cd software
python -m unittest discover -s tests -v
```

The suite does not require KataGo at runtime: engine tests use a fake GTP
engine, while `--vs-katago` was verified manually against the real binary.

## Layout

- `board.py` — board representation and pieces
- `engine.py` — Go rules (groups, liberties, captures, suicide, ko)
- `gamestate.py` — board state, turns, captures, history, undo, save/load
- `game.py` — game facade and joystick/button input controller
- `analysis.py` — KataGo GTP client, `KataGoPlayer`, coordinate conversion
- `renderer.py` — text board renderer, LED frame renderer, serial transport
- `main.py` — demo, interactive, and KataGo entry point
- `scripts/install_katago.sh` — user-local KataGo model/config setup
