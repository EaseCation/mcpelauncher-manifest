// 主机信息接口必须按 Bionic 布局写入调用方缓冲区（游戏内置 Tracy 等在启动时调用）。
#include <libc_shim.h>
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <cstring>
#include <string>
#include <unordered_map>

namespace {

constexpr size_t kGuard = 2048;          // 覆盖 Darwin 1280 字节 utsname 的越界范围
constexpr size_t kUtsname = 6 * 65;      // Bionic struct utsname
constexpr size_t kSysinfo = sizeof(long) == 8 ? 112 : 64; // Bionic struct sysinfo
constexpr unsigned char kFill = 0xa5;

struct Guarded {
    unsigned char bytes[kGuard + 4096 + kGuard];
    explicit Guarded() { std::memset(bytes, kFill, sizeof(bytes)); }
    unsigned char* data() { return bytes + kGuard; }
    // 返回 [size, size + kGuard) 及前置保护区内是否全部未被改写
    bool intact(size_t size) const {
        for(size_t i = 0; i < kGuard; ++i)
            if(bytes[i] != kFill || bytes[kGuard + size + i] != kFill) return false;
        return true;
    }
};

bool terminated(const unsigned char* field) {
    return std::memchr(field, 0, 65) != nullptr;
}

}

int main() {
    std::unordered_map<std::string, void*> symbols;
    for(const auto& symbol : shim::get_shimmed_symbols()) symbols[symbol.name] = symbol.value;

    auto androidUname = reinterpret_cast<int(*)(void*)>(symbols.at("uname"));
    Guarded uts;
    assert(androidUname(uts.data()) == 0);
    assert(uts.intact(kUtsname));
    for(int field = 0; field < 6; ++field)
        assert(terminated(uts.data() + field * 65));
    auto sysname = reinterpret_cast<const char*>(uts.data());
    auto release = reinterpret_cast<const char*>(uts.data() + 2 * 65);
    auto machine = reinterpret_cast<const char*>(uts.data() + 4 * 65);
    assert(sysname[0] && release[0] && machine[0]);

    auto androidSysinfo = reinterpret_cast<int(*)(void*)>(symbols.at("sysinfo"));
    Guarded info;
    assert(androidSysinfo(info.data()) == 0);
    assert(info.intact(kSysinfo));
    unsigned long totalram = 0;
    unsigned int memUnit = 0;
    std::memcpy(&totalram, info.data() + 4 * sizeof(long), sizeof(totalram));
    std::memcpy(&memUnit, info.data() + (sizeof(long) == 8 ? 104 : 52), sizeof(memUnit));
    assert(memUnit != 0 && totalram != 0);

    // 无登录会话时允许返回 NULL，但必须是可调用的宿主实现而非终止桩。
    auto androidGetlogin = reinterpret_cast<const char*(*)()>(symbols.at("getlogin"));
    const char* login = androidGetlogin();
    assert(!login || login[0]);
    return 0;
}
