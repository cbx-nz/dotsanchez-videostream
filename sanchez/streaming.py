"""
Sanchez Streaming Module - Stream .sanchez video over network or satellite

Supports:
- TCP unicast streaming (reliable, for local network)
- UDP unicast streaming (low latency, for direct connections)
- UDP multicast streaming (for satellite/broadcast distribution)
- RTP-like packet framing for reliable transport

Protocol:
    Stream Packet Format:
    - MAGIC (4 bytes): "SNCH"
    - VERSION (1 byte): Protocol version
    - TYPE (1 byte): Packet type (metadata, config, frame, sync, end)
    - SEQ (4 bytes): Sequence number
    - TIMESTAMP (8 bytes): Presentation timestamp (microseconds)
    - PAYLOAD_LEN (4 bytes): Payload length
    - PAYLOAD: Actual data
    - CHECKSUM (4 bytes): CRC32 of packet

Satellite considerations:
- Forward Error Correction (FEC) for packet loss recovery
- Larger packet sizes with Reed-Solomon encoding
- Adaptive bitrate based on link quality
- Store-and-forward buffering for high latency links
"""

import socket
import struct
import threading
import time
import queue
import zlib
import json
import hashlib
from dataclasses import dataclass
from typing import Optional, Callable, List, Tuple, Generator
from enum import IntEnum
import numpy as np

from .format import SanchezFile, SanchezMetadata, SanchezConfig, FrameCompressor


# Protocol Constants
MAGIC = b'SNCH'
PROTOCOL_VERSION = 1
MAX_UDP_PAYLOAD = 65507  # Max UDP payload size
DEFAULT_CHUNK_SIZE = 8192  # Default chunk size for large frames
SATELLITE_CHUNK_SIZE = 1400  # Smaller chunks for satellite (MTU friendly)


class PacketType(IntEnum):
    """Types of streaming packets"""
    METADATA = 0x01      # Stream metadata (title, creator, etc.)
    CONFIG = 0x02        # Video configuration (dimensions, fps)
    FRAME_START = 0x10   # Start of a frame
    FRAME_CHUNK = 0x11   # Frame data chunk
    FRAME_END = 0x12     # End of frame marker
    AUDIO_CONFIG = 0x40  # Audio configuration (sample rate, channels, etc.)
    AUDIO_CHUNK = 0x41   # Audio data chunk
    SYNC = 0x20          # Synchronization packet (heartbeat)
    FEC_DATA = 0x30      # Forward Error Correction data
    END_STREAM = 0xFF    # End of stream


class StreamMode(IntEnum):
    """Streaming transport modes"""
    TCP_UNICAST = 1      # TCP point-to-point
    UDP_UNICAST = 2      # UDP point-to-point
    UDP_MULTICAST = 3    # UDP multicast (satellite/broadcast)
    UDP_BROADCAST = 4    # UDP broadcast (local network)


@dataclass
class StreamPacket:
    """A streaming protocol packet"""
    packet_type: PacketType
    sequence: int
    timestamp: int  # microseconds
    payload: bytes
    
    def serialize(self) -> bytes:
        """Serialize packet to bytes"""
        header = struct.pack(
            '>4sBBIQI',
            MAGIC,
            PROTOCOL_VERSION,
            self.packet_type,
            self.sequence,
            self.timestamp,
            len(self.payload)
        )
        checksum = zlib.crc32(header + self.payload) & 0xFFFFFFFF
        return header + self.payload + struct.pack('>I', checksum)
    
    @classmethod
    def deserialize(cls, data: bytes) -> Optional['StreamPacket']:
        """Deserialize bytes to packet, returns None if invalid"""
        if len(data) < 26:  # Minimum packet size
            return None
        
        # Check magic
        if data[:4] != MAGIC:
            return None
        
        # Parse header
        try:
            magic, version, ptype, seq, ts, payload_len = struct.unpack(
                '>4sBBIQI', data[:22]
            )
        except struct.error:
            return None
        
        if version != PROTOCOL_VERSION:
            return None
        
        # Extract payload
        if len(data) < 22 + payload_len + 4:
            return None
        
        payload = data[22:22 + payload_len]
        checksum_received = struct.unpack('>I', data[22 + payload_len:26 + payload_len])[0]
        
        # Verify checksum
        checksum_computed = zlib.crc32(data[:22 + payload_len]) & 0xFFFFFFFF
        if checksum_received != checksum_computed:
            return None
        
        return cls(
            packet_type=PacketType(ptype),
            sequence=seq,
            timestamp=ts,
            payload=payload
        )


