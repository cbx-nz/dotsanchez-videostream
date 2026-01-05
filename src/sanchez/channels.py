"""
Sanchez Channel Guide - Client-side channel management

Save favorite channels with names and quickly tune in!
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict
from enum import Enum


def get_config_dir() -> Path:
    """Get the sanchez config directory"""
    if os.name == 'nt':
        # Windows
        config_dir = Path(os.environ.get('APPDATA', Path.home())) / 'sanchez'
    else:
        # Linux/Mac
        config_dir = Path.home() / '.config' / 'sanchez'
    
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_channels_file() -> Path:
    """Get the channels config file path"""
    return get_config_dir() / 'channels.json'


@dataclass
class SavedChannel:
    """A saved channel with connection info"""
    name: str
    host: str
    port: int = 9999
    mode: str = 'tcp'  # tcp, udp, multicast, broadcast
    description: str = ""
    favorite: bool = False
    last_watched: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SavedChannel':
        return cls(**data)
    
    def display_name(self) -> str:
        """Get display string for the channel"""
        mode_icon = {
            'tcp': '🔗',
            'udp': '📡',
            'multicast': '📺',
            'broadcast': '📻'
        }.get(self.mode, '📺')
        
        fav = '⭐' if self.favorite else '  '
        return f"{fav} {mode_icon} {self.name}"
    
    def connection_string(self) -> str:
        """Get connection info string"""
        return f"{self.host}:{self.port} ({self.mode})"


class ChannelGuide:
    """Manages saved channels for the receiver"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or get_channels_file()
        self.channels: List[SavedChannel] = []
        self.load()
    
    def load(self):
        """Load channels from config file"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.channels = [SavedChannel.from_dict(ch) for ch in data.get('channels', [])]
            except (json.JSONDecodeError, KeyError):
                self.channels = []
        else:
            self.channels = []
    
    def save(self):
        """Save channels to config file"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump({
                'channels': [ch.to_dict() for ch in self.channels]
            }, f, indent=2)
    
    def add(self, channel: SavedChannel) -> bool:
        """Add a channel (or update if name exists)"""
        # Check for existing channel with same name
        for i, ch in enumerate(self.channels):
            if ch.name.lower() == channel.name.lower():
                self.channels[i] = channel
                self.save()
                return False  # Updated existing
        
        self.channels.append(channel)
        self.save()
        return True  # Added new
    
    def remove(self, name: str) -> bool:
        """Remove a channel by name"""
        for i, ch in enumerate(self.channels):
            if ch.name.lower() == name.lower():
                del self.channels[i]
                self.save()
                return True
        return False
    
    def get(self, name: str) -> Optional[SavedChannel]:
        """Get a channel by name"""
        for ch in self.channels:
            if ch.name.lower() == name.lower():
                return ch
        return None
    
    def get_by_index(self, index: int) -> Optional[SavedChannel]:
        """Get a channel by index (1-based for user display)"""
        if 1 <= index <= len(self.channels):
            return self.channels[index - 1]
        return None
    
    def list_channels(self) -> List[SavedChannel]:
        """Get all channels, favorites first"""
        favorites = [ch for ch in self.channels if ch.favorite]
        others = [ch for ch in self.channels if not ch.favorite]
        return favorites + others
    
    def set_favorite(self, name: str, favorite: bool = True) -> bool:
        """Set/unset a channel as favorite"""
        for ch in self.channels:
            if ch.name.lower() == name.lower():
                ch.favorite = favorite
                self.save()
                return True
        return False
    
    def update_last_watched(self, name: str):
        """Update the last watched timestamp"""
        from datetime import datetime
        for ch in self.channels:
            if ch.name.lower() == name.lower():
                ch.last_watched = datetime.now().isoformat()
                self.save()
                return


