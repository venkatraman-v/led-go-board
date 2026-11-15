import sys
import threading
import unittest
from pathlib import Path

SOFTWARE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SOFTWARE_DIR))

from analysis import (  # noqa: E402
    EngineMove,
    KataGoError,
    KataGoPlayer,
    from_gtp,
    to_gtp,
)
from board import Board, Piece  # noqa: E402
from game import Game  # noqa: E402
from gamestate import GameState  # noqa: E402
from renderer import LEDRenderer, SerialLEDTransport  # noqa: E402


class FakeEngine:
    """Minimal stand-in for :class:`analysis.KataGo` used by the player tests."""

    def __init__(self, replies=(), board_size=19):
        self.replies = list(replies)
        self.board_size = board_size
        self.calls = []
        self.closed = False

    def command(self, command, timeout=None):
        self.calls.append(("command", command))
        return ""

    def clear_board(self):
        self.calls.append(("clear_board",))

    def play(self, color, x, y):
        self.calls.append(("play", color, x, y))

    def play_pass(self, color):
        self.calls.append(("play_pass", color))

    def genmove(self, color):
        self.calls.append(("genmove", color))
        if not self.replies:
            return EngineMove(x=0, y=0, raw="A1")
        reply = self.replies.pop(0)
        if isinstance(reply, EngineMove):
            return reply
        return from_gtp(reply)

    def close(self):
        self.closed = True


class GtpCoordinateTests(unittest.TestCase):
    def test_to_gtp_skips_the_letter_i(self):
        self.assertEqual(to_gtp(0, 0), "A1")
        self.assertEqual(to_gtp(7, 4), "H5")
        self.assertEqual(to_gtp(8, 0), "J1")
        self.assertEqual(to_gtp(9, 9), "K10")
        self.assertEqual(to_gtp(12, 12), "N13")

    def test_from_gtp_skips_the_letter_i(self):
        move = from_gtp("K10")
        self.assertEqual(move.coordinate, (9, 9))
        self.assertEqual(from_gtp("a1").coordinate, (0, 0))
        self.assertEqual(from_gtp("N13").coordinate, (12, 12))

    def test_pass_and_resign(self):
        self.assertTrue(from_gtp("pass").passed)
        self.assertTrue(from_gtp("PASS").passed)
        self.assertTrue(from_gtp("resign").resigned)
        self.assertIsNone(from_gtp("resign").coordinate)

    def test_invalid_vertices(self):
        for vertex in ("I5", "A0", "Z9", "nonsense", ""):
            with self.assertRaises(KataGoError):
                from_gtp(vertex)


class KataGoPlayerTests(unittest.TestCase):
    def _state(self):
        state = GameState(5)
        state.play_move(1, 0)      # Blue
        state.play_move(0, 0)      # Red
        state.play_move(0, 1)      # Blue captures at (0, 0)
        return state

    def test_sync_replays_full_history(self):
        state = self._state()
        engine = FakeEngine(board_size=5)
        player = KataGoPlayer(color=Piece.RED, engine=engine)
        player.sync(state)

        self.assertEqual(engine.calls[0], ("clear_board",))
        replay = engine.calls[1:]
        self.assertEqual(
            replay,
            [
                ("play", Piece.BLUE, 1, 0),
                ("play", Piece.RED, 0, 0),
                ("play", Piece.BLUE, 0, 1),
            ],
        )

    def test_sync_replays_passes_and_resizes_engine(self):
        state = GameState(5)
        state.play_pass()
        engine = FakeEngine(board_size=19)
        player = KataGoPlayer(color=Piece.RED, engine=engine)
        player.sync(state)

        self.assertEqual(engine.board_size, 5)
        self.assertIn(("command", "boardsize 5"), engine.calls)
        self.assertEqual(engine.calls[-1], ("play_pass", Piece.BLUE))

    def test_choose_move_requires_engine_turn(self):
        state = GameState(5)  # Blue to play
        player = KataGoPlayer(color=Piece.RED, engine=FakeEngine(board_size=5))
        with self.assertRaises(KataGoError):
            player.choose_move(state)

    def test_choose_move_rejects_finished_game(self):
        state = GameState(5)
        state.resign(Piece.BLUE)
        player = KataGoPlayer(color=Piece.RED, engine=FakeEngine(board_size=5))
        with self.assertRaises(KataGoError):
            player.choose_move(state)

    def test_make_move_applies_engine_choice(self):
        game = Game(size=5)
        engine = FakeEngine(replies=["C3"], board_size=5)
        player = KataGoPlayer(color=Piece.BLUE, engine=engine)

        decision = player.make_move(game)

        self.assertEqual(decision.coordinate, (2, 2))
        self.assertIs(game.board.stone_at(2, 2), Piece.BLUE)
        self.assertIs(game.current_player, Piece.RED)
        self.assertEqual(engine.calls[-1], ("genmove", Piece.BLUE))

    def test_make_move_passes(self):
        game = Game(size=5)
        player = KataGoPlayer(
            color=Piece.BLUE, engine=FakeEngine(replies=["pass"], board_size=5)
        )
        decision = player.make_move(game)
        self.assertTrue(decision.passed)
        self.assertEqual(game.game_state.consecutive_passes, 1)

    def test_make_move_resigns(self):
        game = Game(size=5)
        player = KataGoPlayer(
            color=Piece.BLUE, engine=FakeEngine(replies=["resign"], board_size=5)
        )
        decision = player.make_move(game)
        self.assertTrue(decision.resigned)
        self.assertIs(game.game_state.resigned_by, Piece.BLUE)
        self.assertTrue(game.game_state.is_over)


