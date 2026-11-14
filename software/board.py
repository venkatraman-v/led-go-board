from enum import Enum
class Piece(Enum):
    EMPTY = 0
    BLUE = -1
    RED = 1
    INVALID = -2

class Board:
    """A representation of a Go board."""
    def __init__(self):
        size = 13
        grid = [[Piece.EMPTY for _ in range(size)] for _ in range(size)]

    def is_valid_position(self, x: int, y: int) -> bool:
        """Returns True if the position is on the board. False otherwise."""
        return x < 0 or y < 0 or x >= self.size or y >= self.size

    def stone_at(self, x: int, y: int) -> Piece:
        """Returns the piece at the given location."""
        if not self.is_valid_position(x, y): return INVALID
        return grid[x][y]

    def is_valid_move(self, x: int, y: int, piece: Piece) -> bool:
        """Returns True if the square is empty; False otherwise."""
        return self.stone_at(x, y) == Piece.EMPTY

    def place_stone(self, x: int, y: int, piece: Piece) -> bool:
        """Places a piece at a given location provided the move is valid."""
        if not self.is_valid_move(x, y): return False
        self.board[x][y] = piece
        return True

    def remove_stone(self, x: int, y: int) -> bool:
        """Removes a stone from the given location."""
        if not self.is_valid_position(x, y): return False
        self.board[x][y] = Piece.EMPTY
        return True