def interactive_channel_selector(guide: Optional[ChannelGuide] = None) -> Optional[SavedChannel]:
    """
    Interactive CLI channel selector with arrow key navigation
    
    Returns the selected channel or None if cancelled
    """
    import sys
    import time
    import threading
    
    if guide is None:
        guide = ChannelGuide()
    
    channels = guide.list_channels()
    
    if not channels:
        print("\n" + "="*60)
        print("  📺 No Saved Channels")
        print("="*60)
        print("\n  You don't have any saved channels yet!")
        print("\n  Add a channel with:")
        print("    python -m sanchez channels add \"Channel Name\" <host> [port]")
        print("\n  Example:")
        print("    python -m sanchez channels add \"Rick's TV\" 192.168.1.100 9999")
        print("="*60 + "\n")
        return None
    
    selected_index = 0
    
    # Number input state for 3-digit channel entry
    number_input = ""
    number_input_time = 0
    NUMBER_INPUT_TIMEOUT = 2.0  # seconds to wait before auto-selecting
    
    # Check if we can use advanced terminal features
    try:
        if os.name == 'nt':
            import msvcrt
            use_arrows = True
        else:
            import tty
            import termios
            use_arrows = True
    except ImportError:
        use_arrows = False
    
    def get_key_with_timeout(timeout=0.1):
        """Get a single keypress with timeout (returns None if no key)"""
        if os.name == 'nt':
            import msvcrt
            # Check if a key is available
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\xe0':  # Arrow key prefix on Windows
                    key = msvcrt.getch()
                    if key == b'H':
                        return 'up'
                    elif key == b'P':
                        return 'down'
                    elif key == b'K':
                        return 'left'
                    elif key == b'M':
                        return 'right'
                elif key == b'\r':
                    return 'enter'
                elif key == b'q' or key == b'Q':
                    return 'quit'
                elif key == b'a' or key == b'A':
                    return 'add'
                elif key == b'f' or key == b'F':
                    return 'favorite'
                elif key == b'\x1b':
                    return 'quit'
                elif key == b'\x08':  # Backspace
                    return 'backspace'
                else:
                    try:
                        char = key.decode('utf-8')
                        if char.isdigit():
                            return ('digit', int(char))
                    except:
                        pass
                return None
            return None  # No key pressed
        else:
            import select
            import tty
            import termios
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                # Use select to check if input is available
                rlist, _, _ = select.select([sys.stdin], [], [], timeout)
                if rlist:
                    key = sys.stdin.read(1)
                    if key == '\x1b':
                        # Check for arrow keys
                        rlist2, _, _ = select.select([sys.stdin], [], [], 0.01)
                        if rlist2:
                            key2 = sys.stdin.read(2)
                            if key2 == '[A':
                                return 'up'
                            elif key2 == '[B':
                                return 'down'
                            elif key2 == '[C':
                                return 'right'
                            elif key2 == '[D':
                                return 'left'
                        return 'quit'
                    elif key == '\r' or key == '\n':
                        return 'enter'
                    elif key == 'q' or key == 'Q':
                        return 'quit'
                    elif key == 'a' or key == 'A':
                        return 'add'
                    elif key == 'f' or key == 'F':
                        return 'favorite'
                    elif key == '\x7f' or key == '\x08':  # Backspace
                        return 'backspace'
                    elif key.isdigit():
                        return ('digit', int(key))
                return None
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
    def clear_screen():
        """Clear terminal screen"""
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')
    
    def draw_ui(number_overlay=""):
        """Draw the channel selection UI"""
        clear_screen()
        
        # Calculate visible area (show max 15 channels at a time with scrolling)
        max_visible = 15
        total = len(channels)
        
        # Calculate scroll offset
        if total <= max_visible:
            start_idx = 0
            end_idx = total
        else:
            # Keep selected item visible with some context
            half = max_visible // 2
            if selected_index < half:
                start_idx = 0
            elif selected_index >= total - half:
                start_idx = total - max_visible
            else:
                start_idx = selected_index - half
            end_idx = min(start_idx + max_visible, total)
        
        print("\n" + "="*60)
        print("  📺 Sanchez Channel Guide")
        print("="*60)
        print()
        
        # Show scroll indicator if needed
        if start_idx > 0:
            print("      ↑ more channels above")
        
        for i in range(start_idx, end_idx):
            ch = channels[i]
            prefix = "  ▶ " if i == selected_index else "    "
            highlight = "\033[7m" if i == selected_index else ""
            reset = "\033[0m" if i == selected_index else ""
            
            num = f"[{i + 1}]"
            print(f"{prefix}{highlight}{num:5} {ch.display_name():30} {ch.connection_string()}{reset}")
        
        if end_idx < total:
            print("      ↓ more channels below")
        
        print()
        print("-"*60)
        
        # Show number input overlay if active
        if number_overlay:
            # Format as 3-digit display with underscores for empty positions
            display = number_overlay.ljust(3, '_')
            remaining = NUMBER_INPUT_TIMEOUT - (time.time() - number_input_time)
            if remaining > 0:
                bar_width = int((remaining / NUMBER_INPUT_TIMEOUT) * 10)
                bar = "█" * bar_width + "░" * (10 - bar_width)
                print(f"                                        ┌─────────────┐")
                print(f"                                        │  CH: {display}   │")
                print(f"                                        │  {bar}  │")
                print(f"                                        └─────────────┘")
            else:
                print(f"                                        ┌─────────────┐")
                print(f"                                        │  CH: {display}   │")
                print(f"                                        │  Tuning...  │")
                print(f"                                        └─────────────┘")
        else:
            print("  ↑/↓  Navigate   |  Enter  Select  |  0-9  Channel #")
            print("  Q    Quit       |  A      Add New |  F    Toggle Favorite")
        
        print("="*60)
    
    def simple_selector():
        """Simple number-based selection (fallback)"""
        print("\n" + "="*60)
        print("  📺 Sanchez Channel Guide")
        print("="*60)
        print()
        
        for i, ch in enumerate(channels):
            num = f"[{i + 1}]"
            print(f"  {num:5} {ch.display_name():30} {ch.connection_string()}")
        
        print()
        print("-"*60)
        print("  Enter channel number (or 'q' to quit): ", end='')
        
        try:
            choice = input().strip().lower()
            if choice == 'q':
                return None
            
            idx = int(choice)
            if 1 <= idx <= len(channels):
                return channels[idx - 1]
        except (ValueError, KeyboardInterrupt):
            pass
        
        return None
    
    if not use_arrows:
        return simple_selector()
    
    # Interactive mode with arrow keys and number input
    try:
        while True:
            draw_ui(number_input)
            
            # Check for number input timeout
            if number_input and (time.time() - number_input_time) >= NUMBER_INPUT_TIMEOUT:
                # Try to select the channel
                try:
                    idx = int(number_input)
                    if 1 <= idx <= len(channels):
                        selected = channels[idx - 1]
                        guide.update_last_watched(selected.name)
                        clear_screen()
                        return selected
                    else:
                        # Invalid channel number - flash and clear
                        number_input = ""
                except ValueError:
                    number_input = ""
                continue
            
            key = get_key_with_timeout(0.1)
            
            if key is None:
                continue
            
            # Handle digit input for channel number
            if isinstance(key, tuple) and key[0] == 'digit':
                digit = key[1]
                number_input += str(digit)
                number_input_time = time.time()
                
                # Keep only last 3 digits
                if len(number_input) > 3:
                    number_input = number_input[-3:]
                
                # If we have 3 digits, select immediately
                if len(number_input) == 3:
                    try:
                        idx = int(number_input)
                        if 1 <= idx <= len(channels):
                            selected = channels[idx - 1]
                            guide.update_last_watched(selected.name)
                            clear_screen()
                            return selected
                        else:
                            number_input = ""
                    except ValueError:
                        number_input = ""
                continue
            
            # Clear number input on other keys
            if number_input and key not in ('backspace',):
                if key in ('up', 'down', 'enter', 'quit', 'add', 'favorite'):
                    number_input = ""
            
            if key == 'backspace':
                if number_input:
                    number_input = number_input[:-1]
                    if number_input:
                        number_input_time = time.time()
            elif key == 'up':
                selected_index = (selected_index - 1) % len(channels)
            elif key == 'down':
                selected_index = (selected_index + 1) % len(channels)
            elif key == 'enter':
                selected = channels[selected_index]
                guide.update_last_watched(selected.name)
                clear_screen()
                return selected
            elif key == 'quit':
                clear_screen()
                return None
            elif key == 'add':
                # Could trigger add_channel_interactive here
                pass
            elif key == 'favorite':
                # Toggle favorite
                ch = channels[selected_index]
                guide.set_favorite(ch.name, not ch.favorite)
                channels = guide.list_channels()
                # Find the channel's new position
                for i, c in enumerate(channels):
                    if c.name == ch.name:
                        selected_index = i
                        break
    
    except KeyboardInterrupt:
        clear_screen()
        return None


