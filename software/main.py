import argparse
import queue
import re
import shlex
import sys
import threading
import time

from analysis import KataGoError, KataGoPlayer
from board import Board, Piece
from game import Game
from renderer import (
    BoardRenderer,
    LEDRenderer,
    SerialLEDTransport,
    format_coordinate,
)


def demo_moves(size: int) -> list:
    """A short capture sequence that works on any board of size 5 or more."""
    if size < 5:
        raise ValueError("the capture demo needs a board of at least 5x5")
    centre_x, centre_y = size // 2, size // 2
    return [
        (centre_x + 1, centre_y),      # Blue
        (centre_x, centre_y),          # Red
        (centre_x, centre_y - 1),      # Blue
        (size - 1, size - 1),          # Red
        (centre_x, centre_y + 1),      # Blue
        (size - 1, size - 2),          # Red
        (centre_x - 1, centre_y),      # Blue captures the centre stone
    ]


def parse_coordinate(text: str) -> tuple:
    """Parses ``A1`` style or zero-based ``"x y"`` / ``"x,y"`` coordinates."""
    text = text.strip()
    if not text:
        raise ValueError("empty coordinate")

    numeric = re.fullmatch(r"(\d+)\s*[,\s]\s*(\d+)", text)
    if numeric:
        return int(numeric.group(1)), int(numeric.group(2))

    labelled = re.fullmatch(r"([A-Za-z]+)(\d+)", text)
    if labelled:
        letters, row = labelled.groups()
        x = 0
        for letter in letters.upper():
            x = x * 26 + (ord(letter) - ord("A") + 1)
        return x - 1, int(row) - 1

    raise ValueError(f"unrecognised coordinate: {text!r}")


def run_demo(size: int) -> int:
    game = Game(size=size)
    print("LED Go board demo: playing a short capture sequence.\n")

    for number, (x, y) in enumerate(demo_moves(size), start=1):
        color = game.current_player
        if not game.play_move(x, y):
            print(f"Move {number} ({color.name} {format_coordinate(x, y)}) was illegal.")
            return 1
        move = game.game_state.last_move
        text = f"{number:2d}. {color.name.title():4s} {format_coordinate(x, y)}"
        if move.captured:
            text += f" captured {len(move.captured)}"
        print(text)

    print()
    game.render()

    captured = game.game_state.captured[Piece.BLUE]
    print()
    print(f"Blue captured {captured} stone(s); move history has {len(game.game_state.history)} moves.")
    return 0 if captured == 1 else 1


def _render(game: Game, led: LEDRenderer = None) -> None:
    cursor = game.input_controller.position
    game.render(cursor=cursor)
    if led is not None:
        led.render(
            game.board,
            cursor=cursor,
            captured=game.game_state.captured,
        )


def _engine_turn(game: Game, player: KataGoPlayer, led: LEDRenderer = None) -> bool:
    """Lets KataGo move if it is its turn.  Returns True if it moved."""
    if player is None or game.game_state.is_over:
        return False
    if game.current_player is not player.color:
        return False

    print(f"\n{player.name} is thinking...")
    try:
        decision = player.make_move(game)
    except KataGoError as error:
        print(f"{player.name} error: {error}")
        return False

    if decision.resigned:
        print(f"{player.name} resigned.")
    elif decision.passed:
        print(f"{player.name} passed.")
    else:
        print(
            f"{player.name} played "
            f"{format_coordinate(decision.x, decision.y)}."
        )
    _render(game, led)
    return True


def _finish_turn(game: Game, player: KataGoPlayer, led: LEDRenderer = None) -> None:
    """Shows the human move, then lets the engine reply."""
    # Render before the engine starts thinking so the player sees their own
    # stone immediately instead of waiting for KataGo's reply.
    _render(game, led)
    if player is not None and not game.game_state.is_over and game.current_player is player.color:
        _engine_turn(game, player, led)


