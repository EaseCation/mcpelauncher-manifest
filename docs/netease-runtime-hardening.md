# macOS 运行包、冷启动与客户端 Python 通道

2026-10-05。本轮实现与实机验证记录；未提交、发布或恢复账号登录实验。

## 可搬运运行包

构建入口：

```sh
python3 tools/build_macos_runtime.py
```

产物为 `build-macos-arm64/McpyRuntime.app`，是供 mcpy 调用的原生运行组件，不包含 APK、`libminecraftpe.so`、`vanilla.mcp`、游戏资源或世界。

- OpenSSL 3.6.3、curl 8.21.0 从固定 SHA-256 的源码构建并静态链接。
- ANGLE 从校验过的上游 v1.8.5 DMG 提取 arm64 slice，附许可与来源记录。构建不读取已安装的 Launcher。
- 只携带明确列出的支持 ELF；不复制原生 FMOD、Qt、WebView 或整个旧 Launcher 应用。
- 关闭 `ENABLE_DEV_PATHS`；支持库使用组件内的相对目录查找。
- `run_netease_dev.py` 和 load probe 改为接受 `--runtime`，默认使用上述运行包；仍可显式覆盖开发用的 client／ANGLE 路径。
- 启动器在实例数据目录运行，不依赖源码仓库作为工作目录。
- 构建脚本校验 Mach-O 架构、最低系统标记和动态依赖，并进行 ad-hoc 签名校验。

已将运行包复制到 `/tmp/mcpy runtime relocation 20261005/McpyRuntime.app`，在精简 PATH 下实际进入新世界、加载两个 Mod、保存重开。`vmmap` 验证游戏进程没有映射 `/opt/homebrew/` 或 `/Applications/Minecraft Bedrock Launcher.app/` 下的库。

**最低构建目标为 macOS 11.0**，包括 launcher、ANGLE、OpenSSL 和 curl；不再错误地以本机 26.6 为部署下限。实机验证环境仍只有 Apple M1 Max／macOS 26.6.2，不能把构建目标当作已经完成 macOS 11 的实机验收。当前签名为 ad-hoc，尚未进行 Developer ID 签名／公证。

## 首次创建世界的 SIGBUS

复现使用完全独立的数据、缓存和世界目录，额外等待 15 秒仍能复现。发现并处理两处独立问题：

1. 开发者 APK 的一个标量分派函数使用了 Apple arm64 ABI 保留的 `x18`。故障时该寄存器为零，缺失跳转偏移 `0x96f80a`，使计算结果成为未对齐地址。兼容代码在内存中将该函数的临时值保存在按 ABI 跨调用保留的 `d15` 中，并保存／恢复调用者的 `d15`；没有跳过函数或伪造返回值。
2. libc-shim 将 Android `MAP_FIXED` 错译成了宿主 `MAP_FILE`。内嵌加载器因此得到错误地址而误认为映射成功。修正为 `MAP_FIXED`，并增加保留区内定址重映射的行为测试。

负向对照：仅修正 `MAP_FIXED` 仍触发原始分派跳转故障；仅处理寄存器后则在错误的映射地址继续出现访问故障。两项都修正后，多组全新目录成功首次创建世界。

寄存器适配集中在 `mcpelauncher-client/src/developer_arm64.h`，目前仅接受 `3.9.100.297020` 及匹配的函数指纹。它是本轮保留的版本相关机器码适配，不能宣称适用于任意 APK。游戏文件在磁盘上保持原样；界面和 Python 请求通道不使用这个机制。

对于 Android 内部加载器提出的 4 KiB 对齐、而宿主不接受的定址请求，现在返回真实失败。没有实现通用 4 KiB 页面仿真；当前测试路径能够处理这种失败。

基线与对照证据保留于 `build-macos-arm64/stability/` 的 `baseline-*`、`map-only`、`x18-*`、`fixedmap-01`。临时信号／mmap 调试插桩已经撤回。

## 保存退出与窗口清理

