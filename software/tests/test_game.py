import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOFTWARE_DIR))

from board import Board, Piece  # noqa: E402
from engine import RulesEngine  # noqa: E402
from game import Game, InputController  # noqa: E402
from gamestate import GameState  # noqa: E402
from main import parse_coordinate  # noqa: E402
from renderer import BoardRenderer, LEDRenderer  # noqa: E402


class BoardTests(unittest.TestCase):
    def test_bounds_and_placement(self):
        board = Board(5)
        self.assertTrue(board.is_valid_position(0, 0))
        self.assertTrue(board.is_valid_position(4, 4))
        self.assertFalse(board.is_valid_position(-1, 0))
        self.assertFalse(board.is_valid_position(5, 0))
        self.assertIs(board.stone_at(-1, 0), Piece.INVALID)

        self.assertTrue(board.place_stone(2, 3, Piece.BLUE))
        self.assertIs(board.stone_at(2, 3), Piece.BLUE)
        self.assertFalse(board.place_stone(2, 3, Piece.RED))
        self.assertTrue(board.remove_stone(2, 3))
        self.assertIs(board.stone_at(2, 3), Piece.EMPTY)

    def test_copy_is_independent(self):
        board = Board(3)
        board.place_stone(1, 1, Piece.RED)
        clone = board.copy()
        clone.remove_stone(1, 1)
        self.assertIs(board.stone_at(1, 1), Piece.RED)
        self.assertNotEqual(board.signature(), clone.signature())


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = RulesEngine()

    def test_adjacent_stones_respect_edges(self):
        board = Board(5)
        self.assertEqual(
            set(self.engine.get_adjacent_stones(board, 0, 0)), {(1, 0), (0, 1)}
        )
        self.assertEqual(len(self.engine.get_adjacent_stones(board, 2, 2)), 4)

    def test_group_and_liberties(self):
        board = Board(5)
        board.place_stone(1, 1, Piece.BLUE)
        board.place_stone(2, 1, Piece.BLUE)
        self.assertEqual(
            self.engine.get_group(board, 1, 1), {(1, 1), (2, 1)}
        )
        self.assertEqual(
            self.engine.get_liberties(board, 1, 1),
            {(0, 1), (1, 0), (1, 2), (2, 0), (2, 2), (3, 1)},
        )

    def test_capture_single_and_group(self):
        board = Board(5)
        board.place_stone(1, 1, Piece.RED)
        for point in [(0, 1), (2, 1), (1, 0)]:
            board.place_stone(*point, Piece.BLUE)
        self.assertEqual(
            self.engine.get_captured_stones(board, 1, 2, Piece.BLUE), {(1, 1)}
        )

        grouped = Board(5)
        grouped.place_stone(1, 1, Piece.RED)
        grouped.place_stone(2, 1, Piece.RED)
        for point in [(0, 1), (1, 0), (2, 0), (3, 1), (1, 2)]:
            grouped.place_stone(*point, Piece.BLUE)
        captured = self.engine.apply_move(grouped, 2, 2, Piece.BLUE)
        self.assertEqual(captured, {(1, 1), (2, 1)})
        self.assertIs(grouped.stone_at(1, 1), Piece.EMPTY)
        self.assertIs(grouped.stone_at(2, 1), Piece.EMPTY)

    def test_suicide_is_illegal(self):
        board = Board(5)
        board.place_stone(0, 1, Piece.BLUE)
        board.place_stone(1, 0, Piece.BLUE)
        self.assertTrue(self.engine.is_suicide(board, 0, 0, Piece.RED))
        self.assertFalse(self.engine.is_legal(board, 0, 0, Piece.RED))

    def test_occupied_and_out_of_bounds_are_illegal(self):
        board = Board(5)
        board.place_stone(0, 0, Piece.BLUE)
        self.assertFalse(self.engine.is_legal(board, 0, 0, Piece.RED))
        self.assertFalse(self.engine.is_legal(board, -1, 0, Piece.RED))
        self.assertFalse(self.engine.is_legal(board, 5, 5, Piece.RED))


