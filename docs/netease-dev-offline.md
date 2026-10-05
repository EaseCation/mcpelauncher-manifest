# macOS arm64 离线开发者版实验

运行时 Python、日志及 UI/玩家调试现已通过 Safaia 接入 mcpywrap，见 [调试操作说明](netease-dev-debug.md)。调试模式只开放回环网络。

2026-10-04：已用 `dev_launcher_3.9.100.297020.apk`（com.netease.mctest）在 macOS arm64 原生进程中创建、进入、保存并重新打开本地单人世界。已看到平坦世界、玩家与 HUD；键盘 E 打开物品栏、Esc 打开暂停菜单、鼠标点击保存退出均实测。当前属于开发验证环境，不是完整中国版启动器移植。

## 运行

从本仓库根目录：

```sh
python3 tools/run_netease_dev.py
```

本机会复用已准备好的 `build-macos-arm64/netease-dev/game` 与 `data`，进入 `codex-arm64-smoke`。首次不存在的世界才会创建为固定种子的平坦创造模式世界；再次启动保留并重开已有存档。

可以直接打开本地测试应用：

```text
build-macos-arm64/NetEase Developer Test.app
```

重新生成这个应用（不会安装到 /Applications）：

```sh
python3 tools/run_netease_dev.py --make-app --prepare-only
```

在另一份干净工作目录第一次准备时：

```sh
python3 tools/run_netease_dev.py \
  --apk /absolute/path/dev_launcher_3.9.100.297020.apk \
  --make-app --prepare-only
```

`--apk` 要求目标 game 目录为空，避免覆盖已有资源。也可以通过 `--game-dir` 使用已解包的 APK 根目录。需要源代码编译出的 arm64 client 和包含 arm64 的 ANGLE；默认复用本机已安装 Minecraft Bedrock Launcher.app 的 Frameworks，使用 `--angle-dir` 可更换。

默认文件位置：

- 游戏资源：`build-macos-arm64/netease-dev/game`
- 用户数据：`build-macos-arm64/netease-dev/data`
- 存档：`data/minecraftWorlds/codex-arm64-smoke`
- 日志：`build-macos-arm64/netease-dev/run.log`
- 实际命令序列：同目录 `commands.json`
- APK 自带脚本日志：`data/mcp.log`，其中大部分行以 base64 编码。

使用游戏内“保存并退出”保存世界。`--run-seconds N` 用于有时限的诊断，超时停止进程**不是**保存测试；不要用于正在编辑的重要存档。测试后已保留当前游戏窗口供用户继续使用。

## 实际复用的启动链

```text
现有 Android ELF linker / libc-shim / FakeJni / FakeEGL / GameActivity
  → 开发者版 JNI_OnLoad / GameActivity_register / initializeNativeCode
  → android_main / MinecraftGame::init
  → 同一 APK 的 vanilla.mcp（Python 2.7 / ModSDK）
  → nativeJsCall(JSON, callback)
  → minecraft/webview.py 的 on_webview_call_rn
  → world.create_world / set_world_info / play_world
  → 本地 LevelDB 世界 / 原有 HUD 与输入
```

没有重写 Minecraft 引擎、Python 解释器、世界格式、窗口后端或 Android 框架；没有把 3.5 脚本部署到 3.9 运行时。用户提供的 `3.5.zip` 只作为接口文档参考；所有调用均通过 3.9 APK 的实际返回值验证。

JSON 协议：

```json
{"module_name":"clientlevel","func_name":"get_level_id","args":[],"use_instance":false}
```

JNI 导出 `Java_com_mojang_minecraftpe_MainActivity_nativeJsCall` 接收消息和回调对象。3.9 实际回调是 `Result(int, String)` / `Reject(int)`，不是 React 的通用 invoke 数组回调。调用在现有 MainActivity.tick 中、收到 engineIsReady 后按序发送；上一调用未返回不会发送下一条，拒绝、无效响应或 ret=false 会停止后续队列。

可用 `--commands-json` 替换命令序列，仅用于本地开发测试。它会经游戏自身的 Python 调度执行，因此这是代码级开发接口。

验证得到的区别：

