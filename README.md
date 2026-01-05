# .sanchez Video Format

> pip i sanchez==2.5.5 (only works on Python 3.13)
\n
**Interdimensional Cable Video Format** - A custom video format inspired by Rick & Morty

> "Nobody exists on purpose. Nobody belongs anywhere. Everybody's gonna die. Come watch TV." - Morty

## Overview

The `.sanchez` format is a simple, human-readable video/image format where each pixel is stored as RGB hex values. This implementation includes zlib compression to reduce file sizes from ~14.5MB per frame to typically <1MB per frame.

### Format Specification

```
Line 1: Metadata (JSON, one line)
Line 2: Config (WWWWHHHH + 7-digit frame count)
Line 3+: Frame data (compressed or hex pixels)
```

**Example:**
```
{"title":"MyVideo","creator":"cbx","created_at":"2026-01-02T01:30:43Z","seconds":"2.0"}
03200240000048
eJzLzklMT8...base64 compressed data...
```

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Also need ffmpeg for audio extraction/muxing either from website or;
# Windows: choco install ffmpeg / winget install ffmpeg
# Mac: brew install ffmpeg
# Linux: sudo apt install ffmpeg
```

## Usage

### Command Line

```bash
# Encode video to .sanchez
python -m sanchez encode video.mp4 output.sanchez

# Encode with resize
python -m sanchez encode video.mp4 -r 640x480

# Encode image to .sanchez
python -m sanchez encode image.png output.sanchez

# Decode .sanchez to MP4
python -m sanchez decode input.sanchez output.mp4

# Decode with audio
python -m sanchez decode input.sanchez -a audio.mp3

# Extract single frame
python -m sanchez decode input.sanchez -f 0 -o frame.png

# Extract all frames
python -m sanchez decode input.sanchez --frames

# Play .sanchez file
python -m sanchez play video.sanchez

# Show file info
python -m sanchez info video.sanchez
```

### Python API

```python
from sanchez import SanchezFile, SanchezEncoder, SanchezDecoder, SanchezPlayer

# Encode a video
encoder = SanchezEncoder()
encoder.encode("input.mp4", "output.sanchez", title="My Video", creator="cbx")

# Decode back to MP4
decoder = SanchezDecoder()
decoder.decode("output.sanchez", "decoded.mp4", audio_path="output.mp3")

# Play a .sanchez file
player = SanchezPlayer()
player.play("output.sanchez")

# Create .sanchez from scratch
import numpy as np

sanchez = SanchezFile.create("MyVideo", "cbx", width=320, height=240)
frame = np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
sanchez.add_frame(frame)
sanchez.save("custom.sanchez")

# Read .sanchez file
sanchez = SanchezFile.load("custom.sanchez")
for frame in sanchez.get_frames():
    # Process frame (numpy array)
    pass
```

## Player Controls

When playing with `python -m sanchez play`:

| Key | Action |
|-----|--------|
| Space | Pause/Resume |
| Left Arrow | Seek backward 5 seconds |
| Right Arrow | Seek forward 5 seconds |
| , | Previous frame (when paused) |
| . | Next frame (when paused) |
| R | Restart |
| I | Toggle info overlay |
| F | Toggle fullscreen |
| M | Mute/unmute audio |
| Q / Esc | Quit |

## Compression

The format uses zlib compression with base64 encoding to store frame data efficiently:

- **Uncompressed**: ~6.2 MB per 1920x1080 frame (raw RGB bytes)
- **Compressed**: Typically 0.5-2 MB per frame depending on content
- Compression ratio: 3-10x typical

For maximum compatibility with the original spec (hex per pixel), use `--no-compression` flag, but note this creates much larger files.

## File Structure

### Metadata (Line 1)
```json
{"title":"Example","creator":"cbx","created_at":"2026-01-02T01:30:43Z","seconds":"2.0"}
```

### Config (Line 2)
```
WWWWHHHH + FFFFFFF
```
- WWWW: Width (4 digits, zero-padded)
- HHHH: Height (4 digits, zero-padded)  
- FFFFFFF: Frame count (7 digits, zero-padded)

Example: `192010800000048` = 1920x1080, 48 frames

### Frame Data (Lines 3+)
Each line is one frame, either:
- **Compressed**: Base64-encoded zlib-compressed RGB bytes
- **Uncompressed**: `{RRGGBB,RRGGBB,...}` hex format

## 🔊 Audio Support

The `.sanchez` format stores video only - audio is kept as a separate `.mp3` file with the same base name. This separation allows for flexible audio handling and efficient streaming.

### How Audio Works

```
video.sanchez  ← Video frames (compressed RGB data)
video.mp3      ← Audio track (MP3 format)
```

### Encoding with Audio

When encoding from MP4 or other video formats, audio is automatically extracted:

```bash
# Audio automatically extracted to output.mp3
python -m sanchez encode video.mp4 output.sanchez