class GameStateTests(unittest.TestCase):
    def test_turns_and_simple_capture(self):
        state = GameState(5)
        moves = [(1, 0), (0, 0), (0, 1)]
        # Blue surrounds a red stone at the corner; red moves elsewhere.
        self.assertTrue(state.play_move(1, 0))  # Blue
        self.assertTrue(state.play_move(0, 0))  # Red
        self.assertTrue(state.play_move(0, 1))  # Blue captures (0,0)
        self.assertIs(state.board.stone_at(0, 0), Piece.EMPTY)
        self.assertEqual(state.captured[Piece.BLUE], 1)
        self.assertIs(state.current_player, Piece.RED)

    def test_ko_prevents_immediate_recapture(self):
        state = GameState(5)
        # Ko shape.
        for point in [(0, 1), (1, 0), (1, 2)]:
            state.board.place_stone(*point, Piece.RED)
        for point in [(2, 0), (3, 1), (2, 2)]:
            state.board.place_stone(*point, Piece.BLUE)
        state.board.place_stone(2, 1, Piece.RED)

        self.assertTrue(state.play_move(1, 1))  # Blue captures the ko stone
        self.assertEqual(state.ko_point, (2, 1))
        self.assertFalse(state.play_move(2, 1))  # White may not recapture

        self.assertTrue(state.play_move(4, 4))   # White plays elsewhere
        self.assertTrue(state.play_move(4, 3))   # Black answers
        self.assertTrue(state.play_move(2, 1))   # Recapture is now allowed
        self.assertEqual(state.captured[Piece.RED], 1)

    def test_undo_restores_board_player_and_captures(self):
        state = GameState(5)
        state.play_move(1, 0)
        state.play_move(0, 0)
        state.play_move(0, 1)  # capture
        before = state.board.signature()
        self.assertTrue(state.undo_move())
        self.assertIs(state.board.stone_at(0, 0), Piece.RED)
        self.assertIs(state.current_player, Piece.BLUE)
        self.assertEqual(state.captured[Piece.BLUE], 0)
        self.assertNotEqual(state.board.signature(), before)

    def test_pass_and_game_over(self):
        state = GameState(5)
        self.assertTrue(state.play_pass())
        self.assertFalse(state.is_over)
        self.assertTrue(state.play_pass())
        self.assertTrue(state.is_over)
        self.assertFalse(state.play_move(2, 2))
        self.assertTrue(state.undo_move())
        self.assertFalse(state.is_over)

    def test_save_load_round_trip(self):
        game = Game(size=5)
        for point in [(1, 0), (0, 0), (0, 1), (4, 4)]:
            self.assertTrue(game.play_move(*point))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "game.json"
            game.save(path)
            data = json.loads(path.read_text())
            self.assertEqual(len(data["moves"]), 4)

            loaded = Game(size=5)
            loaded.load(path)
            self.assertEqual(
                loaded.game_state.board.signature(), game.game_state.board.signature()
            )
            self.assertIs(loaded.current_player, game.current_player)
            self.assertEqual(loaded.game_state.captured, game.game_state.captured)
            self.assertEqual(len(loaded.game_state.history), 4)


class InputOutputTests(unittest.TestCase):
    def test_joystick_clamps_and_button_plays(self):
        game = Game(size=5)
        controller = game.input_controller
        self.assertEqual(controller.handle_joystick(-1, -1), (0, 0))
        self.assertEqual(controller.handle_joystick(10, 10), (4, 4))
        self.assertEqual(controller.set_position(2, 3), (2, 3))
        self.assertTrue(controller.handle_button_press())
        self.assertIs(game.board.stone_at(2, 3), Piece.BLUE)

    def test_renderer_marks_cursor_and_status(self):
        state = GameState(5)
        state.play_move(2, 2)
        text = BoardRenderer().to_string(state.board, cursor=(2, 2), state=state)
        self.assertIn("A B C D E", text)
        self.assertIn("Red to play", text)
        self.assertIn("Captures", text)
        self.assertIn("b", text)  # cursor is lowercase when over a stone

    def test_led_frame(self):
        board = Board(13)
        board.place_stone(0, 0, Piece.BLUE)
        board.place_stone(12, 12, Piece.RED)
        renderer = LEDRenderer(matrix_size=32)
        frame = renderer.frame(board, cursor=(6, 6))
        self.assertEqual(len(frame), 32)
        self.assertEqual(len(frame[0]), 32)
        values = {value for row in frame for value in row}
        self.assertEqual(values, {LEDRenderer.EMPTY, LEDRenderer.BLUE, LEDRenderer.RED, LEDRenderer.CURSOR})

    def test_coordinate_parsing(self):
        self.assertEqual(parse_coordinate("A1"), (0, 0))
        self.assertEqual(parse_coordinate("M13"), (12, 12))
        self.assertEqual(parse_coordinate("4 5"), (4, 5))
        self.assertEqual(parse_coordinate("4,5"), (4, 5))
        with self.assertRaises(ValueError):
            parse_coordinate("nope")


class MainEntryPointTests(unittest.TestCase):
    def test_default_non_tty_mode_runs_demo(self):
        result = subprocess.run(
            [sys.executable, "main.py"],
            cwd=SOFTWARE_DIR,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("captured 1", result.stdout)

    def test_demo_cli_runs_and_captures(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--demo"],
            cwd=SOFTWARE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("captured 1", result.stdout)
        self.assertIn("Blue captured 1 stone(s)", result.stdout)

    def test_interactive_cli(self):
        result = subprocess.run(
            [sys.executable, "main.py", "--interactive"],
            cwd=SOFTWARE_DIR,
            input="play E6\nup\npress\nundo\npass\nquit\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Blue played E6", result.stdout)
        self.assertIn("Red played E5", result.stdout)
        self.assertIn("Undid the last move", result.stdout)


if __name__ == "__main__":
    unittest.main()
