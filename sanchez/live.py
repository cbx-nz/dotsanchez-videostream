"""
Sanchez Live Streaming Module - Stream live video feeds

Supports:
- MP4/video file streaming (without pre-conversion to .sanchez)
- Webcam/camera feeds
- Screen capture (full screen or region)
- Application/window capture

Uses OpenCV for camera capture and mss for screen capture.
"""

import sys
import time
import threading
from pathlib import Path
from typing import Optional, Callable, List, Tuple, Generator, Dict, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False


class FeedType(Enum):
    """Types of video feeds"""
    VIDEO_FILE = "video"
    CAMERA = "camera"
    SCREEN = "screen"
    WINDOW = "window"


@dataclass
class VideoFeed:
    """Represents a video feed source"""
    feed_type: FeedType
    name: str
    description: str
    device_id: Optional[int] = None  # For cameras
    file_path: Optional[str] = None  # For video files
    monitor_id: Optional[int] = None  # For screen capture
    window_title: Optional[str] = None  # For window capture
    resolution: Optional[Tuple[int, int]] = None  # (width, height)
    
    def __str__(self) -> str:
        res_str = f" ({self.resolution[0]}x{self.resolution[1]})" if self.resolution else ""
        return f"{self.name}{res_str}"


class FeedDiscovery:
    """Discover available video feeds on the system"""
    
    @staticmethod
    def find_cameras(max_cameras: int = 10) -> List[VideoFeed]:
        """Find available camera devices"""
        if not CV2_AVAILABLE:
            return []
        
        cameras = []
        for i in range(max_cameras):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if sys.platform == 'win32' else cv2.CAP_ANY)
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cameras.append(VideoFeed(
                    feed_type=FeedType.CAMERA,
                    name=f"Camera {i}",
                    description=f"Video capture device {i}",
                    device_id=i,
                    resolution=(width, height)
                ))
                cap.release()
            else:
                cap.release()
                # Don't break - there might be gaps in device IDs
        
        return cameras
    
    @staticmethod
    def find_screens() -> List[VideoFeed]:
        """Find available screens/monitors"""
        if not MSS_AVAILABLE:
            return []
        
        screens = []
        with mss.mss() as sct:
            for i, monitor in enumerate(sct.monitors):
                if i == 0:
                    # Monitor 0 is "all monitors combined"
                    name = "All Screens"
                    desc = "Capture all monitors combined"
                else:
                    name = f"Screen {i}"
                    desc = f"Monitor {i}"
                
                screens.append(VideoFeed(
                    feed_type=FeedType.SCREEN,
                    name=name,
                    description=desc,
                    monitor_id=i,
                    resolution=(monitor['width'], monitor['height'])
                ))
        
        return screens
    
    @staticmethod
    def find_windows() -> List[VideoFeed]:
        """Find available application windows (Windows only for now)"""
        windows = []
        
        if sys.platform == 'win32':
            try:
                import ctypes
                from ctypes import wintypes
                
                user32 = ctypes.windll.user32
                
                # Callback for EnumWindows
                EnumWindowsProc = ctypes.WINFUNCTYPE(
                    ctypes.c_bool, 
                    wintypes.HWND, 
                    wintypes.LPARAM
                )
                
                def enum_callback(hwnd, lParam):
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buff, length + 1)
                            title = buff.value
                            
                            # Skip certain system windows
                            skip_titles = ['Program Manager', 'Settings', 'Microsoft Text Input']
                            if title and not any(skip in title for skip in skip_titles):
                                # Get window dimensions
                                rect = wintypes.RECT()
                                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                                width = rect.right - rect.left
                                height = rect.bottom - rect.top
                                
                                if width > 100 and height > 100:  # Skip tiny windows
                                    windows.append(VideoFeed(
                                        feed_type=FeedType.WINDOW,
                                        name=title[:50] + ('...' if len(title) > 50 else ''),
                                        description=f"Window: {title}",
                                        window_title=title,
                                        resolution=(width, height)
                                    ))
                    return True
                
                user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
                
            except Exception as e:
                print(f"Window enumeration error: {e}")
        
        return windows
    
    @classmethod
    def discover_all(cls) -> Dict[str, List[VideoFeed]]:
        """Discover all available feeds"""
        return {
            'cameras': cls.find_cameras(),
            'screens': cls.find_screens(),
            'windows': cls.find_windows()
        }


