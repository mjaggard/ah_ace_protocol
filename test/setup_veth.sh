#!/bin/bash
# Creates a virtual Ethernet (veth) pair for testing ah_converter
# without Allen & Heath hardware.
#
# This creates two linked interfaces:
#   veth_ace      - the "mixer side" (converter listens here)
#   veth_ace_peer - the "test side"  (sender script injects frames here)
#
# Usage:
#   sudo ./setup_veth.sh          # create interfaces
#   sudo ./setup_veth.sh teardown  # remove interfaces

set -e

if [ "$1" = "teardown" ]; then
    echo "Removing veth_ace pair..."
    ip link delete veth_ace 2>/dev/null && echo "Done." || echo "Already removed."
    exit 0
fi

echo "Creating veth pair: veth_ace <-> veth_ace_peer"
ip link add veth_ace type veth peer name veth_ace_peer

echo "Bringing interfaces up..."
ip link set veth_ace up
ip link set veth_ace_peer up

# Disable IPv6 to reduce noise on the raw socket
sysctl -q net.ipv6.conf.veth_ace.disable_ipv6=1
sysctl -q net.ipv6.conf.veth_ace_peer.disable_ipv6=1

echo ""
echo "Ready. Interfaces:"
ip -br link show veth_ace
ip -br link show veth_ace_peer
echo ""
echo "Test procedure:"
echo "  Terminal 1: sudo ./ah_converter eth0      # (or whichever output interface you want)"
echo "  Terminal 2: python3 ace_receiver.py --port 17000"
echo "  Terminal 3: sudo python3 ace_sender.py veth_ace_peer --rate 100 --count 500"
echo ""
echo "Note: ah_converter receives on ALL interfaces (not bound), so frames"
echo "injected on veth_ace_peer will appear on veth_ace and be picked up."
echo ""
echo "To tear down:  sudo $0 teardown"
