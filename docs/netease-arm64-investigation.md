# 中国版 Android → macOS arm64：第一阶段实验记录

后续已完成开发者版单人世界创建、进入、保存及重开，见 [当前运行说明](netease-dev-offline.md)。以下保留第一阶段历史证据。

2026-10-04。当前接入目标：开发者版的离线单人开发测试环境。

**结论：开发者版已通过 ELF 装载、构造函数、JNI_OnLoad 和 GameActivity 注册；尚未启动 Activity、渲染游戏帧或进入世界。** 正式版在 ELF 初始化阶段包含直接 Linux 系统调用，先保留为对照样本。

## 样本与可重复性

| | 正式版 | 开发者版 |
|---|---|---|
| APK 包名 | com.netease.x19 | com.netease.mctest |
| 版本 | 3.9.15.297907 | 3.9.100.297020 |
| versionCode | 840297907 | 840297020 |
| libminecraftpe.so 字节数 | 334055168 | 321592968 |
| 动态符号条目数 | 143669 | 77367 |
| ELF entry VA | 0x13530000 | 0 |
| 标准 JNI/GameActivity 导出 | 磁盘动态符号表无对应明文导出 | 存在 |
| 实测状态 | 构造函数中的 Linux syscall 不兼容 | 装载与 JNI 注册成功 |

库文件 SHA-256（不是整个 APK 的哈希）：

- 正式版：`953d4ebd1caf4d806597e20d4319538a265282a6e7b336ddfea14ff288c0c73d`
- 开发者版：`a0f5332d443f20063cc0adce5cf935597cccf6c790ea6a9a7e79ec8a067b72f3`

原始 APK 均未修改。测试数据/cache 为独立目录；最终探针用 macOS `sandbox-exec` 禁止网络。库和脚本资源不能上传到源码仓库。

## 环境与构建

子代理完成本仓库全部启用目标的原生构建：client、webview、error 和 axml_parser_demo 均为 Mach-O arm64。它没有构建独立仓库里的 mcpelauncher-ui-qt 主界面。

- AppleClang 21 / Xcode、CMake 3.25.2、Ninja 1.12.1。
- 本机已有 Homebrew Qt5 5.15.16_2；QtCore 和 QtWebEngineCore 都是 arm64，WebEngine helper 编译成功。这不等于 Qt 官方提供了当前应用所带 Qt5.15.0 的 arm64 预构建包，也说明现阶段无需先迁移 Qt6。
- curl 8.0.1 由 ExternalProject 编译。
- 使用现有 `/Applications/Minecraft Bedrock Launcher.app/Contents/Frameworks` 中的 arm64 ANGLE。

从仓库根运行：

```sh
cmake -S . -B build-macos-arm64 -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_PREFIX_PATH=/opt/homebrew/opt/qt@5 \
  -DQt5_DIR=/opt/homebrew/opt/qt@5/lib/cmake/Qt5 \
  -DBUILD_UI=ON -DBUILD_CLIENT=ON -DBUILD_WEBVIEW=ON \
  -DBUILD_TESTING=OFF -DENABLE_DEV_PATHS=ON \
  -DUSE_OWN_CURL=ON -DUSE_GAMECONTROLLERDB=OFF
cmake --build build-macos-arm64 --parallel 4
```

## 已实现的诊断工具

- `tools/inspect_android_elf.py`：只读取 ELF64 AArch64，不执行输入文件。不依赖 section 名称，通过 PT_DYNAMIC、GNU/SysV hash、RELA 解析导入/导出和 JNI 方法表候选。仅用 Python 标准库。
- client `--probe-library`：配置现有 libc/EGL/Android 兼容层，装载 libminecraftpe.so 并执行其 ELF 构造函数，打印入口，随后直接退出；不加载 mod、不启动 Activity。
- client `--probe-jni`：在上一阶段之后运行 FakeJni、JNI_OnLoad、GameActivity_register，检查返回值及待处理 JNI 异常，再退出。
- `tools/run_android_library_probe.py`：用绝对路径运行上述探针，隔离数据和缓存，禁用网络、限定运行时长，保存 log/result.json，并传播失败退出码。

**诊断绑定不等于完整兼容实现。** `library_probe.h` 中传感器报告不可用；若构造函数实际调用尚未实现的 socketpair、pthread_sigmask、sysinfo、vsprintf、eglQueryContext 等接口，立即记录并退出 53，而非返回伪造成功。已有上游兼容层的 stub 行为未作全面审计。因此一次装载成功只能证明当前初始化路径通过，不能证明这些接口在游戏运行阶段可用。

开发者 APK 仅抽取了 arm64 库和 Manifest 到 `/tmp/apkinspect/developer`，本次 probe 不需要完整游戏 assets。后续启动世界必须从**同一开发者 APK**提取资源，不能混用正式版资源。

```sh
python3 tools/inspect_android_elf.py \
  /tmp/apkinspect/developer/lib/arm64-v8a/libminecraftpe.so \
  --output build-macos-arm64/netease-probe/developer-elf-report.json

python3 tools/run_android_library_probe.py \
  --game-dir /tmp/apkinspect/developer \
  --stage jni \
  --output build-macos-arm64/netease-probe/developer-jni-final
```

如临时解包目录消失，可用 Python zipfile 从用户提供的 APK 重新抽取 `AndroidManifest.xml` 和 `lib/arm64-v8a/`；不要把 APK/JAR 当成文本读取。脚本的 `--game-dir` 指向包含 `lib` 的目录。