- `world.create_world` 与 `world.set_world_info` 返回 true，磁盘生成 level.dat 和 LevelDB。
- 3.5 的 `clientlevel.start_local_game` Python 包装仍存在，但此 3.9 Android 二进制的 `_clientlevel` 无该属性，实测 Reject(-4)。它不能作为 Android 启动入口。
- `world.play_world` 返回 true，随后 `clientlevel.get_level_id` 返回真实存档 ID；日志进入 `world_loading_progress_screen`、`in_game_play_screen`、`hud_screen`。
- 通过 `application.InitOfflinePlayer` 与已有 `set_offline_start` 初始化本地开发状态，不调用账号登录流程。
- Cocos 的在线更新界面仍会尝试检查服务器；网络被系统 sandbox 拒绝。通过 Cocos 现有 `Director.getInstance().getRunningScene().setVisible(False)` 隐藏这层界面，让原生世界与 HUD 显示出来。没有把在线验证改为成功。

## 本轮代码清理与兼容修复

- 撤销错误的 MainActivity$6.run 入口猜测，继续复用现有 GameActivity 启动。
- 撤销未生效的 start_screen.json 可见性修改和 client_cfg 实验，解包资源已与 APK 原文件核对一致。
- 删除临时菜单资源路径跟踪；不再使用 cpp.launch_rn_succ 等启动事件试探。
- 探针功能留在 `library_probe.h`；开发者所需的额外绑定集中在 `developer_compat.h`，只在显式开发者/探针模式启用。一般版本使用原有路径。
- `CLOCK_MONOTONIC_RAW`、getentropy、sem_trywait 补入现有 libc-shim；保留 environ 数据符号导出。
- vsprintf 复用已附带的 Android ABI vsnprintf，避免将 Android arm64 va_list 传给 Darwin。
- 开发者模式默认采用 APK FMOD + 已有 SDL3 音频适配。宿主 FMOD 路径在进入世界时触发 SoundSystemFMOD::playMusic 的 bad_function_call，切换后未复现。
- 保留已确认的 linker 16 KB 段末尾向上取整修复；这是可复现的通用页映射错误，不是对正式版初始化代码的绕过。
- 没有新增发布运行所需的第三方依赖。静态分析临时使用的 capstone/pyelftools 不属于启动器依赖。

当前仍保留少数“调用即记录并终止”的未知 ABI 绑定（如 sysinfo、socketpair 等），没有拿假成功值当实现。已验证路径未触及这些缺口。原有启动器的通用 stub 也未全面审计。

## 验证与限制

- 本仓库 client / webview / error 全部 arm64 编译通过；独立 UI 主仓库不在此次构建范围。
- `tests/libc_compat_smoke.cpp` 验证 RAW 时钟递增、getentropy 长度限制/errno/缓冲区边界、信号量空值与 post/trywait 的非阻塞语义。

```sh
cmake -S . -B build-macos-arm64 -DBUILD_COMPAT_TESTS=ON
cmake --build build-macos-arm64 --parallel 6
ctest --test-dir build-macos-arm64 --output-on-failure -R '^libc-compat-smoke$'
```

- 通过 `sandbox-exec` 禁止 IP 网络，只允许本机 UNIX IPC；不是只设置游戏里的联网开关。
- 游戏实际渲染与输入、保存后重开均验证；当前简单平坦场景的 FPS 浮层曾显示约 111 FPS，这不是复杂地图/Addon 的性能基准。
- 仍有中国版 VIP、皮肤、聊天等脚本因大厅管理器未初始化而报错，部分日志出现 `entity type str server entity not exists`。尚未承诺完整 ModSDK/所有原生组件正常；不应把世界能启动等同于功能完全兼容。
- SDK 版本属性、设备信息和部分 Java 类仍沿用现有框架的缺省实现，包版本目前显示 0.0.0.0。没有改写服务器认证或使用真实账号凭据。
- 当前只验证这份 arm64 开发者 APK；升级后需重新检查 JNI/桥接协议和测试返回值。

早期正式版对照与入口定位见 `netease-arm64-investigation.md`。其“未进入世界”描述仅代表第一阶段。
