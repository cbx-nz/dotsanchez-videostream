#!/usr/bin/env python3
"""
Sanchez CLI - Command-line interface for .sanchez video format

Interdimensional Cable Video Format for Rick & Morty

Usage:
    python -m sanchez encode <input.mp4> [output.sanchez] [options]
    python -m sanchez decode <input.sanchez> [output.mp4] [options]
    python -m sanchez play <input.sanchez> [options]
    python -m sanchez info <input.sanchez>
    python -m sanchez watch              # Interactive channel selector
    python -m sanchez channels add/remove/list
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


def cmd_live(args):
    """Stream live video feeds"""
    from .live import (
        LiveStreamServer, FeedCapture, VideoFeed, FeedType,
        interactive_feed_picker, stream_video_file, stream_camera, stream_screen
    )
    from .streaming import StreamMode
    
    # Parse resize
    resize = None
    if args.resize:
        parts = args.resize.lower().split('x')
        resize = (int(parts[0]), int(parts[1]))
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    stream_mode = mode_map.get(args.mode.lower(), StreamMode.TCP_UNICAST)
    
    feed = None
    
    # Determine feed source
    if args.input:
        # Video file specified
        from pathlib import Path
        if not Path(args.input).exists():
            print(f"Error: File not found: {args.input}")
            sys.exit(1)
        
        feed = VideoFeed(
            feed_type=FeedType.VIDEO_FILE,
            name=Path(args.input).name,
            description=f"Video file: {args.input}",
            file_path=args.input
        )
    
    elif args.camera is not None:
        # Camera specified
        feed = VideoFeed(
            feed_type=FeedType.CAMERA,
            name=f"Camera {args.camera}",
            description=f"Camera device {args.camera}",
            device_id=args.camera
        )
    
    elif args.screen is not None:
        # Screen capture specified
        name = "All Screens" if args.screen == 0 else f"Screen {args.screen}"
        feed = VideoFeed(
            feed_type=FeedType.SCREEN,
            name=name,
            description=f"Screen capture: {name}",
            monitor_id=args.screen
        )
    
    elif args.window:
        # Window capture specified
        feed = VideoFeed(
            feed_type=FeedType.WINDOW,
            name=args.window[:50],
            description=f"Window: {args.window}",
            window_title=args.window
        )
    
    else:
        # No source specified - show interactive picker
        feed = interactive_feed_picker()
        if feed is None:
            print("No feed selected.")
            sys.exit(0)
    
    # Start streaming
    server = LiveStreamServer(mode=stream_mode)
    
    if feed.feed_type == FeedType.VIDEO_FILE and args.loop:
        # Loop video files
        while True:
            try:
                server.stream_feed(
                    feed,
                    host=args.host,
                    port=args.port,
                    fps=args.fps,
                    resize=resize
                )
                print("\n   Looping video...")
            except KeyboardInterrupt:
                break
    else:
        server.stream_feed(
            feed,
            host=args.host,
            port=args.port,
            fps=args.fps,
            resize=resize
        )


def cmd_channel(args):
    """Stream a playlist of videos like a TV channel"""
    from .playlist import Playlist, PlaylistMode, ChannelServer, create_channel
    from .streaming import StreamMode
    from pathlib import Path
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    stream_mode = mode_map.get(args.mode.lower(), StreamMode.TCP_UNICAST)
    
    playlist_mode_map = {
        'sequential': PlaylistMode.SEQUENTIAL,
        'shuffle': PlaylistMode.SHUFFLE,
        'repeat_one': PlaylistMode.REPEAT_ONE,
        'repeat_all': PlaylistMode.REPEAT_ALL,
        'shuffle_repeat': PlaylistMode.SHUFFLE_REPEAT
    }
    playlist_mode = playlist_mode_map.get(args.playlist_mode.lower(), PlaylistMode.SEQUENTIAL)
    
    # Force shuffle mode if --shuffle flag is used
    if args.shuffle:
        if playlist_mode == PlaylistMode.REPEAT_ALL:
            playlist_mode = PlaylistMode.SHUFFLE_REPEAT
        else:
            playlist_mode = PlaylistMode.SHUFFLE
    
    # Parse resize
    resize = None
    if args.resize:
        parts = args.resize.lower().split('x')
        resize = (int(parts[0]), int(parts[1]))
    
    # Create playlist from input
    playlist = None
    
    if args.playlist:
        # Load from playlist file
        playlist_path = Path(args.playlist)
        if not playlist_path.exists():
            print(f"Error: Playlist file not found: {args.playlist}")
            sys.exit(1)
        
        playlist = Playlist.load(str(playlist_path))
        playlist.mode = playlist_mode
        
    elif args.videos:
        # Create playlist from video files
        playlist = create_channel(
            args.videos,
            name=args.name or "Sanchez Channel",
            mode=playlist_mode
        )
    else:
        print("Error: Specify --playlist file or video files")
        sys.exit(1)
    
    if playlist is None or len(playlist.items) == 0:
        print("Error: No valid videos in playlist")
        sys.exit(1)
    
    # Start channel server
    server = ChannelServer(mode=stream_mode)
    
    print(f"\n{'='*60}")
    print(f"  📺 Sanchez TV Channel")
    print(f"{'='*60}")
    print(f"  Channel:     {playlist.name}")
    print(f"  Videos:      {len(playlist.items)}")
    print(f"  Mode:        {playlist_mode.value}")
    print(f"  Stream:      {args.mode.upper()}")
    print(f"  Host:        {args.host}:{args.port}")
    print(f"{'='*60}")
    print("\n  Now Playing:")
    for i, item in enumerate(playlist.items[:10]):
        prefix = "  ▶" if i == 0 else "   "
        print(f"{prefix} {i+1}. {item.title}")
    if len(playlist.items) > 10:
        print(f"    ... and {len(playlist.items) - 10} more")
    print(f"\n{'='*60}\n")
    
    # Parse overlay color
    overlay_color = (255, 255, 255)  # Default white
    if hasattr(args, 'overlay_color') and args.overlay_color:
        try:
            parts = args.overlay_color.split(',')
            overlay_color = (int(parts[0]), int(parts[1]), int(parts[2]))
        except:
            pass
    
    # Set up text overlay if specified (new method)
    if args.overlay:
        opacity = getattr(args, 'overlay_opacity', 0.8)
        position = getattr(args, 'overlay_position', 'top-left')
        font_size = getattr(args, 'overlay_size', 24)
        server.set_overlay(
            args.overlay,
            position=position,
            opacity=opacity,
            font_size=font_size,
            color=overlay_color
        )
        print(f"  📝 Text overlay: '{args.overlay}' at {position}")
    
    # Legacy watermark support (now just text)
    elif args.watermark:
        opacity = getattr(args, 'watermark_opacity', 0.8)
        # Treat watermark as overlay text
        server.set_overlay(args.watermark, opacity=opacity)
        print(f"  📝 Text overlay: '{args.watermark}'")
    
    # Set up per-video text overlays
    if args.video_overlays:
        for vo in args.video_overlays:
            parts = vo.split(':', 1)
            if len(parts) == 2:
                video_pattern, text = parts
                server.set_video_overlay(video_pattern, text)
                print(f"  📝 Video overlay for '{video_pattern}': '{text}'")
    
    # Legacy video watermarks (now text overlays)
    elif args.video_watermarks:
        for vw in args.video_watermarks:
            parts = vw.split(':', 1)
            if len(parts) == 2:
                video_pattern, text = parts
                server.set_video_overlay(video_pattern, text)
    
    # Set up PNG logo overlay if specified
    if args.logo:
        logo_path = Path(args.logo)
        if logo_path.exists():
            logo_position = getattr(args, 'logo_position', 'top-left')
            logo_opacity = getattr(args, 'logo_opacity', 0.8)
            logo_scale = getattr(args, 'logo_scale', 1.0)
            server.add_logo(
                str(logo_path),
                position=logo_position,
                opacity=logo_opacity,
                scale=logo_scale
            )
            print(f"  🖼️  PNG logo: '{args.logo}' at {logo_position}")
        else:
            print(f"  ⚠️  Logo not found: {args.logo}")
    
    # Set up per-video PNG logos
    if args.video_logos:
        for vl in args.video_logos:
            parts = vl.split(':', 1)
            if len(parts) == 2:
                video_pattern, logo_path = parts
                if Path(logo_path).exists():
                    server.add_video_logo(video_pattern, logo_path)
                    print(f"  🖼️  Video logo for '{video_pattern}': '{logo_path}'")
                else:
                    print(f"  ⚠️  Logo not found for '{video_pattern}': {logo_path}")
    
    server.stream_playlist(
        playlist,
        host=args.host,
        port=args.port,
        queue_file=args.queue_file
    )


def cmd_channels(args):
    """Manage saved channels"""
    from .channels import (
        ChannelGuide, SavedChannel, 
        cmd_add_channel, cmd_remove_channel, cmd_favorite_channel,
        list_channels_display, add_channel_interactive
    )
    
    if args.channels_command == 'add':
        if args.name and args.host:
            cmd_add_channel(
                name=args.name,
                host=args.host,
                port=args.port,
                mode=args.mode,
                description=args.description or '',
                favorite=args.favorite
            )
        else:
            # Interactive add
            add_channel_interactive()
    
    elif args.channels_command == 'remove':
        if args.name:
            cmd_remove_channel(args.name)
        else:
            print("Error: Specify channel name to remove")
            sys.exit(1)
    
    elif args.channels_command == 'list':
        list_channels_display()
    
    elif args.channels_command == 'favorite':
        if args.name:
            cmd_favorite_channel(args.name, not args.unfavorite)
        else:
            print("Error: Specify channel name")
            sys.exit(1)
    
    else:
        list_channels_display()


def cmd_watch(args):
    """Watch a channel - interactive selector or by name"""
    from .channels import ChannelGuide, interactive_channel_selector
    from .streaming import SanchezStreamClient, SanchezStreamPlayer, StreamMode
    
    guide = ChannelGuide()
    
    # Get channel - either by name/number or interactive selection
    channel = None
    
    if args.channel:
        # Try to get by name first
        channel = guide.get(args.channel)
        
        # Try as number
        if channel is None:
            try:
                idx = int(args.channel)
                channel = guide.get_by_index(idx)
            except ValueError:
                pass
        
        if channel is None:
            print(f"Error: Channel not found: {args.channel}")
            print("Use 'python -m sanchez channels list' to see saved channels")
            sys.exit(1)
    else:
        # Interactive selector
        channel = interactive_channel_selector(guide)
        if channel is None:
            sys.exit(0)
    
    # Connect to channel
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    stream_mode = mode_map.get(channel.mode.lower(), StreamMode.TCP_UNICAST)
    
    print(f"\n📺 Tuning to: {channel.name}")
    print(f"   {channel.connection_string()}")
    print()
    
    guide.update_last_watched(channel.name)
    
    if args.output:
        # Save stream to file
        from .format import SanchezFile
        
        client = SanchezStreamClient(mode=stream_mode)
        sanchez = None
        
        print(f"Recording to: {args.output}")
        
        for frame_idx, frame_array in client.receive_stream(channel.host, channel.port):
            if sanchez is None and client.metadata and client.config:
                sanchez = SanchezFile.create(
                    client.metadata.title + " (recorded)",
                    client.metadata.creator,
                    client.config.width,
                    client.config.height
                )
            
            if sanchez:
                sanchez.add_frame(frame_array)
                print(f"\rRecorded frame {frame_idx + 1}", end='', flush=True)
        
        if sanchez:
            sanchez.save(args.output)
            print(f"\nSaved to: {args.output}")
            
            if client.audio_data:
                audio_path = Path(args.output).with_suffix('.mp3')
                with open(audio_path, 'wb') as f:
                    f.write(client.audio_data)
                print(f"Saved audio to: {audio_path}")
    else:
        # Play stream directly
        player = SanchezStreamPlayer(mode=stream_mode, scale=args.scale)
        player.play_stream(
            channel.host,
            channel.port,
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

Live Streaming Examples:
  Interactive feed picker: python -m sanchez live
  Stream MP4 directly:     python -m sanchez live video.mp4
  Stream camera:           python -m sanchez live --camera 0
  Stream screen:           python -m sanchez live --screen 0
  Stream all screens:      python -m sanchez live --screen

TV Channel Examples:
  Stream playlist file:    python -m sanchez channel --playlist videos.m3u
  Stream multiple videos:  python -m sanchez channel video1.sanchez video2.mp4 video3.sanchez
  Shuffle mode:            python -m sanchez channel --playlist tv.m3u --shuffle
  Repeat all:              python -m sanchez channel *.sanchez --playlist-mode repeat_all
  Named channel:           python -m sanchez channel --playlist tv.m3u -n "Rick's TV"

Channel Guide (Receiver):
  Add a channel:           python -m sanchez channels add "Rick's TV" 192.168.1.100 9999
  Add multicast channel:   python -m sanchez channels add "Sat TV" 239.0.0.1 9999 -m multicast
  List saved channels:     python -m sanchez channels list
  Remove a channel:        python -m sanchez channels remove "Rick's TV"
  Watch (interactive):     python -m sanchez watch
  Watch by name:           python -m sanchez watch "Rick's TV"
  Watch by number:         python -m sanchez watch 1
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
    
    # Live streaming command
    live_parser = subparsers.add_parser('live', help='Stream live video feeds (camera, screen, video file)')
    live_parser.add_argument('input', nargs='?', help='Video file to stream (or use --camera/--screen)')
    live_parser.add_argument('--camera', type=int, nargs='?', const=0, metavar='ID',
                             help='Stream from camera (default: 0)')
    live_parser.add_argument('--screen', type=int, nargs='?', const=0, metavar='ID',
                             help='Stream screen capture (default: 0 = all screens)')
    live_parser.add_argument('--window', type=str, metavar='TITLE',
                             help='Stream a specific window by title')
    live_parser.add_argument('-H', '--host', default='0.0.0.0', help='Host/IP to bind (default: 0.0.0.0)')
    live_parser.add_argument('-p', '--port', type=int, default=9999, help='Port number (default: 9999)')
    live_parser.add_argument('-m', '--mode', default='tcp',
                             choices=['tcp', 'udp', 'multicast', 'broadcast'],
                             help='Streaming mode (default: tcp)')
    live_parser.add_argument('--fps', type=int, default=24, help='Frames per second (default: 24)')
    live_parser.add_argument('-r', '--resize', help='Resize to WxH (e.g., 1280x720)')
    live_parser.add_argument('--loop', action='store_true', help='Loop video file')
    
    # Channel/playlist command
    channel_parser = subparsers.add_parser('channel', help='Stream a playlist like a TV channel')
    channel_parser.add_argument('videos', nargs='*', help='Video files to stream (.sanchez or .mp4)')
    channel_parser.add_argument('--playlist', '-P', help='Playlist file (.m3u, .json, .txt, .pls)')
    channel_parser.add_argument('-n', '--name', help='Channel name')
    channel_parser.add_argument('--shuffle', action='store_true', help='Shuffle playlist order')
    channel_parser.add_argument('--playlist-mode', default='sequential',
                                choices=['sequential', 'shuffle', 'repeat_one', 'repeat_all', 'shuffle_repeat'],
                                help='Playlist mode (default: sequential)')
    channel_parser.add_argument('-H', '--host', default='0.0.0.0', help='Host/IP to bind (default: 0.0.0.0)')
    channel_parser.add_argument('-p', '--port', type=int, default=9999, help='Port number (default: 9999)')
    channel_parser.add_argument('-m', '--mode', default='tcp',
                                choices=['tcp', 'udp', 'multicast', 'broadcast'],
                                help='Streaming mode (default: tcp)')
    channel_parser.add_argument('--fps', type=int, default=24, help='Frames per second for live conversion (default: 24)')
    channel_parser.add_argument('-r', '--resize', help='Resize to WxH (e.g., 1280x720)')
    
    # Text overlay options (replaces watermark)
    channel_parser.add_argument('--overlay', '-o', help='Text overlay for channel branding (e.g., "SPORTS TV")')
    channel_parser.add_argument('--overlay-position', default='top-left',
                                choices=['top-left', 'top-right', 'bottom-left', 'bottom-right', 'center', 'top-center', 'bottom-center'],
                                help='Overlay position (default: top-left)')
    channel_parser.add_argument('--overlay-opacity', type=float, default=0.8, 
                                help='Overlay opacity 0.0-1.0 (default: 0.8)')
    channel_parser.add_argument('--overlay-size', type=int, default=24,
                                help='Overlay font size (default: 24)')
    channel_parser.add_argument('--overlay-color', default='255,255,255',
                                help='Overlay color as R,G,B (default: 255,255,255 for white)')
    channel_parser.add_argument('--video-overlays', nargs='*', metavar='PATTERN:TEXT',
                                help='Per-video text overlays (e.g., "sports*.mp4:LIVE SPORTS" "news.sanchez:BREAKING NEWS")')
    
    # PNG logo overlay options
    channel_parser.add_argument('--logo', '-l', help='PNG logo overlay with transparency')
    channel_parser.add_argument('--logo-position', default='top-left',
                                choices=['top-left', 'top-right', 'bottom-left', 'bottom-right', 'center', 'top-center', 'bottom-center'],
                                help='Logo position (default: top-left)')
    channel_parser.add_argument('--logo-opacity', type=float, default=0.8,
                                help='Logo opacity 0.0-1.0 (default: 0.8)')
    channel_parser.add_argument('--logo-scale', type=float, default=1.0,
                                help='Logo scale factor (default: 1.0)')
    channel_parser.add_argument('--video-logos', nargs='*', metavar='PATTERN:PATH',
                                help='Per-video PNG logos (e.g., "sports*.mp4:sports_logo.png")')
    
    channel_parser.add_argument('--queue-file', '-q', help='File to watch for adding videos to queue (one path per line)')
    
    # Legacy watermark support (now just maps to overlay)
    channel_parser.add_argument('--watermark', '-w', help='[DEPRECATED] Use --overlay or --logo instead')
    channel_parser.add_argument('--watermark-opacity', type=float, help='[DEPRECATED] Use --overlay-opacity instead')
    channel_parser.add_argument('--video-watermarks', nargs='*', help='[DEPRECATED] Use --video-overlays instead')
    
    # Channels management command (for receivers)
    channels_parser = subparsers.add_parser('channels', help='Manage saved channels (add, remove, list)')
    channels_subparsers = channels_parser.add_subparsers(dest='channels_command', help='Channel management commands')
    
    # channels add
    ch_add = channels_subparsers.add_parser('add', help='Add a new channel')
    ch_add.add_argument('name', nargs='?', help='Channel name')
    ch_add.add_argument('host', nargs='?', help='Host/IP address or multicast group')
    ch_add.add_argument('port', type=int, nargs='?', default=9999, help='Port number (default: 9999)')
    ch_add.add_argument('-m', '--mode', default='tcp',
                        choices=['tcp', 'udp', 'multicast', 'broadcast'],
                        help='Streaming mode (default: tcp)')
    ch_add.add_argument('-d', '--description', help='Channel description')
    ch_add.add_argument('-f', '--favorite', action='store_true', help='Mark as favorite')
    
    # channels remove
    ch_remove = channels_subparsers.add_parser('remove', help='Remove a channel')
    ch_remove.add_argument('name', help='Channel name to remove')
    
    # channels list
    channels_subparsers.add_parser('list', help='List all saved channels')
    
    # channels favorite
    ch_fav = channels_subparsers.add_parser('favorite', help='Toggle channel favorite status')
    ch_fav.add_argument('name', help='Channel name')
    ch_fav.add_argument('-u', '--unfavorite', action='store_true', help='Remove from favorites')
    
    # Watch command - interactive channel selector
    watch_parser = subparsers.add_parser('watch', help='Watch a saved channel (interactive selector)')
    watch_parser.add_argument('channel', nargs='?', help='Channel name or number (omit for interactive selector)')
    watch_parser.add_argument('-o', '--output', help='Record stream to .sanchez file')
    watch_parser.add_argument('-s', '--scale', type=float, default=1.0, help='Display scale')
    watch_parser.add_argument('--fullscreen', action='store_true', help='Fullscreen playback')
    
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
    elif args.command == 'live':
        cmd_live(args)
    elif args.command == 'channel':
        cmd_channel(args)
    elif args.command == 'channels':
        cmd_channels(args)
    elif args.command == 'watch':
        cmd_watch(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
