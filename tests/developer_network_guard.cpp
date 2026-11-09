// Linux 进程内网络守卫：只放行回环、本地套接字和显式声明的 UDP 端点。
#include "developer_network_guard.h"
#include <cstdio>
#include <cstdlib>
#include <unistd.h>

namespace {
int calls = 0;
int failures = 0;

void check(bool condition, const char* message) {
    if(!condition) { std::fprintf(stderr, "FAIL: %s\n", message); ++failures; }
}

sockaddr_in v4(const char* address, uint16_t port) {
    sockaddr_in result{};
    result.sin_family = AF_INET;
    result.sin_port = htons(port);
    inet_pton(AF_INET, address, &result.sin_addr);
    return result;
}

sockaddr_in6 v6(const char* address, uint16_t port) {
    sockaddr_in6 result{};
    result.sin6_family = AF_INET6;
    result.sin6_port = htons(port);
    inet_pton(AF_INET6, address, &result.sin6_addr);
    return result;
}
}

int main() {
    std::unordered_map<std::string, void*> libC;
    libC["connect"] = (void*)+[](int, const sockaddr*, socklen_t) -> int { ++calls; return 0; };
    libC["sendto"] = (void*)+[](int, const void*, size_t size, int, const sockaddr*, socklen_t) -> ssize_t { ++calls; return (ssize_t)size; };
    libC["sendmsg"] = (void*)+[](int, const msghdr*, int) -> ssize_t { ++calls; return 1; };

    bool rejected = false;
    try { DeveloperNetworkGuard::parse("udp:example.com:19132"); } catch(const std::exception&) { rejected = true; }
    check(rejected, "names are rejected; the helper resolves them");
    rejected = false;
    try { DeveloperNetworkGuard::parse("tcp:1.2.3.4:80"); } catch(const std::exception&) { rejected = true; }
    check(rejected, "only UDP allowances are accepted");

    DeveloperNetworkGuard::install(libC, {"udp:203.0.113.7:19132", "udp:[2001:db8::7]:19132"});
    auto connectFn = reinterpret_cast<int (*)(int, const sockaddr*, socklen_t)>(libC.at("connect"));
    auto sendtoFn = reinterpret_cast<ssize_t (*)(int, const void*, size_t, int, const sockaddr*, socklen_t)>(libC.at("sendto"));
    auto sendmsgFn = reinterpret_cast<ssize_t (*)(int, const msghdr*, int)>(libC.at("sendmsg"));

    int udp = socket(AF_INET, SOCK_DGRAM, 0), tcp = socket(AF_INET, SOCK_STREAM, 0);
    int udp6 = socket(AF_INET6, SOCK_DGRAM, 0);
    check(udp >= 0 && tcp >= 0 && udp6 >= 0, "test sockets");

    auto loop = v4("127.0.0.1", 19132);
    check(connectFn(tcp, (sockaddr*)&loop, sizeof(loop)) == 0, "IPv4 loopback TCP is allowed");
    auto loop6 = v6("::1", 1);
    check(connectFn(udp6, (sockaddr*)&loop6, sizeof(loop6)) == 0, "IPv6 loopback is allowed");
    auto mapped = v6("::ffff:127.0.0.1", 1);
    check(connectFn(udp6, (sockaddr*)&mapped, sizeof(mapped)) == 0, "IPv4-mapped loopback is allowed");
    sockaddr_un local{}; local.sun_family = AF_UNIX;
    check(connectFn(tcp, (sockaddr*)&local, sizeof(local)) == 0, "Unix sockets are allowed");

    int before = calls;
    auto external = v4("8.8.8.8", 53);
    errno = 0;
    check(connectFn(udp, (sockaddr*)&external, sizeof(external)) == -1 && errno == ENETUNREACH, "external connect is blocked");
    check(sendtoFn(udp, "x", 1, 0, (sockaddr*)&external, sizeof(external)) == -1, "external sendto is blocked");
    auto broadcast = v4("255.255.255.255", 19132);
    check(sendtoFn(udp, "x", 1, 0, (sockaddr*)&broadcast, sizeof(broadcast)) == -1, "broadcast discovery is blocked");
    msghdr message{}; message.msg_name = &external; message.msg_namelen = sizeof(external);
    check(sendmsgFn(udp, &message, 0) == -1, "external sendmsg is blocked");
    auto server = v4("203.0.113.7", 19132);
    check(connectFn(tcp, (sockaddr*)&server, sizeof(server)) == -1, "allowance does not cover TCP");
    auto otherPort = v4("203.0.113.7", 19133);
    check(sendtoFn(udp, "x", 1, 0, (sockaddr*)&otherPort, sizeof(otherPort)) == -1, "allowance is port specific");
    check(calls == before, "blocked calls never reach the host");

    check(sendtoFn(udp, "x", 1, 0, (sockaddr*)&server, sizeof(server)) == 1, "declared UDP server is allowed");
    auto server6 = v6("2001:db8::7", 19132);
    check(sendtoFn(udp6, "x", 1, 0, (sockaddr*)&server6, sizeof(server6)) == 1, "declared IPv6 UDP server is allowed");
    check(sendtoFn(udp, "x", 1, 0, nullptr, 0) == 1, "connected sockets send without a destination");
    sockaddr truncated{}; truncated.sa_family = AF_INET;
    check(connectFn(udp, &truncated, sizeof(sa_family_t) + 2) == -1, "truncated addresses are blocked");
    sockaddr unknown{}; unknown.sa_family = 17; // AF_PACKET
    check(connectFn(udp, &unknown, sizeof(unknown)) == -1, "unknown families are blocked");

    close(udp); close(tcp); close(udp6);
    if(failures) return 1;
    std::puts("developer network guard ok");
    return 0;
}