## 入口定位（地址均为对应库的 ELF 相对 VA）

| 意义 | 开发者版 | 正式版候选 |
|---|---|---|
| JNI_OnLoad | 0x5eee1f0 | 明文动态导出不存在，尚未定位 |
| GameActivity_register | 0x10e22f0c | 0x10eedc2c |
| Java_com_google_androidgamesdk_GameActivity_initializeNativeCode | 0x10e23ce4 | 包装函数 0x10eeea04 |
| initializeNativeCode JNI 方法表目标 | 0x10e23d58 | 0x10eeea78 |
| GameActivity_onCreate | 0x10e26478 | 0x10ef1198 |
| GameActivity JNI 方法表起始 | 0x12c47a68 | 0x12cd1a70 |

开发者版名称与地址来自真实 ELF 导出。正式版候选来自 JNI 三元组 `{name, signature, function}`、RELA、反汇编和 PLT/GOT 引用，尚未实际调用。

正式版注册函数在 `0x10eee480` 附近引用 `com/google/androidgamesdk/GameActivity`；在 `0x10eee4a0` 附近传入方法表，在 `0x10eee4ac` 设置数量 24，然后通过 JNI `RegisterNatives` 调用。扫描器筛出其中 23 个带 init/native 等关键词的条目，24 为反汇编得到的完整注册数量。

两版 initializeNativeCode 的准确方法表签名：

```text
(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Landroid/content/res/AssetManager;[BLandroid/content/res/Configuration;)J
```

当前启动器的 GameActivity 路径使用 `com/google/androidgamesdk/Config`。后续需要适配这份 Android Configuration 参数及结构版本，不能按当前上游 ABI 直接硬调用。

开发者版 MainActivity 的 smali 明确继承 `com/google/androidgamesdk/GameActivity`，静态加载顺序包括 c++_shared、fmod、minecraftpe；`maesdk` 加载失败允许继续。这证实游戏入口是 GameActivity 路径。

之前对 `Java_com_mojang_minecraftpe_MainActivity_000246_run__` 的判断已纠正：它在正式版 `libandroidmainruns.so` 中，是 **MainActivity$6.run()**，不是游戏库导出的 MainActivity.run()。错误实验分支已撤销，不再调用该函数。

## 运行证据

开发者版 `developer-jni-01/probe.log`（输出目录位于 build-macos-arm64/netease-probe）：

```text
[LibraryProbe] Load completed; base=...
[LibraryProbe] Invoking JNI_OnLoad
[Minecraft] JNI_OnLoad completed
[LibraryProbe] JNI_OnLoad returned 0x10004
[LibraryProbe] Invoking GameActivity_register
[LibraryProbe] GameActivity_register returned 0
[LibraryProbe] JNI probe completed; no activity or world was started
```

退出码 0。0x10004 是 JNI_VERSION_1_4。

正式版依次遇到缺失符号、不可执行页以及直接系统调用：

1. environ 缺失：向 embedded linker 导出环境变量**指针变量的地址**，macOS 用 `_NSGetEnviron()`。
2. 补充 probe-only 导入绑定后，游戏库和四个 PhysX 库完成重定位；PhysX 构造函数通过。
3. 游戏第一个构造函数在 `0x13530000` 第一条指令触发 EXC_BAD_ACCESS(code=2)。发现 macOS linker 把已对齐的 RW 段末尾又扩展一页，覆盖后继 RX 段首页；已改为正确的 exclusive-end 向上取整。
4. 修复后执行进入该构造函数，LLDB 在 `0x13530528` 的 `svc #0` 后停止，PC 为 `base+0x1353052c`，stop reason 为 EXC_SYSCALL。寄存器 x8=0xe2（Linux AArch64 mprotect），x2=7（RWX），x1=0x659000。调用直接进入内核，不经过 libc 符号 shim。
5. 此代码按 4 KB 页处理内存，且修改含动态字符串的映射；macOS Apple Silicon 的 16 KB 页和 MAP_JIT 写/执行切换也是后续兼容问题。没有通过删除构造函数或绕过此初始化来伪造成功。

复现与证据日志：`load-probe-09.log`（修复前）、`lldb-crash.log`（修复前）、`load-probe-10.log` 和 `lldb-after-page-fix.log`（修复后）。LLDB 自己退出 0 不表示被调试游戏成功。

## 离线单人目标仍需验证

- 开发者库有 `nativeGetOfflineStartState()`（0x5ef3e6c），可用来追踪真实离线状态；这是 getter，不是已确认的离线启动开关。
- `nativeLaunchCommand()`（0x5ef970c）与 `nativeCustomCommand()`（0x5ef9708）大小均为 4 字节，当前为返回指令，不能据名称推断能启动世界。
- SDK、通知代码里的 offlineGameFlag/FLAG_AVAILABLE_OFFLINE 不能证明游戏允许无账号启动。
- 未直接 DT_NEEDED 网易登录库，不代表运行时不会经 dlopen/JNI 调用 SDK。
- Cocos、Python/ModSDK、资源目录 `assets/assets`、本地世界创建/加载和 Android Configuration 尚需适配。现有版本检测把 com.netease.* 显示为 0.0.0.0，需要单独的引擎版本识别。
- 本阶段未测试游戏帧率、Python Addon、存档读写或登录；成功装载不能推出可以流畅进入单人世界。

下一阶段优先使用开发者版，从 GameActivity 实例初始化与资源路径开始，逐步实现真实调用到的 shim；正式版壳兼容不再作为前置条件。
