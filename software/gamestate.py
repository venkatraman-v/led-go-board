from collections.abc import Callable
from engine import RulesEngine
from board import Board, Piece

class GameState:
    """keeps track of score, """
    def __init__(self):
        self.current_player = Piece.BLUE
        self.board = Board()
        self.engine = RulesEngine(self.board)
        self.history = []
    
    def play_move(self, x: int, y: int) -> bool:
        self.engine.
        pass

    def undo_move(self) -> bool:
        pass
