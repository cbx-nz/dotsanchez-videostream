"""
.sanchez file format specification and data structures

Format:
    Line 1: Metadata JSON (one line)
    Line 2: Config - WWWWHHHH + 7 digit frame count (15 chars total)
    Line 3+: Frame data (compressed pixel data)

Compression:
    - Uses zlib compression on raw pixel bytes
    - Stored as base64 encoded string per frame
    - Reduces file size from ~14.5MB/frame to typically <1MB/frame
"""

import json
import zlib
import base64
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional
import numpy as np


@dataclass
class SanchezMetadata:
    """Metadata for a .sanchez file"""
    title: str
    creator: str
    created_at: str
    seconds: float
    
    def to_json_line(self) -> str:
        """Convert metadata to single-line JSON"""
        data = {
            "title": self.title,
            "creator": self.creator,
            "created_at": self.created_at,
            "seconds": str(self.seconds)
        }
        return json.dumps(data, separators=(',', ':'))
    
    @classmethod
    def from_json_line(cls, line: str) -> 'SanchezMetadata':
        """Parse metadata from JSON line"""
        data = json.loads(line.strip())
        return cls(
            title=data["title"],
            creator=data["creator"],
            created_at=data["created_at"],
            seconds=float(data["seconds"])
        )
    
    @classmethod
    def create_new(cls, title: str, creator: str, duration_seconds: float) -> 'SanchezMetadata':
        """Create new metadata with current timestamp"""
        return cls(
            title=title,
            creator=creator,
            created_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            seconds=duration_seconds
        )