# Results in:
#   output.sanchez  (video)
#   output.mp3      (audio)
```

### Decoding with Audio

When decoding, audio is automatically detected and muxed back:

```bash
# Auto-detects input.mp3 and muxes it
python -m sanchez decode input.sanchez output.mp4

# Or specify audio explicitly
python -m sanchez decode input.sanchez output.mp4 -a custom_audio.mp3
```

### Playing with Audio

The player automatically finds and plays the matching `.mp3` file:

```bash
# Plays video.sanchez with video.mp3 audio
python -m sanchez play video.sanchez

# Or specify audio explicitly
python -m sanchez play video.sanchez -a other_audio.mp3
```

### Streaming with Audio

Audio is automatically streamed alongside video:

```bash
# Server auto-detects video.mp3 and streams it
python -m sanchez serve video.sanchez

# Or specify audio explicitly
python -m sanchez serve video.sanchez -a custom_audio.mp3

# Client receives both video and audio
python -m sanchez receive 192.168.1.100 9999

# Recording a stream saves both files
python -m sanchez receive 192.168.1.100 9999 -o recorded.sanchez
# Results in: recorded.sanchez + recorded.mp3
```

### Audio in Python API

```python
from sanchez import SanchezEncoder, SanchezDecoder, SanchezPlayer
from sanchez import SanchezStreamServer, SanchezStreamClient

# Encoding extracts audio automatically
encoder = SanchezEncoder()
sanchez_path, audio_path = encoder.encode("video.mp4", "output.sanchez")
print(f"Video: {sanchez_path}, Audio: {audio_path}")

# Decoding muxes audio back
decoder = SanchezDecoder()
decoder.decode("output.sanchez", "final.mp4", audio_path="output.mp3")

# Player handles audio automatically
player = SanchezPlayer()
player.play("output.sanchez")  # Finds output.mp3 automatically

# Streaming includes audio
server = SanchezStreamServer()
server.stream_file("video.sanchez", audio_path="video.mp3")  # Or auto-detect

# Client receives audio
client = SanchezStreamClient()
for frame_idx, frame_array in client.receive_stream("192.168.1.100", 9999):
    process_frame(frame_array)
# After stream ends:
if client.audio_data:
    with open("received.mp3", "wb") as f:
        f.write(client.audio_data)
```

### Why Separate Audio?

1. **Flexibility**: Use different audio tracks with the same video
2. **Streaming efficiency**: Audio can be buffered before playback starts
3. **Format simplicity**: Keeps `.sanchez` format focused on video
4. **Standard format**: MP3 is universally supported

## 📡 Streaming

The sanchez format supports video streaming over network and satellite connections!

### Streaming Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **TCP** | Reliable point-to-point | Local network, guaranteed delivery |
| **UDP** | Low-latency point-to-point | Direct connections, live streaming |
| **Multicast** | One-to-many broadcast | Satellite, IPTV, campus networks |
| **Broadcast** | Local network broadcast | LAN streaming, discovery |

### Command Line Streaming

```bash
# Start a TCP stream server
python -m sanchez serve video.sanchez

# Stream on specific port
python -m sanchez serve video.sanchez -p 8080

