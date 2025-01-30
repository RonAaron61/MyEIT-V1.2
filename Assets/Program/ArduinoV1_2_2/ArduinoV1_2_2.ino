#include <Wire.h>
#include <Adafruit_ADS1X15.h>
#include <MD_AD9833.h>
#include <SPI.h>

Adafruit_ADS1115 ads;

#define Frequency 50000  // Frequency = 50kHz

// Pin Definitions
const uint8_t PIN_DATA = 35;   // SPI Data pin
const uint8_t PIN_CLK = 36;    // SPI Clock pin
const uint8_t PIN_FSYNC = 34;  // SPI Load pin (FSYNC in AD9833 usage)
MD_AD9833 AD(PIN_DATA, PIN_CLK, PIN_FSYNC);  // AD9833 object

// MUX control pins (grouped by function)
const uint8_t MUX_A_PINS[4] = {1, 2, 3, 4};   // First electrode pair
const uint8_t MUX_B_PINS[4] = {5, 6, 7, 10};  // Second electrode pair
const uint8_t MUX_C_PINS[4] = {11, 12, 13, 14};  // Third electrode pair
const uint8_t MUX_D_PINS[4] = {16, 17, 18, 21};  // Fourth electrode pair

// LED pins
const uint8_t LED_PINS[3] = {39, 40, 38};  // LED1, LED2, LED3
const uint8_t LED_BuIn = 15;               // Button LED

// MUX channel patterns (binary representation)
const uint8_t mux[16] = {
  0b0000, 0b0001, 0b0010, 0b0011,
  0b0100, 0b0101, 0b0110, 0b0111,
  0b1000, 0b1001, 0b1010, 0b1011,
  0b1100, 0b1101, 0b1110, 0b1111
};

// Data storage
float result[208];  // Array to store voltage differences

// Serial command character
char ser;

// I2C pins
#define SDA 8
#define SCL 9

// Blink an LED
void blinkLED(uint8_t ledIndex, uint16_t duration = 300) {
  digitalWrite(LED_PINS[ledIndex], HIGH);
  delay(duration);
  digitalWrite(LED_PINS[ledIndex], LOW);
}

// ==================== SETUP ====================
void setup() {
  Serial.begin(115200);

  // Initialize AD9833
  AD.begin();
  AD.setFrequency(MD_AD9833::CHAN_0, Frequency);
  AD.setMode(MD_AD9833::MODE_OFF);

  // Initialize ADS1115
  Wire.begin(SDA, SCL);
  ads.setGain(GAIN_TWOTHIRDS);  // +/- 6.144V range
  if (!ads.begin()) {
    Serial.println("Failed to initialize ADS.");
    while (1);
  }

  // Set pin modes
  for (uint8_t i = 0; i < 4; i++) {
    pinMode(MUX_A_PINS[i], OUTPUT);
    pinMode(MUX_B_PINS[i], OUTPUT);
    pinMode(MUX_C_PINS[i], OUTPUT);
    pinMode(MUX_D_PINS[i], OUTPUT);
  }

  for (uint8_t i = 0; i < 3; i++) {
    pinMode(LED_PINS[i], OUTPUT);
  }
  pinMode(LED_BuIn, INPUT);

  // LED test sequence
  for (uint8_t i = 0; i < 3; i++) {
    blinkLED(i);
  }
}

// ==================== HELPER FUNCTIONS ====================

// Set MUX channel
void setMuxChannel(const uint8_t* muxPins, uint8_t channel) {
  for (uint8_t i = 0; i < 4; i++) {
    digitalWrite(muxPins[i], bitRead(mux[channel], i));
  }
}

// Read and calibrate voltage
float readCalibratedVoltage(uint8_t channel) {
  int16_t adc = ads.readADC_SingleEnded(channel);
  float volts = ads.computeVolts(adc);
  return volts * 1.1695;  // Combined calibration factor
}

// Send results over Serial
void sendResults() {
  // Send binary header
  Serial.write(0xAA);  // Start marker
  Serial.write(0x55);

  // Send binary data
  Serial.write((byte*)result, sizeof(result));

  // Send end marker
  Serial.write("\r\nDone\r\n");
}

void sendResults2() {
  digitalWrite(LED_PINS[1], HIGH);  // Turn on LED2
  for (int i=0; i<208;i++){
    Serial.println(result[i],5);
    }
  Serial.println("Done");
  digitalWrite(LED_PINS[1], LOW);  // Turn on LED2
}

// ==================== MAIN FUNCTIONS ====================

void Get_Data(int n_elec = 16) {
  AD.setMode(MD_AD9833::MODE_SINE);
  digitalWrite(LED_PINS[0], HIGH);  // Turn on LED1

  uint8_t iter = 0;
  for (uint8_t i = 0; i < n_elec; i++) {
    uint8_t a = (i + 1) % n_elec;

    setMuxChannel(MUX_A_PINS, i);
    setMuxChannel(MUX_B_PINS, a);

    for (uint8_t j = 0; j < n_elec; j++) {
      uint8_t b = (j + 1) % n_elec;

      if (j == i || j == a || b == i) continue;

      setMuxChannel(MUX_C_PINS, j);
      setMuxChannel(MUX_D_PINS, b);

      result[iter++] = readCalibratedVoltage(0) - readCalibratedVoltage(1);
    }
  }

  AD.setMode(MD_AD9833::MODE_OFF);
  digitalWrite(LED_PINS[0], LOW);  // Turn off LED1
}

void Tester(uint8_t a, uint8_t b, uint8_t c, uint8_t d) {
  AD.setMode(MD_AD9833::MODE_SINE);
  digitalWrite(LED_PINS[2], HIGH);  // Turn on LED3

  setMuxChannel(MUX_A_PINS, a);
  setMuxChannel(MUX_B_PINS, b);
  setMuxChannel(MUX_C_PINS, c);
  setMuxChannel(MUX_D_PINS, d);

  float voltage = readCalibratedVoltage(0);
  float voltageReff = readCalibratedVoltage(1);

  digitalWrite(LED_PINS[2], LOW);  // Turn off LED3

  Serial.print(voltage, 5);
  Serial.print(" - ");
  Serial.print(voltageReff, 5);
  Serial.print(" = ");
  Serial.println(voltage - voltageReff, 5);
}

// ==================== LOOP ====================
void loop() {
  if (Serial.available() > 0) {
    ser = Serial.read();
    if (ser == 'D') {
      Get_Data();
      sendResults2();
    } else if (ser == 'C') {
      Tester(14, 15, 12, 13);
    }
  }
}
