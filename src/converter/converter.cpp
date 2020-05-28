#include <iostream>
#include <vector>
#include <string>
#include <sys/socket.h>
#include <linux/if_ether.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <gst/gst.h>

#define ACE_MAX_PACKET_LEN 239

using namespace std;

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

    while (true)
    {
        struct sockaddr saddr;
        int saddr_len = sizeof(saddr);

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

        extractPacket(buffer);
    }
}