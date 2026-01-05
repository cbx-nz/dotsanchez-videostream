"""
Sanchez Playlist/Channel Module - Stream multiple videos like a TV channel

Supports:
- Sequential playback of multiple .sanchez or video files
- Playlist files (.m3u, .txt, .json)
- Shuffle and repeat modes
- Mixed playlists (.sanchez and .mp4 files together)
- Channel scheduling
- Dynamic queue management (add videos while streaming)
- Watermark/overlay support
"""

import json
import random
import time
import threading
from pathlib import Path
from typing import List, Optional, Callable, Union, Generator
from dataclasses import dataclass, field
from enum import Enum


class PlaylistMode(Enum):
    """Playlist playback modes"""
    SEQUENTIAL = "sequential"  # Play in order
    SHUFFLE = "shuffle"        # Random order
    REPEAT_ONE = "repeat_one"  # Repeat current video
    REPEAT_ALL = "repeat_all"  # Loop entire playlist
    SHUFFLE_REPEAT = "shuffle_repeat"  # Shuffle and repeat forever


@dataclass
class PlaylistItem:
    """A single item in a playlist"""
    path: str
    title: Optional[str] = None
    duration: Optional[float] = None  # Duration in seconds (if known)
    
    def __post_init__(self):
        if self.title is None:
            self.title = Path(self.path).stem
    
    @property
    def is_sanchez(self) -> bool:
        return self.path.lower().endswith('.sanchez')
    
    @property
    def is_video(self) -> bool:
        video_exts = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}
        return Path(self.path).suffix.lower() in video_exts
    
    @property
    def exists(self) -> bool:
        return Path(self.path).exists()
    
    def __str__(self) -> str:
        status = "✓" if self.exists else "✗"
        duration_str = f" ({self.duration:.1f}s)" if self.duration else ""
        return f"[{status}] {self.title}{duration_str}"