网易模式的窗口关闭、SIGINT、SIGTERM 统一调用现有 `minecraft.instance.quit_local_game()`，等待当前进程不再持有世界数据库文件后退出。窗口关闭回调不再立即 `_Exit`。启动尚未完成、没有世界数据库时也可取消。数据库已打开但世界仍在加载时，每 250 ms 用 clientlevel 就绪状态检查一次，再调用退出 API，避免先退出、后打开世界的竞态。

`mcpy stop` 继续使用原有进程身份检查和 worker 清理；新 launcher 在收到 terminate 时完成保存。旧版附加进程由 `stop_netease_debug.py` 先通过原 Python 通道保存，再调用同一 mcpy stop。超时保留进程并报错，不强杀尚未保存的世界。

通过 run_netease_dev.py 对同一数据目录的第二次启动／部署因文件锁被拒绝。实测包括 mcpy stop、SIGINT、Cocoa Quit 对应的 GLFW 关闭回调，以及初始化期间取消。世界中的测试金块在保存重开后保留；测试窗口和 worker 均已结束。

GLFW 会先取消 Cocoa 的同步 Quit 请求，再进行异步保存，因此 AppleScript 可返回 `-128`；测试以游戏日志的数据库关闭记录、进程退出码 0 和 worker 结束确认结果，不把 AppleScript 返回值单独当作验收。

## 只隐藏启动页，保留其他 Cocos 页面

窗口依然立即显示，没有新增等待界面，没有延迟 `window.show()`。

3.9 的登录／更新页由 `launcher.launcher.base_scene` 管理，其名字为 `launcher_scene`；实际 `destroy_patch_loading_ui()` 是空函数。启动配方通过正常客户端 Python 请求，在该对象存在后调用 `base_scene.setVisible(False)`。

这里没有修改 Cocos 的 C++ 绑定、vtable 或固定地址，也没有隐藏任意 `Director.getRunningScene()`。专用 `developerEarlyCommand` 已移除：隐藏请求与外部用户代码使用同一客户端请求队列，其等待条件是普通 Python 表达式。

除了检查新建 Cocos 场景仍可见，还实际调用了当前 APK 的 `CocosSceneManager` 导航接口：其 `BaseScene` 可见，同时 `launcher_scene` 仍不可见，随后恢复场景栈。这证明没有全局关闭 Cocos 渲染。处理时机是现有 JNI/Python 桥接可执行后的最早阶段；未做逐帧录制，不声称已证明首帧完全无闪现。

## 通用客户端 Python 能力

新增能力只面向客户端；服务端仍走原 Safaia。启动器复用现有 simple-ipc 和 JNI `nativeJsCall`，mcpy 复用既有 session、RuntimeControlServer、输出捕获与异常序列化。

- 游戏进程开始后建立本地客户端请求入口；Python VM 尚未就绪时请求排队。
- 用无副作用的 `True` 调用确认 Python 已可执行，再调度用户代码。
- 一次执行一个客户端请求；支持表达式、语句、函数定义、import，以及本进程内持久变量。
- 可选择无副作用的等待表达式；等待条件未满足时，其他可执行请求仍能运行。
- 支持 stdout、stderr、返回值、traceback、结果查询、尚未执行请求的取消，以及保留期内同 ID／同内容的幂等提交。
- 运行中的代码不强行中断；同步等待结束仍返回原 request_id 和真实状态，不重发代码。
- Python 源码为 UTF-8；代码上限 32 KiB，结果沿用 mcpy 原有限制。非 JSON 值沿用类型／repr 表示，过大结果返回 `result_too_large`。
- mcpy 保留最近 64 个已查询完成的请求；启动器队列／历史有容量上限，退出后清理入口。变量与请求结果不跨游戏进程持久化。

连接进程后使用原命令：

```sh
mcpy --local --project /path/to/project runtime py --session SESSION \
  --code 'counter = 41' --json
mcpy --local --project /path/to/project runtime py --session SESSION \
  --code 'counter + 1' --json
```

排队与查询：

```sh
mcpy --local --project /path/to/project runtime py --session SESSION \
  --file /path/to/probe.py --no-wait --json
mcpy --local --project /path/to/project runtime py-result REQUEST_ID \
  --session SESSION --json
mcpy --local --project /path/to/project runtime py-result REQUEST_ID \
  --session SESSION --cancel --json
```

