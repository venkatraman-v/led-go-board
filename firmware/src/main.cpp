#include <Arduino.h>
#include <Adafruit_GFX.h>
#include <RGBmatrixPanel.h>

// Control and Row Select Pins for Arduino Uno / Elegoo R3
#define CLK 8
#define OE  9
#define LAT 10
#define A   A0
#define B   A1
#define C   A2
#define D   A3

// Initialize the 32x32 RGB Matrix panel
// Note: RGB data pins (R1, G1, B1, R2, G2, B2) are hardcoded 
// to digital pins 2 through 7 in the library for the Uno.
RGBmatrixPanel matrix(A, B, C, D, CLK, LAT, OE, false); 

unsigned long lastSwitchTime = 0;
int shapeState = 0;

// Function declaration for our custom shape
void drawStar(uint16_t color);

void setup() {
  matrix.begin();
  // Seed the random number generator using analog noise from an unconnected pin
  randomSeed(analogRead(A5)); 
}

void loop() {
  // Switch shapes every 2000 milliseconds (2 seconds)
  if (millis() - lastSwitchTime > 2000) {
    lastSwitchTime = millis();

    // 1. KEEP THE BACKGROUND BLACK (Massive power savings for AA batteries)
    matrix.fillScreen(matrix.Color333(0, 0, 0)); 
    
    // 2. GENERATE DIM COLORS ONLY
    // Use random(2) which only generates a 0 or 1.
    // 1 is the lowest possible brightness setting.
    uint8_t fgR = random(2);
    uint8_t fgG = random(2);
    uint8_t fgB = random(2);
    
    // Make sure it doesn't accidentally pick black (0,0,0) for the shape
    if (fgR == 0 && fgG == 0 && fgB == 0) {
      fgR = 1; 
    }

    uint16_t shapeColor = matrix.Color333(fgR, fgG, fgB);

    // Draw the current shape in the sequence using the ultra-dim color
    switch (shapeState) {
      case 0:
        // Square (x, y, width, height)
        matrix.fillRect(6, 6, 20, 20, shapeColor);
        break;
      case 1:
        // Circle (center_x, center_y, radius)
        matrix.fillCircle(15, 15, 10, shapeColor);
        break;
      case 2:
        // Triangle (x0, y0, x1, y1, x2, y2)
        matrix.fillTriangle(15, 4, 4, 26, 26, 26, shapeColor);
        break;
      case 3:
        // Star (Custom function)
        drawStar(shapeColor);
        break;
    }

    // Advance to the next shape (0 -> 1 -> 2 -> 3 -> 0)
    shapeState = (shapeState + 1) % 4;
  }
}

void drawStar(uint16_t color) {
  // Draw a classic 5-point pentagram using lines, mapped to 32x32 coordinates
  matrix.drawLine(15, 4, 24, 25, color);
  matrix.drawLine(24, 25, 4, 12, color);
  matrix.drawLine(4, 12, 26, 12, color);
  matrix.drawLine(26, 12, 6, 25, color);
  matrix.drawLine(6, 25, 15, 4, color);
}