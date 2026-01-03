# .sanchez Video Format

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

## Audio

Audio is stored as a separate `.mp3` file with the same name as the `.sanchez` file. When encoding from MP4, audio is automatically extracted. When decoding, audio is automatically detected and muxed if `ffmpeg` is available.

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
- `0xFF` END_STREAM - Stream termination

## Example

Run the example script to see the format in action:

```bash
python example.py
```

This creates a test pattern video, saves it as `.sanchez`, reads info, extracts a frame, and decodes it back to MP4.

---

*Get schwifty!* 🛸
