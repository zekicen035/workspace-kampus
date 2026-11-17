// Node zona Utara: 1 ESP32 memantau 6 meja. Posisi sensor di diagram meniru denah asli.
// Lampu per meja (NeoPixel) DAN layar TFT ILI9341 per meja:
//   hijau = tersedia, merah = dipakai (sudah scan QR), kuning = ada orang tapi belum scan.
// Tiap meja punya layar sendiri yang menampilkan QR code mejanya. Kuning > GRACE_MS -> buzzer berbunyi.
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_NeoPixel.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include <qrcode.h>   // bawaan ESP32 (ESP-IDF): esp_qrcode_*, tidak perlu library tambahan

const char* ZONA       = "Utara";
const char* SERVER_URL = "https://workspace-kampus.onrender.com/api/iot/telemetry";
const char* DEVICE_KEY = "ISI_DEVICE_KEY_KAMU";   // samakan dengan DEVICE_KEY di Render
// Isi QR = QR_BASE + kode meja. Server /api/checkin membaca kode meja saja (mis. "WS-S01"),
// jadi dikosongkan: QR berisi kode meja saja dan dibaca oleh scanner di dalam aplikasi.
const char* QR_BASE    = "";

#define N 6
const char* CODE[N] = {"WS-U01", "WS-U02", "WS-U03", "WS-U04", "WS-U05", "WS-U06"};
const int ECHO[N]   = {34, 35, 36, 39, 32, 33};
const int TFT_CS[N] = {25, 26, 27, 14, 12, 15};
const int PIX[N]    = {0, 5, 2, 3, 1, 4};   // urutan lampu pada rantai NeoPixel untuk tiap meja
#define TRIG_PIN 5           // satu pin TRIG dipakai bersama semua sensor (hemat pin)
#define TFT_DC   17          // SCK=18, MOSI=23 (SPI bawaan), RST layar disambung ke 3V3
#define BUZZER 13
#define PIXPIN 4
#define THRESHOLD_CM 80      // jarak < 80 cm = ada orang
#define GRACE_MS 10000       // waktu untuk scan QR sebelum alarm
#define QR_MAX_VERSION 6     // versi QR otomatis dipilih sesuai panjang teks, maksimal ini
#define QR_AREA 170          // lebar maksimum area modul QR (piksel)
#define QR_QUIET 16          // area putih di sekeliling QR (piksel)

enum { ST_AVAILABLE, ST_OCCUPIED, ST_DETECTED, ST_ERROR, ST_WAIT };

LiquidCrystal_I2C lcd(0x27, 16, 2);
Adafruit_NeoPixel strip(N, PIXPIN, NEO_GRB + NEO_KHZ800);
Adafruit_ILI9341* tft[N];
WiFiClientSecure client;
HTTPClient http;
unsigned long since[N];
int shown[N];

// ---------- layar per meja ----------
void centerText(Adafruit_ILI9341* d, const char* s, int y, uint8_t size, uint16_t fg) {
  d->setTextSize(size); d->setTextColor(fg);
  d->setCursor((240 - (int)strlen(s) * 6 * size) / 2, y);
  d->print(s);
}

Adafruit_ILI9341* qrTarget;            // layar tujuan untuk callback QR
void qrDisplay(esp_qrcode_handle_t q) {
  int size = esp_qrcode_get_size(q);
  int sc = QR_AREA / size; if (sc < 1) sc = 1;
  int box = size * sc + 2 * QR_QUIET;
  int x0 = (240 - box) / 2, y0 = 42;
  qrTarget->fillRect(x0, y0, box, box, ILI9341_WHITE);
  for (int y = 0; y < size; y++)
    for (int x = 0; x < size; x++)
      if (esp_qrcode_get_module(q, x, y))
        qrTarget->fillRect(x0 + QR_QUIET + x * sc, y0 + QR_QUIET + y * sc, sc, sc, ILI9341_BLACK);
}

void drawTable(int i) {
  Adafruit_ILI9341* d = tft[i];
  d->fillScreen(ILI9341_BLACK);
  d->fillRect(0, 0, 240, 36, d->color565(25, 40, 90));
  char head[20]; snprintf(head, sizeof(head), "MEJA %s", CODE[i] + 3);
  centerText(d, head, 8, 3, ILI9341_WHITE);

  String text = String(QR_BASE) + CODE[i];
  esp_qrcode_config_t cfg = {};
  cfg.display_func = qrDisplay;
  cfg.max_qrcode_version = QR_MAX_VERSION;
  cfg.qrcode_ecc_level = ESP_QRCODE_ECC_LOW;
  qrTarget = d;
  if (esp_qrcode_generate(&cfg, text.c_str()) != ESP_OK)
    centerText(d, "QR terlalu panjang", 120, 2, ILI9341_RED);   // naikkan QR_MAX_VERSION
  char lbl[24]; snprintf(lbl, sizeof(lbl), "%s | %s", CODE[i], ZONA);
  centerText(d, lbl, 246, 2, ILI9341_WHITE);
  shown[i] = -1;
}

