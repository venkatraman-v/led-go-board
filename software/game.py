from collections.abc import Callable
from engine import RulesEngine
from board import Board, Piece
from gamestate import GameState

class Game:
    """Handles user input to play a game of Go."""
    def __init__(self):
        self.input_controller = InputController(self.play_move)
        self.engine = RulesEngine(self.board)
        self.game_state = GameState()

    def play_move(position: [int, int]):
        self.game_state.play


class InputController:
    """Handles controls from the joystick and button."""
    def __init__(self, play_move: Callable[[int, int], bool]):
        self.position = (0,0)
        self.play_move = play_move

    def handle_joystick(self, x: int, y: int):
        self.position = (x, y)

    def handle_button_press(self):
        return self.play_move(self.position[0], self.position[1])
    