class ForwardErrorCorrection:
    """
    Simple XOR-based FEC for packet loss recovery.
    For every N data packets, generates 1 parity packet.
    
    For satellite, use fec_ratio=4 (1 parity per 4 data packets)
    """
    
    def __init__(self, fec_ratio: int = 4):
        self.fec_ratio = fec_ratio
        self._buffer: List[bytes] = []
        self._max_len = 0
    
    def add_packet(self, data: bytes) -> Optional[bytes]:
        """
        Add a packet and return FEC packet if ready.
        
        Returns FEC parity packet when buffer is full, None otherwise.
        """
        self._buffer.append(data)
        self._max_len = max(self._max_len, len(data))
        
        if len(self._buffer) >= self.fec_ratio:
            # Generate XOR parity
            parity = bytearray(self._max_len)
            for pkt in self._buffer:
                padded = pkt.ljust(self._max_len, b'\x00')
                for i, b in enumerate(padded):
                    parity[i] ^= b
            
            # Reset buffer
            self._buffer = []
            self._max_len = 0
            
            return bytes(parity)
        
        return None
    
    def recover_packet(self, packets: List[Optional[bytes]], fec_parity: bytes) -> Optional[bytes]:
        """
        Attempt to recover a missing packet using FEC parity.
        
        Args:
            packets: List of packets where None indicates missing
            fec_parity: The FEC parity packet
            
        Returns:
            Recovered packet or None if recovery not possible
        """
        missing_count = sum(1 for p in packets if p is None)
        
        if missing_count != 1:
            # Can only recover exactly one missing packet
            return None
        
        # XOR all available packets with parity to recover missing
        max_len = len(fec_parity)
        recovered = bytearray(fec_parity)
        
        for pkt in packets:
            if pkt is not None:
                padded = pkt.ljust(max_len, b'\x00')
                for i, b in enumerate(padded):
                    recovered[i] ^= b
        
        return bytes(recovered).rstrip(b'\x00')


