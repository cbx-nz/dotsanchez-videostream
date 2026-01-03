"""
Encoder module - Convert video files (MP4, etc.) to .sanchez format

Uses OpenCV for video processing and ffmpeg (via subprocess) for audio extraction.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Callable
import cv2
import numpy as np

from .format import SanchezFile, SanchezMetadata, SanchezConfig


class SanchezEncoder:
    """
    Encode video files to .sanchez format.
    
    Usage:
        encoder = SanchezEncoder()
        encoder.encode("input.mp4", "output.sanchez", title="My Video", creator="cbx")
    """
    
    TARGET_FPS = 24  # .sanchez format is always 24fps
    
    def __init__(self):
        self.progress_callback: Optional[Callable[[int, int, str], None]] = None
    
    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """
        Set a callback for progress updates.
        
        Args:
            callback: Function that receives (current_frame, total_frames, status_message)
        """
        self.progress_callback = callback
    
    def _report_progress(self, current: int, total: int, message: str) -> None:
        """Report progress if callback is set"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
        else:
            # Default: print to console
            percent = (current / total * 100) if total > 0 else 0
            print(f"\r[{percent:5.1f}%] {message}: {current}/{total}", end='', flush=True)
    
    def encode(
        self,
        input_path: str,
        output_path: str,
        title: Optional[str] = None,
        creator: str = "cbx",
        resize: Optional[tuple] = None,
        max_frames: Optional[int] = None,
        use_compression: bool = True
    ) -> tuple[str, Optional[str]]:
        """
        Encode a video file to .sanchez format.
        
        Args:
            input_path: Path to input video file (MP4, AVI, etc.)
            output_path: Path for output .sanchez file
            title: Video title (defaults to filename)
            creator: Creator name
            resize: Optional (width, height) to resize video
            max_frames: Optional limit on number of frames to encode
            use_compression: Use zlib compression (recommended)
            
        Returns:
            Tuple of (sanchez_path, audio_path) - audio_path may be None if no audio
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Default title from filename
        if title is None:
            title = input_path.stem
        
        # Ensure output has .sanchez extension
        if output_path.suffix.lower() != '.sanchez':
            output_path = output_path.with_suffix('.sanchez')
        
        # Open video
        cap = cv2.VideoCapture(str(input_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {input_path}")
        
        try:
            # Get video properties
            original_fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames_original = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Apply resize if specified
            if resize:
                width, height = resize
            
            # Calculate frame sampling to convert to 24fps
            frame_interval = original_fps / self.TARGET_FPS
            total_frames_target = int(total_frames_original / frame_interval)
            
            if max_frames:
                total_frames_target = min(total_frames_target, max_frames)
            
            print(f"Encoding: {input_path.name}")
            print(f"  Original: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} @ {original_fps:.2f}fps")
            print(f"  Output: {width}x{height} @ {self.TARGET_FPS}fps")
            print(f"  Frames to encode: {total_frames_target}")
            print(f"  Compression: {'Enabled' if use_compression else 'Disabled'}")
            
            # Create sanchez file
            sanchez = SanchezFile.create(title, creator, width, height)
            
            # Process frames
            frame_index = 0
            encoded_count = 0
            
            while encoded_count < total_frames_target:
                # Calculate which original frame to read
                target_original_frame = int(encoded_count * frame_interval)
                
                # Seek to the target frame if needed
                if frame_index != target_original_frame:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_original_frame)
                    frame_index = target_original_frame
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                frame_index += 1
                
                # Convert BGR to RGB (OpenCV uses BGR)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Resize if needed
                if resize:
                    frame_rgb = cv2.resize(frame_rgb, (width, height), interpolation=cv2.INTER_AREA)
                
                # Add frame to sanchez file
                sanchez.add_frame(frame_rgb, use_compression=use_compression)
                encoded_count += 1
                
                # Report progress
                self._report_progress(encoded_count, total_frames_target, "Encoding frames")
            
            print()  # New line after progress
            
            # Save sanchez file
            sanchez.save(str(output_path))
            print(f"Saved: {output_path}")
            
            # Extract audio
            audio_path = self._extract_audio(str(input_path), str(output_path.with_suffix('.mp3')))
            
            return str(output_path), audio_path
            
        finally:
            cap.release()
    
    def _extract_audio(self, video_path: str, audio_output_path: str) -> Optional[str]:
        """
        Extract audio from video file using ffmpeg.
        
        Args:
            video_path: Path to video file
            audio_output_path: Path for output audio file
            
        Returns:
            Path to audio file, or None if extraction failed
        """
        try:
            print("Extracting audio...")
            
            # Use ffmpeg to extract audio
            cmd = [
                'ffmpeg', '-y',  # Overwrite output
                '-i', video_path,
                '-vn',  # No video
                '-acodec', 'libmp3lame',
                '-ab', '192k',  # Audio bitrate
                '-ar', '44100',  # Sample rate
                audio_output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0 and os.path.exists(audio_output_path):
                print(f"Audio saved: {audio_output_path}")
                return audio_output_path
            else:
                print("Warning: Could not extract audio (ffmpeg may not be installed)")
                return None
                
        except FileNotFoundError:
            print("Warning: ffmpeg not found. Audio extraction skipped.")
            return None
        except Exception as e:
            print(f"Warning: Audio extraction failed: {e}")
            return None
    
    def encode_image(
        self,
        input_path: str,
        output_path: str,
        title: Optional[str] = None,
        creator: str = "cbx",
        resize: Optional[tuple] = None
    ) -> str:
        """
        Encode a single image to .sanchez format (single-frame).
        
        Args:
            input_path: Path to input image (PNG, JPG, etc.)
            output_path: Path for output .sanchez file
            title: Image title (defaults to filename)
            creator: Creator name
            resize: Optional (width, height) to resize
            
        Returns:
            Path to created .sanchez file
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        if title is None:
            title = input_path.stem
        
        if output_path.suffix.lower() != '.sanchez':
            output_path = output_path.with_suffix('.sanchez')
        
        # Read image
        image = cv2.imread(str(input_path))
        if image is None:
            raise ValueError(f"Could not read image: {input_path}")
        
        # Convert BGR to RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Resize if needed
        if resize:
            image_rgb = cv2.resize(image_rgb, resize, interpolation=cv2.INTER_AREA)
        
        height, width = image_rgb.shape[:2]
        
        # Create sanchez file with single frame
        sanchez = SanchezFile.create(title, creator, width, height)
        sanchez.add_frame(image_rgb)
        sanchez.save(str(output_path))
        
        print(f"Encoded image: {output_path} ({width}x{height})")
        
        return str(output_path)
    
    def encode_frames(
        self,
        frames: list,
        output_path: str,
        title: str,
        creator: str = "cbx",
        use_compression: bool = True
    ) -> str:
        """
        Encode a list of numpy frames to .sanchez format.
        
        Args:
            frames: List of numpy arrays (height, width, 3) RGB
            output_path: Path for output .sanchez file
            title: Video/image title
            creator: Creator name
            use_compression: Use zlib compression
            
        Returns:
            Path to created .sanchez file
        """
        if not frames:
            raise ValueError("No frames provided")
        
        output_path = Path(output_path)
        if output_path.suffix.lower() != '.sanchez':
            output_path = output_path.with_suffix('.sanchez')
        
        # Get dimensions from first frame
        height, width = frames[0].shape[:2]
        
        # Create sanchez file
        sanchez = SanchezFile.create(title, creator, width, height)
        
        for i, frame in enumerate(frames):
            sanchez.add_frame(frame, use_compression=use_compression)
            self._report_progress(i + 1, len(frames), "Encoding frames")
        
        print()  # New line after progress
        
        sanchez.save(str(output_path))
        print(f"Saved: {output_path}")
        
        return str(output_path)
