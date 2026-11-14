from dataclasses import dataclass, field
from typing import Optional

from board import Board, Piece
from engine import RulesEngine


@dataclass
class Move:
    """A single move in the game history.

    ``board_before`` and the other ``*_before`` fields contain a snapshot used
    by :meth:`GameState.undo_move`.  ``board_before`` is deliberately excluded
    from :meth:`to_dict`; saved games store the move list and replay it.
    """

    color: Piece
    x: Optional[int] = None
    y: Optional[int] = None
    captured: tuple = ()
    board_before: Optional[Board] = None
    ko_before: Optional[tuple] = None
    passes_before: int = 0
    captured_before: dict = field(default_factory=dict)

    @property
    def is_pass(self) -> bool:
        return self.x is None or self.y is None

    def to_dict(self) -> dict:
        return {
            "color": self.color.name,
            "x": self.x,
            "y": self.y,
            "captured": [list(position) for position in self.captured],
        }


class GameState:
    """Keeps track of the board, turn order, captures and move history."""

    def __init__(self, size: int = Board.DEFAULT_SIZE):
        self.board = Board(size)
        self.engine = RulesEngine()
        self.current_player = Piece.BLUE
        self.history = []
        self.ko_point = None
        self.consecutive_passes = 0
        self.captured = {Piece.BLUE: 0, Piece.RED: 0}

    @property
    def is_over(self) -> bool:
        """The game ends after two consecutive passes."""
        return self.consecutive_passes >= 2

    @property
    def last_move(self) -> Optional[Move]:
        return self.history[-1] if self.history else None

    def _snapshot(self) -> dict:
        return {
            "board_before": self.board.copy(),
            "ko_before": self.ko_point,
            "passes_before": self.consecutive_passes,
            "captured_before": dict(self.captured),
        }

    def play_move(self, x: int, y: int) -> bool:
        """Attempts to play a stone for the current player.

        Returns ``True`` when the move was legal and applied.
        """
        if self.is_over:
            return False

        color = self.current_player
        if not self.engine.is_legal(self.board, x, y, color, self.ko_point):
            return False

        snapshot = self._snapshot()
        captured = self.engine.apply_move(self.board, x, y, color)
        self.captured[color] += len(captured)
        self.ko_point = self.engine.ko_point(self.board, x, y, color, captured)
        self.consecutive_passes = 0
        self.history.append(
            Move(
                color=color,
                x=x,
                y=y,
                captured=tuple(sorted(captured)),
                **snapshot,
            )
        )
        self.current_player = color.opponent
        return True

    def play_pass(self) -> bool:
        """Passes the turn.  Two consecutive passes end the game."""
        if self.is_over:
            return False

        color = self.current_player
        snapshot = self._snapshot()
        self.ko_point = None
        self.consecutive_passes += 1
        self.history.append(
            Move(
                color=color,
                x=None,
                y=None,
                captured=(),
                **snapshot,
            )
        )
        self.current_player = color.opponent
        return True

    def undo_move(self) -> bool:
        """Restores the position before the most recent move or pass."""
        if not self.history:
            return False

        move = self.history.pop()
        self.board = move.board_before
        self.ko_point = move.ko_before
        self.consecutive_passes = move.passes_before
        self.captured = dict(move.captured_before)
        self.current_player = move.color
        return True

    def to_dict(self) -> dict:
        """Serialises the game as a replayable move list."""
        return {
            "size": self.board.size,
            "moves": [
                {"color": move.color.name, "x": move.x, "y": move.y}
                for move in self.history
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        """Replays a dictionary produced by :meth:`to_dict`."""
        state = cls(size=data.get("size", Board.DEFAULT_SIZE))
        for entry in data.get("moves", []):
            color = Piece[entry["color"]]
            # Replay enforces the same turn order and legality rules as live
            # play.  This also rebuilds captures and ko state.
            if color is not state.current_player:
                raise ValueError("move list is not in turn order")
            x, y = entry.get("x"), entry.get("y")
            if x is None or y is None:
                if not state.play_pass():
                    raise ValueError("invalid pass in move list")
            elif not state.play_move(x, y):
                raise ValueError(f"illegal move in move list: {entry}")
        return state
