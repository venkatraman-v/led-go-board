#include <Arduino.h>
#include <Adafruit_GFX.h>   // Core graphics library
#include <RGBmatrixPanel.h> // Hardware-specific library for the matrix

// Control and Row Select Pins for Arduino Uno / Elegoo R3
#define CLK 8
#define OE  9
#define LAT 10
#define A   A0
#define B   A1
#define C   A2
#define D   A3

// Initialize the 32x32 RGB Matrix panel
// Note: The 6 RGB data pins (R1, G1, B1, R2, G2, B2) are hardcoded 
// in the library to digital pins 2 through 7 for the Uno.
RGBmatrixPanel matrix(A, B, C, D, CLK, LAT, OE, false); 

// put function declarations here:
void runWiringTest();

void setup() {
  // put your setup code here, to run once:
  matrix.begin();
  
  runWiringTest();
}

void loop() {
  // put your main code here, to run repeatedly:
  // Leaving this blank so the board doesn't have to constantly redraw
}

// put function definitions here:
void runWiringTest() {
  // Fill the screen with green 
  matrix.fillScreen(matrix.Color333(0, 7, 0));
  
  // Draw a yellow rectangle outline
  matrix.drawRect(0, 0, 32, 32, matrix.Color333(7, 7, 0));
  
  // Draw a red 'X' through the middle to test coordinate mapping
  matrix.drawLine(0, 0, 31, 31, matrix.Color333(7, 0, 0));
  matrix.drawLine(31, 0, 0, 31, matrix.Color333(7, 0, 0));
}