void showStatus(int i, int st) {
  if (shown[i] == st) return;            // hanya gambar ulang kalau status berubah
  shown[i] = st;
  Adafruit_ILI9341* d = tft[i];
  uint16_t bg, fg = ILI9341_WHITE; const char* txt;
  switch (st) {
    case ST_AVAILABLE: bg = d->color565(0, 140, 60);  txt = "TERSEDIA"; break;
    case ST_OCCUPIED:  bg = d->color565(190, 25, 40); txt = "DIPAKAI";  break;
    case ST_DETECTED:  bg = d->color565(235, 170, 0); txt = "SCAN QR!"; fg = ILI9341_BLACK; break;
    case ST_WAIT:      bg = d->color565(90, 90, 90);  txt = "MENUNGGU"; break;
    default:           bg = d->color565(90, 90, 90);  txt = "OFFLINE";  break;
  }
  d->fillRect(0, 268, 240, 52, bg);
  centerText(d, txt, 282, 3, fg);
}

// ---------- sensor, lampu, server ----------
float readCm(int i) {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10); digitalWrite(TRIG_PIN, LOW);
  long d = pulseIn(ECHO[i], HIGH, 30000);
  return d ? d * 0.0343 / 2 : 400;
}

void beep(int ms) {
  for (int t = 0; t < ms; t++) { digitalWrite(BUZZER, HIGH); delayMicroseconds(500); digitalWrite(BUZZER, LOW); delayMicroseconds(500); }
}

void lamp(int i, uint8_t r, uint8_t g, uint8_t b) { strip.setPixelColor(PIX[i], strip.Color(r, g, b)); }

String post(int i, float cm) {
  char body[96];
  snprintf(body, sizeof(body), "{\"code\":\"%s\",\"present\":%s,\"distance\":%.1f}", CODE[i], cm < THRESHOLD_CM ? "true" : "false", cm);
  if (!http.begin(client, SERVER_URL)) return "error";
  http.addHeader("Content-Type", "application/json");
  http.addHeader("x-device-key", DEVICE_KEY);
  int code = http.POST(body);
  String res = code > 0 ? http.getString() : "";
  http.end();
  Serial.printf("%s | %.1f cm | HTTP %d | %s\n", CODE[i], cm, code, res.c_str());
  if (res.indexOf("\"occupied\"") >= 0) return "occupied";
  if (res.indexOf("\"detected\"") >= 0) return "detected";
  if (res.indexOf("\"available\"") >= 0) return "available";
  return "error";
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  for (int i = 0; i < N; i++) { pinMode(ECHO[i], INPUT); since[i] = 0; pinMode(TFT_CS[i], OUTPUT); digitalWrite(TFT_CS[i], HIGH); }
  pinMode(BUZZER, OUTPUT);
  strip.begin(); strip.setBrightness(80); strip.show();
  lcd.init(); lcd.backlight(); lcd.print("Zona "); lcd.print(ZONA); lcd.setCursor(0, 1); lcd.print("Gambar QR...");
  for (int i = 0; i < N; i++) {
    tft[i] = new Adafruit_ILI9341(TFT_CS[i], TFT_DC, -1);   // RST bersama -> 3V3
    tft[i]->begin();
    tft[i]->setRotation(0);
    drawTable(i);
    showStatus(i, ST_WAIT);
  }
  lcd.setCursor(0, 1); lcd.print("Konek WiFi...   ");
  WiFi.begin("Wokwi-GUEST", "", 6);
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  client.setInsecure(); http.setReuse(true); http.setTimeout(15000);
  Serial.println("\nWiFi OK");
}

void loop() {
  int kosong = 0; bool alarm = false; const char* who = "";
  for (int i = 0; i < N; i++) {
    String st = post(i, readCm(i));
    if (st == "detected") {
      if (since[i] == 0) since[i] = millis();
      lamp(i, 200, 140, 0); showStatus(i, ST_DETECTED);
      if (millis() - since[i] > GRACE_MS) { alarm = true; who = CODE[i] + 3; }
    } else {
      since[i] = 0;
      if (st == "occupied")       { lamp(i, 200, 20, 30); showStatus(i, ST_OCCUPIED); }
      else if (st == "available") { lamp(i, 0, 120, 40);  showStatus(i, ST_AVAILABLE); kosong++; }
      else                        { lamp(i, 0, 0, 0);     showStatus(i, ST_ERROR); }
    }
  }
  strip.show();
  char l1[17], l2[17];
  snprintf(l1, sizeof(l1), "%.3s %d/%d kosong   ", ZONA, kosong, N);
  snprintf(l2, sizeof(l2), "%-16s", alarm ? (String("SCAN QR: ") + who).c_str() : "Semua aman");
  lcd.setCursor(0, 0); lcd.print(l1); lcd.setCursor(0, 1); lcd.print(l2);
  if (alarm) for (int k = 0; k < 3; k++) { beep(150); delay(100); }
  delay(1000);
}
