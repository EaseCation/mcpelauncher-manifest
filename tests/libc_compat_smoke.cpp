// Standalone behavior checks against the same symbol table used by Android ELF.
#include <libc_shim.h>
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <cstring>
#include <ctime>
#include <unordered_map>
#include <cstdio>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/mman.h>
#include <unistd.h>

int main() {
    std::unordered_map<std::string, void*> symbols;
    for(const auto& symbol : shim::get_shimmed_symbols()) symbols[symbol.name] = symbol.value;
    auto clock = reinterpret_cast<int(*)(unsigned, timespec*)>(symbols.at("clock_gettime"));
    timespec before{}, after{};
    assert(clock(4, &before) == 0);
    assert(clock(4, &after) == 0);
    assert(after.tv_sec > before.tv_sec || (after.tv_sec == before.tv_sec && after.tv_nsec >= before.tv_nsec));
    auto entropy = reinterpret_cast<int(*)(void*, size_t)>(symbols.at("getentropy"));
    auto error = reinterpret_cast<int*(*)()>(symbols.at("__errno"));
    unsigned char bytes[258];
    std::memset(bytes, 0xa5, sizeof(bytes));
    assert(entropy(bytes + 1, 256) == 0);
    assert(bytes[0] == 0xa5 && bytes[257] == 0xa5);
    assert(entropy(bytes, 257) == -1 && *error() == 5); // Android EIO
    auto init = reinterpret_cast<int(*)(void*, int, unsigned)>(symbols.at("sem_init"));
    auto wait = reinterpret_cast<int(*)(void*)>(symbols.at("sem_trywait"));
    auto post = reinterpret_cast<int(*)(void*)>(symbols.at("sem_post"));
    auto destroy = reinterpret_cast<int(*)(void*)>(symbols.at("sem_destroy"));
    alignas(16) unsigned char sem[64]{};
    assert(init(sem, 0, 0) == 0);
    assert(wait(sem) == -1 && *error() == 11); // Android EAGAIN
    assert(post(sem) == 0);
    assert(wait(sem) == 0);
    assert(wait(sem) == -1 && *error() == 11);
    assert(destroy(sem) == 0);
    auto androidFcntl = reinterpret_cast<int(*)(int, int, void*)>(symbols.at("fcntl"));
    int sockets[2];
    auto androidSocketpair = reinterpret_cast<int(*)(int, int, int, int*)>(symbols.at("socketpair"));
    assert(androidSocketpair(1, 1 | 0x800 | 0x80000, 0, sockets) == 0);
    assert((::fcntl(sockets[0], F_GETFL) & O_NONBLOCK) && (::fcntl(sockets[1], F_GETFL) & O_NONBLOCK));
    assert(::fcntl(sockets[0], F_GETFD) == FD_CLOEXEC && ::fcntl(sockets[1], F_GETFD) == FD_CLOEXEC);
    const char input = 'x'; char output = 0;
    assert(::write(sockets[0], &input, 1) == 1);
    assert(::read(sockets[1], &output, 1) == 1 && output == input);
    assert(androidFcntl(sockets[0], 2, reinterpret_cast<void*>(1)) == 0);
    assert(androidFcntl(sockets[0], 1, nullptr) == FD_CLOEXEC);
    assert(androidFcntl(sockets[0], 4, reinterpret_cast<void*>(0x802)) == 0);
    assert((::fcntl(sockets[0], F_GETFL) & O_NONBLOCK) != 0);
    assert((androidFcntl(sockets[0], 3, nullptr) & 0x800) != 0);
    assert(androidFcntl(sockets[0], 4, reinterpret_cast<void*>(2)) == 0);
    assert((::fcntl(sockets[0], F_GETFL) & O_NONBLOCK) == 0);
    assert(androidFcntl(-1, 3, nullptr) == -1 && *error() == 9); // Android EBADF
    ::close(sockets[0]); ::close(sockets[1]);
    auto androidMmap = reinterpret_cast<void*(*)(void*, size_t, int, int, int, int64_t)>(symbols.at("mmap"));
    auto page = static_cast<size_t>(::sysconf(_SC_PAGESIZE));
    auto region = static_cast<unsigned char*>(::mmap(nullptr, page * 2, PROT_READ | PROT_WRITE,
                                                    MAP_PRIVATE | MAP_ANON, -1, 0));
    assert(region != MAP_FAILED);
    region[0] = 42;
    region[page] = 73;
    // Only remap the second page of a reservation owned by this test.
    assert(androidMmap(region + page, page, PROT_READ | PROT_WRITE, 0x32, -1, 0) == region + page);
    assert(region[0] == 42 && region[page] == 0);
    assert(::munmap(region, page * 2) == 0);
    std::puts("PASS: clocks, entropy, semaphores, socket fcntl flags, fixed mmap and errno");
}
