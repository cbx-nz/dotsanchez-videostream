#!/usr/bin/env python3
"""
Example usage of the Sanchez video format encoder/decoder.

This script demonstrates how to:
1. Create a simple test video
2. Encode it to .sanchez format
3. Read it back and show info
4. Decode it back to MP4
"""

import numpy as np
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent))

from sanchez import SanchezFile, SanchezEncoder, SanchezDecoder


def create_test_pattern(width: int, height: int, frame_num: int) -> np.ndarray:
    """Create a colorful test pattern that changes each frame"""
    # Create gradient background
    x = np.linspace(0, 1, width)
    y = np.linspace(0, 1, height)
    xx, yy = np.meshgrid(x, y)
    
    # Animate the pattern
    t = frame_num / 24  # Time in seconds
    
    # RGB channels with different patterns
    r = ((np.sin(xx * 4 + t * 2) + 1) / 2 * 255).astype(np.uint8)
    g = ((np.sin(yy * 4 + t * 3) + 1) / 2 * 255).astype(np.uint8)
    b = ((np.sin((xx + yy) * 4 + t * 4) + 1) / 2 * 255).astype(np.uint8)
    
    # Stack into RGB image
    frame = np.stack([r, g, b], axis=2)
    
    return frame


def example_create_sanchez():
    """Example: Create a .sanchez file from scratch"""
    print("=" * 60)
    print("Example 1: Creating a .sanchez file from scratch")
    print("=" * 60)
    
    # Create a 320x240 video with 48 frames (2 seconds at 24fps)
    width, height = 320, 240
    num_frames = 48
    
    # Create sanchez file
    sanchez = SanchezFile.create(
        title="TestPattern",
        creator="cbx",
        width=width,
        height=height
    )
    
    print(f"Creating {width}x{height} video with {num_frames} frames...")
    
    # Add frames
    for i in range(num_frames):
        frame = create_test_pattern(width, height, i)
        sanchez.add_frame(frame)
        print(f"\rAdding frame {i + 1}/{num_frames}", end='')
    
    print()
    
    # Save
    output_path = "test_output/test_pattern.sanchez"
    Path("test_output").mkdir(exist_ok=True)
    sanchez.save(output_path)
    
    print(f"Saved: {output_path}")
    print(f"File info: {sanchez}")
    
    return output_path


def example_read_sanchez(sanchez_path: str):
    """Example: Read and display info about a .sanchez file"""
    print("\n" + "=" * 60)
    print("Example 2: Reading .sanchez file info")
    print("=" * 60)
    
    decoder = SanchezDecoder()
    info = decoder.get_info(sanchez_path)
    
    print(f"Title:      {info['title']}")
    print(f"Creator:    {info['creator']}")
    print(f"Created:    {info['created_at']}")
    print(f"Resolution: {info['width']}x{info['height']}")
    print(f"Frames:     {info['frame_count']}")
    print(f"Duration:   {info['duration_seconds']:.2f}s")
    print(f"File size:  {info['file_size_mb']:.3f} MB")
    
    # Calculate compression ratio
    uncompressed_size = info['width'] * info['height'] * 3 * info['frame_count']  # bytes
    compression_ratio = uncompressed_size / info['file_size_bytes']
    print(f"Compression: {compression_ratio:.1f}x")


def example_decode_sanchez(sanchez_path: str):
    """Example: Decode .sanchez back to MP4"""
    print("\n" + "=" * 60)
    print("Example 3: Decoding .sanchez to MP4")
    print("=" * 60)
    
    decoder = SanchezDecoder()
    
    output_path = sanchez_path.replace('.sanchez', '_decoded.mp4')
    decoder.decode(sanchez_path, output_path)
    
    return output_path


def example_extract_frame(sanchez_path: str):
    """Example: Extract a single frame as an image"""
    print("\n" + "=" * 60)
    print("Example 4: Extracting a single frame")
    print("=" * 60)
    
    decoder = SanchezDecoder()
    
    output_path = sanchez_path.replace('.sanchez', '_frame_0.png')
    decoder.decode_to_image(sanchez_path, output_path, frame_index=0)
    
    return output_path


def example_encode_video():
    """Example: Encode an existing video to .sanchez"""
    print("\n" + "=" * 60)
    print("Example 5: Encoding an existing video")
    print("=" * 60)
    
    print("To encode an existing video, use:")
    print("  encoder = SanchezEncoder()")
    print("  encoder.encode('input.mp4', 'output.sanchez')")
    print("")
    print("Or from command line:")
    print("  python -m sanchez encode input.mp4 output.sanchez")


def main():
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   .sanchez - Interdimensional Cable Video Format          ║
    ║                                                           ║
    ║   "Nobody exists on purpose. Nobody belongs anywhere.     ║
    ║    Everybody's gonna die. Come watch TV."                 ║
    ║                                              - Morty      ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Run examples
    try:
        # Create a test .sanchez file
        sanchez_path = example_create_sanchez()
        
        # Read info
        example_read_sanchez(sanchez_path)
        
        # Extract a frame
        example_extract_frame(sanchez_path)
        
        # Decode to video
        example_decode_sanchez(sanchez_path)
        
        # Show encoding example
        example_encode_video()
        
        print("\n" + "=" * 60)
        print("All examples completed! Check the test_output folder.")
        print("=" * 60)
        
    except ImportError as e:
        print(f"\nMissing dependency: {e}")
        print("Install requirements with: pip install -r requirements.txt")
    except Exception as e:
        print(f"\nError: {e}")
        raise


if __name__ == '__main__':
    main()
