# .sanchez file format - Interdimensional Cable Video Format
# Rick & Morty inspired custom video format

__version__ = "2.5.0"
__author__ = "cbx"

from .format import SanchezFile, SanchezMetadata, SanchezConfig
from .encoder import SanchezEncoder
from .decoder import SanchezDecoder
from .player import SanchezPlayer
from .streaming import (
    SanchezStreamServer,
    SanchezStreamClient,
    SanchezStreamPlayer,
    StreamMode,
    PacketType,
    stream_server,
    stream_client
)
from .live import (
    LiveStreamServer,
    FeedCapture,
    FeedDiscovery,
    VideoFeed,
    FeedType,
    interactive_feed_picker,
    stream_video_file,
    stream_camera,
    stream_screen
)
from .playlist import (
    Playlist,
    PlaylistItem,
    PlaylistMode,
    ChannelServer,
    create_channel,
    stream_channel
)
from .channels import (
    ChannelGuide,
    SavedChannel,
    interactive_channel_selector,
    get_channels_file
)
from .watermark import (
    TextOverlay,
    ImageOverlay,
    OverlayManager,
    WatermarkManager
)

__all__ = [
    # Core
    "SanchezFile",
    "SanchezMetadata",
    "SanchezConfig",
    "SanchezEncoder",
    "SanchezDecoder",
    "SanchezPlayer",
    # Streaming
    "SanchezStreamServer",
    "SanchezStreamClient",
    "SanchezStreamPlayer",
    "StreamMode",
    "PacketType",
    "stream_server",
    "stream_client",
    # Live
    "LiveStreamServer",
    "FeedCapture",
    "FeedDiscovery",
    "VideoFeed",
    "FeedType",
    "interactive_feed_picker",
    "stream_video_file",
    "stream_camera",
    "stream_screen",
    # Playlist
    "Playlist",
    "PlaylistItem",
    "PlaylistMode",
    "ChannelServer",
    "create_channel",
    "stream_channel",
    # Channels
    "ChannelGuide",
    "SavedChannel",
    "interactive_channel_selector",
    "get_channels_file",
    # Overlays
    "TextOverlay",
    "ImageOverlay",
    "OverlayManager",
    "WatermarkManager",
]
