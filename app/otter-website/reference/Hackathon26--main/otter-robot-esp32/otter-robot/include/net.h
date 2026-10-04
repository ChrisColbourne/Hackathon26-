#pragma once
#include <stddef.h>
namespace net {
typedef void (*Handler)(const char* json, size_t len);
void begin(Handler onMessage, void (*onDisconnect)());
void loop();
void send(const char* json);
}
