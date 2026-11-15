import sys
import threading
import time

from board import Board, Piece


SYMBOLS = {
    Piece.EMPTY: ".",
    Piece.BLUE: "B",
    Piece.RED: "R",
    Piece.INVALID: "?",
}

CURSOR_SYMBOLS = {
    Piece.EMPTY: "+",
    Piece.BLUE: "b",
    Piece.RED: "r",
}


def column_label(x: int) -> str:
    """Returns spreadsheet-style column labels: A..Z, AA, AB, ..."""
    label = ""
    x += 1
    while x > 0:
        x, remainder = divmod(x - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def format_coordinate(x: int, y: int) -> str:
    return f"{column_label(x)}{y + 1}"


class BoardRenderer:
    """Renders the board and game information as text."""

    def to_string(
        self,
        board: Board,
        cursor: tuple | None = None,
        state=None,
        show_cursor: bool = True,
    ) -> str:
        lines = []
        header = "   " + " ".join(column_label(x) for x in range(board.size))
        lines.append(header)

        for y in range(board.size):
            cells = []
            for x in range(board.size):
                piece = board.stone_at(x, y)
                if show_cursor and cursor is not None and (x, y) == tuple(cursor):
                    cells.append(CURSOR_SYMBOLS.get(piece, SYMBOLS[piece]))
                else:
                    cells.append(SYMBOLS.get(piece, "?"))
            lines.append(f"{y + 1:2d} " + " ".join(cells))

        if state is not None:
            lines.append("")
            lines.append(self._status(state))
        return "\n".join(lines)

    def _status(self, state) -> str:
        if state.resigned_by is not None:
            status = f"Game over ({state.resigned_by.name.title()} resigned)"
        elif state.is_over:
            status = "Game over (two passes)"
        else:
            status = f"{state.current_player.name.title()} to play"
        status += (
            f" | Captures: Blue {state.captured[Piece.BLUE]},"
            f" Red {state.captured[Piece.RED]}"
        )

        last_move = state.last_move
        if last_move is not None:
            if last_move.is_pass:
                move_text = f"{last_move.color.name.title()} passed"
            else:
                move_text = (
                    f"{last_move.color.name.title()} "
                    f"{format_coordinate(last_move.x, last_move.y)}"
                )
                if last_move.captured:
                    move_text += f" captured {len(last_move.captured)}"
            status += f" | Last: {move_text}"
        return status

    def render(
        self,
        board: Board,
        cursor: tuple | None = None,
        state=None,
        file=None,
        show_cursor: bool = True,
    ) -> str:
        text = self.to_string(board, cursor, state, show_cursor)
        if file is not False:
            print(text, file=file or sys.stdout)
        return text


def matrix_layout(matrix_size: int, size: int) -> tuple:
    """Returns ``(tile, offset)`` for drawing a board on the LED matrix.

    The 32x32 panels are scanned as two 16-row halves, and the libraries do
    not always render a tile split across that seam correctly.  Keep the
    centred layout when possible, but nudge it up or down so no tile crosses
    the half-panel boundary.  When the tiles are too large for that to be
    possible (for example a 3x3 board with 10x10 tiles) the centred layout is
    used unchanged.
    """
    if matrix_size < size:
        raise ValueError("matrix must be at least as large as the board")

    tile = max(1, matrix_size // size)
    span = tile * size
    offset = max(0, (matrix_size - span) // 2)
    seam = matrix_size // 2

    def crosses_seam(value: int) -> bool:
        return any(
            value + row * tile < seam < value + row * tile + tile
            for row in range(size)
        )

    if tile > 1 and crosses_seam(offset):
        candidates = [
            value
            for value in range(0, matrix_size - span + 1)
            if not crosses_seam(value)
        ]
        if candidates:
            # Prefer the offset closest to the centred layout; break ties
            # towards the upper half for a stable, reproducible frame.
            offset = min(candidates, key=lambda value: (abs(value - offset), value))

    return tile, offset


def panel_geometry(matrix_size: int, size: int) -> dict:
    """Returns the board layout and the border coordinates around it.

    The board occupies ``span`` pixels starting at ``offset``.  The border
    sits one pixel outside that area.  When the board fills the panel the
    border coordinates fall outside it; callers should use :func:`has_border`
    before drawing.
    """
    tile, offset = matrix_layout(matrix_size, size)
    span = tile * size
    return {
        "tile": tile,
        "offset": offset,
        "span": span,
        "left": offset - 1,
        "top": offset - 1,
        "right": offset + span,
        "bottom": offset + span,
    }


def has_border(matrix_size: int, size: int) -> bool:
    """Reports whether a one-pixel border fits around the board."""
    geometry = panel_geometry(matrix_size, size)
    return (
        geometry["left"] >= 0
        and geometry["top"] >= 0
        and geometry["right"] < matrix_size
        and geometry["bottom"] < matrix_size
    )


def border_lines(matrix_size: int, size: int) -> list:
    """Returns ``(x0, y0, x1, y1)`` lines for the border around the board."""
    if not has_border(matrix_size, size):
        return []
    geometry = panel_geometry(matrix_size, size)
    left = geometry["left"]
    right = geometry["right"]
    top = geometry["top"]
    bottom = geometry["bottom"]
    return [
        (left, top, right, top),
        (left, bottom, right, bottom),
        (left, top, left, bottom),
        (right, top, right, bottom),
    ]


def tick_pixels(matrix_size: int, size: int) -> set:
    """Returns the border pixels that mark every board line boundary."""
    if not has_border(matrix_size, size):
        return set()
    geometry = panel_geometry(matrix_size, size)
    ticks = set()
    top_row = geometry["top"] - 1
    bottom_row = geometry["bottom"] + 1
    left_col = geometry["left"] - 1
    right_col = geometry["right"] + 1
    for index in range(size + 1):
        position = geometry["offset"] + index * geometry["tile"]
        if not 0 <= position < matrix_size:
            continue
        for row in (top_row, bottom_row):
            if 0 <= row < matrix_size:
                ticks.add((position, row))
        for column in (left_col, right_col):
            if 0 <= column < matrix_size:
                ticks.add((column, position))
    return ticks


def cursor_tick_pixels(matrix_size: int, size: int, cursor: tuple | None) -> set:
    """Returns the tick pixels highlighted for the cursor's row and column."""
    if cursor is None or not has_border(matrix_size, size):
        return set()
    geometry = panel_geometry(matrix_size, size)
    x, y = cursor
    if not (0 <= x < size and 0 <= y < size):
        return set()

    pixels = set()
    tile = geometry["tile"]
    x_start = geometry["offset"] + x * tile
    y_start = geometry["offset"] + y * tile
    for px in range(x_start, min(x_start + tile, matrix_size)):
        for row in (geometry["top"] - 1, geometry["bottom"] + 1):
            if 0 <= row < matrix_size:
                pixels.add((px, row))
    for py in range(y_start, min(y_start + tile, matrix_size)):
        for column in (geometry["left"] - 1, geometry["right"] + 1):
            if 0 <= column < matrix_size:
                pixels.add((column, py))
    return pixels


def tracker_rectangles(
    matrix_size: int, size: int, count: int, side: str
) -> list:
    """Returns ``(x, y, width, height)`` blocks for captured stones.

    Blue captures run along the bottom edge and red captures down the right
    edge.  Each stone is a 2x2 block, and the far corner is left free so the
    two tracks cannot overwrite each other.
    """
    if side not in ("bottom", "right"):
        raise ValueError("side must be 'bottom' or 'right'")
    if count <= 0 or not has_border(matrix_size, size):
        return []

    geometry = panel_geometry(matrix_size, size)
    # Leave the last two pixels of the edge for the other tracker.
    slots = max(0, (matrix_size - 2) // 2)
    count = min(count, slots)
    rectangles = []
    if side == "bottom":
        y = geometry["bottom"] + 2
        if y >= matrix_size:
            return []
        height = min(2, matrix_size - y)
        for index in range(count):
            rectangles.append((index * 2, y, 2, height))
    else:
        x = geometry["right"] + 2
        if x >= matrix_size:
            return []
        width = min(2, matrix_size - x)
        for index in range(count):
            rectangles.append((x, index * 2, width, 2))
    return rectangles


class LEDRenderer:
    """Renders the board into a square LED-matrix frame.

    ``write`` may be any callable accepting a ``str``; when supplied it
    receives a simple newline-separated frame.  ``transport`` may be an object
    with a ``send(board, cursor)`` method, such as
    :class:`SerialLEDTransport`.  This keeps the renderer usable with a serial
    port or a test transport without forcing a hardware dependency on the rest
    of the program.
    """

    EMPTY = 0
    BLUE = 1
    RED = 2
    CURSOR = 3
    BORDER = 4
    TICK = 5
    CURSOR_TICK = 6
    BLUE_TRACKER = 7
    RED_TRACKER = 8

    def __init__(self, matrix_size: int = 32, write=None, transport=None):
        if matrix_size < 1:
            raise ValueError("matrix size must be positive")
        self.matrix_size = matrix_size
        self.write = write
        self.transport = transport

    def frame(
        self,
        board: Board,
        cursor: tuple | None = None,
        captured: dict | None = None,
    ) -> list:
        size = board.size
        if self.matrix_size < size:
            raise ValueError("matrix must be at least as large as the board")
        tile, offset = matrix_layout(self.matrix_size, size)
        frame = [
            [self.EMPTY for _ in range(self.matrix_size)]
            for _ in range(self.matrix_size)
        ]

        for x0, y0, x1, y1 in border_lines(self.matrix_size, size):
            if y0 == y1:
                for px in range(min(x0, x1), max(x0, x1) + 1):
                    frame[y0][px] = self.BORDER
            else:
                for py in range(min(y0, y1), max(y0, y1) + 1):
                    frame[py][x0] = self.BORDER

        captured = captured or {}
        # Blue captures red stones, so the bottom track is red; red captures
        # blue stones, so the right track is blue.
        trackers = (
            ("bottom", Piece.BLUE, self.RED_TRACKER),
            ("right", Piece.RED, self.BLUE_TRACKER),
        )
        for side, capturer, value in trackers:
            for x, y, width, height in tracker_rectangles(
                self.matrix_size, size, captured.get(capturer, 0), side
            ):
                for dy in range(height):
                    for dx in range(width):
                        frame[y + dy][x + dx] = value

        for px, py in tick_pixels(self.matrix_size, size):
            frame[py][px] = self.TICK

        for y in range(size):
            for x in range(size):
                piece = board.stone_at(x, y)
                if piece is Piece.BLUE:
                    value = self.BLUE
                elif piece is Piece.RED:
                    value = self.RED
                else:
                    value = self.EMPTY
                if cursor is not None and (x, y) == tuple(cursor):
                    value = self.CURSOR
                for dy in range(tile):
                    for dx in range(tile):
                        frame[offset + y * tile + dy][offset + x * tile + dx] = value

        for px, py in cursor_tick_pixels(self.matrix_size, size, cursor):
            frame[py][px] = self.CURSOR_TICK
        return frame

    def encode(self, frame: list) -> str:
        return "\n".join(",".join(str(value) for value in row) for row in frame)

    def render(
        self,
        board: Board,
        cursor: tuple | None = None,
        captured: dict | None = None,
    ) -> list:
        frame = self.frame(board, cursor, captured)
        if self.transport is not None:
            self.transport.send(board, cursor, captured)
        elif self.write is not None:
            self.write(self.encode(frame))
        return frame

    def move_cursor(self, board: Board, cursor: tuple | None) -> None:
        """Moves the LED cursor without sending a full frame."""
        move = getattr(self.transport, "move_cursor", None)
        if move is not None:
            move(board, cursor)


class SerialLEDTransport:
    """Sends board positions to Nathan's Arduino firmware over a serial port.

    The firmware accepts newline-terminated commands.  This transport uses:

    * ``B n`` — set brightness (1 = dimmest, 7 = brightest)
    * ``C`` — clear the panel
    * ``S x y size r g b 1`` — draw a filled square
    * ``P x y r g b`` — draw one pixel
    * ``L x0 y0 x1 y1 r g b`` — draw a line
    * ``J`` — read the joystick state (``J <U|D|L|R|0> <0|1>``)

    The cursor blinks by toggling just its own pixels, so the rest of the
    board is not redrawn.  It can also be moved without redrawing the whole
    board, which keeps joystick movement responsive.

    A one-pixel border with ticks surrounds the board.  The tick beside the
    cursor's row and column is brightened, so the border acts as a coordinate
    indicator.  Captured stones are tracked along the edges in the colour of
    the captured stone: blue's captures (red stones) run along the bottom and
    red's captures (blue stones) down the right side.

    Each intersection is drawn as a centred tile.  Blue stones use blue,
    red stones use red, and the cursor uses grey on an empty point or a white
    pixel on top of a stone.  The cursor blinks by default by toggling only
    those pixels, so the rest of the board is not redrawn.  The firmware also
    supports ``P`` (pixel), ``X`` (clear pixel), ``L`` (line) and ``T``
    (triangle), so other scripts can draw on the same panel.
    """

    MAX_SIZE = 19
    MATRIX_SIZE = 32
    MIN_BRIGHTNESS = 1
    MAX_BRIGHTNESS = 7

    BLUE_RGB = (0, 0, 7)
    RED_RGB = (7, 0, 0)
    CURSOR_RGB = (4, 4, 4)
    WHITE_RGB = (7, 7, 7)
    BORDER_RGB = (1, 1, 1)
    TICK_RGB = (3, 3, 3)
    CURSOR_TICK_RGB = (7, 7, 7)
    TRACKER_RGB = {
        Piece.BLUE: (0, 0, 7),
        Piece.RED: (7, 0, 0),
    }

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
        brightness: int = 1,
        matrix_size: int = MATRIX_SIZE,
        ready_timeout: float = 3.0,
        ack_timeout: float = 1.0,
        blink: bool = True,
        blink_interval: float = 0.25,
    ):
        if not self.MIN_BRIGHTNESS <= brightness <= self.MAX_BRIGHTNESS:
            raise ValueError(
                f"brightness must be {self.MIN_BRIGHTNESS}-{self.MAX_BRIGHTNESS}"
            )
        if matrix_size < 1:
            raise ValueError("matrix size must be positive")
        if blink_interval <= 0:
            raise ValueError("blink interval must be positive")
        try:
            import serial
        except ImportError as error:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "pyserial is required for LED output; run "
                "'python3 -m pip install --user pyserial'"
            ) from error
        self.port = port
        self.brightness = brightness
        self.matrix_size = matrix_size
        self.ack_timeout = ack_timeout
        self.serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        # Opening the port resets the Uno.  Wait for its READY banner so the
        # first board frame is not sent while the firmware is still booting.
        self._wait_for_ready(ready_timeout)

        self._lock = threading.RLock()
        self._blink_stop = threading.Event()
        self._blink_interval = blink_interval
        self._blink_thread = None
        self._cursor = None
        self._cursor_piece = None
        self._cursor_size = None
        self._blink_visible = True
        if blink:
            self._blink_thread = threading.Thread(
                target=self._blink_loop, name="led-cursor-blink", daemon=True
            )
            self._blink_thread.start()

    def _layout(self, size: int) -> tuple:
        return matrix_layout(self.matrix_size, size)

    def _wait_for_ready(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.serial.readline().decode("ascii", "replace").strip()
            if line == "READY":
                return True
        return False

    def _rect_commands(self, rectangle: tuple, colour: tuple) -> list:
        x, y, width, height = rectangle
        red, green, blue = colour
        if width == 2 and height == 2:
            return [f"S {x} {y} 2 {red} {green} {blue} 1"]
        if height == 1:
            return [f"L {x} {y} {x + width - 1} {y} {red} {green} {blue}"]
        if width == 1:
            return [f"L {x} {y} {x} {y + height - 1} {red} {green} {blue}"]
        return [
            f"P {x + dx} {y + dy} {red} {green} {blue}"
            for dy in range(height)
            for dx in range(width)
        ]

    def encode(
        self,
        board: Board,
        cursor: tuple | None = None,
        captured: dict | None = None,
    ) -> bytes:
        size = board.size
        if not 1 <= size <= self.MAX_SIZE:
            raise ValueError(f"board size {size} is not supported by the LED firmware")
        if size > self.matrix_size:
            raise ValueError("matrix must be at least as large as the board")

        tile, offset = self._layout(size)

        commands = [f"B {self.brightness}", "C"]
        red, green, blue = self.BORDER_RGB
        for x0, y0, x1, y1 in border_lines(self.matrix_size, size):
            commands.append(f"L {x0} {y0} {x1} {y1} {red} {green} {blue}")

        captured = captured or {}
        # The track shows the colour of the captured stone, not the colour of
        # the side that captured it.  Blue captures red stones along the
        # bottom; red captures blue stones down the right.
        trackers = (
            ("bottom", Piece.BLUE),
            ("right", Piece.RED),
        )
        for side, capturer in trackers:
            colour = self.TRACKER_RGB[capturer.opponent]
            for rectangle in tracker_rectangles(
                self.matrix_size, size, captured.get(capturer, 0), side
            ):
                commands.extend(self._rect_commands(rectangle, colour))

        red, green, blue = self.TICK_RGB
        for px, py in sorted(tick_pixels(self.matrix_size, size)):
            commands.append(f"P {px} {py} {red} {green} {blue}")

        for y in range(size):
            for x in range(size):
                piece = board.stone_at(x, y)
                px = offset + x * tile
                py = offset + y * tile
                is_cursor = cursor is not None and (x, y) == tuple(cursor)

                if piece is Piece.BLUE:
                    red, green, blue = self.BLUE_RGB
                elif piece is Piece.RED:
                    red, green, blue = self.RED_RGB
                elif is_cursor:
                    red, green, blue = self.CURSOR_RGB
                else:
                    continue

                commands.append(
                    f"S {px} {py} {tile} {red} {green} {blue} 1"
                )
                if is_cursor and piece in (Piece.BLUE, Piece.RED):
                    # Keep the stone colour while showing where the cursor is.
                    commands.append(f"P {px} {py} 7 7 7")

        red, green, blue = self.CURSOR_TICK_RGB
        for px, py in sorted(cursor_tick_pixels(self.matrix_size, size, cursor)):
            commands.append(f"P {px} {py} {red} {green} {blue}")
        return ("\n".join(commands) + "\n").encode("ascii")

    def _wait_for_ack(self, command: bytes, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.serial.readline().decode("ascii", "replace").strip()
            if line == "OK":
                return
            if line == "ERR":
                raise OSError(
                    "LED firmware rejected command: "
                    f"{command.decode('ascii', 'replace')!r}"
                )
        raise OSError(
            "LED firmware did not acknowledge command: "
            f"{command.decode('ascii', 'replace')!r}"
        )

    def _write_acked(self, command: bytes) -> None:
        self.serial.write(command + b"\n")
        self.serial.flush()
        self._wait_for_ack(command, self.ack_timeout)

    def poll_joystick(self, timeout: float = 0.3) -> tuple | None:
        """Returns ``(direction, pressed, pass_pressed)`` or ``None``.

        ``direction`` is one of ``U``, ``D``, ``L``, ``R`` or ``0``.  The
        firmware replies to a ``J`` command with
        ``J <direction> <0|1> <0|1>``.  Older firmware that omits the final
        pass field is still accepted.  The serial transaction is locked so it
        cannot interleave with the cursor-blink thread.
        """
        with self._lock:
            previous_timeout = getattr(self.serial, "timeout", None)
            try:
                if previous_timeout is not None:
                    # Keep a missing reply from stalling the input loop.
                    self.serial.timeout = min(previous_timeout, 0.05)
                self.serial.write(b"J\n")
                self.serial.flush()
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    raw = self.serial.readline()
                    if not raw:
                        continue
                    line = raw.decode("ascii", "replace").strip()
                    if not line.startswith("J "):
                        continue
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    direction = parts[1].upper()
                    if direction not in ("U", "D", "L", "R"):
                        direction = "0"
                    pass_pressed = len(parts) >= 4 and parts[3] != "0"
                    return direction, parts[2] != "0", pass_pressed
                return None
            finally:
                if previous_timeout is not None:
                    self.serial.timeout = previous_timeout

    def _remember_cursor(self, board: Board, cursor: tuple | None) -> None:
        if cursor is None:
            self._cursor = None
            return
        x, y = cursor
        if not (0 <= x < board.size and 0 <= y < board.size):
            self._cursor = None
            return
        self._cursor = (x, y)
        self._cursor_piece = board.stone_at(x, y)
        self._cursor_size = board.size
        # The full frame just drew the cursor in its visible state.
        self._blink_visible = True

    def _write_cursor(self) -> None:
        if self._cursor is None:
            return

        x, y = self._cursor
        tile, offset = self._layout(self._cursor_size)
        px = offset + x * tile
        py = offset + y * tile
        piece = self._cursor_piece

        if self._blink_visible:
            if piece in (Piece.BLUE, Piece.RED):
                red, green, blue = self.WHITE_RGB
                command = f"P {px} {py} {red} {green} {blue}"
            else:
                red, green, blue = self.CURSOR_RGB
                command = f"S {px} {py} {tile} {red} {green} {blue} 1"
        elif piece is Piece.BLUE:
            red, green, blue = self.BLUE_RGB
            command = f"P {px} {py} {red} {green} {blue}"
        elif piece is Piece.RED:
            red, green, blue = self.RED_RGB
            command = f"P {px} {py} {red} {green} {blue}"
        else:
            command = f"S {px} {py} {tile} 0 0 0 1"

        self._write_acked(command.encode("ascii"))

    def _write_cursor_ticks(
        self, size: int, cursor: tuple | None, restore: bool = False
    ) -> None:
        """Draws or restores the row/column highlight on the tick border."""
        pixels = cursor_tick_pixels(self.matrix_size, size, cursor)
        if not pixels:
            return
        ticks = tick_pixels(self.matrix_size, size) if restore else set()
        for px, py in sorted(pixels):
            if restore:
                colour = (
                    self.TICK_RGB if (px, py) in ticks else (0, 0, 0)
                )
            else:
                colour = self.CURSOR_TICK_RGB
            red, green, blue = colour
            self._write_acked(f"P {px} {py} {red} {green} {blue}".encode("ascii"))

    def _draw_point(self, board: Board, point: tuple, size: int = None) -> None:
        """Redraws one intersection, including clearing an empty point."""
        if size is None:
            size = board.size
        tile, offset = self._layout(size)
        x, y = point
        piece = board.stone_at(x, y)
        if piece is Piece.BLUE:
            red, green, blue = self.BLUE_RGB
        elif piece is Piece.RED:
            red, green, blue = self.RED_RGB
        else:
            red, green, blue = (0, 0, 0)
        px = offset + x * tile
        py = offset + y * tile
        self._write_acked(
            f"S {px} {py} {tile} {red} {green} {blue} 1".encode("ascii")
        )

    def move_cursor(self, board: Board, cursor: tuple | None) -> None:
        """Moves the cursor without redrawing the whole board.

        Joystick movement can therefore update the panel at button-repeat
        speed instead of taking a full-frame serial transfer per step.
        """
        with self._lock:
            old = self._cursor
            old_size = self._cursor_size
            self._remember_cursor(board, cursor)
            if old == self._cursor:
                return
            if old is not None:
                self._write_cursor_ticks(old_size, old, restore=True)
                self._draw_point(board, old, old_size)
            if self._cursor is not None:
                self._blink_visible = True
                self._write_cursor()
                self._write_cursor_ticks(board.size, self._cursor)

    def _blink_loop(self) -> None:
        while not self._blink_stop.wait(self._blink_interval):
            with self._lock:
                if self._cursor is None:
                    continue
                self._blink_visible = not self._blink_visible
                try:
                    self._write_cursor()
                except OSError:
                    # The port was unplugged or closed; stop blinking quietly.
                    return

    def send(
        self,
        board: Board,
        cursor: tuple | None = None,
        captured: dict | None = None,
    ) -> None:
        # The Uno has a 64-byte serial input buffer.  Send one command at a
        # time and wait for the firmware's "OK", otherwise a full 13x13 board
        # can overrun the buffer and leave a partial frame on the panel.
        payload = self.encode(board, cursor, captured)
        with self._lock:
            for line in payload.splitlines():
                self._write_acked(line)
            self._remember_cursor(board, cursor)
            # Drop any late or unsolicited replies so they cannot confuse the
            # next acknowledgement.
            reset_input = getattr(self.serial, "reset_input_buffer", None)
            if reset_input is not None:
                reset_input()

    def close(self) -> None:
        self._blink_stop.set()
        thread = self._blink_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self.ack_timeout + 0.5))
        self._blink_thread = None
        with self._lock:
            if self._cursor is not None:
                # Leave the panel with a visible cursor instead of whichever
                # blink phase happened to be active when the game ended.
                self._blink_visible = True
                try:
                    self._write_cursor()
                except OSError:
                    pass
            self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
