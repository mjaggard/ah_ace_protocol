#!/usr/bin/env python3
"""
Generates fake ACE Ethernet frames and sends them on a network interface.
Simulates an Allen & Heath mixer for testing ah_converter without hardware.

Audio is generated at a fixed 48 kHz sample rate (one sample per frame, matching
real ACE). The --rate flag controls how fast frames are sent, but the audio
content is always generated as if played back at 48 kHz. This means:

  --rate 48000   Real-time playback (1 second of audio per second)
  --rate 24000   Half-speed (1 second of audio takes 2 seconds to send)
  --rate 96000   Double-speed (may not keep up on slow hardware)

The default rate of 1000 is fine for testing the forwarding pipeline. The audio
will sound correct once received and played back at 48 kHz in a DAW regardless
of the send rate.

Test tone layout (all at -6 dBFS):
  ACE Ch 1  (Mixer Ch 1):  440 Hz  (A4 concert pitch)
  ACE Ch 9  (Mixer Ch 2):  1000 Hz (standard line-up tone)
  ACE Ch 17 (Mixer Ch 3):  261.63 Hz (C4 middle C)
  ACE Ch 25 (Mixer Ch 4):  100 Hz  (low frequency test)
  All other channels:       silence

Usage:
    sudo python3 ace_sender.py <interface> [--rate PACKETS_PER_SEC] [--duration SECONDS]

Example:
    # Set up veth pair first (see setup_veth.sh), then:
    sudo python3 ace_sender.py veth_ace_peer --rate 48000 --duration 10
"""

import argparse
import math
import socket
import time

ETH_P_ALL = 0x0003
BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'
FAKE_SOURCE_MAC = b'\x00\x10\x4b\xab\xcd\xef'  # A&H OUI prefix 00:10:4b
ACE_ETHERTYPE = b'\x88\xb5'  # EtherType used by ACE (IEEE 802.1 local experimental)
SAMPLE_RATE = 48000

# Sync pattern (post-conversion PCM values)
SYNC_PATTERN = [
    0x40, 0x44, 0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C,
    0x60, 0x64, 0x68, 0x6C, 0x70, 0x74, 0x78, 0x7C,
]

# Test tones: (ACE channel, frequency Hz, description)
# These use the real mixer-to-ACE channel mapping
TEST_TONES = [
    (1,  440.00,  "A4 concert pitch"),
    (9,  1000.00, "1 kHz line-up tone"),
    (17, 261.63,  "C4 middle C"),
    (25, 100.00,  "100 Hz low freq test"),
]

# -6 dBFS in 24-bit signed: 2^23 * 10^(-6/20) ~= 4194304 * 0.501 ~= 2102017
AMPLITUDE = int((2**23 - 1) * 10**(-6.0/20.0))


def pcm_to_ace_bytes(value):
    """Convert a signed 24-bit PCM value to 3 ACE wire-format bytes.

    Inverse of the documented ace_to_pcm24 conversion:
    1. Swap nibbles in each byte
    2. Reverse bytes 0 and 2
    """
    value &= 0xFFFFFF
    # Swap nibbles within each byte
    value = ((value & 0xF0F0F0) >> 4) | ((value & 0x0F0F0F) << 4)
    # Reverse bytes 0 and 2
    b0 = (value >> 0) & 0xFF
    b1 = (value >> 8) & 0xFF
    b2 = (value >> 16) & 0xFF
    return bytes([b2, b1, b0])


# Pre-compute which ACE channels have tones and their frequencies
TONE_MAP = {}
for ace_ch, freq, _desc in TEST_TONES:
    TONE_MAP[ace_ch] = freq

# Pre-compute silence in ACE wire format
SILENCE_ACE = pcm_to_ace_bytes(0)


def build_ace_frame(sync_index, sample_number):
    """Build a single 235-byte ACE Ethernet frame (no VLAN tag)."""
    # Ethernet header (14 bytes)
    header = BROADCAST_MAC + FAKE_SOURCE_MAC + ACE_ETHERTYPE

    # Channel 0: sync signal
    sync_value = SYNC_PATTERN[sync_index % len(SYNC_PATTERN)]
    channel_data = pcm_to_ace_bytes(sync_value)

    # Channels 1-64
    phase_base = 2.0 * math.pi * sample_number / SAMPLE_RATE
    for ch in range(1, 65):
        freq = TONE_MAP.get(ch)
        if freq is not None:
            sample = int(AMPLITUDE * math.sin(freq * phase_base))
            channel_data += pcm_to_ace_bytes(sample)
        else:
            channel_data += SILENCE_ACE

    # Control/bridged data (26 bytes) - zeros
    control_data = b'\x00' * 26

    frame = header + channel_data + control_data
    assert len(frame) == 235, f"Frame size {len(frame)} != 235"
    return frame


def main():
    parser = argparse.ArgumentParser(
        description='Send fake ACE Ethernet frames for testing ah_converter',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('interface',
                        help='Network interface to send on (e.g. veth_ace_peer)')
    parser.add_argument('--rate', type=int, default=1000,
                        help='Packets per second (default: 1000, use 48000 for real-time audio)')
    parser.add_argument('--duration', type=float, default=10.0,
                        help='Seconds of audio to generate (default: 10)')
    args = parser.parse_args()

    total_samples = int(SAMPLE_RATE * args.duration)

    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
    sock.bind((args.interface, 0))

    interval = 1.0 / args.rate

    print(f"Sending {args.duration}s of ACE audio ({total_samples} frames)")
    print(f"Interface:  {args.interface}")
    print(f"Send rate:  {args.rate} packets/sec")
    print(f"Source MAC: {FAKE_SOURCE_MAC.hex(':')}")
    print(f"Frame size: 235 bytes (no VLAN)")
    print()
    print("Test tones (-6 dBFS):")
    for ace_ch, freq, desc in TEST_TONES:
        mixer_ch = (ace_ch - 1) % 8 * 8 + (ace_ch - 1) // 8 + 1
        print(f"  ACE ch {ace_ch:>2} (mixer ch {mixer_ch:>2}):  {freq:>8.2f} Hz  ({desc})")
    print(f"  All other channels: silence")
    print()

    sync_index = 0
    sent = 0

    try:
        start_time = time.monotonic()
        while sent < total_samples:
            frame = build_ace_frame(sync_index, sent)
            sock.send(frame)
            sent += 1
            sync_index = (sync_index + 1) % len(SYNC_PATTERN)

            # Rate limiting
            expected_time = start_time + sent * interval
            sleep_time = expected_time - time.monotonic()
            if sleep_time > 0:
                time.sleep(sleep_time)

            if sent % args.rate == 0:
                elapsed = time.monotonic() - start_time
                audio_secs = sent / SAMPLE_RATE
                print(f"  {audio_secs:.1f}s of audio sent  "
                      f"({sent}/{total_samples} samples, {elapsed:.1f}s elapsed)")

    except KeyboardInterrupt:
        print("\nInterrupted.")

    elapsed = time.monotonic() - start_time
    audio_secs = sent / SAMPLE_RATE
    print(f"\nDone: {audio_secs:.2f}s of audio ({sent} frames) "
          f"sent in {elapsed:.1f}s ({sent/max(elapsed,0.001):.0f} pkt/s)")
    sock.close()


if __name__ == '__main__':
    main()
