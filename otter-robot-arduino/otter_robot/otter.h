#pragma once
namespace otter {
void begin();
void setMood(const char* state);  // idle, listening, thinking, talking, happy, confused
void setMouth(float level);       // 0..1, sent while ElevenLabs audio plays
void update();                    // call every loop
}