def add_channel_interactive() -> Optional[SavedChannel]:
    """Interactive prompts to add a new channel"""
    print("\n" + "="*60)
    print("  ➕ Add New Channel")
    print("="*60)
    
    try:
        name = input("\n  Channel name: ").strip()
        if not name:
            print("  Cancelled.")
            return None
        
        host = input("  Host/IP address: ").strip()
        if not host:
            print("  Cancelled.")
            return None
        
        port_str = input("  Port [9999]: ").strip()
        port = int(port_str) if port_str else 9999
        
        print("\n  Streaming modes:")
        print("    1. TCP (reliable)")
        print("    2. UDP (low latency)")
        print("    3. Multicast (satellite/IPTV)")
        print("    4. Broadcast (local network)")
        
        mode_choice = input("  Mode [1]: ").strip()
        mode_map = {'1': 'tcp', '2': 'udp', '3': 'multicast', '4': 'broadcast', '': 'tcp'}
        mode = mode_map.get(mode_choice, 'tcp')
        
        description = input("  Description (optional): ").strip()
        
        channel = SavedChannel(
            name=name,
            host=host,
            port=port,
            mode=mode,
            description=description
        )
        
        guide = ChannelGuide()
        is_new = guide.add(channel)
        
        if is_new:
            print(f"\n  ✓ Added channel: {name}")
        else:
            print(f"\n  ✓ Updated channel: {name}")
        
        return channel
        
    except KeyboardInterrupt:
        print("\n  Cancelled.")
        return None
    except ValueError as e:
        print(f"\n  Error: {e}")
        return None


