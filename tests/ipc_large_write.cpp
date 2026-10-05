// A small nonblocking socket buffer must not truncate a JSON response.
#include "../simple-ipc/src/unix/common/unix_connection.h"
#include <sys/socket.h>
#include <fcntl.h>
#include <unistd.h>
#include <thread>
#include <string>
#include <iostream>
#include <chrono>

int main() {
    int pair[2];
    if(socketpair(AF_UNIX, SOCK_STREAM, 0, pair)) return 1;
    int size = 4096;
    setsockopt(pair[0], SOL_SOCKET, SO_SNDBUF, &size, sizeof(size));
    fcntl(pair[0], F_SETFL, fcntl(pair[0], F_GETFL) | O_NONBLOCK);
    std::string payload(180000, 'x'), received;
    payload = "{\"value\":\"" + payload + "\"}\n";
    std::thread reader([&] {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        char buffer[1024]; ssize_t count;
        while((count = read(pair[1], buffer, sizeof(buffer))) > 0) received.append(buffer, count);
    });
    bool success = true;
    try { simpleipc::unix_connection(pair[0]).send_data(payload.data(), payload.size()); }
    catch(const std::exception& error) { std::cerr << error.what() << '\n'; success = false; }
    shutdown(pair[0], SHUT_WR); reader.join(); close(pair[0]); close(pair[1]);
    return success && received == payload ? 0 : 1;
}
