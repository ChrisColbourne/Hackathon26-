#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include "config.h"
#include "net.h"

namespace net {
static WebSocketsClient ws;
static Handler handler = nullptr;
static void (*lost)() = nullptr;

static void onEvent(WStype_t type, uint8_t* payload, size_t len) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.println("[net] connected to server");
      ws.sendTXT("{\"status\":\"ready\"}");
      break;
    case WStype_DISCONNECTED:
      Serial.println("[net] disconnected");
      if (lost) lost();
      break;
    case WStype_TEXT:
      if (handler) handler((const char*)payload, len);
      break;
    default: break;
  }
}

void begin(Handler h, void (*onDisconnect)()) {
  handler = h; lost = onDisconnect;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("[net] joining %s", WIFI_SSID);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) { delay(300); Serial.print("."); }
  Serial.printf("\n[net] wifi %s, ip %s\n", WiFi.status() == WL_CONNECTED ? "ok" : "FAILED",
                WiFi.localIP().toString().c_str());
  ws.begin(SERVER_HOST, SERVER_PORT, SERVER_PATH);
  ws.onEvent(onEvent);
  ws.setReconnectInterval(2000);
}

void loop() { ws.loop(); }
void send(const char* json) { ws.sendTXT(json); Serial.printf("[tx] %s\n", json); }
}
