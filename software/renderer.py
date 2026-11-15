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

    def __init__(self, matrix_size: int = 32, write=None, transport=None):
        if matrix_size < 1:
            raise ValueError("matrix size must be positive")
        self.matrix_size = matrix_size
        self.write = write
        self.transport = transport

    def frame(self, board: Board, cursor: tuple | None = None) -> list:
        size = board.size
        if self.matrix_size < size:
            raise ValueError("matrix must be at least as large as the board")
        tile = max(1, self.matrix_size // size)
        span = tile * size
        offset = max(0, (self.matrix_size - span) // 2)
        frame = [
            [self.EMPTY for _ in range(self.matrix_size)]
            for _ in range(self.matrix_size)
        ]

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
        return frame

    def encode(self, frame: list) -> str:
        return "\n".join(",".join(str(value) for value in row) for row in frame)

    def render(self, board: Board, cursor: tuple | None = None) -> list:
        frame = self.frame(board, cursor)
        if self.transport is not None:
            self.transport.send(board, cursor)
        elif self.write is not None:
            self.write(self.encode(frame))
        return frame


class SerialLEDTransport:
    """Sends board positions to Nathan's Arduino firmware over a serial port.

    The firmware accepts newline-terminated commands.  This transport uses:

    * ``B n`` — set brightness (1 = dimmest, 7 = brightest)
    * ``C`` — clear the panel
    * ``S x y size r g b 1`` — draw a filled square
    * ``P x y r g b`` — draw one pixel

    The cursor blinks by toggling just its own pixels, so the rest of the
    board is not redrawn.

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
        tile = max(1, self.matrix_size // size)
        span = tile * size
        offset = max(0, (self.matrix_size - span) // 2)
        return tile, offset

    def _wait_for_ready(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.serial.readline().decode("ascii", "replace").strip()
            if line == "READY":
                return True
        return False

    def encode(self, board: Board, cursor: tuple | None = None) -> bytes:
        size = board.size
        if not 1 <= size <= self.MAX_SIZE:
            raise ValueError(f"board size {size} is not supported by the LED firmware")
        if size > self.matrix_size:
            raise ValueError("matrix must be at least as large as the board")

        tile, offset = self._layout(size)

        commands = [f"B {self.brightness}", "C"]
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

    def send(self, board: Board, cursor: tuple | None = None) -> None:
        # The Uno has a 64-byte serial input buffer.  Send one command at a
        # time and wait for the firmware's "OK", otherwise a full 13x13 board
        # can overrun the buffer and leave a partial frame on the panel.
        payload = self.encode(board, cursor)
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