# UDP multicast for satellite/broadcast
python -m sanchez serve video.sanchez -m multicast -H 239.0.0.1

# Satellite mode with FEC and smaller packets
python -m sanchez serve video.sanchez -m multicast -H 239.0.0.1 --satellite --loop

# Receive and play a stream
python -m sanchez receive 192.168.1.100 9999

# Receive multicast stream
python -m sanchez receive 239.0.0.1 9999 -m multicast

# Record stream to file
python -m sanchez receive 192.168.1.100 9999 -o recorded.sanchez
```

### Python Streaming API

```python
from sanchez import (
    SanchezStreamServer, 
    SanchezStreamClient, 
    SanchezStreamPlayer,
    StreamMode
)

# Start a streaming server
server = SanchezStreamServer(mode=StreamMode.TCP_UNICAST)
server.stream_file("video.sanchez", host="0.0.0.0", port=9999, loop=True)

# For satellite/multicast streaming
server = SanchezStreamServer(mode=StreamMode.UDP_MULTICAST)
server.stream_file(
    "video.sanchez", 
    host="239.0.0.1",  # Multicast group
    port=9999,
    loop=True,
    satellite_mode=True  # Enables FEC and smaller packets
)

# Receive and process stream frames
client = SanchezStreamClient(mode=StreamMode.TCP_UNICAST)
for frame_idx, frame_array in client.receive_stream("192.168.1.100", 9999):
    # frame_array is a numpy RGB array
    process_frame(frame_array)

# Play stream directly
player = SanchezStreamPlayer(mode=StreamMode.UDP_MULTICAST)
player.play_stream("239.0.0.1", 9999)
```

### Satellite Features

The streaming module includes features designed for satellite/high-latency links:

- **Forward Error Correction (FEC)**: XOR-based parity packets to recover lost data
- **Smaller MTU-friendly packets**: 1400-byte chunks for satellite links
- **Sync packets**: Periodic timing beacons for receiver synchronization
- **CRC32 checksums**: Packet integrity verification
- **Sequence numbers**: Lost packet detection

### Streaming Protocol

The Sanchez streaming protocol uses a custom packet format:

```
┌─────────┬─────────┬──────┬──────┬───────────┬─────────────┬─────────┬──────────┐
│ MAGIC   │ VERSION │ TYPE │ SEQ  │ TIMESTAMP │ PAYLOAD_LEN │ PAYLOAD │ CHECKSUM │
│ 4 bytes │ 1 byte  │ 1 B  │ 4 B  │ 8 bytes   │ 4 bytes     │ N bytes │ 4 bytes  │
└─────────┴─────────┴──────┴──────┴───────────┴─────────────┴─────────┴──────────┘
```

Packet Types:
- `0x01` METADATA - Stream metadata (title, creator)
- `0x02` CONFIG - Video configuration (dimensions)
- `0x10` FRAME_START - Beginning of a frame
- `0x11` FRAME_CHUNK - Frame data chunk
- `0x12` FRAME_END - End of frame marker
- `0x20` SYNC - Synchronization heartbeat
- `0x30` FEC_DATA - Error correction parity
- `0x40` AUDIO_CONFIG - Audio format and size
- `0x41` AUDIO_CHUNK - Audio data chunk
- `0xFF` END_STREAM - Stream termination

## 🎬 Live Streaming

Stream live video feeds directly - cameras, screens, windows, or video files without pre-conversion!

### Interactive Feed Picker

Run without arguments to see a nice UI listing all available feeds:

```bash
python -m sanchez live
```

```
============================================================
  🎬 Sanchez Live Feed Selector
============================================================

  Discovering available feeds...

  📷 Cameras (2 found):
     [1] Camera 0 (1280x720)
     [2] Camera 1 (640x480)

  🖥️  Screens (3 found):
     [3] All Screens (3840x1080)
     [4] Screen 1 (1920x1080)
     [5] Screen 2 (1920x1080)

  🪟 Windows (5 found):
     [6] Visual Studio Code
     [7] Google Chrome
     [8] Discord
     ...

  [0] Enter video file path
  [q] Quit

