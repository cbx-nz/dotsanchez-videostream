"""
Sanchez Player - Play .sanchez files directly using pygame

Features:
- Real-time playback at 24fps
- Pause/Resume with spacebar
- Seek with arrow keys
- Frame-by-frame with comma/period keys
- Audio sync when audio file is present
"""

import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Callable
import numpy as np

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

from .format import SanchezFile


class SanchezPlayer:
    """
    Interactive player for .sanchez files.
    
    Usage:
        player = SanchezPlayer()
        player.play("video.sanchez")
    
    Controls:
        Space  - Pause/Resume
        Left   - Seek backward 5 seconds
        Right  - Seek forward 5 seconds
        ,      - Previous frame (when paused)
        .      - Next frame (when paused)
        R      - Restart from beginning
        I      - Show info overlay
        Q/Esc  - Quit
    """
    
    def __init__(self, scale: float = 1.0):
        """
        Initialize the player.
        
        Args:
            scale: Display scale factor (e.g., 0.5 for half size)
        """
        if not PYGAME_AVAILABLE:
            raise ImportError("pygame is required for the player. Install with: pip install pygame")
        
        self.scale = scale
        self.sanchez: Optional[SanchezFile] = None
        self.audio_path: Optional[str] = None
        self.current_frame = 0
        self.playing = False
        self.running = False
        self.show_info = False
        
        # Frame cache for smoother playback
        self._frame_cache: dict = {}
        self._cache_size = 50  # Cache up to 50 frames ahead
        self._preload_thread: Optional[threading.Thread] = None
        self._stop_preload = False
    
    def play(
        self,
        sanchez_path: str,
        audio_path: Optional[str] = None,
        start_frame: int = 0,
        fullscreen: bool = False
    ) -> None:
        """
        Play a .sanchez file.
        
        Args:
            sanchez_path: Path to .sanchez file
            audio_path: Optional path to audio file
            start_frame: Frame to start from
            fullscreen: Start in fullscreen mode
        """
        sanchez_path = Path(sanchez_path)
        
        if not sanchez_path.exists():
            raise FileNotFoundError(f"File not found: {sanchez_path}")
        
        # Load sanchez file
        print(f"Loading: {sanchez_path}")
        self.sanchez = SanchezFile.load(str(sanchez_path))
        print(f"  {self.sanchez.config.width}x{self.sanchez.config.height}, {self.sanchez.frame_count} frames")
        
        # Find audio file
        if audio_path is None:
            auto_audio = sanchez_path.with_suffix('.mp3')
            if auto_audio.exists():
                audio_path = str(auto_audio)
                print(f"  Audio: {audio_path}")
        
        self.audio_path = audio_path
        self.current_frame = min(start_frame, self.sanchez.frame_count - 1)
        
        # Initialize pygame
        pygame.init()
        pygame.mixer.init()
        
        # Calculate display size
        display_width = int(self.sanchez.config.width * self.scale)
        display_height = int(self.sanchez.config.height * self.scale)
        
        # Create window
        flags = pygame.RESIZABLE
        if fullscreen:
            flags |= pygame.FULLSCREEN
        
        screen = pygame.display.set_mode((display_width, display_height), flags)
        pygame.display.set_caption(f"Sanchez Player - {self.sanchez.metadata.title}")
        
        # Set up clock for frame timing
        clock = pygame.time.Clock()
        fps = self.sanchez.config.fps
        
        # Load audio if available
        if self.audio_path and os.path.exists(self.audio_path):
            try:
                pygame.mixer.music.load(self.audio_path)
            except Exception as e:
                print(f"Warning: Could not load audio: {e}")
                self.audio_path = None
        
        # Start preloading frames
        self._start_preload()
        
        # Start playback
        self.playing = True
        self.running = True
        
        if self.audio_path:
            pygame.mixer.music.play()
            # Seek to start position if not starting from beginning
            if self.current_frame > 0:
                start_time = self.current_frame / fps
                pygame.mixer.music.set_pos(start_time)
        
        # Initialize font for info overlay
        try:
            font = pygame.font.Font(None, 36)
        except:
            font = pygame.font.SysFont('arial', 24)
        
        # Main loop
        last_time = time.time()
        frame_duration = 1.0 / fps
        accumulated_time = 0.0
        
        print("\nControls: Space=Pause, Arrows=Seek, Q=Quit, I=Info")
        
        try:
            while self.running:
                # Handle events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    
                    elif event.type == pygame.KEYDOWN:
                        self._handle_key(event.key, fps)
                    
                    elif event.type == pygame.VIDEORESIZE:
                        screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                        display_width, display_height = event.size
                
                # Update timing
                current_time = time.time()
                delta_time = current_time - last_time
                last_time = current_time
                
                if self.playing:
                    accumulated_time += delta_time
                    
                    # Advance frames based on accumulated time
                    while accumulated_time >= frame_duration:
                        accumulated_time -= frame_duration
                        self.current_frame += 1
                        
                        # Loop or stop at end
                        if self.current_frame >= self.sanchez.frame_count:
                            if self.sanchez.is_image:
                                self.current_frame = 0
                                self.playing = False
                            else:
                                self.current_frame = 0
                                accumulated_time = 0.0
                                if self.audio_path:
                                    pygame.mixer.music.play()
                
                # Get and display frame
                frame = self._get_cached_frame(self.current_frame)
                if frame is not None:
                    # Convert numpy array to pygame surface
                    surface = pygame.surfarray.make_surface(frame.swapaxes(0, 1))
                    
                    # Scale to display size
                    if (surface.get_width(), surface.get_height()) != (display_width, display_height):
                        surface = pygame.transform.scale(surface, (display_width, display_height))
                    
                    screen.blit(surface, (0, 0))
                
                # Draw info overlay
                if self.show_info:
                    self._draw_info(screen, font, display_width, display_height)
                
                # Draw pause indicator
                if not self.playing:
                    pause_text = font.render("PAUSED", True, (255, 255, 0))
                    screen.blit(pause_text, (10, 10))
                
                pygame.display.flip()
                clock.tick(fps)
        
        finally:
            self._stop_preload_thread()
            pygame.mixer.music.stop()
            pygame.quit()
    
    def _handle_key(self, key: int, fps: int) -> None:
        """Handle keyboard input"""
        if key in (pygame.K_q, pygame.K_ESCAPE):
            self.running = False
        
        elif key == pygame.K_SPACE:
            self.playing = not self.playing
            if self.audio_path:
                if self.playing:
                    pygame.mixer.music.unpause()
                else:
                    pygame.mixer.music.pause()
        
        elif key == pygame.K_LEFT:
            # Seek backward 5 seconds
            self._seek_frames(-5 * fps)
        
        elif key == pygame.K_RIGHT:
            # Seek forward 5 seconds
            self._seek_frames(5 * fps)
        
        elif key == pygame.K_COMMA:
            # Previous frame (when paused)
            if not self.playing:
                self._seek_frames(-1)
        
        elif key == pygame.K_PERIOD:
            # Next frame (when paused)
            if not self.playing:
                self._seek_frames(1)
        
        elif key == pygame.K_r:
            # Restart
            self.current_frame = 0
            self.playing = True
            if self.audio_path:
                pygame.mixer.music.play()
        
        elif key == pygame.K_i:
            # Toggle info overlay
            self.show_info = not self.show_info
        
        elif key == pygame.K_f:
            # Toggle fullscreen
            pygame.display.toggle_fullscreen()
    
    def _seek_frames(self, delta: int) -> None:
        """Seek by a number of frames"""
        self.current_frame = max(0, min(self.sanchez.frame_count - 1, self.current_frame + delta))
        
        # Sync audio
        if self.audio_path and self.playing:
            seek_time = self.current_frame / self.sanchez.config.fps
            try:
                pygame.mixer.music.set_pos(seek_time)
            except:
                pass  # Some audio formats don't support seeking
    
    def _get_cached_frame(self, index: int) -> Optional[np.ndarray]:
        """Get a frame, using cache if available"""
        if index in self._frame_cache:
            return self._frame_cache[index]
        
        # Load frame directly if not cached
        try:
            frame = self.sanchez.get_frame(index)
            self._frame_cache[index] = frame
            return frame
        except Exception as e:
            print(f"Error loading frame {index}: {e}")
            return None
    
    def _start_preload(self) -> None:
        """Start background thread to preload frames"""
        self._stop_preload = False
        self._preload_thread = threading.Thread(target=self._preload_worker, daemon=True)
        self._preload_thread.start()
    
    def _stop_preload_thread(self) -> None:
        """Stop the preload thread"""
        self._stop_preload = True
        if self._preload_thread:
            self._preload_thread.join(timeout=1.0)
    
    def _preload_worker(self) -> None:
        """Worker thread to preload frames ahead of playback"""
        while not self._stop_preload and self.running:
            # Preload frames ahead of current position
            for offset in range(1, self._cache_size):
                if self._stop_preload or not self.running:
                    break
                
                target_frame = self.current_frame + offset
                if target_frame < self.sanchez.frame_count and target_frame not in self._frame_cache:
                    try:
                        frame = self.sanchez.get_frame(target_frame)
                        self._frame_cache[target_frame] = frame
                    except:
                        pass
            
            # Clean up old cached frames
            current = self.current_frame
            keys_to_remove = [k for k in self._frame_cache.keys() if k < current - 10]
            for k in keys_to_remove:
                del self._frame_cache[k]
            
            time.sleep(0.01)  # Small delay to prevent CPU spinning
    
    def _draw_info(self, screen, font, width: int, height: int) -> None:
        """Draw info overlay"""
        if not self.sanchez:
            return
        
        fps = self.sanchez.config.fps
        current_time = self.current_frame / fps
        total_time = self.sanchez.frame_count / fps
        
        info_lines = [
            f"Title: {self.sanchez.metadata.title}",
            f"Creator: {self.sanchez.metadata.creator}",
            f"Size: {self.sanchez.config.width}x{self.sanchez.config.height}",
            f"Frame: {self.current_frame + 1}/{self.sanchez.frame_count}",
            f"Time: {current_time:.1f}s / {total_time:.1f}s",
            f"FPS: {fps}",
            f"Audio: {'Yes' if self.audio_path else 'No'}"
        ]
        
        # Draw semi-transparent background
        overlay = pygame.Surface((300, len(info_lines) * 30 + 20))
        overlay.fill((0, 0, 0))
        overlay.set_alpha(180)
        screen.blit(overlay, (10, 50))
        
        # Draw text
        y = 60
        for line in info_lines:
            text = font.render(line, True, (255, 255, 255))
            screen.blit(text, (20, y))
            y += 30


