"""
Sanchez Overlay Module - Dynamic text and image overlays for streams

Supports:
- Dynamic text overlays (change text while streaming)
- PNG image overlays with transparency (logos, watermarks)
- Multiple text positions
- Configurable opacity, font size, color
- Per-video text/image overlays
- Background boxes for readability
"""

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Tuple, List, Union
import numpy as np

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


@dataclass
class ImageOverlay:
    """Configuration for a PNG image overlay (logo, watermark)"""
    path: str  # Path to PNG file
    position: str = "top-left"  # "top-left", "top-right", "bottom-left", "bottom-right", "center"
    opacity: float = 0.8  # 0.0 = fully transparent, 1.0 = fully opaque
    scale: float = 1.0  # Scale factor (1.0 = original size)
    margin: int = 15  # Margin from edges
    
    # Cached image data
    _image: Optional[np.ndarray] = field(default=None, repr=False)
    _alpha: Optional[np.ndarray] = field(default=None, repr=False)
    _size: Optional[Tuple[int, int]] = field(default=None, repr=False)
    
    def load(self) -> bool:
        """Load and prepare the image overlay."""
        if not Path(self.path).exists():
            print(f"Warning: Image overlay not found: {self.path}")
            return False
        
        if HAS_PIL:
            return self._load_pil()
        elif HAS_CV2:
            return self._load_cv2()
        else:
            print("Warning: Neither PIL nor OpenCV available for image loading")
            return False
    
    def _load_pil(self) -> bool:
        """Load image using PIL"""
        try:
            img = Image.open(self.path)
            
            # Ensure RGBA
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Scale if needed
            if self.scale != 1.0:
                new_size = (int(img.width * self.scale), int(img.height * self.scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Convert to numpy array (RGB and Alpha separate)
            arr = np.array(img)
            self._image = arr[:, :, :3]  # RGB
            self._alpha = (arr[:, :, 3] / 255.0 * self.opacity).astype(np.float32)
            self._size = (img.width, img.height)
            
            return True
        except Exception as e:
            print(f"Error loading image overlay: {e}")
            return False
    
    def _load_cv2(self) -> bool:
        """Load image using OpenCV"""
        try:
            img = cv2.imread(self.path, cv2.IMREAD_UNCHANGED)
            if img is None:
                return False
            
            # Ensure 4 channels
            if len(img.shape) == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
            elif img.shape[2] == 3:
                alpha = np.ones((img.shape[0], img.shape[1], 1), dtype=img.dtype) * 255
                img = np.concatenate([img, alpha], axis=2)
            
            # Scale if needed
            if self.scale != 1.0:
                new_size = (int(img.shape[1] * self.scale), int(img.shape[0] * self.scale))
                img = cv2.resize(img, new_size, interpolation=cv2.INTER_LINEAR)
            
            # Convert BGR to RGB
            self._image = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2RGB)
            self._alpha = (img[:, :, 3] / 255.0 * self.opacity).astype(np.float32)
            self._size = (img.shape[1], img.shape[0])
            
            return True
        except Exception as e:
            print(f"Error loading image overlay: {e}")
            return False
    
    def render_to_frame(self, frame: np.ndarray) -> np.ndarray:
        """Render image overlay onto a frame."""
        if self._image is None:
            if not self.load():
                return frame
        
        height, width = frame.shape[:2]
        img_height, img_width = self._image.shape[:2]
        
        # Calculate position
        x, y = self._calculate_position(width, height, img_width, img_height)
        
        # Ensure bounds
        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        
        # Calculate actual overlay region
        x2 = min(x + img_width, width)
        y2 = min(y + img_height, height)
        img_x2 = x2 - x
        img_y2 = y2 - y
        
        # Apply using alpha blending
        result = frame.copy()
        
        frame_region = result[y:y2, x:x2].astype(np.float32)
        img_region = self._image[:img_y2, :img_x2].astype(np.float32)
        alpha_region = self._alpha[:img_y2, :img_x2, np.newaxis]
        
        blended = img_region * alpha_region + frame_region * (1 - alpha_region)
        result[y:y2, x:x2] = blended.astype(np.uint8)
        
        return result
    
    def _calculate_position(
        self,
        frame_width: int,
        frame_height: int,
        img_width: int,
        img_height: int
    ) -> Tuple[int, int]:
        """Calculate image position based on position setting"""
        if self.position == "top-left":
            return self.margin, self.margin
        elif self.position == "top-right":
            return frame_width - img_width - self.margin, self.margin
        elif self.position == "top-center":
            return (frame_width - img_width) // 2, self.margin
        elif self.position == "bottom-left":
            return self.margin, frame_height - img_height - self.margin
        elif self.position == "bottom-right":
            return frame_width - img_width - self.margin, frame_height - img_height - self.margin
        elif self.position == "bottom-center":
            return (frame_width - img_width) // 2, frame_height - img_height - self.margin
        elif self.position == "center":
            return (frame_width - img_width) // 2, (frame_height - img_height) // 2
        else:
            return self.margin, self.margin


@dataclass
class TextOverlay:
    """Configuration for a single text overlay"""
    text: str = ""
    position: str = "top-left"  # "top-left", "top-right", "bottom-left", "bottom-right", "center", "top-center", "bottom-center"
    opacity: float = 0.8  # 0.0 = fully transparent, 1.0 = fully opaque
    font_size: int = 24
    color: Tuple[int, int, int] = (255, 255, 255)  # RGB
    background: bool = True  # Show background box behind text
    background_color: Tuple[int, int, int] = (0, 0, 0)  # RGB
    background_opacity: float = 0.5
    margin: int = 15  # Margin from edges
    padding: int = 8  # Padding around text in background box
    
    # For rendering
    _font: any = field(default=None, repr=False)
    _last_size: Tuple[int, int] = field(default=(0, 0), repr=False)
    
    def _get_font(self, size: int = None):
        """Get PIL font for rendering"""
        if not HAS_PIL:
            return None
        
        font_size = size or self.font_size
        
        try:
            # Try common fonts
            font_paths = [
                "arial.ttf",
                "Arial.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
            ]
            
            for font_path in font_paths:
                try:
                    return ImageFont.truetype(font_path, font_size)
                except:
                    continue
            
            # Fall back to default
            return ImageFont.load_default()
        except:
            return None
    
    def render_to_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Render text overlay onto a frame.
        
        Args:
            frame: RGB numpy array (height, width, 3)
        
        Returns:
            Frame with text overlay applied
        """
        if not self.text or not HAS_PIL:
            return frame
        
        height, width = frame.shape[:2]
        
        # Convert frame to PIL Image
        pil_image = Image.fromarray(frame)
        
        # Create overlay for alpha blending
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        font = self._get_font()
        if font is None:
            return frame
        
        # Get text size
        bbox = draw.textbbox((0, 0), self.text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Calculate position
        x, y = self._calculate_position(width, height, text_width, text_height)
        
        # Draw background box if enabled
        if self.background:
            bg_x1 = x - self.padding
            bg_y1 = y - self.padding
            bg_x2 = x + text_width + self.padding
            bg_y2 = y + text_height + self.padding
            
            bg_alpha = int(255 * self.background_opacity)
            bg_color = (*self.background_color, bg_alpha)
            
            draw.rectangle([bg_x1, bg_y1, bg_x2, bg_y2], fill=bg_color)
        
        # Draw text
        text_alpha = int(255 * self.opacity)
        text_color = (*self.color, text_alpha)
        draw.text((x, y), self.text, font=font, fill=text_color)
        
        # Composite overlay onto frame
        pil_image = pil_image.convert('RGBA')
        result = Image.alpha_composite(pil_image, overlay)
        
        return np.array(result.convert('RGB'))
    
    def _calculate_position(
        self,
        frame_width: int,
        frame_height: int,
        text_width: int,
        text_height: int
    ) -> Tuple[int, int]:
        """Calculate text position based on position setting"""
        
        if self.position == "top-left":
            return self.margin, self.margin
        elif self.position == "top-right":
            return frame_width - text_width - self.margin, self.margin
        elif self.position == "top-center":
            return (frame_width - text_width) // 2, self.margin
        elif self.position == "bottom-left":
            return self.margin, frame_height - text_height - self.margin
        elif self.position == "bottom-right":
            return frame_width - text_width - self.margin, frame_height - text_height - self.margin
        elif self.position == "bottom-center":
            return (frame_width - text_width) // 2, frame_height - text_height - self.margin
        elif self.position == "center":
            return (frame_width - text_width) // 2, (frame_height - text_height) // 2
        else:
            return self.margin, self.margin


class OverlayManager:
    """
    Manages multiple text and image overlays for a streaming channel.
    
    Features:
    - Multiple simultaneous overlays (text and/or images)
    - PNG logos with transparency
    - Dynamic text changes during streaming
    - Per-video overlay configurations
    - Thread-safe updates
    
    Example:
        manager = OverlayManager()
        
        # Add PNG logo
        manager.add_image("logo", "channel_logo.png", position="top-left")
        
        # Add channel name text
        manager.add_overlay("channel", "SPORTS TV", position="top-right")
        
        # Add dynamic info (can be changed)
        manager.add_overlay("score", "0 - 0", position="top-center")
        
        # Update text while streaming
        manager.set_text("score", "1 - 0")
    """
    
    def __init__(self):
        self._overlays: Dict[str, Union[TextOverlay, ImageOverlay]] = {}
        self._video_overlays: Dict[str, Dict[str, Union[TextOverlay, ImageOverlay]]] = {}
        self._current_video: Optional[str] = None
        self._lock = threading.Lock()
    
    def add_image(
        self,
        overlay_id: str,
        path: str,
        position: str = "top-left",
        opacity: float = 0.8,
        scale: float = 1.0,
        margin: int = 15
    ) -> bool:
        """
        Add a PNG image overlay (logo, watermark).
        
        Args:
            overlay_id: Unique identifier for this overlay
            path: Path to PNG file (supports transparency)
            position: "top-left", "top-right", "bottom-left", "bottom-right", "center", etc.
            opacity: Image opacity (0.0-1.0)
            scale: Scale factor (1.0 = original size, 0.5 = half size)
            margin: Margin from screen edges
        
        Returns:
            True if image was loaded successfully
        """
        overlay = ImageOverlay(
            path=path,
            position=position,
            opacity=opacity,
            scale=scale,
            margin=margin
        )
        
        if overlay.load():
            with self._lock:
                self._overlays[overlay_id] = overlay
            return True
        return False
    
    def add_overlay(
        self,
        overlay_id: str,
        text: str = "",
        position: str = "top-left",
        opacity: float = 0.8,
        font_size: int = 24,
        color: Tuple[int, int, int] = (255, 255, 255),
        background: bool = True,
        background_color: Tuple[int, int, int] = (0, 0, 0),
        background_opacity: float = 0.5,
        margin: int = 15,
        padding: int = 8
    ) -> None:
        """
        Add or update a text overlay.
        
        Args:
            overlay_id: Unique identifier for this overlay (e.g., "channel", "score", "ticker")
            text: Text to display
            position: "top-left", "top-right", "bottom-left", "bottom-right", "center", "top-center", "bottom-center"
            opacity: Text opacity (0.0-1.0)
            font_size: Font size in pixels
            color: RGB tuple for text color
            background: Whether to show a background box
            background_color: RGB tuple for background
            background_opacity: Background opacity (0.0-1.0)
            margin: Margin from screen edges
            padding: Padding inside background box
        """
        with self._lock:
            self._overlays[overlay_id] = TextOverlay(
                text=text,
                position=position,
                opacity=opacity,
                font_size=font_size,
                color=color,
                background=background,
                background_color=background_color,
                background_opacity=background_opacity,
                margin=margin,
                padding=padding
            )
    
    def set_text(self, overlay_id: str, text: str) -> bool:
        """
        Update the text of an existing text overlay.
        
        Args:
            overlay_id: ID of the overlay to update
            text: New text to display
        
        Returns:
            True if overlay exists and was updated (only works for TextOverlay)
        """
        with self._lock:
            overlay = self._overlays.get(overlay_id)
            if overlay and isinstance(overlay, TextOverlay):
                overlay.text = text
                return True
            return False
    
    def set_position(self, overlay_id: str, position: str) -> bool:
        """Update the position of an overlay."""
        with self._lock:
            if overlay_id in self._overlays:
                self._overlays[overlay_id].position = position
                return True
            return False
    
    def set_opacity(self, overlay_id: str, opacity: float) -> bool:
        """Update the opacity of an overlay."""
        with self._lock:
            if overlay_id in self._overlays:
                self._overlays[overlay_id].opacity = max(0.0, min(1.0, opacity))
                return True
            return False
    
    def set_color(self, overlay_id: str, color: Tuple[int, int, int]) -> bool:
        """Update the color of a text overlay."""
        with self._lock:
            overlay = self._overlays.get(overlay_id)
            if overlay and isinstance(overlay, TextOverlay):
                overlay.color = color
                return True
            return False
    
    def set_font_size(self, overlay_id: str, font_size: int) -> bool:
        """Update the font size of a text overlay."""
        with self._lock:
            overlay = self._overlays.get(overlay_id)
            if overlay and isinstance(overlay, TextOverlay):
                overlay.font_size = font_size
                return True
            return False
    
    def set_scale(self, overlay_id: str, scale: float) -> bool:
        """Update the scale of an image overlay (requires reload)."""
        with self._lock:
            overlay = self._overlays.get(overlay_id)
            if overlay and isinstance(overlay, ImageOverlay):
                overlay.scale = scale
                overlay._image = None  # Force reload
                return True
            return False
    
    def remove_overlay(self, overlay_id: str) -> bool:
        """Remove an overlay."""
        with self._lock:
            if overlay_id in self._overlays:
                del self._overlays[overlay_id]
                return True
            return False
    
    def clear_overlays(self) -> None:
        """Remove all overlays."""
        with self._lock:
            self._overlays.clear()
    
    def get_overlay(self, overlay_id: str) -> Optional[Union[TextOverlay, ImageOverlay]]:
        """Get an overlay by ID."""
        with self._lock:
            return self._overlays.get(overlay_id)
    
    def list_overlays(self) -> List[str]:
        """Get list of overlay IDs."""
        with self._lock:
            return list(self._overlays.keys())
    
    def add_video_image(
        self,
        video_pattern: str,
        overlay_id: str,
        path: str,
        position: str = "top-left",
        opacity: float = 0.8,
        scale: float = 1.0
    ) -> bool:
        """
        Add a PNG image overlay for specific videos.
        
        Args:
            video_pattern: Video filename or pattern (e.g., "sports*.mp4")
            overlay_id: Unique ID for this overlay
            path: Path to PNG file
            position: Position on screen
            opacity: Image opacity
            scale: Scale factor
        
        Returns:
            True if image was loaded successfully
        """
        overlay = ImageOverlay(path=path, position=position, opacity=opacity, scale=scale)
        if overlay.load():
            with self._lock:
                if video_pattern not in self._video_overlays:
                    self._video_overlays[video_pattern] = {}
                self._video_overlays[video_pattern][overlay_id] = overlay
            return True
        return False
    
    def add_video_overlay(
        self,
        video_pattern: str,
        overlay_id: str,
        text: str,
        **kwargs
    ) -> None:
        """
        Add a text overlay that only appears for specific videos.
        
        Args:
            video_pattern: Video filename or pattern (e.g., "sports.mp4", "*.sanchez")
            overlay_id: Unique ID for this overlay
            text: Text to display
            **kwargs: Additional TextOverlay options
        """
        with self._lock:
            if video_pattern not in self._video_overlays:
                self._video_overlays[video_pattern] = {}
            
            self._video_overlays[video_pattern][overlay_id] = TextOverlay(
                text=text,
                **kwargs
            )
    
    def set_current_video(self, video_path: str) -> None:
        """Update the current video being played."""
        with self._lock:
            self._current_video = video_path
    
    def _get_video_overlays(self) -> Dict[str, Union[TextOverlay, ImageOverlay]]:
        """Get overlays that apply to the current video."""
        import fnmatch
        
        if not self._current_video:
            return {}
        
        video_name = Path(self._current_video).name
        result = {}
        
        for pattern, overlays in self._video_overlays.items():
            if fnmatch.fnmatch(video_name, pattern) or video_name == pattern:
                result.update(overlays)
        
        return result
    
    def apply(self, frame: np.ndarray) -> np.ndarray:
        """
        Apply all active overlays to a frame.
        
        Args:
            frame: RGB numpy array (height, width, 3)
        
        Returns:
            Frame with all overlays applied
        """
        with self._lock:
            # Combine default overlays and video-specific overlays
            all_overlays = dict(self._overlays)
            all_overlays.update(self._get_video_overlays())
            
            if not all_overlays:
                return frame
            
            result = frame
            for overlay in all_overlays.values():
                # Handle both text and image overlays
                if isinstance(overlay, TextOverlay):
                    if overlay.text:  # Only render if there's text
                        result = overlay.render_to_frame(result)
                elif isinstance(overlay, ImageOverlay):
                    result = overlay.render_to_frame(result)
            
            return result
    
    def has_overlays(self) -> bool:
        """Check if there are any active overlays."""
        with self._lock:
            return bool(self._overlays) or bool(self._video_overlays)


# Legacy compatibility - WatermarkConfig now creates text overlays
@dataclass  
class WatermarkConfig:
    """Legacy watermark config - now creates text overlays instead"""
    text: str = ""
    opacity: float = 0.8
    position: str = "top-left"
    font_size: int = 24
    color: Tuple[int, int, int] = (255, 255, 255)
    background: bool = True
    
    _overlay: Optional[TextOverlay] = field(default=None, repr=False)
    
    def load(self, target_size: Optional[Tuple[int, int]] = None) -> bool:
        """Initialize the text overlay"""
        self._overlay = TextOverlay(
            text=self.text,
            position=self.position,
            opacity=self.opacity,
            font_size=self.font_size,
            color=self.color,
            background=self.background
        )
        return True
    
    def apply(self, frame: np.ndarray) -> np.ndarray:
        """Apply text overlay to a frame"""
        if self._overlay is None:
            self.load()
        return self._overlay.render_to_frame(frame)


class WatermarkManager:
    """
    Watermark manager - supports both text overlays and PNG images.
    
    Usage:
        manager = WatermarkManager()
        
        # Text overlay
        manager.set_default("CHANNEL NAME", opacity=0.8, position="top-left")
        
        # PNG logo (transparent)
        manager.add_logo("logo.png", position="top-right", scale=0.5)
        
        # Per-video overlays
        manager.set_video_text("sports*.mp4", "SPORTS", position="top-right")
        manager.add_video_logo("news*.mp4", "news_logo.png", position="bottom-right")
    """
    
    def __init__(self):
        self._overlay_manager = OverlayManager()
        self._has_default = False
    
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
            scale: Scale factor (1.0 = original size)
            overlay_id: ID for this logo (use different IDs for multiple logos)
        
        Returns:
            True if logo was loaded successfully
        """
        if self._overlay_manager.add_image(overlay_id, path, position, opacity, scale):
            print(f"   🖼️ Logo overlay: '{Path(path).name}' at {position}")
            self._has_default = True
            return True
        return False
    
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
        if self._overlay_manager.add_video_image(
            video_pattern, f"logo_{video_pattern}", path, position, opacity, scale
        ):
            print(f"   🖼️ Video logo for '{video_pattern}': '{Path(path).name}'")
            return True
        return False
    
    def set_default(
        self,
        text: str,
        opacity: float = 0.8,
        position: str = "top-left",
        font_size: int = 24,
        color: Tuple[int, int, int] = (255, 255, 255),
        background: bool = True
    ) -> bool:
        """
        Set the default channel text overlay.
        
        Args:
            text: Text to display (channel name, etc.)
            opacity: Text opacity (0.0-1.0)
            position: Position on screen
            font_size: Font size in pixels
            color: RGB color tuple
            background: Show background box
        
        Returns:
            True (always succeeds for text)
        """
        self._overlay_manager.add_overlay(
            "default",
            text=text,
            opacity=opacity,
            position=position,
            font_size=font_size,
            color=color,
            background=background
        )
        self._has_default = True
        print(f"   📝 Text overlay: '{text}' at {position}")
        return True
    
    def set_video_watermark(
        self,
        video_pattern: str,
        text: str,
        opacity: float = 0.8,
        position: str = "top-right",
        font_size: int = 20,
        color: Tuple[int, int, int] = (255, 255, 255)
    ) -> bool:
        """
        Set a text overlay for specific video(s).
        
        Args:
            video_pattern: Video filename or pattern (e.g., "sports.mp4", "*.sanchez")
            text: Text to display
            opacity: Text opacity
            position: Position on screen
            font_size: Font size
            color: RGB color tuple
        
        Returns:
            True (always succeeds for text)
        """
        self._overlay_manager.add_video_overlay(
            video_pattern,
            f"video_{video_pattern}",
            text=text,
            opacity=opacity,
            position=position,
            font_size=font_size,
            color=color
        )
        print(f"   📝 Video overlay for '{video_pattern}': '{text}'")
        return True
    
    def set_text(self, text: str) -> bool:
        """Update the default overlay text dynamically."""
        return self._overlay_manager.set_text("default", text)
    
    def add_overlay(self, overlay_id: str, text: str, **kwargs) -> None:
        """Add an additional text overlay."""
        self._overlay_manager.add_overlay(overlay_id, text, **kwargs)
    
    def add_image(self, overlay_id: str, path: str, **kwargs) -> bool:
        """Add an additional image overlay."""
        return self._overlay_manager.add_image(overlay_id, path, **kwargs)
    
    def update_overlay(self, overlay_id: str, text: str) -> bool:
        """Update an overlay's text."""
        return self._overlay_manager.set_text(overlay_id, text)
    
    def remove_overlay(self, overlay_id: str) -> bool:
        """Remove an overlay."""
        return self._overlay_manager.remove_overlay(overlay_id)
    
    def get_overlay_manager(self) -> OverlayManager:
        """Get the underlying OverlayManager for advanced use."""
        return self._overlay_manager
    
    def get_watermark_for_video(self, video_path: str) -> Optional['WatermarkManager']:
        """Get watermark manager (returns self for compatibility)."""
        return self
    
    def set_current_video(self, video_path: str) -> None:
        """Update the current video being played."""
        self._overlay_manager.set_current_video(video_path)
    
    def apply(self, frame: np.ndarray) -> np.ndarray:
        """Apply all overlays to a frame."""
        return self._overlay_manager.apply(frame)
    
    def has_watermark(self) -> bool:
        """Check if there are any active overlays."""
        return self._overlay_manager.has_overlays()


def create_text_overlay(
    text: str,
    position: str = "top-left",
    opacity: float = 0.8,
    font_size: int = 24,
    color: Tuple[int, int, int] = (255, 255, 255),
    background: bool = True
) -> TextOverlay:
    """
    Create a text overlay configuration.
    
    Args:
        text: Text to display
        position: Position on screen
        opacity: Text opacity (0.0-1.0)
        font_size: Font size in pixels
        color: RGB color tuple
        background: Show background box
    
    Returns:
        TextOverlay object
    """
    return TextOverlay(
        text=text,
        position=position,
        opacity=opacity,
        font_size=font_size,
        color=color,
        background=background
    )


# For backwards compatibility
def create_watermark_overlay(*args, **kwargs):
    """Legacy function - use create_text_overlay instead"""
    print("Warning: create_watermark_overlay is deprecated, use create_text_overlay")
    return None