------------------------------------------------------------
  Select feed number: _
```

### Command Line Live Streaming

```bash
# Stream a video file directly (no .sanchez conversion needed)
python -m sanchez live video.mp4

# Stream from camera (default: camera 0)
python -m sanchez live --camera
python -m sanchez live --camera 1

# Stream screen capture (default: all screens)
python -m sanchez live --screen
python -m sanchez live --screen 1

# Stream a specific window by title
python -m sanchez live --window "Visual Studio Code"

# With options
python -m sanchez live --camera -p 8080 --fps 30 -r 1280x720
python -m sanchez live video.mp4 -m multicast -H 239.0.0.1 --loop
```

### Live Streaming Options

| Option | Description |
|--------|-------------|
| `--camera [ID]` | Stream from camera device (default: 0) |
| `--screen [ID]` | Stream screen capture (default: 0 = all screens) |
| `--window TITLE` | Stream a specific window by title |
| `-H, --host` | Host/IP to stream to (default: 0.0.0.0) |
| `-p, --port` | Port number (default: 9999) |
| `-m, --mode` | tcp, udp, multicast, or broadcast |
| `--fps` | Frames per second (default: 24) |
| `-r, --resize` | Resize output (e.g., 1280x720) |
| `--loop` | Loop video files continuously |

### Python Live Streaming API

```python
from sanchez import (
    LiveStreamServer,
    FeedCapture,
    FeedDiscovery,
    VideoFeed,
    FeedType,
    interactive_feed_picker,
    StreamMode
)

# Discover available feeds
feeds = FeedDiscovery.discover_all()
print(f"Cameras: {feeds['cameras']}")
print(f"Screens: {feeds['screens']}")
print(f"Windows: {feeds['windows']}")

# Stream from camera
from sanchez import stream_camera
stream_camera(device_id=0, host="0.0.0.0", port=9999, fps=24)

# Stream screen capture
from sanchez import stream_screen
stream_screen(monitor_id=0, host="0.0.0.0", port=9999, fps=15)

# Stream video file directly
from sanchez import stream_video_file
stream_video_file("video.mp4", host="0.0.0.0", port=9999, loop=True)

# Custom feed handling
feed = VideoFeed(
    feed_type=FeedType.CAMERA,
    name="Webcam",
    description="USB Camera",
    device_id=0
)

capture = FeedCapture(feed, fps=24)
with capture:
    for frame in capture.frames():
        # Process each frame (numpy RGB array)
        process_frame(frame)
```

## 📺 TV Channels & Playlists

Stream multiple videos sequentially like a TV channel! Mix `.sanchez` and `.mp4` files in playlists for continuous streaming.

### Channel Guide (Receiver Side)

Save your favorite channels and quickly tune in with an interactive selector!

#### Managing Channels

```bash
# Add a channel
python -m sanchez channels add "Rick's TV" 192.168.1.100 9999

# Add a multicast/satellite channel
python -m sanchez channels add "Satellite TV" 239.0.0.1 9999 -m multicast

# Add with description and mark as favorite
python -m sanchez channels add "Local News" 192.168.1.50 8080 -d "Morning news" -f

# List all saved channels
python -m sanchez channels list

# Remove a channel
python -m sanchez channels remove "Rick's TV"

# Toggle favorite status
python -m sanchez channels favorite "Satellite TV"
```

#### Watching Channels

```bash
# Interactive channel selector (with arrow key navigation!)
python -m sanchez watch

# Watch by channel name
python -m sanchez watch "Rick's TV"

# Watch by channel number
python -m sanchez watch 1

# Watch in fullscreen
python -m sanchez watch "Rick's TV" --fullscreen

# Record a channel to file
python -m sanchez watch "Rick's TV" -o recording.sanchez
```

#### Interactive Channel Selector

Run `python -m sanchez watch` to get a nice interactive UI:

```
============================================================
  📺 Sanchez Channel Guide
