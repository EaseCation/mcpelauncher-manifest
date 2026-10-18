// Exercise request ownership/cancellation and GL state restoration without a GPU.
#include "developer_screenshot.h"
#include "settings.h"
#include "glad/glad.h"
#include <game_window.h>
#include <filesystem>
#include <fstream>
#include <map>
#include <stdexcept>
#include <thread>
#include <sys/stat.h>
#include <sys/resource.h>
#include <csignal>
#include <unistd.h>

std::atomic<int> Settings::menubarsize{1};
namespace DeveloperLifecycle { bool exitRequested() { return false; } }
namespace {
using Json = nlohmann::json;
const std::string first(32, 'a'), second(32, 'b');
int reads = 0;
bool failRead = false, releaseDuringRead = false;
GLenum error = GL_INVALID_ENUM; // Deliberately left by the application.
std::map<GLenum, GLint> state{{GL_READ_FRAMEBUFFER_BINDING, 7}, {GL_PIXEL_PACK_BUFFER_BINDING, 9},
    {GL_PACK_ALIGNMENT, 8}, {GL_PACK_ROW_LENGTH, 17}, {GL_PACK_SKIP_ROWS, 2}, {GL_PACK_SKIP_PIXELS, 3}};
void require(bool condition) { if(!condition) throw std::runtime_error("screenshot contract failed"); }
Json request(const char* op, const std::string& id = first) {
    return DeveloperScreenshot::request({{"op", op}, {"request_id", id}});
}
struct Window : GameWindow {
    int width = 3, height = 4;
    Window() : GameWindow("test", 3, 4, GraphicsApi::OPENGL_ES2) {}
    void getWindowSize(int& w, int& h) const override { w=width; h=height; }
    void makeCurrent(bool) override {}
    void setIcon(const std::string&) override {}
    void show() override {}
    void close() override {}
    void pollEvents() override {}
    void setCursorDisabled(bool) override {}
    bool getCursorDisabled() override { return false; }
    bool getFullscreen() override { return false; }
    void setFullscreen(bool) override {}
    void setClipboardText(const std::string&) override {}
    void swapBuffers() override {}
    void setSwapInterval(int) override {}
};
}

int main() {
    char path[] = "/tmp/mcpy-screenshot-test-XXXXXX";
    require(mkdtemp(path));
    const auto file = std::filesystem::path(path)/("screenshot-"+first+".rgba");
    DeveloperScreenshot::initialize(path);
    glad_glGetError = +[]() -> GLenum { auto value=error; error=GL_NO_ERROR; return value; };
    glad_glGetIntegerv = +[](GLenum key, GLint* value) { *value=state.at(key); };
    glad_glBindFramebuffer = +[](GLenum, GLuint value) { state[GL_READ_FRAMEBUFFER_BINDING]=value; };
    glad_glBindBuffer = +[](GLenum, GLuint value) { state[GL_PIXEL_PACK_BUFFER_BINDING]=value; };
    glad_glPixelStorei = +[](GLenum key, GLint value) { state[key]=value; };
    glad_glReadPixels = +[](GLint x, GLint y, GLsizei w, GLsizei h, GLenum format, GLenum type, void* pixels) {
        ++reads;
        require(x==0 && y==0 && w==3 && h==3 && format==GL_RGBA && type==GL_UNSIGNED_BYTE);
        require(state[GL_READ_FRAMEBUFFER_BINDING]==0 && state[GL_PIXEL_PACK_BUFFER_BINDING]==0 &&
                state[GL_PACK_ALIGNMENT]==1 && state[GL_PACK_ROW_LENGTH]==0 &&
                state[GL_PACK_SKIP_ROWS]==0 && state[GL_PACK_SKIP_PIXELS]==0);
        std::fill_n(static_cast<unsigned char*>(pixels), w*h*4, 123);
        if(failRead) error=GL_INVALID_OPERATION;
        if(releaseDuringRead) {
            require(request("release")["state"]=="released");
            require(request("capture",second)["code"]=="busy");
        }
    };
    Window window;
    const auto original = state;
    DeveloperScreenshot::capture(window);
    require(reads==0);
    require(request("capture", "../bad")["code"]=="invalid_request");
    require(DeveloperScreenshot::request({{"op", 3}, {"request_id", first}})["code"]=="invalid_request");
    require(DeveloperScreenshot::request({{"op", "capture"}, {"request_id", first}, {"path", "/tmp/bad"}})["code"]=="invalid_request");
    require(request("capture")["state"]=="queued");
    require(request("capture")["state"]=="queued");
    require(request("capture",second)["code"]=="busy");
    require(request("release",second)["state"]=="released");
    DeveloperScreenshot::capture(window);
    auto result=request("poll");
    require(result["state"]=="completed" && result["width"]==3 && result["height"]==3);
    require(state==original && reads==1 && std::filesystem::file_size(file)==36);
    struct stat info{}; require(stat(file.c_str(), &info)==0 && (info.st_mode & 0777)==0600);
    std::ifstream bytes(file, std::ios::binary);
    require(std::string(std::istreambuf_iterator<char>(bytes), {})==std::string(36,123));
    DeveloperScreenshot::capture(window); require(reads==1);
    request("release"); require(!std::filesystem::exists(file));

    request("capture"); request("release");
    DeveloperScreenshot::capture(window); require(reads==1);
    failRead=true;
    request("capture"); DeveloperScreenshot::capture(window);
    require(request("poll")["code"]=="capture_graphics_error" && state==original);
    request("release"); failRead=false;

    // A bounded file write failure must leave the renderer alive and releasable.
    request("capture"); DeveloperScreenshot::capture(window);
    struct rlimit previous{}; require(getrlimit(RLIMIT_FSIZE, &previous)==0);
    auto small = previous; small.rlim_cur = 8;
    auto handler = std::signal(SIGXFSZ, SIG_IGN);
    require(setrlimit(RLIMIT_FSIZE, &small)==0);
    auto failedWrite = request("poll");
    require(setrlimit(RLIMIT_FSIZE, &previous)==0); std::signal(SIGXFSZ, handler);
    require(failedWrite["code"]=="capture_io_error");
    request("release"); require(!std::filesystem::exists(file));

    releaseDuringRead=true;
    request("capture"); DeveloperScreenshot::capture(window);
    require(!std::filesystem::exists(file)); releaseDuringRead=false;
    window.width=0;
    request("capture"); DeveloperScreenshot::capture(window);
    require(request("poll")["code"]=="capture_size_limit"); request("release"); window.width=3;

    int before=reads;
    request("capture"); std::this_thread::sleep_for(std::chrono::milliseconds(5100));
    DeveloperScreenshot::capture(window);
    require(request("poll")["code"]=="capture_timeout" && reads==before);
    request("release");
    DeveloperScreenshot::cleanup();
    require(std::filesystem::is_empty(path));
    std::filesystem::remove(path);
}
