from enum import Enum


class Piece(Enum):
    EMPTY = 0
    BLUE = -1
    RED = 1
    INVALID = -2

    @property
    def opponent(self) -> "Piece":
        """Returns the opposing colour for a stone colour."""
        if self is Piece.BLUE:
            return Piece.RED
        if self is Piece.RED:
            return Piece.BLUE
        return Piece.EMPTY


class Board:
    """A representation of a Go board.

    Coordinates are zero based ``(x, y)`` pairs where ``x`` is the column
    and ``y`` is the row.  The upper left corner is ``(0, 0)``.
    """

    DEFAULT_SIZE = 13

    def __init__(self, size: int = DEFAULT_SIZE):
        if size < 1:
            raise ValueError("board size must be positive")
        self.size = size
        self.grid = [[Piece.EMPTY for _ in range(size)] for _ in range(size)]

    def __getitem__(self, x: int):
        """Allow ``board[x][y]`` access for compatibility with the engine."""
        return self.grid[x]

    def is_valid_position(self, x: int, y: int) -> bool:
        """Returns True if the position is on the board. False otherwise."""
        return 0 <= x < self.size and 0 <= y < self.size

    def stone_at(self, x: int, y: int) -> Piece:
        """Returns the piece at the given location."""
        if not self.is_valid_position(x, y):
            return Piece.INVALID
        return self.grid[x][y]

    def is_valid_move(self, x: int, y: int, piece: Piece = Piece.EMPTY) -> bool:
        """Returns True if the intersection is empty and on the board."""
        return self.is_valid_position(x, y) and self.stone_at(x, y) is Piece.EMPTY

    def place_stone(self, x: int, y: int, piece: Piece) -> bool:
        """Places a piece at a given location provided the move is valid."""
        if piece not in (Piece.BLUE, Piece.RED):
            return False
        if not self.is_valid_move(x, y):
            return False
        self.grid[x][y] = piece
        return True

    def remove_stone(self, x: int, y: int) -> bool:
        """Removes a stone from the given location."""
        if not self.is_valid_position(x, y):
            return False
        self.grid[x][y] = Piece.EMPTY
        return True

    def copy(self) -> "Board":
        """Returns an independent copy of this board."""
        clone = Board(self.size)
        clone.grid = [row[:] for row in self.grid]
        return clone

    def signature(self) -> tuple:
        """A hashable snapshot of the board position.

        Used for ko detection and for saving/loading games.
        """
        return tuple(tuple(piece.value for piece in row) for row in self.grid)

    def __str__(self) -> str:
        from renderer import BoardRenderer

        return BoardRenderer().to_string(self)