class ResignationTests(unittest.TestCase):
    def test_resign_ends_game_and_undo_restores_it(self):
        state = GameState(5)
        state.play_move(2, 2)
        self.assertFalse(state.is_over)
        self.assertTrue(state.resign(Piece.RED))
        self.assertTrue(state.is_over)
        self.assertFalse(state.play_move(3, 3))

        self.assertTrue(state.undo_move())
        self.assertIsNone(state.resigned_by)
        self.assertFalse(state.is_over)
        # The resignation is undone first; the move is still on the board.
        self.assertEqual(len(state.history), 1)
        self.assertEqual(state.board.stone_at(2, 2), Piece.BLUE)

    def test_resign_does_not_add_history(self):
        state = GameState(5)
        state.resign()
        self.assertIs(state.resigned_by, Piece.BLUE)
        self.assertEqual(state.history, [])
        self.assertFalse(state.resign(Piece.RED))

    def test_save_load_preserves_resignation(self):
        state = GameState(5)
        state.play_move(2, 2)
        state.resign(Piece.BLUE)
        restored = GameState.from_dict(state.to_dict())
        self.assertIs(restored.resigned_by, Piece.BLUE)
        self.assertTrue(restored.is_over)

    def test_renderer_reports_resignation(self):
        from renderer import BoardRenderer

        state = GameState(5)
        state.resign(Piece.RED)
        text = BoardRenderer().to_string(state.board, state=state)
        self.assertIn("Red resigned", text)