============================================================

  ▶ [1] ⭐ 📺 Rick's TV                192.168.1.100:9999 (tcp)
    [2] ⭐ 📺 Satellite Feed           239.0.0.1:9999 (multicast)
    [3]    🔗 Local Server             localhost:9999 (tcp)
    [4]    📡 UDP Stream               10.0.0.5:8080 (udp)

------------------------------------------------------------
  ↑/↓  Navigate   |  Enter  Select  |  0-9  Channel #
  Q    Quit       |  A      Add New |  F    Toggle Favorite
============================================================
```

**3-Digit Channel Entry:**

When you press number keys, a channel input overlay appears in the bottom-right:

```
                                        ┌─────────────┐
                                        │  CH: 12_   │
                                        │  ██████░░░░  │
                                        └─────────────┘
```

- Type up to **3 digits** to enter a channel number (supports channels 1-999)
- A **countdown bar** shows time remaining before auto-tuning
- After **2 seconds** of no input, automatically tunes to that channel
- If you enter 3 digits, it tunes **immediately**
- Press **Backspace** to correct mistakes
- The overlay disappears after tuning

**Navigation:**
- Use **↑/↓ arrow keys** to navigate
- Press **Enter** to watch the selected channel
- Press **0-9** to enter channel numbers (with overlay)
- Press **F** to toggle favorite (favorites appear first with ⭐)
- Press **Q** to quit

#### Python Channel Guide API

```python
from sanchez import ChannelGuide, SavedChannel, interactive_channel_selector

# Create/load channel guide
guide = ChannelGuide()

# Add a channel
channel = SavedChannel(
    name="Rick's TV",
    host="192.168.1.100",
    port=9999,
    mode="tcp",
    description="Interdimensional Cable",
    favorite=True
)
guide.add(channel)

# List channels
for ch in guide.list_channels():
    print(f"{ch.name}: {ch.connection_string()}")

# Get channel by name or number
ch = guide.get("Rick's TV")
ch = guide.get_by_index(1)

# Interactive selector
selected = interactive_channel_selector()
if selected:
    print(f"Tuning to: {selected.name}")
```

### Playlist Formats

The channel feature supports multiple playlist formats:

| Format | Extension | Description |
|--------|-----------|-------------|
| **M3U** | `.m3u` | Standard playlist format (media players compatible) |
| **JSON** | `.json` | Structured playlist with metadata |
| **Text** | `.txt` | Simple list of file paths (one per line) |
| **PLS** | `.pls` | Winamp-style playlist format |

### Creating Playlists

**M3U Format** (`playlist.m3u`):
```m3u
#EXTM3U
#EXTINF:-1,Episode 1 - Pilot
/videos/episode1.sanchez
#EXTINF:-1,Episode 2 - Ricksy Business
/videos/episode2.mp4
#EXTINF:-1,Interdimensional Cable
/videos/cable.sanchez
```

**JSON Format** (`playlist.json`):
```json
{
  "name": "Rick's TV Channel",
  "mode": "shuffle_repeat",
  "items": [
    {"path": "/videos/episode1.sanchez", "name": "Pilot"},
    {"path": "/videos/episode2.mp4", "name": "Ricksy Business"},
    {"path": "/videos/cable.sanchez", "name": "Interdimensional Cable"}
  ]
}
```

**Text Format** (`playlist.txt`):
```
/videos/episode1.sanchez
/videos/episode2.mp4
/videos/cable.sanchez
```

### Playlist Modes

| Mode | Description |
|------|-------------|
| `sequential` | Play videos in order, then stop (default) |
| `shuffle` | Randomize order, play once |
| `repeat_one` | Loop the current video forever |
| `repeat_all` | Loop the entire playlist forever |
| `shuffle_repeat` | Shuffle and repeat forever |

### Command Line Channel Streaming

```bash
# Stream a playlist file
python -m sanchez channel --playlist videos.m3u

# Stream multiple video files directly
python -m sanchez channel video1.sanchez video2.mp4 video3.sanchez

# Shuffle mode
python -m sanchez channel --playlist tv.m3u --shuffle

# Repeat all videos forever
python -m sanchez channel --playlist tv.m3u --playlist-mode repeat_all

