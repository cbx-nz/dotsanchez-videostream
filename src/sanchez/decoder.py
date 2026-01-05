"""
Decoder module - Convert .sanchez files back to standard video formats (MP4)

Uses OpenCV for video writing and ffmpeg for audio muxing.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Callable
import cv2
import numpy as np

from .format import SanchezFile


class SanchezDecoder:
    """
    Decode .sanchez files back to standard video formats.
    
    Usage:
        decoder = SanchezDecoder()
        decoder.decode("input.sanchez", "output.mp4", audio_path="input.mp3")
    """
    
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
            percent = (current / total * 100) if total > 0 else 0
            print(f"\r[{percent:5.1f}%] {message}: {current}/{total}", end='', flush=True)
    
    def decode(
        self,
        input_path: str,
        output_path: str,
        audio_path: Optional[str] = None,
        resize: Optional[tuple] = None
    ) -> str:
        """
        Decode a .sanchez file to MP4 format.
        
        Args:
            input_path: Path to .sanchez file
            output_path: Path for output video file
            audio_path: Optional path to audio file (MP3) to mux in
            resize: Optional (width, height) to resize output
            
        Returns:
            Path to created video file
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Ensure output has .mp4 extension
        if output_path.suffix.lower() != '.mp4':
            output_path = output_path.with_suffix('.mp4')
        
        # Load sanchez file
        print(f"Loading: {input_path}")
        sanchez = SanchezFile.load(str(input_path))
        print(f"  Title: {sanchez.metadata.title}")
        print(f"  Size: {sanchez.config.width}x{sanchez.config.height}")
        print(f"  Frames: {sanchez.frame_count}")
        print(f"  Duration: {sanchez.metadata.seconds:.2f}s")
        
        # Determine output dimensions
        out_width = resize[0] if resize else sanchez.config.width
        out_height = resize[1] if resize else sanchez.config.height
        
        # Check if audio file exists
        if audio_path is None:
            # Try to find audio file with same name as sanchez file
            auto_audio_path = input_path.with_suffix('.mp3')
            if auto_audio_path.exists():
                audio_path = str(auto_audio_path)
                print(f"  Found audio: {audio_path}")
        
        # Create temporary video file (without audio) if we need to add audio later
        if audio_path and os.path.exists(audio_path):
            temp_video_path = str(output_path.with_suffix('.temp.mp4'))
            final_output_path = str(output_path)
        else:
            temp_video_path = str(output_path)
            final_output_path = str(output_path)
        
        # Set up video writer
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(
            temp_video_path,
            fourcc,
            sanchez.config.fps,
            (out_width, out_height)
        )
        
        if not writer.isOpened():
            raise RuntimeError("Could not create video writer")
        
        try:
            # Write frames
            for i, frame in enumerate(sanchez.get_frames()):
                # Resize if needed
                if resize:
                    frame = cv2.resize(frame, (out_width, out_height), interpolation=cv2.INTER_LANCZOS4)
                
                # Convert RGB to BGR for OpenCV
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                writer.write(frame_bgr)
                self._report_progress(i + 1, sanchez.frame_count, "Decoding frames")
            
            print()  # New line after progress
            
        finally:
            writer.release()
        
        # Mux audio if provided
        if audio_path and os.path.exists(audio_path):
            print("Adding audio...")
            success = self._mux_audio(temp_video_path, audio_path, final_output_path)
            
            # Clean up temp file
            if os.path.exists(temp_video_path) and temp_video_path != final_output_path:
                os.remove(temp_video_path)
            
            if not success:
                print("Warning: Could not add audio. Video saved without audio.")
                # Rename temp to final if mux failed
                if os.path.exists(temp_video_path):
                    os.rename(temp_video_path, final_output_path)
        
        print(f"Saved: {final_output_path}")
        return final_output_path
    
    def _mux_audio(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """
        Combine video and audio using ffmpeg.
        
        Args:
            video_path: Path to video file (no audio)
            audio_path: Path to audio file
            output_path: Path for output file with audio
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-shortest',  # Match duration to shortest stream
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            return result.returncode == 0
            
        except FileNotFoundError:
            print("Warning: ffmpeg not found. Cannot add audio.")
            return False
        except Exception as e:
            print(f"Warning: Audio muxing failed: {e}")
            return False
    
    def decode_to_image(
        self,
        input_path: str,
        output_path: str,
        frame_index: int = 0,
        resize: Optional[tuple] = None
    ) -> str:
        """
        Extract a single frame from .sanchez file as an image.
        
        Args:
            input_path: Path to .sanchez file
            output_path: Path for output image file
            frame_index: Which frame to extract (0-indexed)
            resize: Optional (width, height) to resize
            
        Returns:
            Path to created image file
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Load sanchez file
        sanchez = SanchezFile.load(str(input_path))
        
        if frame_index >= sanchez.frame_count:
            raise IndexError(f"Frame index {frame_index} out of range (max: {sanchez.frame_count - 1})")
        
        # Get frame
        frame = sanchez.get_frame(frame_index)
        
        # Resize if needed
        if resize:
            frame = cv2.resize(frame, resize, interpolation=cv2.INTER_LANCZOS4)
        
        # Convert RGB to BGR for OpenCV
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        
        # Save image
        cv2.imwrite(str(output_path), frame_bgr)
        print(f"Saved frame {frame_index}: {output_path}")
        
        return str(output_path)
    
    def extract_all_frames(
        self,
        input_path: str,
        output_dir: str,
        format: str = 'png',
        resize: Optional[tuple] = None
    ) -> list:
        """
        Extract all frames from .sanchez file as individual images.
        
        Args:
            input_path: Path to .sanchez file
            output_dir: Directory to save frames
            format: Image format (png, jpg, bmp)
            resize: Optional (width, height) to resize
            
        Returns:
            List of paths to created images
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load sanchez file
        sanchez = SanchezFile.load(str(input_path))
        
        created_files = []
        
        for i, frame in enumerate(sanchez.get_frames()):
            # Resize if needed
            if resize:
                frame = cv2.resize(frame, resize, interpolation=cv2.INTER_LANCZOS4)
            
            # Convert RGB to BGR for OpenCV
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            # Save frame
            frame_path = output_dir / f"frame_{i:07d}.{format}"
            cv2.imwrite(str(frame_path), frame_bgr)
            created_files.append(str(frame_path))
            
            self._report_progress(i + 1, sanchez.frame_count, "Extracting frames")
        
        print()  # New line after progress
        print(f"Extracted {len(created_files)} frames to: {output_dir}")
        
        return created_files
    
    def get_info(self, input_path: str) -> dict:
        """
        Get information about a .sanchez file without fully decoding it.
        
        Args:
            input_path: Path to .sanchez file
            
        Returns:
            Dictionary with file information
        """
        input_path = Path(input_path)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        # Load just the header info
        sanchez = SanchezFile.load(str(input_path))
        
        # Calculate file size
        file_size = input_path.stat().st_size
        
        return {
            "title": sanchez.metadata.title,
            "creator": sanchez.metadata.creator,
            "created_at": sanchez.metadata.created_at,
            "duration_seconds": sanchez.metadata.seconds,
            "width": sanchez.config.width,
            "height": sanchez.config.height,
            "frame_count": sanchez.frame_count,
            "fps": sanchez.config.fps,
            "is_image": sanchez.is_image,
            "file_size_bytes": file_size,
            "file_size_mb": file_size / (1024 * 1024)
        }
