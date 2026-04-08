# ACE UDP Payload Format

This document describes the UDP payload sent by `ah_converter` when forwarding
Allen & Heath ACE audio data from one network interface to another.

## Transport

- **Protocol:** UDP multicast
- **Multicast address:** `239.0.147.155`
- **Ports:** Starting at `17000`, one port per unique source device (MAC address)
  - First device discovered: port 17000
  - Second device discovered: port 17001
  - etc.
- **Packet rate:** 48,000 packets/second (one per audio sample period)

## Payload Structure

Each UDP packet is **195 bytes** containing audio channel data only. Control
and bridged network data from the ACE frame is discarded.

```
Offset  Size     Description
------  ----     -----------
0       3        Channel 0 - Sync signal (24 bits)
3       3        Channel 1 - Audio channel (24 bits)
6       3        Channel 2 - Audio channel (24 bits)
...     ...      ...
192     3        Channel 64 - Audio channel (24 bits)
------  ----
Total:  195 bytes (65 channels x 3 bytes)
```

## Audio Channel Data (bytes 0-194)

- **65 channels**, 3 bytes (24 bits) each = 195 bytes
- **Sampling rate:** 48 kHz
- **Bit depth:** 24-bit

### Channel 0: Sync Signal

Channel 0 is a synchronization signal, not audio. Only the least significant
byte carries data (the upper two bytes are always `0x00 0x00`). The sync byte
cycles through this repeating 16-value pattern:

```
0x40, 0x44, 0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C,
0x60, 0x64, 0x68, 0x6C, 0x70, 0x74, 0x78, 0x7C
```

### Channels 1-64: Audio

Audio samples are 24-bit, transmitted in ACE byte order. To convert to standard
PCM (little-endian) for WAV files or audio processing, apply this transformation:

```c
uint32_t ace_to_pcm24(uint32_t src)
{
    // Reverse bytes 0 and 2
    src = (src & 0xff0000) >> 16 | (src & 0x00ff00) | (src & 0x0000ff) << 16;
    // Swap nibbles within each byte
    src = (src & 0xf0f0f0) >>  4 | (src & 0x0f0f0f) <<  4;
    return src;
}
```

### Mixer Channel Mapping

Mixer input channels are NOT mapped 1:1 to ACE channels. They are spaced
8 channels apart:

| Mixer Channel | ACE Channel |
|---------------|-------------|
| 1             | 1           |
| 2             | 9           |
| 3             | 17          |
| 4             | 25          |
| 5             | 33          |
| 6             | 41          |
| 7             | 49          |
| 8             | 57          |
| 9             | 2           |
| 10            | 10          |
| ...           | ...         |

General formula: `ace_channel = ((mixer_channel - 1) % 8) * 8 + ((mixer_channel - 1) / 8) + 1`

## Example: Reading a Single Audio Channel from UDP

```python
import socket
import struct

MULTICAST_GROUP = "239.0.147.155"
PORT = 17000  # First device

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("", PORT))

mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

def ace_to_pcm24(b0, b1, b2):
    """Convert 3 ACE bytes to a signed 24-bit PCM value."""
    # Reverse bytes and swap nibbles
    b0 = ((b0 & 0xF0) >> 4) | ((b0 & 0x0F) << 4)
    b1 = ((b1 & 0xF0) >> 4) | ((b1 & 0x0F) << 4)
    b2 = ((b2 & 0xF0) >> 4) | ((b2 & 0x0F) << 4)
    value = (b2 << 16) | (b1 << 8) | b0
    if value & 0x800000:  # Sign extend
        value -= 0x1000000
    return value

while True:
    data, addr = sock.recvfrom(256)
    if len(data) != 195:
        continue

    # Read mixer channel 1 (ACE channel 1, offset 3 bytes)
    ace_ch = 1
    offset = ace_ch * 3
    sample = ace_to_pcm24(data[offset], data[offset+1], data[offset+2])
    print(f"Channel 1 sample: {sample}")
```