class SerialLEDTransportTests(unittest.TestCase):
    def _transport(self, brightness=1):
        # Bypass __init__ so the encoding tests do not open a serial port.
        transport = SerialLEDTransport.__new__(SerialLEDTransport)
        transport.brightness = brightness
        transport.matrix_size = SerialLEDTransport.MATRIX_SIZE
        transport.ack_timeout = 1.0
        transport._lock = threading.RLock()
        transport._blink_stop = threading.Event()
        transport._blink_thread = None
        transport._cursor = None
        transport._cursor_piece = None
        transport._cursor_size = None
        transport._blink_visible = True
        return transport

    def test_encode_uses_firmware_commands(self):
        board = Board(3)
        board.place_stone(0, 0, Piece.BLUE)
        board.place_stone(2, 1, Piece.RED)

        lines = self._transport().encode(board, cursor=(1, 1)).decode("ascii").splitlines()

        # A 3x3 board uses 10x10 tiles, centred with a one-pixel offset.
        self.assertEqual(
            lines,
            [
                "B 1",
                "C",
                "S 1 1 10 0 0 7 1",
                "S 11 11 10 4 4 4 1",
                "S 21 11 10 7 0 0 1",
            ],
        )

    def test_encode_centres_a_13x13_board(self):
        board = Board(13)
        board.place_stone(0, 0, Piece.BLUE)
        board.place_stone(12, 12, Piece.RED)

        lines = self._transport(brightness=4).encode(board).decode("ascii").splitlines()

        self.assertEqual(lines[0], "B 4")
        self.assertIn("S 3 3 2 0 0 7 1", lines)
        self.assertIn("S 27 27 2 7 0 0 1", lines)

    def test_encode_skips_empty_points(self):
        lines = self._transport().encode(Board(5)).decode("ascii").splitlines()
        self.assertEqual(lines, ["B 1", "C"])

    def test_cursor_over_stone_keeps_stone_colour(self):
        board = Board(3)
        board.place_stone(1, 1, Piece.BLUE)

        lines = self._transport().encode(board, cursor=(1, 1)).decode("ascii").splitlines()

        self.assertIn("S 11 11 10 0 0 7 1", lines)
        self.assertIn("P 11 11 7 7 7", lines)

    def test_blink_toggles_only_the_cursor_pixels(self):
        class FakeSerial:
            def __init__(self):
                self.written = b""

            def write(self, data):
                self.written += data

            def flush(self):
                pass

            def readline(self):
                return b"OK\r\n"

        transport = self._transport()
        transport.serial = FakeSerial()
        transport._cursor = (1, 1)
        transport._cursor_size = 3

        transport._cursor_piece = Piece.BLUE
        transport._blink_visible = True
        transport._write_cursor()
        self.assertEqual(transport.serial.written, b"P 11 11 7 7 7\n")

        transport.serial.written = b""
        transport._blink_visible = False
        transport._write_cursor()
        self.assertEqual(transport.serial.written, b"P 11 11 0 0 7\n")

        transport._cursor_piece = Piece.EMPTY
        transport._blink_visible = False
        transport.serial.written = b""
        transport._write_cursor()
        self.assertEqual(transport.serial.written, b"S 11 11 10 0 0 0 1\n")

        transport._blink_visible = True
        transport.serial.written = b""
        transport._write_cursor()
        self.assertEqual(transport.serial.written, b"S 11 11 10 4 4 4 1\n")

    def test_brightness_is_validated(self):
        with self.assertRaises(ValueError):
            SerialLEDTransport("/dev/null", brightness=0)
        with self.assertRaises(ValueError):
            SerialLEDTransport("/dev/null", brightness=8)

    def test_wait_for_ready_consumes_boot_banner(self):
        class FakeSerial:
            def __init__(self):
                self.lines = [b"\x14\x10\r\n", b"READY\r\n"]

            def readline(self):
                return self.lines.pop(0) if self.lines else b""

        transport = self._transport()
        transport.serial = FakeSerial()
        self.assertTrue(transport._wait_for_ready(0.5))

    def test_encode_rejects_oversized_board(self):
        with self.assertRaises(ValueError):
            self._transport().encode(Board(20))

    def test_led_renderer_uses_transport(self):
        class RecordingTransport:
            def __init__(self):
                self.sent = []

            def send(self, board, cursor=None):
                self.sent.append((board.size, cursor))

        transport = RecordingTransport()
        renderer = LEDRenderer(transport=transport)
        board = Board(13)
        frame = renderer.render(board, cursor=(4, 5))
        self.assertEqual(transport.sent, [(13, (4, 5))])
        self.assertEqual(len(frame), 32)

    def test_send_writes_and_flushes_frame(self):
        class FakeSerial:
            def __init__(self):
                self.written = b""
                self.flushed = False

            def write(self, data):
                self.written += data

            def flush(self):
                self.flushed = True

            def readline(self):
                return b"OK\r\n"

        transport = self._transport()
        transport.serial = FakeSerial()
        board = Board(5)
        board.place_stone(1, 1, Piece.BLUE)
        transport.send(board, cursor=(0, 0))

        self.assertEqual(transport.serial.written, transport.encode(board, (0, 0)))
        self.assertTrue(transport.serial.flushed)

    def test_send_reports_firmware_error(self):
        class ErrorSerial:
            def write(self, data):
                pass

            def flush(self):
                pass

            def readline(self):
                return b"ERR\r\n"

        transport = self._transport()
        transport.serial = ErrorSerial()
        with self.assertRaises(OSError):
            transport.send(Board(5))


if __name__ == "__main__":
    unittest.main()
