#!/usr/bin/env python3
"""
Sanchez CLI - Command-line interface for .sanchez video format

Interdimensional Cable Video Format for Rick & Morty

Usage:
    python -m sanchez encode <input.mp4> [output.sanchez] [options]
    python -m sanchez decode <input.sanchez> [output.mp4] [options]
    python -m sanchez play <input.sanchez> [options]
    python -m sanchez info <input.sanchez>
    python -m sanchez image <input.png> [output.sanchez]
"""

import argparse
import sys
from pathlib import Path


def cmd_encode(args):
    """Encode a video/image to .sanchez format"""
    from .encoder import SanchezEncoder
    
    encoder = SanchezEncoder()
    
    input_path = Path(args.input)
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = str(input_path.with_suffix('.sanchez'))
    
    # Parse resize option
    resize = None
    if args.resize:
        parts = args.resize.lower().split('x')
        resize = (int(parts[0]), int(parts[1]))
    
    # Check if input is image or video
    image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff'}
    
    if input_path.suffix.lower() in image_extensions:
        encoder.encode_image(
            str(input_path),
            output_path,
            title=args.title,
            creator=args.creator,
            resize=resize
        )
    else:
        encoder.encode(
            str(input_path),
            output_path,
            title=args.title,
            creator=args.creator,
            resize=resize,
            max_frames=args.max_frames,
            use_compression=not args.no_compression
        )


def cmd_decode(args):
    """Decode a .sanchez file to video/image"""
    from .decoder import SanchezDecoder
    
    decoder = SanchezDecoder()
    
    input_path = Path(args.input)
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = str(input_path.with_suffix('.mp4'))
    
    # Parse resize option
    resize = None
    if args.resize:
        parts = args.resize.lower().split('x')
        resize = (int(parts[0]), int(parts[1]))
    
    # Check if extracting to image or video
    if args.frame is not None:
        # Extract single frame as image
        if not args.output:
            output_path = str(input_path.with_suffix('.png'))
        decoder.decode_to_image(
            str(input_path),
            output_path,
            frame_index=args.frame,
            resize=resize
        )
    elif args.frames:
        # Extract all frames
        output_dir = args.output if args.output else str(input_path.with_suffix('')) + '_frames'
        decoder.extract_all_frames(
            str(input_path),
            output_dir,
            format=args.format or 'png',
            resize=resize
        )
    else:
        # Decode to video
        decoder.decode(
            str(input_path),
            output_path,
            audio_path=args.audio,
            resize=resize
        )


def cmd_play(args):
    """Play a .sanchez file"""
    from .player import SanchezPlayer, SimplePlayer
    
    if args.simple:
        player = SimplePlayer()
        player.view(args.input, frame_index=args.start_frame or 0)
    else:
        try:
            player = SanchezPlayer(scale=args.scale)
            player.play(
                args.input,
                audio_path=args.audio,
                start_frame=args.start_frame or 0,
                fullscreen=args.fullscreen
            )
        except ImportError:
            print("pygame not available, using simple viewer...")
            player = SimplePlayer()
            player.view(args.input, frame_index=args.start_frame or 0)


def cmd_info(args):
    """Show info about a .sanchez file"""
    from .decoder import SanchezDecoder
    
    decoder = SanchezDecoder()
    info = decoder.get_info(args.input)
    
    print(f"\n{'='*50}")
    print(f"  .sanchez File Info")
    print(f"{'='*50}")
    print(f"  Title:       {info['title']}")
    print(f"  Creator:     {info['creator']}")
    print(f"  Created:     {info['created_at']}")
    print(f"  Type:        {'Image' if info['is_image'] else 'Video'}")
    print(f"  Resolution:  {info['width']}x{info['height']}")
    print(f"  Frames:      {info['frame_count']}")
    print(f"  FPS:         {info['fps']}")
    print(f"  Duration:    {info['duration_seconds']:.2f} seconds")
    print(f"  File Size:   {info['file_size_mb']:.2f} MB")
    print(f"{'='*50}\n")


