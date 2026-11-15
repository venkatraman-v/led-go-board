import json
from collections.abc import Callable

from board import Board, Piece
from engine import RulesEngine
from gamestate import GameState
from renderer import BoardRenderer


class Game:
    """Handles the game state and the input/output flow."""

    def __init__(self, size: int = Board.DEFAULT_SIZE, renderer=None):
        self.game_state = GameState(size)
        self.engine = self.game_state.engine
        self.renderer = renderer or BoardRenderer()
        self.input_controller = InputController(self.play_move, size)

    @property
    def board(self) -> Board:
        return self.game_state.board

    @property
    def current_player(self) -> Piece:
        return self.game_state.current_player

    def play_move(self, x: int, y: int) -> bool:
        """Plays a move for the current player and reports whether it was legal."""
        played = self.game_state.play_move(x, y)
        if played:
            self.input_controller.position = (x, y)
        return played

    def pass_move(self) -> bool:
        return self.game_state.play_pass()

    def undo_move(self) -> bool:
        return self.game_state.undo_move()

    def render(self, file=None, cursor: tuple | None = None) -> str:
        """Renders the current game state and returns the text representation."""
        return self.renderer.render(
            self.board,
            cursor=cursor,
            state=self.game_state,
            file=file,
        )

    def save(self, path: str) -> None:
        """Writes the replayable move list to ``path`` as JSON."""
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.game_state.to_dict(), handle, indent=2)
            handle.write("\n")

    def load(self, path: str) -> None:
        """Replaces the current game with the move list stored at ``path``."""
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.game_state = GameState.from_dict(data)
        self.engine = self.game_state.engine
        self.input_controller = InputController(
            self.play_move, self.game_state.board.size
        )


class InputController:
    """Handles controls from the joystick and button.

    ``handle_joystick`` receives a direction (``dx``, ``dy``) and moves the
    cursor within the board.  ``handle_button_press`` plays at the cursor.
    """

    def __init__(
        self,
        play_move: Callable[[int, int], bool],
        board_size: int = Board.DEFAULT_SIZE,
    ):
        if board_size < 1:
            raise ValueError("board size must be positive")
        self.board_size = board_size
        self.position = (0, 0)
        self.play_move = play_move

    def _clamp(self, value: int) -> int:
        return max(0, min(self.board_size - 1, value))

    def handle_joystick(self, dx: int, dy: int) -> tuple:
        """Moves the cursor by one or more intersections.

        Positive ``dy`` moves down the board, positive ``dx`` moves right.
        The cursor is clamped to the board.
        """
        x, y = self.position
        self.position = (self._clamp(x + dx), self._clamp(y + dy))
        return self.position

    def set_position(self, x: int, y: int) -> tuple:
        if not (0 <= x < self.board_size and 0 <= y < self.board_size):
            raise ValueError(f"cursor outside {self.board_size}x{self.board_size} board")
        self.position = (x, y)
        return self.position

    def handle_button_press(self) -> bool:
        return self.play_move(self.position[0], self.position[1])
