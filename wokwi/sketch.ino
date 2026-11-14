// Node workspace: HC-SR04 mendeteksi ada orang duduk, LED + LCD menampilkan status dari server
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <LiquidCrystal_I2C.h>

const char* WS_CODE    = "WS-A01";                                   // samakan dengan kode di tabel workspaces
const char* SERVER_URL = "https://NAMA-APP.onrender.com/api/iot/telemetry";
const char* DEVICE_KEY = "kunci-rahasia-untuk-esp32";                // samakan dengan env DEVICE_KEY
#define TRIG 5
#define ECHO 18
#define LED_G 26
#define LED_R 27
#define THRESHOLD_CM 80                                              // < 80 cm = ada orang

LiquidCrystal_I2C lcd(0x27, 16, 2);

float readCm() {
  digitalWrite(TRIG, LOW); delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10); digitalWrite(TRIG, LOW);
  long d = pulseIn(ECHO, HIGH, 30000);
  return d ? d * 0.0343 / 2 : 400;
}

void show(const char* l2, bool g) {
  digitalWrite(LED_G, g); digitalWrite(LED_R, !g);
  lcd.setCursor(0, 1); lcd.print("                "); lcd.setCursor(0, 1); lcd.print(l2);
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT); pinMode(ECHO, INPUT); pinMode(LED_G, OUTPUT); pinMode(LED_R, OUTPUT);
  lcd.init(); lcd.backlight(); lcd.setCursor(0, 0); lcd.print(WS_CODE); lcd.setCursor(0, 1); lcd.print("Konek WiFi...");
  WiFi.begin("Wokwi-GUEST", "", 6);
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  Serial.println("\nWiFi OK"); show("Siap", true);
}

void loop() {
  float cm = readCm();
  bool present = cm < THRESHOLD_CM;
  char body[96];
  snprintf(body, sizeof(body), "{\"code\":\"%s\",\"present\":%s,\"distance\":%.1f}", WS_CODE, present ? "true" : "false", cm);

  WiFiClientSecure client; client.setInsecure();
  HTTPClient http; http.setTimeout(15000);            // Render free tier bisa lambat saat bangun
  if (http.begin(client, SERVER_URL)) {
    http.addHeader("Content-Type", "application/json");
    http.addHeader("x-device-key", DEVICE_KEY);
    int code = http.POST(body);
    String res = code > 0 ? http.getString() : "";
    Serial.printf("%.1f cm | HTTP %d | %s\n", cm, code, res.c_str());
    if (res.indexOf("\"available\"") >= 0) show("TERSEDIA", true);
    else if (res.indexOf("\"occupied\"") >= 0) show("DIPAKAI", false);
    else if (res.indexOf("\"detected\"") >= 0) show("ADA ORANG", false);
    else show("Server error", false);
    http.end();
  }
  delay(3000);
}