def list_channels_display():
    """Display all saved channels in a nice format"""
    guide = ChannelGuide()
    channels = guide.list_channels()
    
    print("\n" + "="*60)
    print("  📺 Saved Channels")
    print("="*60)
    
    if not channels:
        print("\n  No channels saved yet!")
        print("\n  Add one with:")
        print("    python -m sanchez channels add \"Name\" <host> [port]")
    else:
        print()
        for i, ch in enumerate(channels):
            num = f"[{i + 1}]"
            print(f"  {num:5} {ch.display_name()}")
            print(f"        {ch.connection_string()}")
            if ch.description:
                print(f"        {ch.description}")
            print()
    
    print("="*60)
    print(f"  Config file: {get_channels_file()}")
    print("="*60 + "\n")


# Convenience functions for CLI
def cmd_add_channel(name: str, host: str, port: int = 9999, 
                    mode: str = 'tcp', description: str = '', 
                    favorite: bool = False):
    """Add a channel from command line args"""
    channel = SavedChannel(
        name=name,
        host=host,
        port=port,
        mode=mode,
        description=description,
        favorite=favorite
    )
    
    guide = ChannelGuide()
    is_new = guide.add(channel)
    
    if is_new:
        print(f"✓ Added channel: {name} -> {host}:{port} ({mode})")
    else:
        print(f"✓ Updated channel: {name} -> {host}:{port} ({mode})")


def cmd_remove_channel(name: str):
    """Remove a channel by name"""
    guide = ChannelGuide()
    if guide.remove(name):
        print(f"✓ Removed channel: {name}")
    else:
        print(f"✗ Channel not found: {name}")


def cmd_favorite_channel(name: str, favorite: bool = True):
    """Set/unset favorite status"""
    guide = ChannelGuide()
    if guide.set_favorite(name, favorite):
        status = "favorited" if favorite else "unfavorited"
        print(f"✓ Channel {status}: {name}")
    else:
        print(f"✗ Channel not found: {name}")
