#!/usr/bin/env bash
# ==============================================================================
# MICRO-DIPLOMACY: 24/7 TWITCH BROADCAST SCRIPT
# Captures the spectator web UI and streams to Twitch via RTMP
# ==============================================================================

export TWITCH_STREAM_KEY="live_YOUR_TWITCH_KEY_HERE"
export SPECTATOR_URL="http://localhost:8000/spectator.html"

# 1. Start a virtual audio server (PulseAudio) so FFmpeg can hear ElevenLabs
pulseaudio -D --exit-idle-time=-1
pacmd load-module module-virtual-sink sink_name=v1

# 2. Start a virtual display (Xvfb) at 1080p
Xvfb :99 -screen 0 1920x1080x24 &
export DISPLAY=:99

# 3. Launch Headless Chrome in full-screen on the virtual display
chromium-browser \
  --kiosk \
  --no-sandbox \
  --disable-gpu \
  --autoplay-policy=no-user-gesture-required \
  --window-size=1920,1080 \
  "$SPECTATOR_URL" &

# 4. Capture the virtual screen and audio, then push to Twitch via FFmpeg
ffmpeg -y \
  -f x11grab -s 1920x1080 -framerate 30 -i :99.0 \
  -f pulse -i v1.monitor \
  -c:v libx264 -preset veryfast -b:v 3000k -maxrate 3000k -bufsize 6000k -pix_fmt yuv420p -g 60 \
  -c:a aac -b:a 160k -ar 44100 \
  -f flv "rtmp://live.twitch.tv/app/$TWITCH_STREAM_KEY"
