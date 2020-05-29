#include <iostream>
#include <vector>
#include <string>
#include <sys/socket.h>
#include <netinet/in.h>
#include <linux/if_ether.h>
#include <linux/if.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <map>
#include <unistd.h>
#include <netdb.h>
#include <errno.h>
#include "converter.h"

using namespace std;

#define NON_ACE_INTERFACE "eth1"

int portNumberSetup = 17000;

int main()
{
    unsigned char broadcast_mac[ETH_ALEN] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

    int sock_r = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
    if (sock_r < 0)
    {
        printf("error in socket\n");
        return -1;
    }

    unsigned char *buffer = (unsigned char *)malloc(ACE_MAX_PACKET_LEN); //to receive data
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

        struct ethhdr *eth = (struct ethhdr *)(buffer);
        int cmp = memcmp(eth->h_dest, broadcast_mac, ETH_ALEN);
        if (cmp != 0)
        {
            continue;
        }

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
            }
        }

        int fd = getConnection(macAddress, mapOfPorts);

        int start = 14;
        if (buflen == 239)
        {
            start = 18;
        }
        if (send(fd, buffer + start, buflen - start, 0) == -1)
        {
            printf("Error sending datagram");
        }
    }
}

int getConnection(std::array<unsigned char, ETH_ALEN> macAddress, std::map<std::array<unsigned char,ETH_ALEN>, int> mapOfPorts)
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
    char *port;
    sprintf(port, "%d", portNumber);

    struct addrinfo* res = 0;
    struct addrinfo hints;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_DGRAM;
    hints.ai_protocol = 0;
    hints.ai_flags = AI_ADDRCONFIG;
    int err = getaddrinfo(MULTICAST_LOCATION, port, &hints, &res);
    
    int fd = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (fd == -1)
    {
        printf("Error opening outbound socket\n");
        exit(-1);
    }

    const int len = strnlen(NON_ACE_INTERFACE, IFNAMSIZ);
    setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, NON_ACE_INTERFACE, len);

    if (connect(fd, res->ai_addr, sizeof(res)) == -1)
    {
        printf("Error connecting outbound socket\n");
        exit(-1);
    }

    return fd;
}