#!/usr/bin/env python3
"""
Receives UDP multicast packets from ah_converter and validates the payload.
Checks sync signal integrity and reports audio channel statistics.

Usage:
    python3 ace_receiver.py [--port PORT] [--bind ADDR] [--count NUM_PACKETS]

Example:
    python3 ace_receiver.py --port 17000 --count 200
"""

import argparse
import socket
import struct

MULTICAST_GROUP = '239.0.147.155'
EXPECTED_PAYLOAD_SIZE = 195  # 65 channels x 3 bytes

SYNC_PATTERN = [
    0x40, 0x44, 0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C,
    0x60, 0x64, 0x68, 0x6C, 0x70, 0x74, 0x78, 0x7C,
]


def ace_to_pcm24(b0, b1, b2):
    """Convert 3 ACE wire-format bytes to a signed 24-bit PCM value."""
    # Swap nibbles within each byte
    b0 = ((b0 & 0xF0) >> 4) | ((b0 & 0x0F) << 4)
    b1 = ((b1 & 0xF0) >> 4) | ((b1 & 0x0F) << 4)
    b2 = ((b2 & 0xF0) >> 4) | ((b2 & 0x0F) << 4)
    # Reverse bytes 0 and 2, assemble
    value = (b2 << 16) | (b1 << 8) | b0
    if value & 0x800000:
        value -= 0x1000000
    return value


def main():
    parser = argparse.ArgumentParser(description='Receive and validate ACE UDP packets')
    parser.add_argument('--port', type=int, default=17000,
                        help='UDP port to listen on (default: 17000)')
    parser.add_argument('--bind', default='',
                        help='Local address to bind to (default: all interfaces)')
    parser.add_argument('--count', type=int, default=200,
                        help='Number of packets to receive (default: 200, 0 = unlimited)')
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))

    mreq = struct.pack('4sl', socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print(f"Listening on {MULTICAST_GROUP}:{args.port}")
    print(f"Expected payload size: {EXPECTED_PAYLOAD_SIZE} bytes")
    print()

    received = 0
    sync_errors = 0
    size_errors = 0
    expected_sync = None
    channel_min = [0x7FFFFF] * 65
    channel_max = [-0x800000] * 65

    try:
        while args.count == 0 or received < args.count:
            data, addr = sock.recvfrom(1024)
            received += 1

            if len(data) != EXPECTED_PAYLOAD_SIZE:
                size_errors += 1
                if size_errors <= 5:
                    print(f"  [FAIL] Packet {received}: size {len(data)}, "
                          f"expected {EXPECTED_PAYLOAD_SIZE}")
                continue

            # Decode all 65 channels
            for ch in range(65):
                offset = ch * 3
                sample = ace_to_pcm24(data[offset], data[offset+1], data[offset+2])

                if ch == 0:
                    # Validate sync signal
                    sync_val = sample & 0xFF
                    if expected_sync is not None and sync_val != expected_sync:
                        sync_errors += 1
                        if sync_errors <= 5:
                            print(f"  [SYNC] Packet {received}: got 0x{sync_val:02x}, "
                                  f"expected 0x{expected_sync:02x}")
                    # Compute next expected sync
                    idx = None
                    for i, v in enumerate(SYNC_PATTERN):
                        if v == sync_val:
                            idx = i
                            break
                    if idx is not None:
                        expected_sync = SYNC_PATTERN[(idx + 1) % len(SYNC_PATTERN)]
                    else:
                        expected_sync = None
                else:
                    channel_min[ch] = min(channel_min[ch], sample)
                    channel_max[ch] = max(channel_max[ch], sample)

            # Progress
            if received % 50 == 0:
                print(f"  Received {received} packets...")

    except KeyboardInterrupt:
        pass

    print()
    print(f"=== Results ({received} packets) ===")
    print(f"Size errors:  {size_errors}")
    print(f"Sync errors:  {sync_errors}")
    if received > size_errors:
        print(f"Sync signal:  OK" if sync_errors == 0 else f"Sync signal:  ERRORS")

    # Show channel activity summary
    active_channels = []
    for ch in range(1, 65):
        if channel_min[ch] != 0 or channel_max[ch] != 0:
            active_channels.append(ch)

    print(f"Active audio channels: {len(active_channels)}/64")
    if active_channels:
        print()
        print(f"  {'Channel':>8}  {'Min':>10}  {'Max':>10}")
        print(f"  {'-------':>8}  {'---':>10}  {'---':>10}")
        for ch in active_channels[:16]:
            print(f"  {ch:>8}  {channel_min[ch]:>10}  {channel_max[ch]:>10}")
        if len(active_channels) > 16:
            print(f"  ... and {len(active_channels) - 16} more")

    if size_errors == 0 and sync_errors == 0 and received > 0:
        print()
        print("PASS: All packets valid")
    else:
        print()
        print("FAIL: Errors detected")

    sock.close()


if __name__ == '__main__':
    main()