def cmd_stream_serve(args):
    """Stream a .sanchez file over network"""
    from .streaming import SanchezStreamServer, StreamMode
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    stream_mode = mode_map.get(args.mode.lower(), StreamMode.TCP_UNICAST)
    
    server = SanchezStreamServer(mode=stream_mode)
    
    print(f"\n{'='*50}")
    print(f"  Sanchez Stream Server")
    print(f"{'='*50}")
    print(f"  Mode:      {args.mode.upper()}")
    print(f"  Host:      {args.host}")
    print(f"  Port:      {args.port}")
    print(f"  Satellite: {'Yes' if args.satellite else 'No'}")
    print(f"  Loop:      {'Yes' if args.loop else 'No'}")
    print(f"{'='*50}\n")
    
    server.stream_file(
        args.input,
        host=args.host,
        port=args.port,
        loop=args.loop,
        satellite_mode=args.satellite,
        audio_path=getattr(args, 'audio', None)
    )


def cmd_stream_receive(args):
    """Receive a .sanchez stream"""
    from .streaming import SanchezStreamClient, SanchezStreamPlayer, StreamMode
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    stream_mode = mode_map.get(args.mode.lower(), StreamMode.TCP_UNICAST)
    
    if args.output:
        # Save stream to file
        from .format import SanchezFile
        from pathlib import Path
        
        client = SanchezStreamClient(mode=stream_mode)
        sanchez = None
        
        print(f"Receiving stream from {args.host}:{args.port}...")
        print(f"Saving to: {args.output}")
        
        for frame_idx, frame_array in client.receive_stream(args.host, args.port):
            if sanchez is None and client.metadata and client.config:
                sanchez = SanchezFile.create(
                    client.metadata.title + " (stream)",
                    client.metadata.creator,
                    client.config.width,
                    client.config.height
                )
            
            if sanchez:
                sanchez.add_frame(frame_array)
                print(f"\rReceived frame {frame_idx + 1}", end='', flush=True)
        
        if sanchez:
            sanchez.save(args.output)
            print(f"\nSaved to: {args.output}")
            
            # Also save audio if received
            if client.audio_data:
                audio_path = Path(args.output).with_suffix('.mp3')
                with open(audio_path, 'wb') as f:
                    f.write(client.audio_data)
                print(f"Saved audio to: {audio_path}")
    else:
        # Play stream directly
        player = SanchezStreamPlayer(mode=stream_mode, scale=args.scale)
        player.play_stream(
            args.host,
            args.port,
            fullscreen=args.fullscreen
        )


