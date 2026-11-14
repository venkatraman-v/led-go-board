import argparse
import re
import shlex
import sys

from board import Board, Piece
from game import Game
from renderer import BoardRenderer, format_coordinate


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


def _render(game: Game) -> None:
    game.render(cursor=game.input_controller.position)


def _print_help() -> None:
    print(
        "\nCommands:\n"
        "  play A1 / play 4 5   play at a labelled or zero-based coordinate\n"
        "  up/down/left/right   move the joystick cursor\n"
        "  goto A1              move the cursor directly\n"
        "  press                press the button (play at the cursor)\n"
        "  pass                 pass the turn\n"
        "  undo                 undo the last move\n"
        "  save FILE / load FILE  write or read a JSON move list\n"
        "  show                 redraw the board\n"
        "  help                 show this help\n"
        "  quit                 exit\n"
    )


def run_interactive(size: int) -> int:
    game = Game(size=size)
    print("LED Go board. Type 'help' for commands.\n")
    _render(game)

    while True:
        try:
            prompt = f"\n{game.current_player.name.title()}> "
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
                _print_help()
            elif command in ("show", "board"):
                _render(game)
            elif command in ("play", "move"):
                if len(args) == 1:
                    x, y = parse_coordinate(args[0])
                elif len(args) == 2:
                    x, y = int(args[0]), int(args[1])
                else:
                    raise ValueError("usage: play A1 or play X Y")
                color = game.current_player
                if game.play_move(x, y):
                    print(f"{color.name.title()} played {format_coordinate(x, y)}.")
                    _render(game)
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
                _render(game)
            elif command in ("goto", "cursor"):
                if len(args) != 1:
                    raise ValueError("usage: goto A1")
                game.input_controller.set_position(*parse_coordinate(args[0]))
                _render(game)
            elif command == "press":
                color = game.current_player
                x, y = game.input_controller.position
                if game.input_controller.handle_button_press():
                    print(f"{color.name.title()} played {format_coordinate(x, y)}.")
                    _render(game)
                else:
                    print("Illegal move (occupied, suicide, ko, or game over).")
            elif command == "pass":
                color = game.current_player
                if game.pass_move():
                    print(f"{color.name.title()} passed.")
                    _render(game)
                else:
                    print("The game is already over.")
            elif command == "undo":
                if game.undo_move():
                    print("Undid the last move.")
                    _render(game)
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
                _render(game)
            else:
                print(f"Unknown command: {command!r}. Type 'help' for commands.")
        except (ValueError, OSError) as error:
            print(f"Error: {error}")


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
    args = parser.parse_args(argv)

    if args.size < 1:
        parser.error("--size must be positive")

    interactive = args.interactive or (not args.demo and sys.stdin.isatty())
    if interactive:
        return run_interactive(args.size)
    if args.size < 5:
        parser.error("--size must be at least 5 in demo mode")
    return run_demo(args.size)


if __name__ == "__main__":
    sys.exit(main())
