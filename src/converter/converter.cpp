#include <iostream>
#include <vector>
#include <string>
#include <sys/socket.h>
#include <netinet/in.h>
#include <linux/if_ether.h>
#include <linux/if_packet.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <map>
#include <unistd.h>
#include <netdb.h>
#include <errno.h>
#include "converter.h"

using namespace std;

#define DEFAULT_NON_ACE_INTERFACE "eth1"

int portNumberSetup = 17000;
const char *outputInterface;

int main(int argc, char *argv[])
{
    const char *inputInterface;
    if (argc < 2)
    {
        printf("Usage: %s <ace_interface> [output_interface]\n", argv[0]);
        printf("  ace_interface:    interface connected to the mixer (e.g. eth0)\n");
        printf("  output_interface: interface to send UDP on (default: eth1)\n");
        return -1;
    }

    inputInterface = argv[1];
    if (argc >= 3)
    {
        outputInterface = argv[2];
    }
    else
    {
        outputInterface = DEFAULT_NON_ACE_INTERFACE;
    }
    unsigned char broadcast_mac[ETH_ALEN] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

    int sock_r = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
    if (sock_r < 0)
    {
        printf("error in socket\n");
        return -1;
    }

    // Bind receive socket to the ACE interface only, so the kernel
    // does not deliver packets from other interfaces to this process
    struct sockaddr_ll sll;
    memset(&sll, 0, sizeof(sll));
    sll.sll_family = AF_PACKET;
    sll.sll_protocol = htons(ETH_P_ALL);
    sll.sll_ifindex = if_nametoindex(inputInterface);
    if (sll.sll_ifindex == 0)
    {
        printf("Unknown interface: %s\n", inputInterface);
        return -1;
    }
    if (bind(sock_r, (struct sockaddr *)&sll, sizeof(sll)) < 0)
    {
        perror("Error binding to ACE interface");
        return -1;
    }

    // Increase receive buffer to reduce drops at 48k packets/sec
    int rcvbuf = 2 * 1024 * 1024;
    setsockopt(sock_r, SOL_SOCKET, SO_RCVBUF, &rcvbuf, sizeof(rcvbuf));

    unsigned char buffer[ACE_MAX_PACKET_LEN];
    memset(buffer, 0, ACE_MAX_PACKET_LEN);

    int discardCounter = 100;
    std::map<std::array<unsigned char,ETH_ALEN>, int> mapOfPorts;

    while (true)
    {
        //Receive a network packet and copy in to buffer
        int buflen = recv(sock_r, buffer, ACE_MAX_PACKET_LEN, 0);
        if (buflen < 0)
        {
            printf("Error in reading recvfrom function\n");
            return -1;
        }

        // Reject non-ACE packets early, before any map lookups
        if (buflen != 235 && buflen != 239)
        {
            continue;
        }

        struct ethhdr *eth = (struct ethhdr *)(buffer);
        if (memcmp(eth->h_dest, broadcast_mac, ETH_ALEN) != 0)
        {
            continue;
        }

        int start = (buflen == 239) ? 18 : 14;

        std::array<unsigned char, ETH_ALEN> macAddress;
        std::copy(std::begin(eth->h_source), std::end(eth->h_source), std::begin(macAddress));

        if (discardCounter > 0)
        {
            mapOfPorts.insert(std::make_pair(macAddress, 0));
            discardCounter--;
            continue;
        }
        else if (discardCounter == 0)
        {
            std::map<std::array<unsigned char,ETH_ALEN>, int>::iterator it = mapOfPorts.begin();
            while (it != mapOfPorts.end())
            {
                int portNumber = portNumberSetup;
                portNumberSetup++;
                it->second = openConnection(portNumber);
                it++;
            }
            discardCounter = -1;
        }

        int fd = getConnection(macAddress, mapOfPorts);
        // Send only the 195 bytes of audio channel data (65 channels x 3 bytes),
        // discarding the 26 bytes of control/bridged data at the end
        int audioDataLen = 65 * 3;
        if (send(fd, buffer + start, audioDataLen, 0) == -1)
        {
            printf("Error sending datagram");
        }
    }
}

int getConnection(std::array<unsigned char, ETH_ALEN> macAddress, std::map<std::array<unsigned char,ETH_ALEN>, int>& mapOfPorts)
{
    std::map<std::array<unsigned char,ETH_ALEN>, int>::iterator it = mapOfPorts.find(macAddress);
    if (it == mapOfPorts.end())
    {
        //create a new port
        int port = portNumberSetup;
        portNumberSetup++;

        int fd = openConnection(port);

        mapOfPorts.insert(std::make_pair(macAddress, fd));
        return fd;
    }
    return it->second;
}

int openConnection(int portNumber)
{
    char port[16];
    sprintf(port, "%d", portNumber);

    struct addrinfo* res = 0;
    struct addrinfo hints;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;
    hints.ai_protocol = 0;
    hints.ai_flags = AI_ADDRCONFIG;
    int err = getaddrinfo(MULTICAST_LOCATION, port, &hints, &res);
    if (err != 0)
    {
        fprintf(stderr, "Error resolving multicast address: %s\n", gai_strerror(err));
        exit(-1);
    }

    int fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (fd == -1)
    {
        perror("Error opening outbound socket\n");
        freeaddrinfo(res);
        exit(-1);
    }

    const int len = strnlen(outputInterface, IFNAMSIZ);
    setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, outputInterface, len);

    if (connect(fd, res->ai_addr, res->ai_addrlen) == -1)
    {
        perror("Error connecting outbound socket\n");
        close(fd);
        freeaddrinfo(res);
        exit(-1);
    }

    freeaddrinfo(res);
    return fd;
}