@dataclass  
class SanchezConfig:
    """Video configuration - dimensions and frame count"""
    width: int
    height: int
    frame_count: int
    fps: int = 24  # Always 24fps as per spec
    
    def to_config_line(self) -> str:
        """Convert config to the format: WWWWHHHH + 7-digit frame count"""
        width_str = str(self.width).zfill(4)
        height_str = str(self.height).zfill(4)
        frame_str = str(self.frame_count).zfill(7)
        return f"{width_str}{height_str}{frame_str}"
    
    @classmethod
    def from_config_line(cls, line: str) -> 'SanchezConfig':
        """Parse config from line"""
        line = line.strip()
        width = int(line[0:4])
        height = int(line[4:8])
        frame_count = int(line[8:15])
        return cls(width=width, height=height, frame_count=frame_count)
    
    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds"""
        return self.frame_count / self.fps


class FrameCompressor:
    """Handles compression and decompression of frame data"""
    
    @staticmethod
    def compress_frame(frame: np.ndarray) -> str:
        """
        Compress a frame (RGB numpy array) to a base64 encoded string.
        
        Args:
            frame: numpy array of shape (height, width, 3) with RGB values
            
        Returns:
            Base64 encoded compressed string
        """
        # Convert frame to bytes (RGB raw bytes)
        raw_bytes = frame.astype(np.uint8).tobytes()
        
        # Compress with zlib (level 9 for max compression)
        compressed = zlib.compress(raw_bytes, level=9)
        
        # Encode as base64 for text storage
        encoded = base64.b64encode(compressed).decode('ascii')
        
        return encoded
    
    @staticmethod
    def decompress_frame(encoded_data: str, width: int, height: int) -> np.ndarray:
        """
        Decompress a base64 encoded string back to a frame.
        
        Args:
            encoded_data: Base64 encoded compressed string
            width: Frame width
            height: Frame height
            
        Returns:
            numpy array of shape (height, width, 3) with RGB values
        """
        # Decode base64
        compressed = base64.b64decode(encoded_data)
        
        # Decompress
        raw_bytes = zlib.decompress(compressed)
        
        # Convert to numpy array
        frame = np.frombuffer(raw_bytes, dtype=np.uint8)
        frame = frame.reshape((height, width, 3))
        
        return frame
    
    @staticmethod
    def frame_to_hex_list(frame: np.ndarray) -> List[str]:
        """
        Convert frame to list of hex codes (uncompressed format).
        This is the original format described in the spec.
        
        Args:
            frame: numpy array of shape (height, width, 3) with RGB values
            
        Returns:
            List of hex strings like ['RRGGBB', 'RRGGBB', ...]
        """
        # Flatten to (n_pixels, 3)
        pixels = frame.reshape(-1, 3)
        
        # Convert each pixel to hex
        hex_list = ['{:02X}{:02X}{:02X}'.format(r, g, b) for r, g, b in pixels]
        
        return hex_list
    
    @staticmethod
    def hex_list_to_frame(hex_list: List[str], width: int, height: int) -> np.ndarray:
        """
        Convert list of hex codes back to a frame.
        
        Args:
            hex_list: List of hex strings like ['RRGGBB', 'RRGGBB', ...]
            width: Frame width
            height: Frame height
            
        Returns:
            numpy array of shape (height, width, 3) with RGB values
        """
        pixels = []
        for hex_code in hex_list:
            r = int(hex_code[0:2], 16)
            g = int(hex_code[2:4], 16)
            b = int(hex_code[4:6], 16)
            pixels.append([r, g, b])
        
        frame = np.array(pixels, dtype=np.uint8)
        frame = frame.reshape((height, width, 3))
        
        return frame


class SanchezFile:
    """
    Represents a .sanchez video/image file.
    
    Usage for creating:
        sanchez = SanchezFile.create("MyVideo", "cbx", 1920, 1080)
        sanchez.add_frame(frame_array)
        sanchez.save("output.sanchez")
    
    Usage for reading:
        sanchez = SanchezFile.load("input.sanchez")
        for frame in sanchez.get_frames():
            # process frame
    """
    
    def __init__(self, metadata: SanchezMetadata, config: SanchezConfig):
        self.metadata = metadata
        self.config = config
        self._frames: List[str] = []  # Compressed frame strings
        self.compressor = FrameCompressor()
    
    @classmethod
    def create(cls, title: str, creator: str, width: int, height: int) -> 'SanchezFile':
        """Create a new empty .sanchez file ready to add frames"""
        metadata = SanchezMetadata.create_new(title, creator, 0.0)
        config = SanchezConfig(width=width, height=height, frame_count=0)
        return cls(metadata, config)
    
    def add_frame(self, frame: np.ndarray, use_compression: bool = True) -> None:
        """
        Add a frame to the video.
        
        Args:
            frame: numpy array of shape (height, width, 3) with RGB values
            use_compression: If True, use zlib compression. If False, use raw hex format.
        """
        if use_compression:
            compressed = self.compressor.compress_frame(frame)
            self._frames.append(compressed)
        else:
            # Use original hex format: {RRGGBB,RRGGBB,...}
            hex_list = self.compressor.frame_to_hex_list(frame)
            hex_str = '{' + ','.join(hex_list) + '}'
            self._frames.append(hex_str)
        
        self.config.frame_count = len(self._frames)
        self.metadata.seconds = self.config.duration_seconds
    
    def get_frame(self, index: int) -> np.ndarray:
        """Get a specific frame by index"""
        if index < 0 or index >= len(self._frames):
            raise IndexError(f"Frame index {index} out of range")
        
        frame_data = self._frames[index]
        
        # Check if it's compressed (base64) or raw hex format
        if frame_data.startswith('{'):
            # Raw hex format
            hex_str = frame_data[1:-1]  # Remove { and }
            hex_list = hex_str.split(',')
            return self.compressor.hex_list_to_frame(hex_list, self.config.width, self.config.height)
        else:
            # Compressed format
            return self.compressor.decompress_frame(frame_data, self.config.width, self.config.height)
    
    def get_frames(self):
        """Generator that yields all frames"""
        for i in range(len(self._frames)):
            yield self.get_frame(i)
    
    def save(self, filepath: str) -> None:
        """Save to a .sanchez file"""
        with open(filepath, 'w', encoding='utf-8') as f:
            # Line 1: Metadata
            f.write(self.metadata.to_json_line() + '\n')
            
            # Line 2: Config
            f.write(self.config.to_config_line() + '\n')
            
            # Lines 3+: Frames
            for frame_data in self._frames:
                f.write(frame_data + '\n')
    
    @classmethod
    def load(cls, filepath: str) -> 'SanchezFile':
        """Load a .sanchez file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        if len(lines) < 2:
            raise ValueError("Invalid .sanchez file: missing metadata or config")
        
        # Parse metadata and config
        metadata = SanchezMetadata.from_json_line(lines[0])
        config = SanchezConfig.from_config_line(lines[1])
        
        # Create instance and load frames
        sanchez = cls(metadata, config)
        
        # Load frame data (lines 3+)
        for i in range(2, len(lines)):
            line = lines[i].strip()
            if line:  # Skip empty lines
                sanchez._frames.append(line)
        
        # Update frame count from actual loaded frames
        sanchez.config.frame_count = len(sanchez._frames)
        
        return sanchez
    
    @property
    def is_image(self) -> bool:
        """Returns True if this is a single-frame image"""
        return self.config.frame_count == 1
    
    @property
    def frame_count(self) -> int:
        """Number of frames"""
        return len(self._frames)
    
    def __repr__(self) -> str:
        return (f"SanchezFile(title='{self.metadata.title}', "
                f"{self.config.width}x{self.config.height}, "
                f"{self.frame_count} frames, "
                f"{self.metadata.seconds:.2f}s)")
