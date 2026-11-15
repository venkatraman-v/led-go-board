"""KataGo integration for the LED Go board.

The :class:`KataGo` class speaks the GTP protocol to a KataGo subprocess.  The
:class:`KataGoPlayer` class adapts the game state to engine requests and applies
the engine's chosen move back to the board.
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from board import Board, Piece
from gamestate import GameState


# GTP columns skip the letter I, unlike the spreadsheet-style labels used in
# the text renderer.  This covers all standard board sizes up to 19x19.
GTP_COLUMNS = "ABCDEFGHJKLMNOPQRST"
GTP_VERTEX_RE = re.compile(r"^([A-HJ-T])(\d+)$", re.IGNORECASE)

DEFAULT_MODEL = Path.home() / ".katago" / "default_model.bin.gz"
DEFAULT_CONFIG = Path.home() / ".katago" / "default_gtp.cfg"
PROJECT_BINARY = Path(__file__).resolve().parent / "tools" / "katago" / "katago"


class KataGoError(RuntimeError):
    """Raised when KataGo cannot start, times out, or rejects a command."""


@dataclass(frozen=True)
class EngineMove:
    """The result of a GTP ``genmove`` command."""

    x: Optional[int] = None
    y: Optional[int] = None
    passed: bool = False
    resigned: bool = False
    raw: str = ""

    @property
    def coordinate(self) -> Optional[tuple]:
        if self.passed or self.resigned:
            return None
        return (self.x, self.y)


def to_gtp(x: int, y: int) -> str:
    """Converts zero-based board coordinates to a GTP vertex."""
    if not 0 <= x < len(GTP_COLUMNS):
        raise ValueError(f"x coordinate {x} is outside GTP's supported range")
    if y < 0:
        raise ValueError(f"y coordinate {y} must not be negative")
    return f"{GTP_COLUMNS[x]}{y + 1}"


def from_gtp(vertex: str) -> EngineMove:
    """Parses a GTP vertex (``D4``, ``pass``, ``resign``)."""
    text = vertex.strip()
    lower = text.lower()
    if lower == "pass":
        return EngineMove(passed=True, raw=text)
    if lower == "resign":
        return EngineMove(resigned=True, raw=text)

    match = GTP_VERTEX_RE.match(text)
    if not match:
        raise KataGoError(f"unrecognised GTP vertex: {vertex!r}")
    column, row = match.groups()
    x = GTP_COLUMNS.index(column.upper())
    y = int(row) - 1
    if y < 0:
        raise KataGoError(f"unrecognised GTP vertex: {vertex!r}")
    return EngineMove(x=x, y=y, raw=text)


def _piece_letter(color: Piece) -> str:
    if color is Piece.BLUE:
        return "B"
    if color is Piece.RED:
        return "W"
    raise ValueError(f"invalid stone colour: {color!r}")


def _find_binary(explicit: Optional[str]) -> str:
    candidates = [
        explicit,
        os.environ.get("KATAGO_BIN"),
        str(PROJECT_BINARY),
        shutil.which("katago"),
        "/usr/bin/katago",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    raise KataGoError(
        "KataGo executable not found. Install KataGo or set KATAGO_BIN."
    )


def _find_model(explicit: Optional[str]) -> str:
    candidates = [
        explicit,
        os.environ.get("KATAGO_MODEL"),
        str(DEFAULT_MODEL),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise KataGoError(
        "KataGo model not found. Run software/scripts/install_katago.sh or set "
        "KATAGO_MODEL to a .bin.gz network."
    )


def _find_config(explicit: Optional[str]) -> str:
    candidates = [
        explicit,
        os.environ.get("KATAGO_CONFIG"),
        str(DEFAULT_CONFIG),
        "/usr/share/doc/katago/configs/gtp_example.cfg",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise KataGoError(
        "KataGo config not found. Run software/scripts/install_katago.sh or set "
        "KATAGO_CONFIG."
    )


class KataGo:
    """A small GTP client for a KataGo subprocess.

    The client starts KataGo with a model and config, reads GTP responses on a
    background thread, and serialises commands with a lock.  Use it as a
    context manager to guarantee that the engine process is stopped.
    """

    def __init__(
        self,
        binary: Optional[str] = None,
        model: Optional[str] = None,
        config: Optional[str] = None,
        board_size: int = Board.DEFAULT_SIZE,
        komi: float = 7.5,
        max_visits: int = 100,
        num_search_threads: Optional[int] = None,
        timeout: float = 30.0,
        startup_timeout: float = 120.0,
        log_dir: Optional[str] = None,
        auto_start: bool = True,
    ):
        if board_size < 1:
            raise ValueError("board size must be positive")
        if max_visits < 1:
            raise ValueError("max visits must be positive")

        self.binary = _find_binary(binary)
        self.model = _find_model(model)
        self.config = _find_config(config)
        self.board_size = board_size
        self.komi = komi
        self.max_visits = max_visits
        self.num_search_threads = num_search_threads
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.log_dir = Path(log_dir or os.environ.get("KATAGO_LOG_DIR", Path.home() / ".katago" / "logs"))

        self._process: Optional[subprocess.Popen] = None
        self._responses: queue.Queue = queue.Queue()
        self._stderr_lines: list = []
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._command_lock = threading.Lock()
        self._started = False

        if auto_start:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _build_command(self) -> list:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        overrides = {
            "maxVisits": self.max_visits,
            "ponderingEnabled": "false",
            "logDir": str(self.log_dir),
        }
        if self.num_search_threads is not None:
            overrides["numSearchThreads"] = self.num_search_threads
        override_text = ",".join(f"{key}={value}" for key, value in overrides.items())
        return [
            self.binary,
            "gtp",
            "-model",
            self.model,
            "-config",
            self.config,
            "-override-config",
            override_text,
        ]

    def start(self) -> None:
        if self.is_running:
            return

        command = self._build_command()
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as error:
            raise KataGoError(f"could not start KataGo: {error}") from error

        self._stdout_thread = threading.Thread(
            target=self._read_stdout, name="katago-stdout", daemon=True
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr, name="katago-stderr", daemon=True
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

        try:
            self.command(f"boardsize {self.board_size}", timeout=self.startup_timeout)
            self.command(f"komi {self.komi}", timeout=self.startup_timeout)
            self.command("clear_board", timeout=self.startup_timeout)
        except Exception:
            self.close()
            raise
        self._started = True

    def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for line in self._process.stdout:
            self._responses.put(line.rstrip("\r\n"))
        self._responses.put(None)

    def _read_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        for line in self._process.stderr:
            self._stderr_lines.append(line.rstrip("\r\n"))
            if len(self._stderr_lines) > 200:
                del self._stderr_lines[:100]

    def _error_context(self) -> str:
        if not self._stderr_lines:
            return ""
        return "\nKataGo stderr:\n" + "\n".join(self._stderr_lines[-10:])

    def command(self, command: str, timeout: Optional[float] = None) -> str:
        """Sends one GTP command and returns its response payload."""
        if not self.is_running:
            raise KataGoError("KataGo is not running")
        if "\n" in command or "\r" in command:
            raise ValueError("GTP commands must be a single line")

        timeout = self.timeout if timeout is None else timeout
        with self._command_lock:
            try:
                assert self._process is not None and self._process.stdin is not None
                self._process.stdin.write(command + "\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as error:
                raise KataGoError(
                    f"KataGo process stopped unexpectedly: {error}{self._error_context()}"
                ) from error

            lines = []
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise KataGoError(
                        f"KataGo timed out after {timeout:.1f}s on {command!r}"
                        f"{self._error_context()}"
                    )
                try:
                    line = self._responses.get(timeout=remaining)
                except queue.Empty:
                    raise KataGoError(
                        f"KataGo timed out after {timeout:.1f}s on {command!r}"
                        f"{self._error_context()}"
                    ) from None
                if line is None:
                    raise KataGoError(
                        f"KataGo exited while running {command!r}"
                        f"{self._error_context()}"
                    )
                if line == "":
                    break
                lines.append(line)

        if not lines:
            raise KataGoError(f"empty GTP response to {command!r}")
        status, _, payload = lines[0].partition(" ")
        if status == "?":
            raise KataGoError(payload or f"KataGo rejected {command!r}")
        if status != "=":
            raise KataGoError(f"malformed GTP response: {lines[0]!r}")
        return "\n".join([payload, *lines[1:]]).strip()

    def clear_board(self) -> None:
        self.command("clear_board")

    def play(self, color: Piece, x: int, y: int) -> None:
        self.command(f"play {_piece_letter(color)} {to_gtp(x, y)}")

    def play_pass(self, color: Piece) -> None:
        self.command(f"play {_piece_letter(color)} pass")

    def genmove(self, color: Piece) -> EngineMove:
        response = self.command(f"genmove {_piece_letter(color)}")
        return from_gtp(response)

    def final_score(self) -> str:
        return self.command("final_score")

    def close(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.write("quit\n")
                    process.stdin.flush()
                process.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        self._process = None
        self._started = False

    def __enter__(self) -> "KataGo":
        if not self.is_running:
            self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class KataGoPlayer:
    """A KataGo-backed player that can make moves on a :class:`Game`.

    ``engine`` may be injected for tests as long as it provides ``clear_board``,
    ``play``, ``play_pass`` and ``genmove``.  The board is replayed from the
    game history before every request, so undo and save/load stay in sync.
    """

    def __init__(
        self,
        color: Piece = Piece.RED,
        engine: Optional[KataGo] = None,
        **engine_kwargs,
    ):
        if color not in (Piece.BLUE, Piece.RED):
            raise ValueError("KataGoPlayer colour must be BLUE or RED")
        self.color = color
        self.engine = engine or KataGo(**engine_kwargs)
        self.last_move: Optional[EngineMove] = None

    @property
    def name(self) -> str:
        return "KataGo"

    def sync(self, state: GameState) -> None:
        """Replays ``state`` into KataGo so the engine and board agree."""
        if state.board.size != self.engine.board_size:
            self.engine.board_size = state.board.size
            self.engine.command(f"boardsize {state.board.size}")
        self.engine.clear_board()
        for move in state.history:
            if move.is_pass:
                self.engine.play_pass(move.color)
            else:
                self.engine.play(move.color, move.x, move.y)

    def choose_move(self, state: GameState) -> EngineMove:
        """Asks KataGo for its move without applying it to the game."""
        if state.is_over:
            raise KataGoError("the game is already over")
        if state.current_player is not self.color:
            raise KataGoError(
                f"it is {state.current_player.name}'s turn, not {self.color.name}'s"
            )
        self.sync(state)
        self.last_move = self.engine.genmove(self.color)
        return self.last_move

    def make_move(self, game) -> EngineMove:
        """Requests a move and applies it to ``game``.

        Returns the engine decision so callers can report passes/resignations.
        """
        move = self.choose_move(game.game_state)
        if move.passed:
            if not game.pass_move():
                raise KataGoError("could not apply KataGo's pass")
        elif move.resigned:
            if not game.game_state.resign(self.color):
                raise KataGoError("could not apply KataGo's resignation")
        else:
            if move.coordinate is None:
                raise KataGoError(f"invalid engine move: {move.raw!r}")
            if not game.play_move(*move.coordinate):
                raise KataGoError(
                    f"KataGo returned an illegal move: {move.raw!r}"
                )
        return move

    def close(self) -> None:
        self.engine.close()

    def __enter__(self) -> "KataGoPlayer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class EnginePlayer(KataGoPlayer):
    """Backwards-compatible name for the KataGo-backed player."""