class FeedCapture:
    """Capture frames from various video sources"""
    
    def __init__(self, feed: VideoFeed, fps: int = 24):
        self.feed = feed
        self.fps = fps
        self.running = False
        self._cap = None
        self._sct = None
    
    def open(self) -> bool:
        """Open the feed for capture"""
        if self.feed.feed_type == FeedType.VIDEO_FILE:
            if not CV2_AVAILABLE:
                raise ImportError("OpenCV required for video file capture")
            self._cap = cv2.VideoCapture(self.feed.file_path)
            return self._cap.isOpened()
        
        elif self.feed.feed_type == FeedType.CAMERA:
            if not CV2_AVAILABLE:
                raise ImportError("OpenCV required for camera capture")
            backend = cv2.CAP_DSHOW if sys.platform == 'win32' else cv2.CAP_ANY
            self._cap = cv2.VideoCapture(self.feed.device_id, backend)
            if self._cap.isOpened():
                # Try to set higher resolution
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self._cap.set(cv2.CAP_PROP_FPS, self.fps)
            return self._cap.isOpened()
        
        elif self.feed.feed_type == FeedType.SCREEN:
            if not MSS_AVAILABLE:
                raise ImportError("mss required for screen capture. Install with: pip install mss")
            self._sct = mss.mss()
            return True
        
        elif self.feed.feed_type == FeedType.WINDOW:
            # Window capture uses screen capture with region
            if not MSS_AVAILABLE:
                raise ImportError("mss required for window capture. Install with: pip install mss")
            self._sct = mss.mss()
            return True
        
        return False
    
    def read_frame(self) -> Optional[np.ndarray]:
        """Read a single frame from the feed"""
        if self.feed.feed_type in (FeedType.VIDEO_FILE, FeedType.CAMERA):
            if self._cap is None or not self._cap.isOpened():
                return None
            ret, frame = self._cap.read()
            if ret:
                # Convert BGR to RGB
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return None
        
        elif self.feed.feed_type == FeedType.SCREEN:
            if self._sct is None:
                return None
            monitor = self._sct.monitors[self.feed.monitor_id]
            screenshot = self._sct.grab(monitor)
            # Convert BGRA to RGB
            frame = np.array(screenshot)
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        
        elif self.feed.feed_type == FeedType.WINDOW:
            if self._sct is None:
                return None
            
            # Get window position
            region = self._get_window_region()
            if region is None:
                return None
            
            screenshot = self._sct.grab(region)
            frame = np.array(screenshot)
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        
        return None
    
    def _get_window_region(self) -> Optional[Dict]:
        """Get the region of the target window"""
        if sys.platform == 'win32':
            try:
                import ctypes
                from ctypes import wintypes
                
                user32 = ctypes.windll.user32
                
                # Find window by title
                hwnd = user32.FindWindowW(None, self.feed.window_title)
                if not hwnd:
                    # Try partial match
                    EnumWindowsProc = ctypes.WINFUNCTYPE(
                        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
                    )
                    found_hwnd = [None]
                    
                    def find_callback(h, lParam):
                        length = user32.GetWindowTextLengthW(h)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(h, buff, length + 1)
                            if self.feed.window_title in buff.value:
                                found_hwnd[0] = h
                                return False
                        return True
                    
                    user32.EnumWindows(EnumWindowsProc(find_callback), 0)
                    hwnd = found_hwnd[0]
                
                if hwnd:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    return {
                        'left': rect.left,
                        'top': rect.top,
                        'width': rect.right - rect.left,
                        'height': rect.bottom - rect.top
                    }
            except Exception:
                pass
        
        return None
    
    def frames(self, max_frames: Optional[int] = None) -> Generator[np.ndarray, None, None]:
        """Generate frames from the feed"""
        self.running = True
        frame_count = 0
        frame_interval = 1.0 / self.fps
        
        while self.running:
            start_time = time.time()
            
            frame = self.read_frame()
            if frame is None:
                if self.feed.feed_type == FeedType.VIDEO_FILE:
                    # End of video file
                    break
                continue
            
            yield frame
            frame_count += 1
            
            if max_frames and frame_count >= max_frames:
                break
            
            # Maintain frame rate
            elapsed = time.time() - start_time
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.running = False
    
    def close(self):
        """Close the feed"""
        self.running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._sct is not None:
            self._sct.close()
            self._sct = None
    
    def __enter__(self):
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class LiveStreamServer:
    """Stream live video feeds over network"""
    
    def __init__(self, mode=None):
        # Import here to avoid circular imports
        from .streaming import StreamMode, SanchezStreamServer
        
        self.mode = mode or StreamMode.TCP_UNICAST
        self._server = SanchezStreamServer(mode=self.mode)
        self.running = False
    
    def stream_feed(
        self,
        feed: VideoFeed,
        host: str = "0.0.0.0",
        port: int = 9999,
        fps: int = 24,
        resize: Optional[Tuple[int, int]] = None,
        quality: int = 80
    ) -> None:
        """
        Stream a live feed over network.
        
        Args:
            feed: VideoFeed to stream
            host: Host to bind/stream to
            port: Port number
            fps: Target frames per second
            resize: Optional (width, height) to resize frames
            quality: JPEG quality for compression (1-100)
        """
        from .streaming import StreamPacket, PacketType, StreamMode
        from .format import SanchezMetadata, SanchezConfig, FrameCompressor
        import socket
        import struct
        
        capture = FeedCapture(feed, fps=fps)
        
        if not capture.open():
            raise RuntimeError(f"Failed to open feed: {feed.name}")
        
        print(f"\n📡 Sanchez Live Stream Server")
        print(f"   Feed: {feed.name}")
        print(f"   Type: {feed.feed_type.value}")
        print(f"   FPS: {fps}")
        print(f"   Mode: {self.mode.name}")
        print(f"   Address: {host}:{port}")
        print(f"\n   Press Ctrl+C to stop\n")
        
        compressor = FrameCompressor()
        
        # Create socket
        sock = self._server._create_socket()
        self._server.socket = sock
        addr = (host, port)
        
        if self.mode == StreamMode.TCP_UNICAST:
            sock.bind(addr)
            sock.listen(5)
            self._stream_tcp(capture, sock, compressor, fps, resize)
        else:
            sock.bind(('0.0.0.0', port + 1))
            self._stream_udp(capture, sock, addr, compressor, fps, resize)
        
        capture.close()
    
    def _stream_tcp(self, capture, sock, compressor, fps, resize):
        """Stream over TCP to connected clients"""
        from .streaming import StreamPacket, PacketType
        import struct
        
        self.running = True
        clients = []
        
        def handle_client(client_sock, client_addr):
            print(f"Client connected: {client_addr}")
            clients.append(client_sock)
        
        # Accept connections in background
        sock.settimeout(0.1)
        
        def accept_loop():
            while self.running:
                try:
                    client_sock, client_addr = sock.accept()
                    handle_client(client_sock, client_addr)
                except socket.timeout:
                    continue
                except:
                    break
        
        import socket
        accept_thread = threading.Thread(target=accept_loop)
        accept_thread.daemon = True
        accept_thread.start()
        
        frame_idx = 0
        seq = 0
        
        try:
            # Send initial metadata/config when first client connects
            metadata_sent = set()
            
            for frame in capture.frames():
                if resize:
                    frame = cv2.resize(frame, resize)
                
                height, width = frame.shape[:2]
                
                # Compress frame
                compressed = compressor.compress_frame(frame)
                frame_data = compressed.encode('utf-8')
                
                # Send to all clients
                for client in clients[:]:
                    try:
                        # Send metadata/config if new client
                        if id(client) not in metadata_sent:
                            # Metadata
                            meta = f'{{"title":"Live: {capture.feed.name}","creator":"sanchez","created_at":"","seconds":"0"}}'
                            meta_pkt = StreamPacket(
                                packet_type=PacketType.METADATA,
                                sequence=seq,
                                timestamp=int(time.time() * 1_000_000),
                                payload=meta.encode()
                            )
                            seq += 1
                            data = meta_pkt.serialize()
                            client.sendall(struct.pack('>I', len(data)) + data)
                            
                            # Config
                            config = f"{width:04d}{height:04d}9999999"
                            config_pkt = StreamPacket(
                                packet_type=PacketType.CONFIG,
                                sequence=seq,
                                timestamp=int(time.time() * 1_000_000),
                                payload=config.encode()
                            )
                            seq += 1
                            data = config_pkt.serialize()
                            client.sendall(struct.pack('>I', len(data)) + data)
                            
                            metadata_sent.add(id(client))
                        
                        # Frame start
                        start_pkt = StreamPacket(
                            packet_type=PacketType.FRAME_START,
                            sequence=seq,
                            timestamp=int(time.time() * 1_000_000),
                            payload=struct.pack('>II', frame_idx, len(frame_data))
                        )
                        seq += 1
                        data = start_pkt.serialize()
                        client.sendall(struct.pack('>I', len(data)) + data)
                        
                        # Frame chunks
                        chunk_size = 8192
                        for chunk_idx in range((len(frame_data) + chunk_size - 1) // chunk_size):
                            offset = chunk_idx * chunk_size
                            chunk = frame_data[offset:offset + chunk_size]
                            
                            chunk_pkt = StreamPacket(
                                packet_type=PacketType.FRAME_CHUNK,
                                sequence=seq,
                                timestamp=int(time.time() * 1_000_000),
                                payload=struct.pack('>II', frame_idx, chunk_idx) + chunk
                            )
                            seq += 1
                            data = chunk_pkt.serialize()
                            client.sendall(struct.pack('>I', len(data)) + data)
                        
                        # Frame end
                        end_pkt = StreamPacket(
                            packet_type=PacketType.FRAME_END,
                            sequence=seq,
                            timestamp=int(time.time() * 1_000_000),
                            payload=struct.pack('>I', frame_idx)
                        )
                        seq += 1
                        data = end_pkt.serialize()
                        client.sendall(struct.pack('>I', len(data)) + data)
                        
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        clients.remove(client)
                        print(f"Client disconnected")
                
                frame_idx += 1
                if frame_idx % fps == 0:
                    print(f"\r   Streaming: {frame_idx} frames, {len(clients)} clients", end='', flush=True)
        
        except KeyboardInterrupt:
            print("\n\n   Stopping stream...")
        finally:
            self.running = False
            for client in clients:
                try:
                    client.close()
                except:
                    pass
            sock.close()
    
    def _stream_udp(self, capture, sock, addr, compressor, fps, resize):
        """Stream over UDP"""
        from .streaming import StreamPacket, PacketType
        import struct
        
        self.running = True
        frame_idx = 0
        seq = 0
        
        try:
            first_frame = True
            
            for frame in capture.frames():
                if resize:
                    frame = cv2.resize(frame, resize)
                
                height, width = frame.shape[:2]
                
                # Send metadata/config on first frame
                if first_frame:
                    meta = f'{{"title":"Live: {capture.feed.name}","creator":"sanchez","created_at":"","seconds":"0"}}'
                    meta_pkt = StreamPacket(
                        packet_type=PacketType.METADATA,
                        sequence=seq,
                        timestamp=int(time.time() * 1_000_000),
                        payload=meta.encode()
                    )
                    seq += 1
                    sock.sendto(meta_pkt.serialize(), addr)
                    
                    config = f"{width:04d}{height:04d}9999999"
                    config_pkt = StreamPacket(
                        packet_type=PacketType.CONFIG,
                        sequence=seq,
                        timestamp=int(time.time() * 1_000_000),
                        payload=config.encode()
                    )
                    seq += 1
                    sock.sendto(config_pkt.serialize(), addr)
                    first_frame = False
                
                # Compress and send frame
                compressed = compressor.compress_frame(frame)
                frame_data = compressed.encode('utf-8')
                
                # Frame start
                start_pkt = StreamPacket(
                    packet_type=PacketType.FRAME_START,
                    sequence=seq,
                    timestamp=int(time.time() * 1_000_000),
                    payload=struct.pack('>II', frame_idx, len(frame_data))
                )
                seq += 1
                sock.sendto(start_pkt.serialize(), addr)
                
                # Frame chunks
                chunk_size = 1400  # MTU-friendly
                for chunk_idx in range((len(frame_data) + chunk_size - 1) // chunk_size):
                    offset = chunk_idx * chunk_size
                    chunk = frame_data[offset:offset + chunk_size]
                    
                    chunk_pkt = StreamPacket(
                        packet_type=PacketType.FRAME_CHUNK,
                        sequence=seq,
                        timestamp=int(time.time() * 1_000_000),
                        payload=struct.pack('>II', frame_idx, chunk_idx) + chunk
                    )
                    seq += 1
                    sock.sendto(chunk_pkt.serialize(), addr)
                
                # Frame end
                end_pkt = StreamPacket(
                    packet_type=PacketType.FRAME_END,
                    sequence=seq,
                    timestamp=int(time.time() * 1_000_000),
                    payload=struct.pack('>I', frame_idx)
                )
                seq += 1
                sock.sendto(end_pkt.serialize(), addr)
                
                frame_idx += 1
                if frame_idx % fps == 0:
                    print(f"\r   Streaming: {frame_idx} frames", end='', flush=True)
        
        except KeyboardInterrupt:
            print("\n\n   Stopping stream...")
        finally:
            self.running = False
            sock.close()


def interactive_feed_picker() -> Optional[VideoFeed]:
    """
    Interactive CLI to pick a video feed.
    
    Returns selected VideoFeed or None if cancelled.
    """
    print("\n" + "="*60)
    print("  🎬 Sanchez Live Feed Selector")
    print("="*60)
    
    # Check dependencies
    if not CV2_AVAILABLE:
        print("\n  ⚠️  OpenCV not installed. Camera/video capture unavailable.")
        print("     Install with: pip install opencv-python")
    
    if not MSS_AVAILABLE:
        print("\n  ⚠️  mss not installed. Screen capture unavailable.")
        print("     Install with: pip install mss")
    
    print("\n  Discovering available feeds...")
    
    all_feeds = []
    
    # Find cameras
    cameras = FeedDiscovery.find_cameras()
    if cameras:
        print(f"\n  📷 Cameras ({len(cameras)} found):")
        for cam in cameras:
            idx = len(all_feeds) + 1
            all_feeds.append(cam)
            print(f"     [{idx}] {cam}")
    
    # Find screens
    screens = FeedDiscovery.find_screens()
    if screens:
        print(f"\n  🖥️  Screens ({len(screens)} found):")
        for screen in screens:
            idx = len(all_feeds) + 1
            all_feeds.append(screen)
            print(f"     [{idx}] {screen}")
    
    # Find windows
    windows = FeedDiscovery.find_windows()
    if windows:
        print(f"\n  🪟 Windows ({len(windows)} found):")
        for i, window in enumerate(windows[:15]):  # Limit to 15 windows
            idx = len(all_feeds) + 1
            all_feeds.append(window)
            print(f"     [{idx}] {window}")
        if len(windows) > 15:
            print(f"     ... and {len(windows) - 15} more")
    
    if not all_feeds:
        print("\n  ❌ No video feeds found!")
        return None
    
    print(f"\n  [0] Enter video file path")
    print(f"  [q] Quit")
    print("\n" + "-"*60)
    
    while True:
        try:
            choice = input("  Select feed number: ").strip().lower()
            
            if choice == 'q':
                return None
            
            if choice == '0':
                file_path = input("  Enter video file path: ").strip().strip('"')
                if Path(file_path).exists():
                    return VideoFeed(
                        feed_type=FeedType.VIDEO_FILE,
                        name=Path(file_path).name,
                        description=f"Video file: {file_path}",
                        file_path=file_path
                    )
                else:
                    print(f"  ❌ File not found: {file_path}")
                    continue
            
            idx = int(choice) - 1
            if 0 <= idx < len(all_feeds):
                return all_feeds[idx]
            else:
                print(f"  ❌ Invalid selection. Enter 1-{len(all_feeds)}, 0, or q")
        
        except ValueError:
            print("  ❌ Invalid input. Enter a number or 'q' to quit")
        except KeyboardInterrupt:
            return None


def stream_video_file(
    file_path: str,
    host: str = "0.0.0.0",
    port: int = 9999,
    mode: str = "tcp",
    fps: int = 24,
    resize: Optional[Tuple[int, int]] = None,
    loop: bool = False
) -> None:
    """
    Stream a video file (MP4, etc.) directly without converting to .sanchez
    
    Args:
        file_path: Path to video file
        host: Host to stream to
        port: Port number
        mode: Streaming mode (tcp, udp, multicast, broadcast)
        fps: Target FPS
        resize: Optional resize dimensions
        loop: Loop the video
    """
    from .streaming import StreamMode
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    
    feed = VideoFeed(
        feed_type=FeedType.VIDEO_FILE,
        name=Path(file_path).name,
        description=f"Video file: {file_path}",
        file_path=file_path
    )
    
    server = LiveStreamServer(mode=mode_map.get(mode, StreamMode.TCP_UNICAST))
    
    while True:
        server.stream_feed(feed, host=host, port=port, fps=fps, resize=resize)
        if not loop:
            break
        print("\n   Looping video...")


def stream_camera(
    device_id: int = 0,
    host: str = "0.0.0.0",
    port: int = 9999,
    mode: str = "tcp",
    fps: int = 24,
    resize: Optional[Tuple[int, int]] = None
) -> None:
    """Stream from a camera device"""
    from .streaming import StreamMode
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    
    feed = VideoFeed(
        feed_type=FeedType.CAMERA,
        name=f"Camera {device_id}",
        description=f"Camera device {device_id}",
        device_id=device_id
    )
    
    server = LiveStreamServer(mode=mode_map.get(mode, StreamMode.TCP_UNICAST))
    server.stream_feed(feed, host=host, port=port, fps=fps, resize=resize)


def stream_screen(
    monitor_id: int = 0,
    host: str = "0.0.0.0",
    port: int = 9999,
    mode: str = "tcp",
    fps: int = 24,
    resize: Optional[Tuple[int, int]] = None
) -> None:
    """Stream screen capture"""
    from .streaming import StreamMode
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    
    name = "All Screens" if monitor_id == 0 else f"Screen {monitor_id}"
    
    feed = VideoFeed(
        feed_type=FeedType.SCREEN,
        name=name,
        description=f"Screen capture: {name}",
        monitor_id=monitor_id
    )
    
    server = LiveStreamServer(mode=mode_map.get(mode, StreamMode.TCP_UNICAST))
    server.stream_feed(feed, host=host, port=port, fps=fps, resize=resize)