def _print_help(with_engine: bool = False) -> None:
    engine_line = (
        "  engine               ask KataGo to move when it is its turn\n"
        if with_engine
        else ""
    )
    print(
        "\nCommands:\n"
        "  play A1 / play 4 5   play at a labelled or zero-based coordinate\n"
        "  up/down/left/right   move the joystick cursor\n"
        "  goto A1              move the cursor directly\n"
        "  press                press the button (play at the cursor)\n"
        "  pass                 pass the turn\n"
        "  undo                 undo the last move\n"
        "  save FILE / load FILE  write or read a JSON move list\n"
        + engine_line
        + "  show                 redraw the board\n"
        "  help                 show this help\n"
        "  quit                 exit\n"
    )


def _start_stdin_reader() -> queue.Queue:
    """Reads typed commands on a thread so the joystick can stay responsive."""
    lines = queue.Queue()

    def read_lines():
        try:
            for line in sys.stdin:
                lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)

    threading.Thread(target=read_lines, name="stdin-reader", daemon=True).start()
    return lines


class _JoystickCursor:
    """Converts polled joystick states into cursor moves and actions.

    The first deflection moves one intersection immediately.  Holding a
    direction then repeats after a short delay, which makes crossing the
    board quick without making single steps hard to control.

    A short press of the joystick button plays at the cursor.  Holding it for
    :attr:`PASS_HOLD` seconds passes the turn instead.  An optional dedicated
    pass button on D11-D13 reports its own state and always passes.
    """

    INITIAL_DELAY = 0.35
    REPEAT_INTERVAL = 0.14
    BUTTON_DEBOUNCE = 0.20
    PASS_HOLD = 0.90

    DELTAS = {
        "U": (0, -1),
        "D": (0, 1),
        "L": (-1, 0),
        "R": (1, 0),
    }

    def __init__(self):
        self.direction = "0"
        self.next_repeat = 0.0
        self.button_down = False
        self.button_started = 0.0
        self.button_ready = 0.0
        self.button_passed = False
        self.pass_down = False
        self.pass_ready = 0.0

    def _move(self, direction: str, game: Game, led: LEDRenderer) -> None:
        dx, dy = self.DELTAS[direction]
        game.input_controller.handle_joystick(dx, dy)
        if led is not None:
            led.move_cursor(game.board, game.input_controller.position)

    def update(self, state, game: Game, led: LEDRenderer, now: float = None):
        """Returns ``"press"`` or ``"pass"`` for a new action, else ``None``."""
        if state is None:
            return None

        if len(state) >= 3:
            direction, pressed, pass_pressed = state[0], state[1], state[2]
        else:
            direction, pressed = state
            pass_pressed = False
        if now is None:
            now = time.monotonic()

        if direction != self.direction:
            self.direction = direction
            if direction != "0":
                self._move(direction, game, led)
                self.next_repeat = now + self.INITIAL_DELAY
        elif direction != "0" and now >= self.next_repeat:
            self._move(direction, game, led)
            self.next_repeat = now + self.REPEAT_INTERVAL

        # Optional dedicated pass button.
        if pass_pressed:
            if not self.pass_down and now >= self.pass_ready:
                self.pass_down = True
                self.pass_ready = now + self.BUTTON_DEBOUNCE
                return "pass"
        else:
            self.pass_down = False

        if pressed:
            if not self.button_down and now >= self.button_ready:
                self.button_down = True
                self.button_started = now
                self.button_passed = False
                self.button_ready = now + self.BUTTON_DEBOUNCE
            elif (
                self.button_down
                and not self.button_passed
                and now - self.button_started >= self.PASS_HOLD
            ):
                # A long hold passes instead of playing a stone.
                self.button_passed = True
                return "pass"
        else:
            if self.button_down:
                self.button_down = False
                if not self.button_passed:
                    self.button_passed = False
                    return "press"
                self.button_passed = False
        return None


def _wait_for_command(
    prompt: str,
    transport: SerialLEDTransport,
    game: Game,
    led: LEDRenderer,
    lines: queue.Queue,
    joystick: _JoystickCursor = None,
) -> str:
    """Waits for a typed command, a joystick press, or a pass.

    Joystick movement is handled here so the cursor keeps moving while the
    program is waiting at the prompt.
    """
    print(prompt, end="", flush=True)
    if joystick is None:
        joystick = _JoystickCursor()

    while True:
        try:
            action = joystick.update(transport.poll_joystick(), game, led)
        except OSError as error:
            print(f"\nJoystick error: {error}", file=sys.stderr)
            return "quit"
        if action in ("press", "pass"):
            print()
            return action

        try:
            line = lines.get(timeout=0.02)
        except queue.Empty:
            continue
        if line is None:
            raise EOFError
        return line.rstrip("\r\n")


