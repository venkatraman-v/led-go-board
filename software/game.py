from collections.abc import Callable
from engine import RulesEngine
from board import Board, Piece

class Game:
    """Handles user input to play a game of Go."""
    def __init__(self):
        self.engine = RulesEngine()
        self.current_player = BLUE
        self.history = []
        self.input_controller = InputController(self.play_move)

    def play_move(self, x: int, y: int) -> bool:
        pass

    def undo_move(self) -> bool:
        pass

class InputController:
    """Handles controls from the joystick and button."""
    def __init__(self, play_move: Callable[[int, int], bool]):
        position = (0,0)
        play_move = play_move

    def handle_joystick(self, x: int, y: int):
        self.position = (x, y)

    def handle_button_press(self):
        return self.play_move(self.position[0], self.position[1])
    