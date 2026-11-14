import time
import sys

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


class BoardRenderer:
    """Handles rendering the Go board state."""
    def __init__(self):
        pass


class LEDRenderer:
    """Handles hardware rendering on the 32x32 RGB LED Matrix and joystick inputs over Serial."""

    def __init__(self, port: str = None, baudrate: int = 115200, timeout: float = 1.0):
        if serial is None:
            raise ImportError(
                "pyserial is not installed. Please run: pip install pyserial"
            )

        if port is None:
            port = self._auto_detect_port()

        print(f"Connecting to LED matrix on {port} at {baudrate} baud...")
        self.ser = serial.Serial(port, baudrate, timeout=timeout)

        # Allow Arduino to boot (DTR reset takes ~1.5 - 2.0s)
        time.sleep(2.0)

        # Drain any startup banner
        while self.ser.in_waiting > 0:
            line = self.ser.readline().decode("utf-8", errors="ignore").strip()
            if line:
                print(f"[Firmware]: {line}")

        self.clear()
        print("Connected and ready.")

    def _auto_detect_port(self) -> str:
        """Looks for an Arduino or USB-Serial device."""
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = p.description.lower()
            hwid = p.hwid.lower()
            if (
                "arduino" in desc
                or "ch340" in desc
                or "usb serial" in desc
                or "vid:2341" in hwid
                or "vid:1a86" in hwid
            ):
                return p.device
        if ports:
            return ports[0].device
        return "COM5"

    def _to_rgb7(self, c: int) -> int:
        """Converts 0-255 or 0-7 into the 0-7 native hardware range."""
        if c > 7:
            return min(7, max(0, c // 36))
        return min(7, max(0, c))

    def send(self, cmd: str) -> str:
        """Sends command line to Arduino and reads response."""
        msg = (cmd.strip() + "\n").encode("utf-8")
        self.ser.write(msg)
        return self.ser.readline().decode("utf-8", errors="ignore").strip()

    # =========================================================================
    # JOYSTICK FUNCTIONS
    # =========================================================================

    def get_joystick(self, invert_x: bool = True) -> tuple[int, int]:
        """
        Reads the current X and Y raw analog values from the joystick.
        Returns (x, y) where values typically range from 0 to 1023.
        Resting center position is around ~512.
        
        invert_x: Reverses the X-axis direction (1023 - raw_x) so moving right
                  increases X and moving left decreases X.
        """
        res = self.send("J")
        parts = res.split()
        if len(parts) >= 3 and parts[0] == "J":
            try:
                raw_x = int(parts[1])
                raw_y = int(parts[2])
                if invert_x:
                    raw_x = 1023 - raw_x
                return (raw_x, raw_y)
            except ValueError:
                pass
        return (512, 512)

    def get_joystick_direction(self, deadzone: int = 150) -> str:
        """
        Translates raw joystick values into a cardinal direction:
        'UP', 'DOWN', 'LEFT', 'RIGHT', or 'CENTER'.
        """
        x, y = self.get_joystick()
        dx = x - 512
        dy = y - 512

        if abs(dx) < deadzone and abs(dy) < deadzone:
            return "CENTER"
        if abs(dx) > abs(dy):
            return "RIGHT" if dx > 0 else "LEFT"
        else:
            return "DOWN" if dy > 0 else "UP"

    # =========================================================================
    # DRAWING PRIMITIVES
    # =========================================================================

    def clear(self):
        """Clears the whole matrix (all LEDs off)."""
        return self.send("C")

    def draw_pixel(self, x: int, y: int, r: int, g: int, b: int):
        """Draws individual pixel with RGB (0-7). Stays on indefinitely."""
        return self.send(f"P {x} {y} {self._to_rgb7(r)} {self._to_rgb7(g)} {self._to_rgb7(b)}")

    def clear_pixel(self, x: int, y: int):
        """Turns off a single pixel; other pixels stay on."""
        return self.send(f"X {x} {y}")

    def draw_line(self, x0: int, y0: int, x1: int, y1: int, r: int, g: int, b: int):
        """Draws a line segment."""
        return self.send(f"L {x0} {y0} {x1} {y1} {self._to_rgb7(r)} {self._to_rgb7(g)} {self._to_rgb7(b)}")

    def draw_square(self, x: int, y: int, size: int, r: int, g: int, b: int, fill: bool = True):
        """Draws a square (wireframe or filled)."""
        f = 1 if fill else 0
        return self.send(f"S {x} {y} {size} {self._to_rgb7(r)} {self._to_rgb7(g)} {self._to_rgb7(b)} {f}")

    def draw_triangle(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        r: int,
        g: int,
        b: int,
        fill: bool = True,
    ):
        """Draws a triangle (wireframe or filled)."""
        f = 1 if fill else 0
        return self.send(
            f"T {x0} {y0} {x1} {y1} {x2} {y2} {self._to_rgb7(r)} {self._to_rgb7(g)} {self._to_rgb7(b)} {f}"
        )

    def set_brightness(self, level: int):
        """Sets brightness scale (1 to 7)."""
        return self.send(f"B {min(7, max(1, level))}")

    def close(self):
        """Closes connection."""
        if hasattr(self, "ser") and self.ser and self.ser.is_open:
            self.clear()
            self.ser.close()

    # =========================================================================
    # EXAMPLES
    # =========================================================================

    def joystick_example(self):
        """
        Interactive Example:
        Reads the joystick position in real time and moves a bright LED
        cursor around the 32x32 matrix.
        """
        print("\n=======================================================")
        print("  Joystick LED Matrix Interactive Demo")
        print("  Move your joystick to steer the dot across the board!")
        print("  Press Ctrl+C to stop.")
        print("=======================================================\n")

        # Start in the center of the 32x32 board
        pos_x = 15
        pos_y = 15

        self.clear()
        # Draw initial green dot at center
        self.draw_pixel(pos_x, pos_y, 0, 7, 0)

        try:
            while True:
                # 1. Read joystick (returns raw analog 0-1023)
                raw_x, raw_y = self.get_joystick()

                # 2. Determine movement based on joystick position
                new_x, new_y = pos_x, pos_y

                # X-axis movement
                if raw_x < 300:      # Pushed Left
                    new_x = max(0, pos_x - 1)
                elif raw_x > 700:    # Pushed Right
                    new_x = min(31, pos_x + 1)

                # Y-axis movement
                if raw_y < 300:      # Pushed Up
                    new_y = max(0, pos_y - 1)
                elif raw_y > 700:    # Pushed Down
                    new_y = min(31, pos_y + 1)

                # 3. If position changed, update display
                if new_x != pos_x or new_y != pos_y:
                    # Erase previous pixel
                    self.clear_pixel(pos_x, pos_y)
                    # Update coordinates
                    pos_x, pos_y = new_x, new_y
                    # Draw pixel at new position (Green)
                    self.draw_pixel(pos_x, pos_y, 0, 7, 0)

                    print(f"Joystick: (X={raw_x:4d}, Y={raw_y:4d}) | Cursor: ({pos_x:2d}, {pos_y:2d})")

                # Sample interval (smooth, responsive control)
                time.sleep(0.08)

        except KeyboardInterrupt:
            print("\nDemo stopped.")
            self.clear()
            self.close()

    def run_animation(self, interval: float = 1.5):
        """Draws 1 line, 2 lines, 3 lines, 4 lines, square, triangle, and loops."""
        print("Starting progressive line & shape animation. Press Ctrl+C to stop.\n")
        RED    = (7, 0, 0)
        GREEN  = (0, 7, 0)
        BLUE   = (0, 0, 7)
        YELLOW = (7, 7, 0)

        try:
            while True:
                # Step 1: 1 Line
                self.clear()
                self.draw_line(4, 6, 27, 6, *RED)
                time.sleep(interval)

                # Step 2: 2 Lines
                self.draw_line(4, 12, 27, 12, *GREEN)
                time.sleep(interval)

                # Step 3: 3 Lines
                self.draw_line(4, 18, 27, 18, *BLUE)
                time.sleep(interval)

                # Step 4: 4 Lines
                self.draw_line(4, 24, 27, 24, *YELLOW)
                time.sleep(interval)

                # Step 5: Square
                self.clear()
                self.draw_square(6, 6, 20, *RED, fill=True)
                time.sleep(interval)

                # Step 6: Triangle
                self.clear()
                self.draw_triangle(15, 4, 4, 26, 26, 26, *BLUE, fill=True)
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\nAnimation stopped.")
            self.clear()
            self.close()


if __name__ == "__main__":
    target_port = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else None
    mode = sys.argv[2] if len(sys.argv) > 2 else "joystick"

    try:
        renderer = LEDRenderer(port=target_port)
        if mode == "animation":
            renderer.run_animation(interval=1.5)
        else:
            renderer.joystick_example()
    except Exception as e:
        print(f"\n[Error]: {e}")