@dataclass
class Playlist:
    """A playlist of videos to stream as a channel"""
    name: str = "Sanchez Channel"
    items: List[PlaylistItem] = field(default_factory=list)
    mode: PlaylistMode = PlaylistMode.SEQUENTIAL
    current_index: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _queue_file: Optional[str] = field(default=None, repr=False)
    _watch_queue: bool = field(default=False, repr=False)
    _skip_current: bool = field(default=False, repr=False)  # Signal to skip current video
    _jump_to_index: int = field(default=-1, repr=False)  # Signal to jump to specific index
    
    def add(self, path: str, title: Optional[str] = None) -> None:
        """Add a video to the playlist"""
        with self._lock:
            item = PlaylistItem(path=path, title=title)
            self.items.append(item)
    
    def add_next(self, path: str, title: Optional[str] = None) -> None:
        """Add a video to play next (after current)"""
        with self._lock:
            item = PlaylistItem(path=path, title=title)
            insert_pos = self.current_index + 1
            if insert_pos > len(self.items):
                insert_pos = len(self.items)
            self.items.insert(insert_pos, item)
    
    def remove(self, index: int) -> bool:
        """Remove a video by index"""
        with self._lock:
            if 0 <= index < len(self.items):
                del self.items[index]
                if self.current_index >= len(self.items):
                    self.current_index = max(0, len(self.items) - 1)
                return True
            return False
    
    def clear_queue(self) -> None:
        """Clear all items after the current video"""
        with self._lock:
            keep = self.current_index + 1
            self.items = self.items[:keep]
    
    def get_queue(self) -> List[PlaylistItem]:
        """Get upcoming videos in the queue"""
        with self._lock:
            return self.items[self.current_index + 1:]
    
    def skip_current(self) -> None:
        """Skip the currently playing video"""
        with self._lock:
            self._skip_current = True
    
    def jump_to(self, index: int) -> bool:
        """Jump to a specific video by index (0-based)"""
        with self._lock:
            if 0 <= index < len(self.items):
                self._jump_to_index = index
                return True
            return False
    
    def jump_to_title(self, title: str) -> bool:
        """Jump to a video by title (partial match)"""
        with self._lock:
            title_lower = title.lower()
            for i, item in enumerate(self.items):
                if title_lower in item.title.lower():
                    self._jump_to_index = i
                    return True
            return False
    
    def replace_current(self, path: str, title: Optional[str] = None) -> None:
        """Replace the current video with a new one"""
        with self._lock:
            new_item = PlaylistItem(path=path, title=title)
            if self.items:
                self.items[self.current_index] = new_item
            else:
                self.items.append(new_item)
    
    def insert_and_play(self, path: str, title: Optional[str] = None) -> None:
        """Insert a video right after current and skip to it"""
        with self._lock:
            item = PlaylistItem(path=path, title=title)
            insert_pos = self.current_index + 1
            if insert_pos > len(self.items):
                insert_pos = len(self.items)
            self.items.insert(insert_pos, item)
            self._jump_to_index = insert_pos
    
    def should_skip(self) -> bool:
        """Check if we should skip the current video"""
        with self._lock:
            if self._skip_current:
                self._skip_current = False
                return True
            return False
    
    def check_jump(self) -> int:
        """Check if we should jump to a different video. Returns -1 if no jump."""
        with self._lock:
            jump = self._jump_to_index
            self._jump_to_index = -1
            return jump
    
    def watch_queue_file(self, queue_file: str) -> None:
        """
        Watch a file for new videos to add to the queue.
        
        The file should contain one video path per line.
        New lines are added to the queue.
        """
        self._queue_file = queue_file
        self._watch_queue = True
        
        # Create file if it doesn't exist
        Path(queue_file).touch(exist_ok=True)
        
        def watcher():
            last_size = 0
            while self._watch_queue:
                try:
                    path = Path(queue_file)
                    if path.exists():
                        current_size = path.stat().st_size
                        if current_size > last_size:
                            # Read new lines
                            with open(queue_file, 'r') as f:
                                f.seek(last_size)
                                new_lines = f.read()
                            
                            for line in new_lines.strip().split('\n'):
                                line = line.strip()
                                if line and not line.startswith('#') and Path(line).exists():
                                    self.add(line)
                                    print(f"   📥 Added to queue: {Path(line).name}")
                            
                            last_size = current_size
                except Exception as e:
                    pass
                
                time.sleep(1)
        
        thread = threading.Thread(target=watcher, daemon=True)
        thread.start()
    
    def stop_watching_queue(self) -> None:
        """Stop watching the queue file"""
        self._watch_queue = False
    
    def add_directory(self, directory: str, recursive: bool = False) -> int:
        """Add all videos from a directory"""
        dir_path = Path(directory)
        if not dir_path.exists():
            return 0
        
        count = 0
        pattern = "**/*" if recursive else "*"
        
        for file_path in dir_path.glob(pattern):
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext == '.sanchez' or ext in {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}:
                    self.add(str(file_path))
                    count += 1
        
        return count
    
    def shuffle(self) -> None:
        """Shuffle the playlist"""
        random.shuffle(self.items)
        self.current_index = 0
    
    def next(self) -> Optional[PlaylistItem]:
        """Get the next item to play"""
        if not self.items:
            return None
        
        if self.mode == PlaylistMode.REPEAT_ONE:
            return self.items[self.current_index]
        
        if self.mode == PlaylistMode.SHUFFLE:
            self.current_index = random.randint(0, len(self.items) - 1)
            return self.items[self.current_index]
        
        # Sequential or Repeat All
        item = self.items[self.current_index]
        self.current_index += 1
        
        if self.current_index >= len(self.items):
            if self.mode == PlaylistMode.REPEAT_ALL:
                self.current_index = 0
            else:
                return None  # End of playlist
        
        return item
    
    def current(self) -> Optional[PlaylistItem]:
        """Get current item without advancing"""
        if not self.items or self.current_index >= len(self.items):
            return None
        return self.items[self.current_index]
    
    def reset(self) -> None:
        """Reset playlist to beginning"""
        self.current_index = 0
    
    def __len__(self) -> int:
        return len(self.items)
    
    def __iter__(self):
        """Iterate through playlist items based on mode"""
        self.reset()
        while True:
            item = self.next()
            if item is None:
                break
            yield item
    
    def items_generator(self) -> Generator[PlaylistItem, None, None]:
        """Generate playlist items continuously based on mode, with skip/jump support"""
        if not self.items:
            return
        
        self.reset()
        
        if self.mode == PlaylistMode.SHUFFLE:
            self.shuffle()
        
        while True:
            # Check for jump signal before starting iteration
            jump_idx = self.check_jump()
            if jump_idx >= 0:
                self.current_index = jump_idx
            
            # Iterate through items starting from current_index
            while self.current_index < len(self.items):
                # Check for jump signal each iteration
                jump_idx = self.check_jump()
                if jump_idx >= 0:
                    self.current_index = jump_idx
                    continue
                
                item = self.items[self.current_index]
                self.current_index += 1
                
                if item.exists:
                    yield item
                    
                    # After yielding, check if we should skip
                    if self.should_skip():
                        continue  # Move to next item
            
            # End of playlist - check mode
            if self.mode not in (PlaylistMode.REPEAT_ALL, PlaylistMode.SHUFFLE_REPEAT):
                break
            
            # Reset for repeat modes
            self.current_index = 0
            if self.mode == PlaylistMode.SHUFFLE_REPEAT:
                self.shuffle()
    
    @classmethod
    def from_files(cls, files: List[str], name: str = "Sanchez Channel") -> 'Playlist':
        """Create playlist from a list of file paths"""
        playlist = cls(name=name)
        for file_path in files:
            playlist.add(file_path)
        return playlist
    
    @classmethod
    def load(cls, playlist_path: str) -> 'Playlist':
        """Load playlist from a file (.m3u, .txt, .json, or .pls)"""
        path = Path(playlist_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Playlist not found: {playlist_path}")
        
        ext = path.suffix.lower()
        base_dir = path.parent
        
        if ext == '.json':
            return cls._load_json(path, base_dir)
        elif ext in ('.m3u', '.m3u8'):
            return cls._load_m3u(path, base_dir)
        elif ext == '.pls':
            return cls._load_pls(path, base_dir)
        else:
            # Assume simple text file with one path per line
            return cls._load_txt(path, base_dir)
    
    @classmethod
    def _load_json(cls, path: Path, base_dir: Path) -> 'Playlist':
        """Load JSON playlist"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        playlist = cls(name=data.get('name', path.stem))
        
        if 'mode' in data:
            try:
                playlist.mode = PlaylistMode(data['mode'])
            except ValueError:
                pass
        
        for item in data.get('items', []):
            if isinstance(item, str):
                file_path = item
                title = None
            else:
                file_path = item.get('path', item.get('file', ''))
                title = item.get('title')
            
            # Handle relative paths
            if not Path(file_path).is_absolute():
                file_path = str(base_dir / file_path)
            
            playlist.add(file_path, title)
        
        return playlist
    
    @classmethod
    def _load_m3u(cls, path: Path, base_dir: Path) -> 'Playlist':
        """Load M3U playlist"""
        playlist = cls(name=path.stem)
        current_title = None
        
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                if not line or line.startswith('#EXTM3U'):
                    continue
                
                if line.startswith('#EXTINF:'):
                    # Parse extended info: #EXTINF:duration,title
                    try:
                        info = line[8:]
                        if ',' in info:
                            _, current_title = info.split(',', 1)
                            current_title = current_title.strip()
                    except:
                        pass
                elif not line.startswith('#'):
                    # This is a file path
                    file_path = line
                    if not Path(file_path).is_absolute():
                        file_path = str(base_dir / file_path)
                    
                    playlist.add(file_path, current_title)
                    current_title = None
        
        return playlist
    
    @classmethod
    def _load_pls(cls, path: Path, base_dir: Path) -> 'Playlist':
        """Load PLS playlist"""
        playlist = cls(name=path.stem)
        files = {}
        titles = {}
        
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.lower()
                    
                    if key.startswith('file'):
                        num = key[4:]
                        files[num] = value
                    elif key.startswith('title'):
                        num = key[5:]
                        titles[num] = value
        
        for num in sorted(files.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            file_path = files[num]
            if not Path(file_path).is_absolute():
                file_path = str(base_dir / file_path)
            playlist.add(file_path, titles.get(num))
        
        return playlist
    
    @classmethod
    def _load_txt(cls, path: Path, base_dir: Path) -> 'Playlist':
        """Load simple text playlist (one file per line)"""
        playlist = cls(name=path.stem)
        
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    file_path = line
                    if not Path(file_path).is_absolute():
                        file_path = str(base_dir / file_path)
                    playlist.add(file_path)
        
        return playlist
    
    def save(self, playlist_path: str) -> None:
        """Save playlist to a file"""
        path = Path(playlist_path)
        ext = path.suffix.lower()
        
        if ext == '.json':
            self._save_json(path)
        elif ext in ('.m3u', '.m3u8'):
            self._save_m3u(path)
        else:
            self._save_txt(path)
    
    def _save_json(self, path: Path) -> None:
        """Save as JSON playlist"""
        data = {
            'name': self.name,
            'mode': self.mode.value,
            'items': [
                {'path': item.path, 'title': item.title}
                for item in self.items
            ]
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def _save_m3u(self, path: Path) -> None:
        """Save as M3U playlist"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for item in self.items:
                duration = int(item.duration) if item.duration else -1
                f.write(f'#EXTINF:{duration},{item.title}\n')
                f.write(f'{item.path}\n')
    
    def _save_txt(self, path: Path) -> None:
        """Save as simple text playlist"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'# {self.name}\n')
            for item in self.items:
                f.write(f'{item.path}\n')
    
    def print_info(self) -> None:
        """Print playlist information"""
        print(f"\n{'='*60}")
        print(f"  📺 {self.name}")
        print(f"{'='*60}")
        print(f"  Mode: {self.mode.value}")
        print(f"  Items: {len(self.items)}")
        print(f"\n  Playlist:")
        
        for i, item in enumerate(self.items):
            marker = "▶" if i == self.current_index else " "
            print(f"  {marker} {i+1:3}. {item}")
        
        # Count valid items
        valid = sum(1 for item in self.items if item.exists)
        if valid < len(self.items):
            print(f"\n  ⚠️  {len(self.items) - valid} files not found")
        
        print(f"{'='*60}\n")


class ChannelServer:
    """
    Stream a playlist of videos like a TV channel.
    
    Supports:
    - Dynamic text overlays (change text while streaming)
    - Per-video text overlays
    - Dynamic queue management (add/remove/skip videos)
    - Skip, jump, and replace current video
    
    Usage:
        channel = ChannelServer()
        channel.set_overlay("SPORTS TV", position="top-left")
        channel.add_overlay("score", "0 - 0", position="top-right")
        channel.stream_playlist(playlist, host="0.0.0.0", port=9999)
        
        # During streaming (from another thread/process):
        channel.set_text("score", "1 - 0")  # Update score
        channel.playlist.skip_current()  # Skip to next video
    """
    
    def __init__(self, mode=None):
        from .streaming import StreamMode
        self.stream_mode = mode or StreamMode.TCP_UNICAST
        self.running = False
        self.current_video: Optional[str] = None
        self.on_video_change: Optional[Callable[[PlaylistItem, int, int], None]] = None
        self.playlist: Optional[Playlist] = None  # Reference to current playlist
        
        # Text overlay support (replaces watermark)
        self._watermark_manager = None
    
    def set_overlay(
        self,
        text: str,
        position: str = "top-left",
        opacity: float = 0.8,
        font_size: int = 24,
        color: tuple = (255, 255, 255),
        background: bool = True
    ) -> bool:
        """
        Set the default channel text overlay.
        
        Args:
            text: Text to display (channel name, sport, etc.)
            position: "top-left", "top-right", "bottom-left", "bottom-right", "center", "top-center", "bottom-center"
            opacity: Text opacity (0.0 = transparent, 1.0 = opaque)
            font_size: Font size in pixels
            color: RGB tuple for text color, e.g., (255, 255, 255) for white
            background: Show semi-transparent background box
        
        Returns:
            True (always succeeds for text)
        """
        from .watermark import WatermarkManager
        
        if self._watermark_manager is None:
            self._watermark_manager = WatermarkManager()
        
        return self._watermark_manager.set_default(text, opacity, position, font_size, color, background)
    
    def add_logo(
        self,
        path: str,
        position: str = "top-left",
        opacity: float = 0.8,
        scale: float = 1.0,
        overlay_id: str = "logo"
    ) -> bool:
        """
        Add a PNG logo overlay with transparency.
        
        Args:
            path: Path to PNG file (supports transparency)
            position: Position on screen
            opacity: Logo opacity (0.0-1.0)
            scale: Scale factor (1.0 = original size, 0.5 = half)
            overlay_id: ID for this logo (use different IDs for multiple logos)
        
        Returns:
            True if logo was loaded successfully
        """
        from .watermark import WatermarkManager
        
        if self._watermark_manager is None:
            self._watermark_manager = WatermarkManager()
        
        return self._watermark_manager.add_logo(path, position, opacity, scale, overlay_id)
    
    def add_video_logo(
        self,
        video_pattern: str,
        path: str,
        position: str = "top-left",
        opacity: float = 0.8,
        scale: float = 1.0
    ) -> bool:
        """
        Add a PNG logo for specific videos.
        
        Args:
            video_pattern: Video filename or pattern (e.g., "sports*.mp4")
            path: Path to PNG file
            position: Position on screen
            opacity: Logo opacity
            scale: Scale factor
        
        Returns:
            True if logo was loaded successfully
        """
        from .watermark import WatermarkManager
        
        if self._watermark_manager is None:
            self._watermark_manager = WatermarkManager()
        
        return self._watermark_manager.add_video_logo(video_pattern, path, position, opacity, scale)
    
    def add_overlay(
        self,
        overlay_id: str,
        text: str,
        position: str = "top-right",
        opacity: float = 0.8,
        font_size: int = 20,
        color: tuple = (255, 255, 255),
        background: bool = True
    ) -> None:
        """
        Add an additional text overlay.
        
        Args:
            overlay_id: Unique ID for this overlay (e.g., "score", "ticker", "info")
            text: Text to display
            position: Position on screen
            opacity: Text opacity
            font_size: Font size
            color: RGB color tuple
            background: Show background box
        """
        from .watermark import WatermarkManager
        
        if self._watermark_manager is None:
            self._watermark_manager = WatermarkManager()
        
        self._watermark_manager.add_overlay(overlay_id, text, position=position, opacity=opacity, 
                                            font_size=font_size, color=color, background=background)
    
    def set_text(self, overlay_id: str, text: str) -> bool:
        """
        Update the text of an overlay dynamically.
        
        Args:
            overlay_id: ID of overlay to update ("default" for main overlay)
            text: New text to display
        
        Returns:
            True if overlay was updated
        """
        if self._watermark_manager is None:
            return False
        return self._watermark_manager.update_overlay(overlay_id, text)
    
    def set_default_text(self, text: str) -> bool:
        """Update the default overlay text."""
        if self._watermark_manager is None:
            return False
        return self._watermark_manager.set_text(text)
    
    def remove_overlay(self, overlay_id: str) -> bool:
        """Remove an overlay."""
        if self._watermark_manager is None:
            return False
        return self._watermark_manager.remove_overlay(overlay_id)
    
    def set_video_overlay(
        self,
        video_pattern: str,
        text: str,
        position: str = "top-right",
        opacity: float = 0.8,
        font_size: int = 20,
        color: tuple = (255, 255, 255)
    ) -> bool:
        """
        Set a text overlay for specific video(s).
        
        Args:
            video_pattern: Video filename or pattern (e.g., "sports*.mp4", "news.sanchez")
            text: Text to display for matching videos
            position: Position on screen
            opacity: Text opacity
            font_size: Font size
            color: RGB color tuple
        
        Returns:
            True (always succeeds for text)
        """
        from .watermark import WatermarkManager
        
        if self._watermark_manager is None:
            self._watermark_manager = WatermarkManager()
        
        return self._watermark_manager.set_video_watermark(video_pattern, text, opacity, position, font_size, color)
    
    # Legacy method names for backwards compatibility
    def set_watermark(self, text: str, opacity: float = 0.8, position: str = "top-left") -> bool:
        """Legacy method - use set_overlay instead"""
        return self.set_overlay(text, position, opacity)
    
    def set_video_watermark(self, video_pattern: str, text: str, opacity: float = 0.8, position: str = "top-right") -> bool:
        """Legacy method - use set_video_overlay instead"""
        return self.set_video_overlay(video_pattern, text, position, opacity)
    
    def stream_playlist(
        self,
        playlist: Playlist,
        host: str = "0.0.0.0",
        port: int = 9999,
        satellite_mode: bool = False,
        queue_file: Optional[str] = None
    ) -> None:
        """
        Stream a playlist of videos.
        
        Args:
            playlist: Playlist to stream
            host: Host to stream to
            port: Port number
            satellite_mode: Enable satellite optimizations
            queue_file: Optional file to watch for new videos to add to queue
        """
        from .streaming import SanchezStreamServer
        from .live import LiveStreamServer, VideoFeed, FeedType
        
        self.playlist = playlist  # Store reference for external control
        playlist.print_info()
        
        # Start watching queue file if specified
        if queue_file:
            playlist.watch_queue_file(queue_file)
            print(f"   📥 Watching queue file: {queue_file}")
        
        print(f"📡 Starting channel: {playlist.name}")
        print(f"   Mode: {self.stream_mode.name}")
        print(f"   Address: {host}:{port}")
        print(f"   Playlist mode: {playlist.mode.value}")
        
        if self._watermark_manager and self._watermark_manager.has_watermark():
            print(f"   📝 Text overlays: enabled")
        
        print(f"\n   Press Ctrl+C to stop\n")
        
        self.running = True
        video_num = 0
        
        try:
            for item in playlist.items_generator():
                if not self.running:
                    break
                
                video_num += 1
                total_videos = len(playlist)  # Dynamic count
                self.current_video = item.path
                
                print(f"\n{'─'*60}")
                print(f"  ▶ Now playing ({video_num}/{total_videos}): {item.title}")
                print(f"    File: {item.path}")
                
                # Update watermark for this video
                if self._watermark_manager:
                    self._watermark_manager.set_current_video(item.path)
                
                # Show queue if there are items
                queue = playlist.get_queue()
                if queue:
                    print(f"    Queue: {len(queue)} videos waiting")
                
                print(f"{'─'*60}")
                
                if self.on_video_change:
                    self.on_video_change(item, video_num, total_videos)
                
                try:
                    if item.is_sanchez:
                        # Stream .sanchez file with watermark
                        server = SanchezStreamServer(mode=self.stream_mode)
                        server.stream_file(
                            item.path,
                            host=host,
                            port=port,
                            loop=False,
                            satellite_mode=satellite_mode,
                            frame_processor=self._apply_watermark if self._watermark_manager else None
                        )
                    else:
                        # Stream video file (MP4, etc.) with watermark
                        feed = VideoFeed(
                            feed_type=FeedType.VIDEO_FILE,
                            name=item.title,
                            description=f"Video: {item.path}",
                            file_path=item.path
                        )
                        server = LiveStreamServer(mode=self.stream_mode)
                        server.stream_feed(
                            feed,
                            host=host,
                            port=port,
                            fps=24,
                            frame_processor=self._apply_watermark if self._watermark_manager else None
                        )
                
                except Exception as e:
                    print(f"\n  ⚠️  Error playing {item.title}: {e}")
                    continue
                
                # Brief pause between videos
                if self.running:
                    time.sleep(0.5)
        
        except KeyboardInterrupt:
            print("\n\n  Stopping channel...")
        finally:
            self.running = False
            playlist.stop_watching_queue()
            print(f"\n  Channel stopped. Played {video_num} videos.")
    
    def _apply_watermark(self, frame):
        """Apply watermark to a frame (used as frame_processor callback)"""
        if self._watermark_manager:
            return self._watermark_manager.apply(frame)
        return frame
    
    def stop(self) -> None:
        """Stop the channel"""
        self.running = False
    
    def stream_channel(
        self,
        playlist: Playlist,
        host: str = "0.0.0.0",
        port: int = 9999,
        fps: int = 24,
        resize: Optional[tuple] = None
    ) -> None:
        """Alias for stream_playlist with additional options"""
        self.stream_playlist(playlist, host, port)


def create_channel(
    files: List[str],
    name: str = "Sanchez Channel",
    mode: str = "sequential",
    shuffle: bool = False
) -> Playlist:
    """
    Create a channel from a list of files.
    
    Args:
        files: List of video file paths (.sanchez or .mp4)
        name: Channel name
        mode: Playback mode (sequential, shuffle, repeat_one, repeat_all)
        shuffle: Whether to shuffle initially
    
    Returns:
        Playlist object
    """
    mode_map = {
        'sequential': PlaylistMode.SEQUENTIAL,
        'shuffle': PlaylistMode.SHUFFLE,
        'repeat_one': PlaylistMode.REPEAT_ONE,
        'repeat_all': PlaylistMode.REPEAT_ALL,
        'loop': PlaylistMode.REPEAT_ALL
    }
    
    playlist = Playlist.from_files(files, name=name)
    playlist.mode = mode_map.get(mode.lower(), PlaylistMode.SEQUENTIAL)
    
    if shuffle:
        playlist.shuffle()
    
    return playlist


def stream_channel(
    files_or_playlist: Union[List[str], str, Playlist],
    host: str = "0.0.0.0",
    port: int = 9999,
    mode: str = "tcp",
    playlist_mode: str = "repeat_all",
    shuffle: bool = False,
    name: str = "Sanchez Channel"
) -> None:
    """
    Stream multiple videos as a TV channel.
    
    Args:
        files_or_playlist: List of files, path to playlist file, or Playlist object
        host: Host to stream to
        port: Port number
        mode: Streaming mode (tcp, udp, multicast, broadcast)
        playlist_mode: Playlist mode (sequential, shuffle, repeat_one, repeat_all)
        shuffle: Shuffle playlist before starting
        name: Channel name
    """
    from .streaming import StreamMode
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    
    # Create or load playlist
    if isinstance(files_or_playlist, Playlist):
        playlist = files_or_playlist
    elif isinstance(files_or_playlist, str):
        # It's a playlist file path
        playlist = Playlist.load(files_or_playlist)
    else:
        # It's a list of files
        playlist = create_channel(
            files_or_playlist,
            name=name,
            mode=playlist_mode,
            shuffle=shuffle
        )
    
    # Set playlist mode
    pmode_map = {
        'sequential': PlaylistMode.SEQUENTIAL,
        'shuffle': PlaylistMode.SHUFFLE,
        'repeat_one': PlaylistMode.REPEAT_ONE,
        'repeat_all': PlaylistMode.REPEAT_ALL,
        'loop': PlaylistMode.REPEAT_ALL
    }
    playlist.mode = pmode_map.get(playlist_mode.lower(), PlaylistMode.REPEAT_ALL)
    
    if shuffle:
        playlist.shuffle()
    
    # Start streaming
    channel = ChannelServer(mode=mode_map.get(mode.lower(), StreamMode.TCP_UNICAST))
    channel.stream_playlist(playlist, host=host, port=port)