class SimplePlayer:
    """
    Simple frame-by-frame viewer using tkinter (no pygame required).
    Good for viewing single-frame images or stepping through videos.
    """
    
    def __init__(self):
        try:
            import tkinter as tk
            from PIL import Image, ImageTk
            self.tk = tk
            self.Image = Image
            self.ImageTk = ImageTk
        except ImportError as e:
            raise ImportError(f"tkinter and PIL are required: {e}")
    
    def view(self, sanchez_path: str, frame_index: int = 0) -> None:
        """
        View a .sanchez file in a simple window.
        
        Args:
            sanchez_path: Path to .sanchez file
            frame_index: Frame to display
        """
        sanchez = SanchezFile.load(sanchez_path)
        frame = sanchez.get_frame(frame_index)
        
        # Create window
        root = self.tk.Tk()
        root.title(f"{sanchez.metadata.title} - Frame {frame_index + 1}/{sanchez.frame_count}")
        
        # Convert numpy array to PIL Image
        image = self.Image.fromarray(frame)
        photo = self.ImageTk.PhotoImage(image)
        
        # Create label with image
        label = self.tk.Label(root, image=photo)
        label.pack()
        
        # Keyboard navigation
        current_frame = [frame_index]
        
        def update_frame(delta: int):
            new_frame = max(0, min(sanchez.frame_count - 1, current_frame[0] + delta))
            if new_frame != current_frame[0]:
                current_frame[0] = new_frame
                new_img = self.Image.fromarray(sanchez.get_frame(new_frame))
                new_photo = self.ImageTk.PhotoImage(new_img)
                label.configure(image=new_photo)
                label.image = new_photo
                root.title(f"{sanchez.metadata.title} - Frame {new_frame + 1}/{sanchez.frame_count}")
        
        root.bind('<Left>', lambda e: update_frame(-1))
        root.bind('<Right>', lambda e: update_frame(1))
        root.bind('<q>', lambda e: root.destroy())
        root.bind('<Escape>', lambda e: root.destroy())
        
        root.mainloop()
