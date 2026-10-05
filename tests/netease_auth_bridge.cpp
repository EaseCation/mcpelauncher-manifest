// Account-free contract tests: never load Minecraft or contact a server.
#include "../mcpelauncher-client/src/jni/netease_sdk.h"
#include "../mcpelauncher-client/src/main.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>
#include <filesystem>
#include <fstream>
#include <sys/stat.h>
#include <unistd.h>

LauncherOptions options{};

int main() {
    char directory[] = "/tmp/netease-auth-test-XXXXXX";
    assert(mkdtemp(directory));
    auto path = std::filesystem::path(directory) / "session.json";
    options.neteaseOnline = true;
    options.neteasePackage = "com.netease.mctest";
    options.neteaseSessionFile = path.string();
    nlohmann::json payload = {
        {"schema_version", 1}, {"package_name", options.neteasePackage},
        {"created_at", std::chrono::duration_cast<std::chrono::seconds>(std::chrono::system_clock::now().time_since_epoch()).count()},
        {"sauth", {{"sdkuid", "test-user"}, {"sessionid", "test-token"}, {"deviceid", "test-device"},
                   {"gameid", "x19"}, {"app_channel", "netease"}, {"login_channel", "netease"},
                   {"platform", "ad"}, {"udid", "test-udid"}, {"sdk_version", "3.4.0"}}}
    };
    auto save = [&](const nlohmann::json& value, int mode = 0600) {
        std::ofstream(path) << value.dump();
        assert(chmod(path.c_str(), mode) == 0);
    };
    {
        NetEaseSdk sdk;
        int inits = 0, logins = 0;
        assert(sdk.init()); assert(!sdk.init());
        sdk.login();
        sdk.tick([&](bool init, int code) { assert(init && code == 0); ++inits; });
        assert(inits == 1 && logins == 0); // Missing file must not mean login success.
    }
    save(payload);
    {
        NetEaseSdk sdk;
        sdk.login();
        int callbacks = 0;
        sdk.tick([&](bool init, int code) {
            assert(!init && code == 0);
            // A callback may synchronously reenter getters: verify no lock held.
            assert(sdk.getString("SESSION") == "test-token");
            assert(nlohmann::json::parse(sdk.getString("SAUTH_JSON"))["sdkuid"] == "test-user");
            ++callbacks;
        });
        assert(callbacks == 1);
        sdk.tick([&](bool, int) { assert(false); });
    }
    auto rejected = [&]() {
        NetEaseSdk sdk;
        sdk.login();
        int callbacks = 0;
        sdk.tick([&](bool init, int code) { assert(!init && code != 0); ++callbacks; });
        assert(callbacks == 1 && sdk.getString("SESSION").empty());
    };
    save(payload, 0644); rejected();
    auto bad = payload; bad["sauth"]["gameid"] = "other-product";
    save(bad); rejected();
    bad = payload; bad["sauth"].erase("deviceid");
    save(bad); rejected();
    bad = payload; bad["created_at"] = 1;
    save(bad); rejected();
    std::filesystem::remove(path);
    auto target = std::filesystem::path(directory) / "target.json";
    std::ofstream(target) << payload.dump(); chmod(target.c_str(), 0600);
    std::filesystem::create_symlink(target, path); rejected();
    std::filesystem::remove_all(directory);
    std::puts("PASS: missing input, SAuth handoff, reentrant callback, permissions, product, expiry and symlink rejection");
}
