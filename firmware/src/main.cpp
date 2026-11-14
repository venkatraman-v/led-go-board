#include <Arduino.h>
#include <Adafruit_GFX.h>
#include <RGBmatrixPanel.h>

// ============================================================================
// Hardware Pin Configuration for Arduino Uno / Elegoo R3
// ============================================================================
#define CLK 8
#define OE  9
#define LAT 10
#define A   A0
#define B   A1
#define C   A2
#define D   A3
// Note: RGB data pins (R1, G1, B1, R2, G2, B2) are hardcoded 
// to digital pins 2 through 7 in the library for the Uno.

RGBmatrixPanel matrix(A, B, C, D, CLK, LAT, OE, false);

// Global brightness setting: 1 to 7 (1 is lowest/dimmest/battery-safe, 7 is maximum)
uint8_t globalBrightness = 1;

// Serial reception buffer
char rxBuf[32];
uint8_t rxIdx = 0;

// ============================================================================
// BASE DRAW & COLOR FUNCTIONS
// ============================================================================

// Color creation helper (Native Color333: r, g, b from 0 to 7)
uint16_t makeColor(uint8_t r, uint8_t g, uint8_t b, uint8_t brightness = globalBrightness) {
  uint8_t br = constrain(brightness, 1, 7);
  uint8_t scaledR = (r * br) / 7;
  uint8_t scaledG = (g * br) / 7;
  uint8_t scaledB = (b * br) / 7;

  // Make sure non-zero inputs don't turn completely off
  if (r > 0 && scaledR == 0) scaledR = 1;
  if (g > 0 && scaledG == 0) scaledG = 1;
  if (b > 0 && scaledB == 0) scaledB = 1;

  return matrix.Color333(scaledR, scaledG, scaledB);
}

void setBrightness(uint8_t b) {
  globalBrightness = constrain(b, 1, 7);
}

// Draw individual pixel: stays on indefinitely in the buffer until cleared
void drawPixel(int16_t x, int16_t y, uint16_t color) {
  if (x >= 0 && x < 32 && y >= 0 && y < 32) {
    matrix.drawPixel(x, y, color);
  }
}

// Clear individual pixel: turns off that LED, other LEDs remain on
void clearPixel(int16_t x, int16_t y) {
  drawPixel(x, y, matrix.Color333(0, 0, 0));
}

// Clear entire board
void clearBoard() {
  matrix.fillScreen(matrix.Color333(0, 0, 0));
}

// Draw line
void drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint16_t color) {
  matrix.drawLine(x0, y0, x1, y1, color);
}

// Draw square (wireframe or filled)
void drawSquare(int16_t x, int16_t y, int16_t size, uint16_t color, bool filled = true) {
  if (filled) {
    matrix.fillRect(x, y, size, size, color);
  } else {
    matrix.drawRect(x, y, size, size, color);
  }
}

// Draw triangle (wireframe or filled)
void drawTriangle(int16_t x0, int16_t y0, int16_t x1, int16_t y1, int16_t x2, int16_t y2, uint16_t color, bool filled = true) {
  if (filled) {
    matrix.fillTriangle(x0, y0, x1, y1, x2, y2, color);
  } else {
    matrix.drawTriangle(x0, y0, x1, y1, x2, y2, color);
  }
}

// ============================================================================
// SERIAL COMMAND TRANSLATOR / DISPATCHER
// ============================================================================

// Fast in-place integer parser
int readInt(char** p) {
  while (**p == ' ' || **p == '\t' || **p == ',') (*p)++;
  bool neg = false;
  if (**p == '-') {
    neg = true;
    (*p)++;
  }
  int val = 0;
  while (**p >= '0' && **p <= '9') {
    val = val * 10 + (**p - '0');
    (*p)++;
  }
  return neg ? -val : val;
}

void processCommand(char* buf) {
  char* p = buf;
  while (*p == ' ' || *p == '\t') p++;
  if (*p == '\0') return;

  char cmd = *p++; // First letter determines command

  // 'P' x y r g b  -> Pixel
  if (cmd == 'P' || cmd == 'p') {
    int x = readInt(&p);
    int y = readInt(&p);
    int r = readInt(&p);
    int g = readInt(&p);
    int b = readInt(&p);
    drawPixel(x, y, makeColor(r, g, b));
    Serial.println(F("OK"));
  }
  // 'X' x y        -> Clear Pixel (turn off)
  else if (cmd == 'X' || cmd == 'x') {
    int x = readInt(&p);
    int y = readInt(&p);
    clearPixel(x, y);
    Serial.println(F("OK"));
  }
  // 'C'            -> Clear Board
  else if (cmd == 'C' || cmd == 'c') {
    clearBoard();
    Serial.println(F("OK"));
  }
  // 'L' x0 y0 x1 y1 r g b -> Line
  else if (cmd == 'L' || cmd == 'l') {
    int x0 = readInt(&p);
    int y0 = readInt(&p);
    int x1 = readInt(&p);
    int y1 = readInt(&p);
    int r  = readInt(&p);
    int g  = readInt(&p);
    int b  = readInt(&p);
    drawLine(x0, y0, x1, y1, makeColor(r, g, b));
    Serial.println(F("OK"));
  }
  // 'S' x y size r g b [fill] -> Square
  else if (cmd == 'S' || cmd == 's') {
    int x = readInt(&p);
    int y = readInt(&p);
    int s = readInt(&p);
    int r = readInt(&p);
    int g = readInt(&p);
    int b = readInt(&p);
    int fill = 1;
    if (*p) fill = readInt(&p);
    drawSquare(x, y, s, makeColor(r, g, b), fill != 0);
    Serial.println(F("OK"));
  }
  // 'T' x0 y0 x1 y1 x2 y2 r g b [fill] -> Triangle
  else if (cmd == 'T' || cmd == 't') {
    int x0 = readInt(&p);
    int y0 = readInt(&p);
    int x1 = readInt(&p);
    int y1 = readInt(&p);
    int x2 = readInt(&p);
    int y2 = readInt(&p);
    int r  = readInt(&p);
    int g  = readInt(&p);
    int b  = readInt(&p);
    int fill = 1;
    if (*p) fill = readInt(&p);
    drawTriangle(x0, y0, x1, y1, x2, y2, makeColor(r, g, b), fill != 0);
    Serial.println(F("OK"));
  }
  // 'B' brightness -> Set Brightness (1-7)
  else if (cmd == 'B' || cmd == 'b') {
    int val = readInt(&p);
    setBrightness(val);
    Serial.println(F("OK"));
  }
  // '?' / PING
  else if (cmd == '?' || cmd == 'q' || cmd == 'Q') {
    Serial.println(F("READY"));
  }
  else {
    Serial.println(F("ERR"));
  }
}

// Non-blocking serial listener
void checkSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      rxBuf[rxIdx] = '\0';
      if (rxIdx > 0) {
        processCommand(rxBuf);
      }
      rxIdx = 0;
    } else if (rxIdx < sizeof(rxBuf) - 1) {
      rxBuf[rxIdx++] = c;
    }
  }
}

// ============================================================================
// Setup & Loop
// ============================================================================
void setup() {
  Serial.begin(115200);
  matrix.begin();
  clearBoard();
  Serial.println(F("READY"));
}

void loop() {
  int x = analogRead(A4);
  int y = analogRead(A5);

  Serial.print("X: ");
  Serial.print(x);
  Serial.print(" | Y: ");
  Serial.println(y);

  delay(200);
}