# Shuffle and repeat forever (TV station mode!)
python -m sanchez channel --playlist tv.m3u --playlist-mode shuffle_repeat

# Named channel with multicast
python -m sanchez channel --playlist tv.m3u -n "Rick's TV" -m multicast -H 239.0.0.1

# Stream all .sanchez files in a folder
python -m sanchez channel *.sanchez --playlist-mode repeat_all

# With channel text overlay
python -m sanchez channel --playlist tv.m3u --overlay "SPORTS TV" --overlay-position top-left

# Per-video text overlays (e.g., show "LIVE" for sports videos)
python -m sanchez channel *.sanchez --video-overlays "sports*.mp4:LIVE SPORTS" "news*.sanchez:BREAKING NEWS"

# Custom styling
python -m sanchez channel --playlist tv.m3u --overlay "MY CHANNEL" \
    --overlay-position top-right --overlay-opacity 0.9 \
    --overlay-size 32 --overlay-color "255,0,0"

# Dynamic queue - add videos while streaming
python -m sanchez channel --playlist tv.m3u --queue-file queue.txt
# Then add videos by appending paths to queue.txt
```

### Channel Options

| Option | Description |
|--------|-------------|
| `--playlist, -P` | Path to playlist file (.m3u, .json, .txt, .pls) |
| `-n, --name` | Channel name (displayed in console) |
| `--shuffle` | Shuffle playlist order |
| `--playlist-mode` | sequential, shuffle, repeat_one, repeat_all, shuffle_repeat |
| `-H, --host` | Host/IP to stream to (default: 0.0.0.0) |
| `-p, --port` | Port number (default: 9999) |
| `-m, --mode` | tcp, udp, multicast, or broadcast |
| `--fps` | Frames per second for .mp4 conversion (default: 24) |
| `-r, --resize` | Resize all videos (e.g., 1280x720) |
| `-o, --overlay` | Text overlay for channel branding |
| `--overlay-position` | Position: top-left, top-right, bottom-left, bottom-right, center, top-center, bottom-center |
| `--overlay-opacity` | Text opacity 0.0-1.0 (default: 0.8) |
| `--overlay-size` | Font size in pixels (default: 24) |
| `--overlay-color` | RGB color as R,G,B (default: 255,255,255) |
| `--video-overlays` | Per-video text overlays (pattern:text format) |
| `-l, --logo` | PNG logo overlay (supports transparency) |
| `--logo-position` | Logo position (default: top-left) |
| `--logo-opacity` | Logo opacity 0.0-1.0 (default: 0.8) |
| `--logo-scale` | Logo scale factor (default: 1.0) |
| `--video-logos` | Per-video PNG logos (pattern:path format) |
| `-q, --queue-file` | File to watch for adding videos to queue |

### 📝 Dynamic Text Overlays

Add dynamic text overlays to your streams - change text, position, and style while streaming!

**CLI Examples:**

```bash
# Simple channel branding
python -m sanchez channel --playlist tv.m3u --overlay "MY CHANNEL"