`--wait-until '<布尔表达式>'` 可与客户端执行／排队配合，条件使用相同客户端命名空间。它只决定何时执行，不会循环重跑用户代码。

服务端命令不变：`runtime py --side server`，仍需世界和 Safaia 就绪。游戏内注入的 `mcpy.*` 仍只用于调试，不成为业务 Addon 依赖。

当前仍通过 `tools/run_netease_dev.py` 启动及 `tools/attach_netease_debug.py` 附加。完整的 `mcpy run` macOS 后端与首次 APK 下载引导属于后续集成，本文不将其描述为已经实现。

## diff 收敛

- JNI／网易相关实现从上游 `jni_support.cpp` 和 `main_activity.cpp` 移到独立 `netease_bridge.cpp`；后者恢复到上游原文。
- `environ` 绑定移入已有的 DeveloperCompat，`mcpelauncher-core` 的修改归零。
- 通用 libc 修复保留为独立小补丁；`MAP_FIXED` 本轮只有一行功能修改。
- 新的构建、生命周期、客户端队列和版本适配各自集中，不修改 simple-ipc、libjnivm、ANGLE 或 SDL 的源码。
- `mcpelauncher-client` 原有文件的 diff 从本轮开始的约 334 行新增降至约 174 行新增；新增功能及迁出的实现位于独立文件，不能将此数字理解为总体代码量减少。
- Bionic 仍显示 8 个大小写同名头文件的 checkout 差异，是本机大小写不敏感文件系统的既有问题。本轮未修改或隐藏这些文件；真正 linker 功能差异在 `linker/linker_phdr.cpp`，应单独审阅／导出。

## 验证记录

- 原生兼容行为测试、认证桥接测试通过；源码导入器 Python 2 smoke 通过。
- mcpy 原有 runtime_debug 测试及新增客户端通道测试通过。
- 多组全新数据／缓存目录首次建世界成功，包含同时加载最小源码探针、OreDetector、Ration；两个 Mod 服务端模块无需手动 import 即存在。
- 保存重开保留测试金块；退出后无遗留游戏／worker。
- 运行包改名搬到带空格的 `/tmp` 路径后运行正常，映射依赖审计通过。
- 客户端 Python 在进世界前执行、跨进世界保持变量、异常／中文／False 值返回、取消队列、超大结果限制和同 ID 不重复执行均实测通过；执行期间显式抛出 SyntaxError 不再导致代码被再次执行。
- 通过任意客户端 Python 调用现有 world API 进入世界，随后原 Safaia 服务端执行、runtime install、UI／玩家能力安装通过。

关键结果：`stability/validation-3/`、`relocated-validation/`、`final-native-validation/`、`client-python-test-4/result.json`、`startup-cancel/result.json`。早期失败实验保留为对照，不计入成功验收。

## 中国版 F11 输入模式（2026-10-05 验收修正）

中国版的 F11 不再走启动器全屏快捷键。Android 开发包没有桌面版的这项按键绑定，仅透传按键不能切换；适配层复用现有 emulateTouch 鼠标转触屏路径，在切换时释放/恢复光标约束，并在触屏模式忽略相对鼠标转向。游戏侧通过现有 JNI/Python 调度串行调用 gui.simulate_touch_with_mouse（ModSDK 的 SimulateTouchWithMouse，官方说明明确对应 PC F11）。不添加游戏机器码补丁、不增加服务端协议。按键重复和抬起不重复切换。

运行包 macos-arm64-0.1.0-preview.local5 位于 build-macos-arm64/release-f11-mode-test。实测原生窗口 F11 连续两次，IsTouchWithMouse 返回 false → true → false，窗口保持 1440×1024，未切换全屏。两个 CTest 通过，测试游戏保存退出且无进程残留。证据：stability/f11-validation.json 及 f11-mode-*.json。旧实例仍固定其原运行包，新修复需要新版运行组件；未自动覆盖旧包或迁移用户世界。
