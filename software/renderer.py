import sys

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
        if state.is_over:
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
    receives a simple newline-separated frame.  This keeps the renderer usable
    with a serial port or a test transport without forcing a hardware
    dependency on the rest of the program.
    """

    EMPTY = 0
    BLUE = 1
    RED = 2
    CURSOR = 3

    def __init__(self, matrix_size: int = 32, write=None):
        if matrix_size < 1:
            raise ValueError("matrix size must be positive")
        self.matrix_size = matrix_size
        self.write = write

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
        if self.write is not None:
            self.write(self.encode(frame))
        return frame
