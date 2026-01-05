#!/usr/bin/env python3
"""
Sanchez Streaming Example

Demonstrates how to stream .sanchez video over network.

Usage:
    # Terminal 1 - Start server
    python streaming_example.py server video.sanchez
    
    # Terminal 2 - Start client
    python streaming_example.py client localhost

For satellite multicast:
    # Terminal 1 - Server
    python streaming_example.py server video.sanchez --multicast
    
    # Terminal 2 - Client  
    python streaming_example.py client 239.0.0.1 --multicast
"""

import sys
import argparse


def run_server(args):
    """Run streaming server"""
    from sanchez import SanchezStreamServer, StreamMode
    
    mode = StreamMode.UDP_MULTICAST if args.multicast else StreamMode.TCP_UNICAST
    host = "239.0.0.1" if args.multicast else "0.0.0.0"
    
    print(f"\n🛸 Sanchez Interdimensional Cable Transmitter")
    print(f"   Mode: {'Multicast (Satellite)' if args.multicast else 'TCP Unicast'}")
    print(f"   Broadcasting on: {host}:{args.port}")
    print(f"   File: {args.input}")
    print(f"\n   Press Ctrl+C to stop\n")
    
    server = SanchezStreamServer(mode=mode)
    server.stream_file(
        args.input,
        host=host,
        port=args.port,
        loop=args.loop,
        satellite_mode=args.satellite
    )


def run_client(args):
    """Run streaming client"""
    from sanchez import SanchezStreamPlayer, SanchezStreamClient, StreamMode
    
    mode = StreamMode.UDP_MULTICAST if args.multicast else StreamMode.TCP_UNICAST
    host = args.host
    
    print(f"\n📺 Sanchez Interdimensional Cable Receiver")
    print(f"   Connecting to: {host}:{args.port}")
    print(f"   Mode: {'Multicast' if args.multicast else 'TCP'}")
    
    if args.output:
        # Record stream to file
        from sanchez import SanchezFile
        
        print(f"   Recording to: {args.output}")
        
        client = SanchezStreamClient(mode=mode)
        sanchez = None
        
        try:
            for frame_idx, frame_array in client.receive_stream(host, args.port):
                if sanchez is None and client.metadata and client.config:
                    sanchez = SanchezFile.create(
                        client.metadata.title + " (recorded)",
                        client.metadata.creator,
                        client.config.width,
                        client.config.height
                    )
                
                if sanchez:
                    sanchez.add_frame(frame_array)
                    print(f"\r   Frame {frame_idx + 1}", end='', flush=True)
        except KeyboardInterrupt:
            print("\n\n   Recording stopped")
        
        if sanchez and sanchez.frame_count > 0:
            sanchez.save(args.output)
            print(f"   Saved {sanchez.frame_count} frames to {args.output}")
            
            stats = client.get_stats()
            print(f"   Stats: {stats}")
    else:
        # Play stream directly
        player = SanchezStreamPlayer(mode=mode, scale=args.scale)
        player.play_stream(host, args.port, fullscreen=args.fullscreen)


def main():
    parser = argparse.ArgumentParser(
        description='Sanchez Streaming Example',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Server command
    server_parser = subparsers.add_parser('server', help='Start streaming server')
    server_parser.add_argument('input', help='.sanchez file to stream')
    server_parser.add_argument('-p', '--port', type=int, default=9999, help='Port (default: 9999)')
    server_parser.add_argument('--multicast', action='store_true', help='Use multicast (for satellite)')
    server_parser.add_argument('--satellite', action='store_true', help='Enable satellite optimizations')
    server_parser.add_argument('--loop', action='store_true', help='Loop continuously')
    
    # Client command
    client_parser = subparsers.add_parser('client', help='Receive and play stream')
    client_parser.add_argument('host', help='Server host or multicast group')
    client_parser.add_argument('-p', '--port', type=int, default=9999, help='Port (default: 9999)')
    client_parser.add_argument('--multicast', action='store_true', help='Join multicast group')
    client_parser.add_argument('-o', '--output', help='Record to .sanchez file')
    client_parser.add_argument('-s', '--scale', type=float, default=1.0, help='Display scale')
    client_parser.add_argument('--fullscreen', action='store_true', help='Fullscreen playback')
    
    args = parser.parse_args()
    
    if args.command == 'server':
        run_server(args)
    elif args.command == 'client':
        run_client(args)
    else:
        parser.print_help()
        print("\nExamples:")
        print("  # Start TCP server:")
        print("  python streaming_example.py server video.sanchez")
        print("")
        print("  # Connect to TCP server:")
        print("  python streaming_example.py client localhost")
        print("")
        print("  # Satellite multicast:")
        print("  python streaming_example.py server video.sanchez --multicast --satellite --loop")
        print("  python streaming_example.py client 239.0.0.1 --multicast")


if __name__ == '__main__':
    main()