def main():
    parser = argparse.ArgumentParser(
        description='Sanchez - Interdimensional Cable Video Format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Encode video:     python -m sanchez encode video.mp4 output.sanchez
  Encode image:     python -m sanchez encode image.png output.sanchez
  Decode to video:  python -m sanchez decode input.sanchez output.mp4
  Extract frame:    python -m sanchez decode input.sanchez -f 0 -o frame.png
  Play video:       python -m sanchez play video.sanchez
  Get info:         python -m sanchez info video.sanchez

  Resize on encode: python -m sanchez encode video.mp4 -r 640x480
  With audio:       python -m sanchez decode video.sanchez -a video.mp3

Streaming Examples:
  Start TCP server:       python -m sanchez serve video.sanchez
  Start UDP multicast:    python -m sanchez serve video.sanchez -m multicast -H 239.0.0.1
  Satellite broadcast:    python -m sanchez serve video.sanchez -m multicast --satellite --loop
  Receive and play:       python -m sanchez receive 192.168.1.100 9999
  Receive multicast:      python -m sanchez receive 239.0.0.1 9999 -m multicast
  Save stream to file:    python -m sanchez receive 192.168.1.100 9999 -o recorded.sanchez
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Encode command
    encode_parser = subparsers.add_parser('encode', help='Encode video/image to .sanchez')
    encode_parser.add_argument('input', help='Input video or image file')
    encode_parser.add_argument('output', nargs='?', help='Output .sanchez file')
    encode_parser.add_argument('-t', '--title', help='Video title')
    encode_parser.add_argument('-c', '--creator', default='cbx', help='Creator name')
    encode_parser.add_argument('-r', '--resize', help='Resize to WxH (e.g., 1280x720)')
    encode_parser.add_argument('-m', '--max-frames', type=int, help='Maximum frames to encode')
    encode_parser.add_argument('--no-compression', action='store_true', help='Disable compression')
    
    # Decode command
    decode_parser = subparsers.add_parser('decode', help='Decode .sanchez to video/image')
    decode_parser.add_argument('input', help='Input .sanchez file')
    decode_parser.add_argument('output', nargs='?', help='Output video/image file')
    decode_parser.add_argument('-a', '--audio', help='Audio file to mux')
    decode_parser.add_argument('-r', '--resize', help='Resize to WxH (e.g., 1280x720)')
    decode_parser.add_argument('-f', '--frame', type=int, help='Extract single frame (0-indexed)')
    decode_parser.add_argument('--frames', action='store_true', help='Extract all frames')
    decode_parser.add_argument('--format', choices=['png', 'jpg', 'bmp'], help='Frame format')
    
    # Play command
    play_parser = subparsers.add_parser('play', help='Play .sanchez file')
    play_parser.add_argument('input', help='Input .sanchez file')
    play_parser.add_argument('-a', '--audio', help='Audio file to play')
    play_parser.add_argument('-s', '--scale', type=float, default=1.0, help='Display scale')
    play_parser.add_argument('--start-frame', type=int, help='Start from frame')
    play_parser.add_argument('--fullscreen', action='store_true', help='Start in fullscreen')
    play_parser.add_argument('--simple', action='store_true', help='Use simple viewer (no pygame)')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show .sanchez file info')
    info_parser.add_argument('input', help='Input .sanchez file')
    
    # Stream serve command
    serve_parser = subparsers.add_parser('serve', help='Stream .sanchez file over network')
    serve_parser.add_argument('input', help='Input .sanchez file to stream')
    serve_parser.add_argument('-a', '--audio', help='Audio file to stream (auto-detects .mp3 with same name)')
    serve_parser.add_argument('-H', '--host', default='0.0.0.0', help='Host/IP to bind (default: 0.0.0.0)')
    serve_parser.add_argument('-p', '--port', type=int, default=9999, help='Port number (default: 9999)')
    serve_parser.add_argument('-m', '--mode', default='tcp', 
                              choices=['tcp', 'udp', 'multicast', 'broadcast'],
                              help='Streaming mode (default: tcp)')
    serve_parser.add_argument('--loop', action='store_true', help='Loop video continuously')
    serve_parser.add_argument('--satellite', action='store_true', 
                              help='Enable satellite mode (smaller packets, more FEC)')
    
    # Stream receive command
    receive_parser = subparsers.add_parser('receive', help='Receive .sanchez stream')
    receive_parser.add_argument('host', help='Server host or multicast group')
    receive_parser.add_argument('port', type=int, nargs='?', default=9999, help='Port number (default: 9999)')
    receive_parser.add_argument('-m', '--mode', default='tcp',
                                choices=['tcp', 'udp', 'multicast', 'broadcast'],
                                help='Streaming mode (default: tcp)')
    receive_parser.add_argument('-o', '--output', help='Save stream to .sanchez file')
    receive_parser.add_argument('-s', '--scale', type=float, default=1.0, help='Display scale')
    receive_parser.add_argument('--fullscreen', action='store_true', help='Fullscreen playback')
    
    args = parser.parse_args()
    
    if args.command == 'encode':
        cmd_encode(args)
    elif args.command == 'decode':
        cmd_decode(args)
    elif args.command == 'play':
        cmd_play(args)
    elif args.command == 'info':
        cmd_info(args)
    elif args.command == 'serve':
        cmd_stream_serve(args)
    elif args.command == 'receive':
        cmd_stream_receive(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