# Sports channel with custom position and color
python -m sanchez channel sports/*.mp4 --overlay "SPORTS TV" \
    --overlay-position top-right --overlay-color "255,255,0" --overlay-size 28

# Per-video overlays (different text for different content)
python -m sanchez channel --playlist mixed.m3u \
    --overlay "NEWS 24/7" \
    --video-overlays "sports*.mp4:LIVE SPORTS" "weather*.mp4:WEATHER UPDATE"
```

**Python API - Full Control:**

```python
from sanchez import ChannelServer, Playlist, OverlayManager

# Create a channel server with text overlays
server = ChannelServer()

# Set main channel overlay
server.set_overlay("SPORTS TV", position="top-left", font_size=28, color=(255, 255, 0))

# Add additional overlays (score, status, etc.)
server.add_overlay("score", "HOME 0 - 0 AWAY", position="top-center", font_size=24)
server.add_overlay("status", "LIVE", position="top-right", color=(255, 0, 0))

# Set per-video overlays
server.set_video_overlay("halftime*.mp4", "HALFTIME", position="center")

# Stream the playlist
playlist = Playlist.load("games.m3u")
server.stream_playlist(playlist, host="0.0.0.0", port=9999)
```

**Dynamic Text Updates (during streaming):**

```python
import threading
import time

# Start streaming in background
def stream():
    server.stream_playlist(playlist)

thread = threading.Thread(target=stream)
thread.start()

# Update overlays dynamically while streaming!
time.sleep(60)
server.set_text("score", "HOME 1 - 0 AWAY")  # Update score

time.sleep(300)
server.set_text("status", "2ND HALF")  # Update status

time.sleep(600)
server.set_default_text("SPORTS TV - GOAL!")  # Flash message on main overlay
```

**Advanced OverlayManager:**

```python
from sanchez import OverlayManager

# Create overlay manager for fine-grained control
manager = OverlayManager()

# Add multiple overlays
manager.add_overlay("channel", "ESPN", position="top-left", font_size=32)
manager.add_overlay("ticker", "Breaking: Big game tonight!", position="bottom-center", font_size=18)
manager.add_overlay("time", "LIVE", position="top-right", color=(255, 0, 0))

# Update text dynamically
manager.set_text("ticker", "Score update: Home leads 2-1")
manager.set_position("ticker", "bottom-left")
manager.set_color("time", (0, 255, 0))  # Change to green

# Remove an overlay
manager.remove_overlay("ticker")

# Apply to frames manually
frame = manager.apply(frame)
```

### �️ PNG Logo Overlays

Add transparent PNG logos to your streams - perfect for channel branding with professional graphics!

**CLI Examples:**

```bash
# Simple channel logo (top-left corner)
python -m sanchez channel --playlist tv.m3u --logo "logo.png"

# Logo with custom position and opacity
python -m sanchez channel sports/*.mp4 --logo "espn_logo.png" \
    --logo-position top-right --logo-opacity 0.9 --logo-scale 0.5

# Combine text overlay AND logo
python -m sanchez channel --playlist news.m3u \
    --logo "news_logo.png" --logo-position top-left \
    --overlay "BREAKING NEWS" --overlay-position bottom-center

# Per-video logos (different logos for different content)
python -m sanchez channel --playlist mixed.m3u \
    --logo "main_logo.png" \
    --video-logos "sports*.mp4:sports_logo.png" "news*.mp4:news_logo.png"
```

**Python API - Full Control:**

```python
from sanchez import ChannelServer, Playlist, ImageOverlay

# Create a channel server with PNG logo
server = ChannelServer()

# Set main channel logo
server.add_logo("logo.png", position="top-left", opacity=0.9, scale=0.5)

# Add per-video logos (different logos for different content)
server.add_video_logo("sports*.mp4", "sports_logo.png")
server.add_video_logo("news*.mp4", "news_logo.png")

# Combine with text overlays
server.set_overlay("LIVE", position="top-right", color=(255, 0, 0))

# Stream the playlist
playlist = Playlist.load("channel.m3u")
server.stream_playlist(playlist, host="0.0.0.0", port=9999)
```

**ImageOverlay Direct Usage:**

```python
from sanchez import ImageOverlay, OverlayManager

# Create image overlay directly
logo = ImageOverlay(
    image_path="logo.png",
    position="top-left",
    opacity=0.8,
    scale=0.5
)

# Load the image
logo.load()

# Add to overlay manager
manager = OverlayManager()
manager.add_image("channel_logo", logo)

# Apply to frames
frame = manager.apply(frame)
```

**Supported Image Formats:**
- PNG (recommended - supports transparency)
- JPEG, JPG (no transparency)
- BMP, WEBP, and other formats supported by PIL/OpenCV

**Tips:**
- Use PNG with transparency for professional-looking overlays
- Scale down large logos for better performance
- Combine multiple logos and text overlays for rich branding
- Use per-video logos to match content (sports logo for sports, news logo for news, etc.)

### �📥 Dynamic Queue Management

Add, skip, and change videos while the channel is streaming - perfect for live TV stations!

**Queue File Method:**

```bash
# Start streaming with queue file watching
python -m sanchez channel --playlist initial.m3u --queue-file queue.txt

# In another terminal, add videos to the queue:
echo "/path/to/new_video.mp4" >> queue.txt
echo "/path/to/another.sanchez" >> queue.txt
```

**Python Queue API:**

```python
from sanchez import Playlist, ChannelServer
import threading

# Create playlist
playlist = Playlist.load("initial.m3u")

# Watch a file for new videos
playlist.watch_queue_file("queue.txt")

# Add videos programmatically (thread-safe)
playlist.add("/path/to/new_video.mp4")  # Add to end of queue
playlist.add_next("/path/to/priority.mp4")  # Play next (after current video)

# Control playback
playlist.skip_current()  # Skip to next video immediately
playlist.jump_to(5)  # Jump to video at index 5
playlist.jump_to_title("Breaking News")  # Jump to video by title (partial match)
playlist.replace_current("/path/to/replacement.mp4")  # Replace currently playing
playlist.insert_and_play("/path/to/urgent.mp4")  # Insert and immediately play

# Query the queue
upcoming = playlist.get_queue()  # Get list of upcoming videos
playlist.clear_queue()  # Clear all videos after current one

threading.Thread(target=add_video_later).start()

# Start streaming
server = ChannelServer()
server.stream_playlist(playlist)
```

### Python Channel API

```python
from sanchez import (
    Playlist,
    PlaylistItem,
    PlaylistMode,
    ChannelServer,
    create_channel,
    stream_channel,
    StreamMode
)

# Create a playlist from files
playlist = create_channel([
    "episode1.sanchez",
    "episode2.mp4",
    "episode3.sanchez"
], name="My Channel", mode=PlaylistMode.SHUFFLE_REPEAT)

# Or load from file
playlist = Playlist.from_file("tv.m3u")
playlist.mode = PlaylistMode.REPEAT_ALL

# Stream the channel
server = ChannelServer(mode=StreamMode.TCP_UNICAST)
server.stream_channel(playlist, host="0.0.0.0", port=9999)

# Multicast for satellite/IPTV
server = ChannelServer(mode=StreamMode.UDP_MULTICAST)
server.stream_channel(playlist, host="239.0.0.1", port=9999)

# Quick stream helper
stream_channel(
    ["video1.sanchez", "video2.mp4"],
    host="0.0.0.0",
    port=9999,
    mode=PlaylistMode.REPEAT_ALL
)

# Access playlist items
for item in playlist.items:
    print(f"{item.name}: {item.path} ({item.file_type})")

# Shuffle playlist
playlist.shuffle()

# Get next video (respects mode)
while True:
    item = playlist.get_next()
    if item is None:
        break  # End of sequential playlist
    print(f"Now playing: {item.name}")
```

### Receiving Channel Streams

Clients don't need to know about playlists - they just receive a continuous stream:

```bash
# Receive and play the channel
python -m sanchez receive 192.168.1.100 9999

# Record the stream (captures all videos as one)
python -m sanchez receive 192.168.1.100 9999 -o recording.sanchez
```

### Example: 24/7 TV Station

Set up a continuous TV channel streaming all your `.sanchez` files:

```bash
# Create a playlist of all videos
ls *.sanchez > channel.txt

# Or create an M3U with nice names
cat > channel.m3u << EOF
#EXTM3U
#EXTINF:-1,Episode 1
episode1.sanchez
#EXTINF:-1,Episode 2
episode2.sanchez
#EXTINF:-1,Interdimensional Cable
cable.sanchez
EOF

# Start the 24/7 channel
python -m sanchez channel --playlist channel.m3u \
    --playlist-mode shuffle_repeat \
    -n "Interdimensional Cable TV" \
    -m multicast -H 239.0.0.1
```

## Example

Run the example script to see the format in action:

```bash
python example.py
```

This creates a test pattern video, saves it as `.sanchez`, reads info, extracts a frame, and decodes it back to MP4.

---

*Get schwifty!* 🛸