class SanchezStreamServer:
    """
    Stream a .sanchez file over network.
    
    Usage:
        server = SanchezStreamServer()
        server.stream_file("video.sanchez", host="0.0.0.0", port=9999)
        
    For satellite multicast:
        server = SanchezStreamServer(mode=StreamMode.UDP_MULTICAST)
        server.stream_file("video.sanchez", host="239.0.0.1", port=9999)
    """
    
    def __init__(self, mode: StreamMode = StreamMode.TCP_UNICAST):
        self.mode = mode
        self.socket: Optional[socket.socket] = None
        self.clients: List[Tuple[socket.socket, tuple]] = []
        self.running = False
        self.sequence = 0
        self._fec = ForwardErrorCorrection(fec_ratio=4)
        self.progress_callback: Optional[Callable[[int, int, str], None]] = None
        
        # Streaming parameters
        self.loop = False
        self.chunk_size = DEFAULT_CHUNK_SIZE
    
    def set_progress_callback(self, callback: Callable[[int, int, str], None]) -> None:
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    def _report_progress(self, current: int, total: int, message: str) -> None:
        if self.progress_callback:
            self.progress_callback(current, total, message)
        else:
            percent = (current / total * 100) if total > 0 else 0
            print(f"\r[{percent:5.1f}%] {message}: {current}/{total}", end='', flush=True)
    
    def _create_socket(self) -> socket.socket:
        """Create socket based on streaming mode"""
        if self.mode == StreamMode.TCP_UNICAST:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if self.mode == StreamMode.UDP_MULTICAST:
                # Set TTL for multicast (higher for satellite)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
                # Enable loopback for testing
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            elif self.mode == StreamMode.UDP_BROADCAST:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        return sock
    
    def _send_packet(self, packet: StreamPacket, addr: Optional[tuple] = None) -> None:
        """Send a packet to clients"""
        data = packet.serialize()
        
        if self.mode == StreamMode.TCP_UNICAST:
            # Send to all connected TCP clients
            for client_sock, _ in self.clients[:]:
                try:
                    # Send length prefix for TCP
                    client_sock.sendall(struct.pack('>I', len(data)) + data)
                except (BrokenPipeError, ConnectionResetError):
                    self.clients.remove((client_sock, _))
        else:
            # UDP modes
            if addr:
                self.socket.sendto(data, addr)
            
            # Also generate FEC if enabled
            if self.mode == StreamMode.UDP_MULTICAST:
                fec_data = self._fec.add_packet(data)
                if fec_data:
                    fec_packet = StreamPacket(
                        packet_type=PacketType.FEC_DATA,
                        sequence=self.sequence,
                        timestamp=packet.timestamp,
                        payload=fec_data
                    )
                    self.sequence += 1
                    if addr:
                        self.socket.sendto(fec_packet.serialize(), addr)
    
    def _next_seq(self) -> int:
        """Get next sequence number"""
        seq = self.sequence
        self.sequence = (self.sequence + 1) & 0xFFFFFFFF
        return seq
    
    def _get_timestamp(self) -> int:
        """Get current timestamp in microseconds"""
        return int(time.time() * 1_000_000)
    
    def stream_file(
        self,
        sanchez_path: str,
        host: str = "0.0.0.0",
        port: int = 9999,
        loop: bool = False,
        satellite_mode: bool = False,
        audio_path: Optional[str] = None
    ) -> None:
        """
        Stream a .sanchez file with optional audio.
        
        Args:
            sanchez_path: Path to .sanchez file
            host: Host to bind/send to
            port: Port number
            loop: Loop the video continuously
            satellite_mode: Enable satellite optimizations (smaller chunks, more FEC)
            audio_path: Path to .mp3 audio file (auto-detected if None)
        """
        from pathlib import Path
        
        # Load the sanchez file
        print(f"Loading: {sanchez_path}")
        sanchez = SanchezFile.load(sanchez_path)
        print(f"  Title: {sanchez.metadata.title}")
        print(f"  Size: {sanchez.config.width}x{sanchez.config.height}")
        print(f"  Frames: {sanchez.frame_count}")
        
        # Find audio file
        self.audio_data: Optional[bytes] = None
        if audio_path is None:
            # Auto-detect audio file with same name
            sanchez_file = Path(sanchez_path)
            auto_audio = sanchez_file.with_suffix('.mp3')
            if auto_audio.exists():
                audio_path = str(auto_audio)
        
        if audio_path and Path(audio_path).exists():
            print(f"  Audio: {audio_path}")
            with open(audio_path, 'rb') as f:
                self.audio_data = f.read()
            print(f"  Audio size: {len(self.audio_data) / 1024:.1f} KB")
        else:
            print(f"  Audio: None")
        
        self.loop = loop
        
        if satellite_mode:
            self.chunk_size = SATELLITE_CHUNK_SIZE
            self._fec = ForwardErrorCorrection(fec_ratio=3)  # More FEC for satellite
        
        # Create socket
        self.socket = self._create_socket()
        addr = (host, port)
        
        if self.mode == StreamMode.TCP_UNICAST:
            self.socket.bind(addr)
            self.socket.listen(5)
            print(f"TCP streaming server listening on {host}:{port}")
            self._tcp_server_loop(sanchez, addr)
        else:
            if self.mode == StreamMode.UDP_MULTICAST:
                print(f"UDP multicast streaming to {host}:{port}")
            elif self.mode == StreamMode.UDP_BROADCAST:
                print(f"UDP broadcast streaming on port {port}")
            else:
                print(f"UDP unicast streaming to {host}:{port}")
            
            self.socket.bind(('0.0.0.0', port + 1))  # Bind to different port for sending
            self._udp_stream_loop(sanchez, addr)
    
    def _tcp_server_loop(self, sanchez: SanchezFile, addr: tuple) -> None:
        """Accept TCP connections and stream to each client"""
        self.running = True
        
        def handle_client(client_sock: socket.socket, client_addr: tuple):
            print(f"Client connected: {client_addr}")
            self.clients.append((client_sock, client_addr))
            
            try:
                self._stream_to_client(sanchez, client_sock, client_addr)
            finally:
                if (client_sock, client_addr) in self.clients:
                    self.clients.remove((client_sock, client_addr))
                client_sock.close()
                print(f"Client disconnected: {client_addr}")
        
        try:
            while self.running:
                try:
                    self.socket.settimeout(1.0)
                    client_sock, client_addr = self.socket.accept()
                    client_thread = threading.Thread(
                        target=handle_client,
                        args=(client_sock, client_addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    continue
        except KeyboardInterrupt:
            print("\nShutting down server...")
        finally:
            self.running = False
            self.socket.close()
    
    def _stream_to_client(self, sanchez: SanchezFile, client_sock: socket.socket, addr: tuple) -> None:
        """Stream sanchez file to a connected TCP client"""
        frame_interval = 1.0 / sanchez.config.fps  # Time between frames
        
        while self.running:
            stream_start = time.time()
            
            # Send metadata
            meta_payload = sanchez.metadata.to_json_line().encode('utf-8')
            self._send_tcp_packet(client_sock, StreamPacket(
                packet_type=PacketType.METADATA,
                sequence=self._next_seq(),
                timestamp=self._get_timestamp(),
                payload=meta_payload
            ))
            
            # Send config
            config_payload = sanchez.config.to_config_line().encode('utf-8')
            self._send_tcp_packet(client_sock, StreamPacket(
                packet_type=PacketType.CONFIG,
                sequence=self._next_seq(),
                timestamp=self._get_timestamp(),
                payload=config_payload
            ))
            
            # Send audio data if available (before frames so client can buffer)
            if self.audio_data:
                self._send_audio_data(client_sock, addr)
            
            # Stream frames
            for frame_idx in range(sanchez.frame_count):
                if not self.running:
                    break
                
                frame_start = time.time()
                
                # Get compressed frame data
                frame_data = sanchez._frames[frame_idx].encode('utf-8')
                
                # Send frame in chunks
                self._send_frame_chunks(client_sock, frame_idx, frame_data, addr)
                
                self._report_progress(frame_idx + 1, sanchez.frame_count, "Streaming")
                
                # Maintain frame rate
                elapsed = time.time() - frame_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
            
            # Send end stream
            self._send_tcp_packet(client_sock, StreamPacket(
                packet_type=PacketType.END_STREAM,
                sequence=self._next_seq(),
                timestamp=self._get_timestamp(),
                payload=b''
            ))
            
            if not self.loop:
                break
            
            print("\nLooping stream...")
    
    def _send_audio_data(self, sock_or_addr, addr: tuple) -> None:
        """Send audio data (MP3) in chunks before video frames"""
        if not self.audio_data:
            return
        
        audio_chunk_size = self.chunk_size * 4  # Larger chunks for audio
        total_chunks = (len(self.audio_data) + audio_chunk_size - 1) // audio_chunk_size
        
        # Send audio config packet first
        # Format: total_size (4 bytes) + chunk_count (4 bytes) + format marker "MP3\0"
        config_payload = struct.pack('>II', len(self.audio_data), total_chunks) + b'MP3\x00'
        config_packet = StreamPacket(
            packet_type=PacketType.AUDIO_CONFIG,
            sequence=self._next_seq(),
            timestamp=self._get_timestamp(),
            payload=config_payload
        )
        
        if self.mode == StreamMode.TCP_UNICAST:
            self._send_tcp_packet(sock_or_addr, config_packet)
        else:
            self.socket.sendto(config_packet.serialize(), addr)
        
        # Send audio chunks
        for chunk_idx in range(total_chunks):
            offset = chunk_idx * audio_chunk_size
            chunk = self.audio_data[offset:offset + audio_chunk_size]
            
            # Payload: chunk_idx (4 bytes) + audio data
            chunk_payload = struct.pack('>I', chunk_idx) + chunk
            chunk_packet = StreamPacket(
                packet_type=PacketType.AUDIO_CHUNK,
                sequence=self._next_seq(),
                timestamp=self._get_timestamp(),
                payload=chunk_payload
            )
            
            if self.mode == StreamMode.TCP_UNICAST:
                self._send_tcp_packet(sock_or_addr, chunk_packet)
            else:
                self.socket.sendto(chunk_packet.serialize(), addr)
        
        print(f"  Sent audio: {total_chunks} chunks")
    
    def _send_tcp_packet(self, sock: socket.socket, packet: StreamPacket) -> bool:
        """Send packet over TCP with length prefix"""
        try:
            data = packet.serialize()
            sock.sendall(struct.pack('>I', len(data)) + data)
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False
    
    def _send_frame_chunks(self, sock_or_addr, frame_idx: int, frame_data: bytes, addr: tuple) -> None:
        """Send frame data in chunks"""
        total_chunks = (len(frame_data) + self.chunk_size - 1) // self.chunk_size
        
        # Frame start packet
        start_payload = struct.pack('>II', frame_idx, len(frame_data))
        start_packet = StreamPacket(
            packet_type=PacketType.FRAME_START,
            sequence=self._next_seq(),
            timestamp=self._get_timestamp(),
            payload=start_payload
        )
        
        if self.mode == StreamMode.TCP_UNICAST:
            self._send_tcp_packet(sock_or_addr, start_packet)
        else:
            self.socket.sendto(start_packet.serialize(), addr)
        
        # Send chunks
        for chunk_idx in range(total_chunks):
            offset = chunk_idx * self.chunk_size
            chunk = frame_data[offset:offset + self.chunk_size]
            
            chunk_payload = struct.pack('>II', frame_idx, chunk_idx) + chunk
            chunk_packet = StreamPacket(
                packet_type=PacketType.FRAME_CHUNK,
                sequence=self._next_seq(),
                timestamp=self._get_timestamp(),
                payload=chunk_payload
            )
            
            if self.mode == StreamMode.TCP_UNICAST:
                self._send_tcp_packet(sock_or_addr, chunk_packet)
            else:
                data = chunk_packet.serialize()
                self.socket.sendto(data, addr)
                
                # FEC for multicast
                if self.mode == StreamMode.UDP_MULTICAST:
                    fec_data = self._fec.add_packet(data)
                    if fec_data:
                        fec_packet = StreamPacket(
                            packet_type=PacketType.FEC_DATA,
                            sequence=self._next_seq(),
                            timestamp=self._get_timestamp(),
                            payload=fec_data
                        )
                        self.socket.sendto(fec_packet.serialize(), addr)
        
        # Frame end packet
        end_packet = StreamPacket(
            packet_type=PacketType.FRAME_END,
            sequence=self._next_seq(),
            timestamp=self._get_timestamp(),
            payload=struct.pack('>I', frame_idx)
        )
        
        if self.mode == StreamMode.TCP_UNICAST:
            self._send_tcp_packet(sock_or_addr, end_packet)
        else:
            self.socket.sendto(end_packet.serialize(), addr)
    
    def _udp_stream_loop(self, sanchez: SanchezFile, addr: tuple) -> None:
        """Stream continuously over UDP"""
        self.running = True
        frame_interval = 1.0 / sanchez.config.fps
        
        try:
            while self.running:
                stream_start = time.time()
                
                # Send metadata
                meta_payload = sanchez.metadata.to_json_line().encode('utf-8')
                meta_packet = StreamPacket(
                    packet_type=PacketType.METADATA,
                    sequence=self._next_seq(),
                    timestamp=self._get_timestamp(),
                    payload=meta_payload
                )
                self.socket.sendto(meta_packet.serialize(), addr)
                
                # Send config
                config_payload = sanchez.config.to_config_line().encode('utf-8')
                config_packet = StreamPacket(
                    packet_type=PacketType.CONFIG,
                    sequence=self._next_seq(),
                    timestamp=self._get_timestamp(),
                    payload=config_payload
                )
                self.socket.sendto(config_packet.serialize(), addr)
                
                # Send audio data if available
                if self.audio_data:
                    self._send_audio_data(None, addr)
                
                # Stream frames
                for frame_idx in range(sanchez.frame_count):
                    if not self.running:
                        break
                    
                    frame_start = time.time()
                    frame_data = sanchez._frames[frame_idx].encode('utf-8')
                    
                    self._send_frame_chunks(None, frame_idx, frame_data, addr)
                    
                    self._report_progress(frame_idx + 1, sanchez.frame_count, "Streaming")
                    
                    elapsed = time.time() - frame_start
                    sleep_time = frame_interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    
                    # Send sync packet periodically
                    if frame_idx % 24 == 0:  # Every second
                        sync_packet = StreamPacket(
                            packet_type=PacketType.SYNC,
                            sequence=self._next_seq(),
                            timestamp=self._get_timestamp(),
                            payload=struct.pack('>If', frame_idx, time.time() - stream_start)
                        )
                        self.socket.sendto(sync_packet.serialize(), addr)
                
                # End stream packet
                end_packet = StreamPacket(
                    packet_type=PacketType.END_STREAM,
                    sequence=self._next_seq(),
                    timestamp=self._get_timestamp(),
                    payload=b''
                )
                self.socket.sendto(end_packet.serialize(), addr)
                
                if not self.loop:
                    break
                
                print("\nLooping stream...")
                time.sleep(0.5)  # Brief pause before loop
                
        except KeyboardInterrupt:
            print("\nStopping stream...")
        finally:
            self.running = False
            self.socket.close()
    
    def stop(self) -> None:
        """Stop the streaming server"""
        self.running = False


class SanchezStreamClient:
    """
    Receive a .sanchez stream over network.
    
    Usage:
        client = SanchezStreamClient()
        for frame in client.receive_stream("192.168.1.100", 9999):
            # Display frame
            display(frame)
    
    For satellite multicast:
        client = SanchezStreamClient(mode=StreamMode.UDP_MULTICAST)
        for frame in client.receive_stream("239.0.0.1", 9999):
            display(frame)
    """
    
    def __init__(self, mode: StreamMode = StreamMode.TCP_UNICAST):
        self.mode = mode
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.metadata: Optional[SanchezMetadata] = None
        self.config: Optional[SanchezConfig] = None
        
        # Buffering
        self._frame_buffer: dict = {}  # frame_idx -> {chunks}
        self._completed_frames: queue.Queue = queue.Queue(maxsize=30)
        self._compressor = FrameCompressor()
        
        # Audio buffering
        self._audio_chunks: dict = {}  # chunk_idx -> data
        self._audio_total_size: int = 0
        self._audio_total_chunks: int = 0
        self._audio_format: str = "MP3"
        self.audio_data: Optional[bytes] = None  # Complete audio when received
        
        # Stats
        self.packets_received = 0
        self.packets_lost = 0
        self.last_sequence = -1
    
    def _create_socket(self) -> socket.socket:
        """Create socket based on streaming mode"""
        if self.mode == StreamMode.TCP_UNICAST:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            
            if self.mode == StreamMode.UDP_MULTICAST:
                # Will join multicast group after binding
                pass
            elif self.mode == StreamMode.UDP_BROADCAST:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        return sock
    
    def receive_stream(
        self,
        host: str,
        port: int,
        buffer_size: int = 10,
        timeout: float = 5.0
    ) -> Generator[Tuple[int, np.ndarray], None, None]:
        """
        Connect to a stream and yield frames.
        
        Args:
            host: Server host or multicast group
            port: Port number
            buffer_size: Number of frames to buffer
            timeout: Connection/receive timeout
            
        Yields:
            Tuple of (frame_index, frame_array)
        """
        self.socket = self._create_socket()
        self.socket.settimeout(timeout)
        self.running = True
        
        try:
            if self.mode == StreamMode.TCP_UNICAST:
                self.socket.connect((host, port))
                print(f"Connected to TCP stream at {host}:{port}")
                yield from self._receive_tcp_stream()
            else:
                self.socket.bind(('0.0.0.0', port))
                
                if self.mode == StreamMode.UDP_MULTICAST:
                    # Join multicast group
                    import struct as st
                    mreq = st.pack('4sl', socket.inet_aton(host), socket.INADDR_ANY)
                    self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                    print(f"Joined multicast group {host}:{port}")
                else:
                    print(f"Listening for UDP stream on port {port}")
                
                yield from self._receive_udp_stream()
                
        finally:
            self.running = False
            self.socket.close()
    
    def _receive_tcp_stream(self) -> Generator[Tuple[int, np.ndarray], None, None]:
        """Receive TCP stream"""
        buffer = b''
        
        while self.running:
            try:
                data = self.socket.recv(65536)
                if not data:
                    break
                
                buffer += data
                
                # Process complete packets
                while len(buffer) >= 4:
                    packet_len = struct.unpack('>I', buffer[:4])[0]
                    
                    if len(buffer) < 4 + packet_len:
                        break  # Wait for more data
                    
                    packet_data = buffer[4:4 + packet_len]
                    buffer = buffer[4 + packet_len:]
                    
                    packet = StreamPacket.deserialize(packet_data)
                    if packet:
                        self.packets_received += 1
                        frame = self._process_packet(packet)
                        if frame is not None:
                            yield frame
                
            except socket.timeout:
                continue
            except ConnectionResetError:
                print("Connection reset by server")
                break
    
    def _receive_udp_stream(self) -> Generator[Tuple[int, np.ndarray], None, None]:
        """Receive UDP stream"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(65536)
                
                packet = StreamPacket.deserialize(data)
                if packet:
                    self.packets_received += 1
                    
                    # Check for lost packets
                    if self.last_sequence >= 0:
                        expected = (self.last_sequence + 1) & 0xFFFFFFFF
                        if packet.sequence != expected:
                            lost = (packet.sequence - self.last_sequence - 1) & 0xFFFFFFFF
                            self.packets_lost += lost
                    
                    self.last_sequence = packet.sequence
                    
                    frame = self._process_packet(packet)
                    if frame is not None:
                        yield frame
                
            except socket.timeout:
                continue
    
    def _process_packet(self, packet: StreamPacket) -> Optional[Tuple[int, np.ndarray]]:
        """Process a received packet, returns frame if complete"""
        
        if packet.packet_type == PacketType.METADATA:
            json_str = packet.payload.decode('utf-8')
            self.metadata = SanchezMetadata.from_json_line(json_str)
            print(f"Stream: {self.metadata.title} by {self.metadata.creator}")
            
        elif packet.packet_type == PacketType.CONFIG:
            config_str = packet.payload.decode('utf-8')
            self.config = SanchezConfig.from_config_line(config_str)
            print(f"  Size: {self.config.width}x{self.config.height}")
            print(f"  Frames: {self.config.frame_count}")
            
        elif packet.packet_type == PacketType.FRAME_START:
            frame_idx, total_size = struct.unpack('>II', packet.payload)
            self._frame_buffer[frame_idx] = {
                'total_size': total_size,
                'chunks': {},
                'received_size': 0
            }
            
        elif packet.packet_type == PacketType.FRAME_CHUNK:
            frame_idx, chunk_idx = struct.unpack('>II', packet.payload[:8])
            chunk_data = packet.payload[8:]
            
            if frame_idx in self._frame_buffer:
                self._frame_buffer[frame_idx]['chunks'][chunk_idx] = chunk_data
                self._frame_buffer[frame_idx]['received_size'] += len(chunk_data)
            
        elif packet.packet_type == PacketType.FRAME_END:
            frame_idx = struct.unpack('>I', packet.payload)[0]
            
            if frame_idx in self._frame_buffer and self.config:
                frame_info = self._frame_buffer[frame_idx]
                
                # Reconstruct frame data
                chunks = frame_info['chunks']
                frame_data = b''.join(
                    chunks[i] for i in sorted(chunks.keys())
                )
                
                if len(frame_data) >= frame_info['total_size']:
                    # Decompress and return frame
                    try:
                        frame_str = frame_data.decode('utf-8')
                        frame_array = self._compressor.decompress_frame(
                            frame_str,
                            self.config.width,
                            self.config.height
                        )
                        del self._frame_buffer[frame_idx]
                        return (frame_idx, frame_array)
                    except Exception as e:
                        print(f"Frame decode error: {e}")
                
                del self._frame_buffer[frame_idx]
            
        elif packet.packet_type == PacketType.END_STREAM:
            print("\nStream ended")
            self.running = False
            
        elif packet.packet_type == PacketType.SYNC:
            frame_idx, stream_time = struct.unpack('>If', packet.payload)
            # Could use for synchronization
            
        elif packet.packet_type == PacketType.AUDIO_CONFIG:
            # Parse audio config: total_size (4) + chunk_count (4) + format (4)
            self._audio_total_size, self._audio_total_chunks = struct.unpack('>II', packet.payload[:8])
            self._audio_format = packet.payload[8:11].decode('ascii')
            self._audio_chunks = {}
            print(f"  Audio: {self._audio_format}, {self._audio_total_size / 1024:.1f} KB, {self._audio_total_chunks} chunks")
            
        elif packet.packet_type == PacketType.AUDIO_CHUNK:
            chunk_idx = struct.unpack('>I', packet.payload[:4])[0]
            chunk_data = packet.payload[4:]
            self._audio_chunks[chunk_idx] = chunk_data
            
            # Check if all audio chunks received
            if len(self._audio_chunks) >= self._audio_total_chunks:
                # Reconstruct audio data
                self.audio_data = b''.join(
                    self._audio_chunks[i] for i in sorted(self._audio_chunks.keys())
                )
                print(f"  Audio received: {len(self.audio_data)} bytes")
            
        return None
    
    def get_stats(self) -> dict:
        """Get streaming statistics"""
        loss_rate = (self.packets_lost / self.packets_received * 100 
                     if self.packets_received > 0 else 0)
        return {
            'packets_received': self.packets_received,
            'packets_lost': self.packets_lost,
            'loss_rate': f"{loss_rate:.2f}%"
        }
    
    def stop(self) -> None:
        """Stop receiving stream"""
        self.running = False


class SanchezStreamPlayer:
    """
    Play a sanchez stream directly with pygame.
    
    Usage:
        player = SanchezStreamPlayer()
        player.play_stream("192.168.1.100", 9999)
        
    For satellite:
        player = SanchezStreamPlayer(mode=StreamMode.UDP_MULTICAST)
        player.play_stream("239.0.0.1", 9999)
    """
    
    def __init__(self, mode: StreamMode = StreamMode.TCP_UNICAST, scale: float = 1.0):
        self.mode = mode
        self.scale = scale
        self.client = SanchezStreamClient(mode=mode)
        
    def play_stream(
        self,
        host: str,
        port: int,
        fullscreen: bool = False
    ) -> None:
        """Play a stream with pygame display and audio"""
        try:
            import pygame
        except ImportError:
            raise ImportError("pygame required for stream playback. Install with: pip install pygame")
        
        pygame.init()
        pygame.mixer.init()
        
        screen = None
        clock = pygame.time.Clock()
        running = True
        frame_count = 0
        audio_started = False
        audio_temp_file = None
        
        print(f"Connecting to stream at {host}:{port}...")
        
        try:
            for frame_idx, frame_array in self.client.receive_stream(host, port):
                # Start audio playback once we have audio data and first frame
                if not audio_started and self.client.audio_data and frame_idx == 0:
                    try:
                        import tempfile
                        import os
                        # Write audio to temp file for pygame to play
                        audio_temp_file = tempfile.NamedTemporaryFile(
                            suffix='.mp3', delete=False
                        )
                        audio_temp_file.write(self.client.audio_data)
                        audio_temp_file.close()
                        
                        pygame.mixer.music.load(audio_temp_file.name)
                        pygame.mixer.music.play()
                        audio_started = True
                        print("  Audio playback started")
                    except Exception as e:
                        print(f"  Audio playback error: {e}")
                
                # Initialize display on first frame
                if screen is None:
                    height, width = frame_array.shape[:2]
                    display_w = int(width * self.scale)
                    display_h = int(height * self.scale)
                    
                    if fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((display_w, display_h))
                    
                    if self.client.metadata:
                        pygame.display.set_caption(f"Sanchez Stream: {self.client.metadata.title}")
                    else:
                        pygame.display.set_caption("Sanchez Stream")
                
                # Handle events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_q, pygame.K_ESCAPE):
                            running = False
                        elif event.key == pygame.K_i:
                            stats = self.client.get_stats()
                            print(f"\nStream stats: {stats}")
                        elif event.key == pygame.K_m:
                            # Mute/unmute audio
                            if pygame.mixer.music.get_volume() > 0:
                                pygame.mixer.music.set_volume(0)
                                print("  Audio muted")
                            else:
                                pygame.mixer.music.set_volume(1.0)
                                print("  Audio unmuted")
                
                if not running:
                    break
                
                # Display frame
                # Convert RGB to pygame surface
                surface = pygame.surfarray.make_surface(
                    np.transpose(frame_array, (1, 0, 2))
                )
                
                if self.scale != 1.0:
                    surface = pygame.transform.scale(surface, (display_w, display_h))
                
                screen.blit(surface, (0, 0))
                pygame.display.flip()
                
                frame_count += 1
                clock.tick(24)  # Target 24fps
                
        except KeyboardInterrupt:
            print("\nPlayback stopped")
        finally:
            self.client.stop()
            pygame.mixer.music.stop()
            pygame.quit()
            
            # Clean up temp audio file
            if audio_temp_file:
                try:
                    import os
                    os.unlink(audio_temp_file.name)
                except:
                    pass
            
            stats = self.client.get_stats()
            print(f"Playback complete. Frames: {frame_count}, Stats: {stats}")


# Convenience functions for CLI
def stream_server(
    sanchez_path: str,
    host: str = "0.0.0.0",
    port: int = 9999,
    mode: str = "tcp",
    loop: bool = False,
    satellite: bool = False
) -> None:
    """Start a streaming server"""
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    stream_mode = mode_map.get(mode.lower(), StreamMode.TCP_UNICAST)
    
    server = SanchezStreamServer(mode=stream_mode)
    server.stream_file(
        sanchez_path,
        host=host,
        port=port,
        loop=loop,
        satellite_mode=satellite
    )


def stream_client(
    host: str,
    port: int = 9999,
    mode: str = "tcp",
    output_path: Optional[str] = None
) -> None:
    """Receive a stream (optionally save to file)"""
    from pathlib import Path
    
    mode_map = {
        'tcp': StreamMode.TCP_UNICAST,
        'udp': StreamMode.UDP_UNICAST,
        'multicast': StreamMode.UDP_MULTICAST,
        'broadcast': StreamMode.UDP_BROADCAST
    }
    stream_mode = mode_map.get(mode.lower(), StreamMode.TCP_UNICAST)
    
    if output_path:
        # Save stream to file
        client = SanchezStreamClient(mode=stream_mode)
        sanchez: Optional[SanchezFile] = None
        
        for frame_idx, frame_array in client.receive_stream(host, port):
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
            sanchez.save(output_path)
            print(f"\nSaved to: {output_path}")
            
            # Also save audio if received
            if client.audio_data:
                audio_path = Path(output_path).with_suffix('.mp3')
                with open(audio_path, 'wb') as f:
                    f.write(client.audio_data)
                print(f"Saved audio to: {audio_path}")
    else:
        # Play stream
        player = SanchezStreamPlayer(mode=stream_mode)
        player.play_stream(host, port)