def run_interactive(
    size: int,
    player: KataGoPlayer = None,
    led: LEDRenderer = None,
    transport: SerialLEDTransport = None,
    joystick: bool = True,
) -> int:
    game = Game(size=size)
    if player is not None:
        print(
            f"Playing against {player.name} ({player.color.name.title()}). "
            "Type 'help' for commands.\n"
        )
    else:
        print("LED Go board. Type 'help' for commands.\n")

    try:
        _render(game, led)

        # KataGo may be playing Blue, in which case it opens the game.
        _engine_turn(game, player, led)
    except OSError as error:
        print(f"LED/serial error: {error}", file=sys.stderr)
        if player is not None:
            player.close()
        return 1

    command_lines = None
    joystick_state = None
    if joystick and transport is not None:
        command_lines = _start_stdin_reader()
        # Keep button state across prompts so a held pass button cannot
        # trigger again on the next turn.
        joystick_state = _JoystickCursor()

    try:
        while True:
            try:
                prompt = f"\n{game.current_player.name.title()}> "
                if command_lines is not None:
                    line = _wait_for_command(
                        prompt,
                        transport,
                        game,
                        led,
                        command_lines,
                        joystick=joystick_state,
                    )
                else:
                    line = input(prompt)
            except (EOFError, KeyboardInterrupt):
                print()
                return 0

            try:
                tokens = shlex.split(line)
            except ValueError as error:
                print(f"Input error: {error}")
                continue
            if not tokens:
                continue

            command = tokens[0].lower()
            args = tokens[1:]

            try:
                if command in ("quit", "exit"):
                    return 0
                elif command == "help":
                    _print_help(with_engine=player is not None)
                elif command in ("show", "board"):
                    _render(game, led)
                elif command in ("play", "move"):
                    if len(args) == 1:
                        x, y = parse_coordinate(args[0])
                    elif len(args) == 2:
                        x, y = int(args[0]), int(args[1])
                    else:
                        raise ValueError("usage: play A1 or play X Y")
                    color = game.current_player
                    if game.play_move(x, y):
                        print(
                            f"{color.name.title()} played "
                            f"{format_coordinate(x, y)}."
                        )
                        _finish_turn(game, player, led)
                    else:
                        print("Illegal move (occupied, suicide, ko, or game over).")
                elif command in ("up", "down", "left", "right"):
                    step = int(args[0]) if args else 1
                    deltas = {
                        "up": (0, -step),
                        "down": (0, step),
                        "left": (-step, 0),
                        "right": (step, 0),
                    }
                    game.input_controller.handle_joystick(*deltas[command])
                    _render(game, led)
                elif command in ("goto", "cursor"):
                    if len(args) != 1:
                        raise ValueError("usage: goto A1")
                    game.input_controller.set_position(*parse_coordinate(args[0]))
                    _render(game, led)
                elif command == "press":
                    color = game.current_player
                    x, y = game.input_controller.position
                    if game.input_controller.handle_button_press():
                        print(
                            f"{color.name.title()} played "
                            f"{format_coordinate(x, y)}."
                        )
                        _finish_turn(game, player, led)
                    else:
                        print("Illegal move (occupied, suicide, ko, or game over).")
                elif command == "pass":
                    color = game.current_player
                    if game.pass_move():
                        print(f"{color.name.title()} passed.")
                        _finish_turn(game, player, led)
                    else:
                        print("The game is already over.")
                elif command in ("engine", "ai"):
                    if player is None:
                        print("No engine is configured; start with --vs-katago.")
                    elif game.current_player is not player.color:
                        print(f"It is {game.current_player.name.title()}'s turn.")
                    elif not _engine_turn(game, player, led):
                        print("KataGo could not move.")
                elif command == "undo":
                    if game.undo_move():
                        print("Undid the last move.")
                        _finish_turn(game, player, led)
                    else:
                        print("Nothing to undo.")
                elif command == "save":
                    if len(args) != 1:
                        raise ValueError("usage: save FILE")
                    game.save(args[0])
                    print(f"Saved {len(game.game_state.history)} moves to {args[0]}.")
                elif command == "load":
                    if len(args) != 1:
                        raise ValueError("usage: load FILE")
                    game.load(args[0])
                    print(f"Loaded {len(game.game_state.history)} moves from {args[0]}.")
                    _finish_turn(game, player, led)
                else:
                    print(f"Unknown command: {command!r}. Type 'help' for commands.")
            except (ValueError, OSError) as error:
                print(f"Error: {error}")
    finally:
        if player is not None:
            player.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Play Go on the LED board.")
    parser.add_argument(
        "--size", type=int, default=Board.DEFAULT_SIZE, help="board size (default: 13)"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="run an automated capture demo")
    mode.add_argument(
        "--interactive", action="store_true", help="read commands from standard input"
    )
    parser.add_argument(
        "--vs-katago", action="store_true", help="play against a KataGo engine"
    )
    parser.add_argument(
        "--ai-color",
        choices=("blue", "red"),
        default="red",
        help="colour KataGo plays (default: red)",
    )
    parser.add_argument(
        "--visits", type=int, default=100, help="KataGo search visits per move"
    )
    parser.add_argument("--komi", type=float, default=7.5, help="KataGo komi")
    parser.add_argument("--katago", help="path to the KataGo executable")
    parser.add_argument("--model", help="path to the KataGo .bin.gz network")
    parser.add_argument("--config", help="path to the KataGo GTP config")
    parser.add_argument(
        "--led-serial",
        metavar="PORT",
        help="serial port for the LED matrix (e.g. /dev/ttyACM0)",
    )
    parser.add_argument(
        "--led-baud", type=int, default=115200, help="LED serial baud rate"
    )
    parser.add_argument(
        "--led-brightness",
        type=int,
        choices=range(1, 8),
        default=1,
        metavar="1-7",
        help="LED brightness, 1 (dimmest) to 7 (brightest)",
    )
    parser.add_argument(
        "--led-blink",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="blink the LED cursor (default: enabled)",
    )
    parser.add_argument(
        "--joystick",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="read the LED board joystick (default: enabled with --led-serial)",
    )
    args = parser.parse_args(argv)

    if args.size < 1:
        parser.error("--size must be positive")
    if args.visits < 1:
        parser.error("--visits must be positive")
    if args.demo and args.vs_katago:
        parser.error("--demo cannot be combined with --vs-katago")

    interactive = args.interactive or args.vs_katago or (
        not args.demo and sys.stdin.isatty()
    )
    if not interactive:
        if args.size < 5:
            parser.error("--size must be at least 5 in demo mode")
        return run_demo(args.size)

    player = None
    if args.vs_katago:
        color = Piece.BLUE if args.ai_color == "blue" else Piece.RED
        try:
            player = KataGoPlayer(
                color=color,
                binary=args.katago,
                model=args.model,
                config=args.config,
                board_size=args.size,
                komi=args.komi,
                max_visits=args.visits,
            )
        except KataGoError as error:
            print(f"Could not start KataGo: {error}", file=sys.stderr)
            return 1

    transport = None
    led = None
    if args.led_serial:
        try:
            transport = SerialLEDTransport(
                args.led_serial,
                baudrate=args.led_baud,
                brightness=args.led_brightness,
                blink=args.led_blink,
            )
            led = LEDRenderer(transport=transport)
        except (RuntimeError, OSError) as error:
            if player is not None:
                player.close()
            print(f"Could not open LED serial port: {error}", file=sys.stderr)
            return 1

    try:
        return run_interactive(
            args.size,
            player=player,
            led=led,
            transport=transport,
            joystick=args.joystick,
        )
    finally:
        if transport is not None:
            transport.close()


if __name__ == "__main__":
    sys.exit(main())
