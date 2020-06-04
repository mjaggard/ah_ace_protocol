#include <linux/if_ether.h>
#include <map>

#define ACE_MAX_PACKET_LEN 239
#define MULTICAST_LOCATION "239.0.147.155"


int main();
int getConnection(std::array<unsigned char, ETH_ALEN> macAddress, std::map<std::array<unsigned char,ETH_ALEN>, int> mapOfPorts);
int openConnection(int portNumber);