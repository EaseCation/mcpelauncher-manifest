# AArch64 Linux 运行包

与 macOS 运行包使用同一套源码、开发者 APK 适配与 mcpy 启动协议，在 AArch64 Linux 上直接运行
Android arm64 游戏库。Linux 与 Android 的 AArch64 调用约定一致，macOS 才需要的 x18 指令改写、
可变参数兼容 libc、V8 jitless 与 ANGLE/Metal 都不使用；图形直接走宿主 EGL/GLES。

## 运行要求

| 项目 | 要求 |
|---|---|
| 架构 / C 库 | AArch64，glibc ≥ 运行包声明的 `minimum_glibc`（发行构建为 2.35，即 Ubuntu 22.04 / Debian 12 起） |
| 内核页大小 | 4 KiB 或 16 KiB（树莓派 5 默认 16 KiB 内核依赖 bionic 的 16 KiB 段对齐修复）；64 KiB 页内核无法加载 16 KiB 对齐的 Android ELF，不支持 |
| 图形 | Wayland 或 X11 会话，GLES 3.0+ 驱动（Mesa V3D/Panfrost/Freedreno 等）；GLFW 运行时 dlopen libwayland/libX11/libEGL |
| 音频 | 可选；没有可用设备时 SDL3 记录失败并以无声继续 |

运行包静态链接 OpenSSL、curl、libstdc++、libgcc。构建审计只允许依赖 glibc 自身、libz 与
libatomic，并拒绝 RPATH 及高于基线的 GLIBC 符号版本。运行包不签名，完整性由
`McpyRuntime.integrity.json` 的 SHA-256 清单校验。

## 布局

```text
McpyRuntime/
  bin/mcpelauncher-client
  share/mcpelauncher/lib/arm64-v8a/libsqliteX.so   # 仅 pairipcore 路径使用
  share/mcpelauncher/gamecontrollerdb.txt
  resources/runtime.json
  resources/launcher/run_netease_dev.py …          # mcpy 启动适配器，与 macOS 相同
  resources/licenses/
McpyRuntime.integrity.json
```

`runtime.json` 的 `platform` 为 `linux-arm64`，协议字段与 macOS 0.4.8 相同，另声明
`network_guard_protocol=1`。

## 与 macOS 的行为差异

**网络隔离。** macOS 由 `sandbox-exec` 在内核层禁止外部网络。Linux 不使用网络命名空间：mcpy 依靠
`/proc` 核对游戏进程拥有的回环端口（Safaia 握手），独立 netns 会破坏这项校验。启动适配器改为传入
`--netease-network-guard`，由客户端在 libc-shim 层包装游戏代码导入的 `connect`、`sendto`、
`sendmsg`：

- 放行回环地址（含 IPv4 映射）、Unix 与 netlink 套接字；
- 无认证联机时额外放行 `--netease-network-allow udp:<数字地址>:<端口>` 声明的服务器端点（地址由适配器解析）；
- 其他目标（包括局域网广播与 DNS）返回 `ENETUNREACH`，前 8 次写入引擎日志 `[NetworkGuard]`。

这是进程内策略，只约束经导入表调用的 Android 代码；宿主侧（GLFW、日志、IPC）不受影响，也不能阻止
直接系统调用。未连接的 UDP 套接字仍可能接收入站数据，但无法向外部回复。

**Tracy。** 宿主允许 perf 事件时，引擎内置 Tracy 会启动系统采样线程。客户端默认设置
`TRACY_NO_SYS_TRACE=1`，与 macOS 行为一致并避免采样开销；显式环境变量优先。仍默认仅监听
`127.0.0.1:8086`。

**截图与保存退出。** 截图协议与 macOS 共用 `glReadPixels` 实现。SIGTERM 时通过 `/proc/self/fd`
判断世界数据库是否已打开：未打开立即退出，已打开则请求保存并在数据库关闭后退出。

## Linux 移植中修复的问题

- `vsprintf` 兼容改写：macOS 需要把 Android 的 `vsprintf` 转到 Bionic `vsnprintf(buf, SIZE_MAX, …)`。
  Linux 上 libc.so 的 `vsnprintf` 即 glibc，计算 `buf + SIZE_MAX` 时指针回绕而不写任何字节，导致
  CPython 2.7 整数格式化读到栈残留，所有日志调用抛出 `UnicodeDecodeError`、Python 桥全部失败。
  该改写现仅在 `__APPLE__` 下启用。
- libc-shim 原先只转换 `SCHED_OTHER`，Tracy 采样线程请求 `SCHED_FIFO` 时进程中止。现在转换
  FIFO/RR/BATCH/IDLE，未知策略返回 `EINVAL`。
- `glfwInit` 失败时异常信息带上 GLFW 的平台原因（例如未检测到可用显示）。

## 构建

```sh
# AArch64 Linux 主机；需要 clang、cmake、ninja、perl、make 以及 X11/Wayland/EGL/GLES、ALSA/PulseAudio 开发头文件
python3 tools/build_linux_runtime.py --output build-linux-arm64/McpyRuntime
python3 tools/package_macos_release.py --runtime build-linux-arm64/McpyRuntime \
  --version 0.5.0 --output build-linux-arm64/release
```

打包输出 `mcpy-runtime-<版本>-linux-arm64.tar.gz`、`mcpy-runtime-<版本>-linux-arm64-sources.tar.gz`、
`catalog-linux-arm64.json` 与 `SHA256SUMS-linux-arm64`，可与 macOS 资产放在同一个 Release。
发行构建由 `.github/workflows/mcpy-runtime.yml` 在 `ubuntu-22.04-arm` 上完成；在更新的系统上本地
构建时需以本机 glibc 作为 `--minimum-glibc`，产物只适合该系统及更新版本。

## 无头实机测试

没有显示器的开发机可以使用 wlroots 无头后端，仍由 GPU 渲染：

```sh
sudo loginctl enable-linger "$USER"     # SSH 断开后保留 /run/user/<uid> 与用户服务
systemd-run --user --unit=mcpy-wayland \
  --setenv=WLR_BACKENDS=headless --setenv=WLR_RENDERER=gles2 \
  --setenv=WLR_RENDER_DRM_DEVICE=/dev/dri/renderD128 labwc
export XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0
wlr-randr --output HEADLESS-1 --custom-mode 1280x720
```

未开启 linger 时，最后一个 SSH 会话结束会回收运行目录，合成器随之退出，之后的启动表现为
`glfwInit error: Failed to detect any supported platform`。需要查看画面时可再运行 `wayvnc`。
