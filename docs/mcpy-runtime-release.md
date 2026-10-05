# macOS 运行包发布与本地组装

`tools/build_macos_runtime.py` 构建原生 arm64 启动器、ANGLE Metal 和所需兼容库；运行端无需 Homebrew 或已安装的 Launcher。构建端需要 Xcode 命令行工具、CMake、Ninja、Python 3.12。构建目标 macOS 11.0，目前实际游戏验证仅在 26.6.2，尚不能把部署目标当作已验证的最低系统。

```sh
python3 tools/build_macos_runtime.py --output build-macos-arm64/McpyRuntime-release.app
python3 tools/package_macos_release.py --runtime build-macos-arm64/McpyRuntime-release.app --version 0.1.0-preview.1 --output build-macos-arm64/release-preview.1
```

产出同目录的 runtime tar.gz、递归源码 tar.gz、catalog.json、SHA256SUMS。catalog 使用相对地址，可以本地安装，也可将全部文件放到同一个不可变 HTTPS 发布目录。尚未配置默认公开发行源；不要把未经网易适配的上游包当作替代。每次改变构建内容必须用新版本号。摘要保证取得的内容匹配目录，目录来源本身必须可信。

源码包含根仓库和全部子模块的提交内容，以及打包时的本地修改；SOURCE_STATE.json 记录各提交和覆盖文件。适配子模块位于 EaseCation 的公开 fork，根仓库固定其提交；维护关系见 `fork-layout.md`。后续发布仍需先推送子模块再更新主仓库引用。macOS 大小写冲突的 AOSP 头文件按 Git 原始内容导出。源码归档解压后可直接运行构建工具；无需 .git，但外部固定依赖仍需联网取得。包中不包含 APK、libminecraftpe.so、vanilla.mcp、用户存档或凭据。许可证随运行包提供，源码归档应随每次二进制一起分发。

`.github/workflows/mcpy-runtime.yml` 提供手动构建和上传 CI artifact，不自动发布 Release。构建机的 brew 只用于构建工具，不会成为运行包依赖。GitHub CI 构建仍需单独触发并验证。

当前为 ad-hoc 签名，无 Developer ID 公证；不能宣称已经完成公开下载后的 Gatekeeper 体验验证。正式发布需配置 Developer ID、公证和真实最低 macOS 的测试矩阵，并验证最终重签名后生成的摘要。不要指导用户全局关闭 Gatekeeper。

在 mcpy 安装：

```sh
mcpy --local engine install --catalog /path/to/release/catalog.json --apk /path/to/dev_launcher_3.9.100.297020.apk --json
mcpy --local engine doctor --json
mcpy --local --project /path/to/addon run --detach --json
```

省略 `--apk` 会从网易官方接口解析匹配版本并下载；暂只接受配置锁定的 3.9.100.297020。最新版 3.10 不会被静默替换。官方旧版下架时提示用户提供匹配 APK。自动下载使用官网公开的 CDN 签名规则，无需 MPay 登录。

默认资源根目录 `~/Library/Application Support/mcpy`；可用 `MCPY_ENGINE_HOME` 隔离测试。`MCPY_RUNTIME_CATALOG` 设置发行目录。下载支持断点续传，完整 SHA-256 验证后才提取；运行包做签名、架构及逐文件校验，APK 做整体摘要、资源数量/大小和关键文件校验。中断可以重试；损坏资源在确认无使用进程后重新组装，世界位于项目 `.runtime/macos/instances` 中。现有实例固定运行包和 APK，默认重开原世界；升级需选择新目录并显式 `run --new`。

## 本轮本机验收（2026-10-05）

本地发行目录：`build-macos-arm64/release-product-test2`，runtime ID `macos-arm64-0.1.0-preview.local2`。APK 从用户本地文件导入，避免重复下载；官方 CDN 签名下载已在前期单独验证。本轮完成实际 tar 提取、摘要/签名校验和 mcpy 资源选择。运行包约 12 MiB、递归源码包约 75 MiB；mcpy wheel 单独构建到 `build-macos-arm64/stability/mcpy-wheel`。这些为开发预览产物，未公开发布。

公开 `mcpy run` 组装最小源码探针和两个本地依赖 OreDetector/Ration，直接进入原生 Metal 单人世界；world_ready、客户端 Python、原 Safaia 服务端 Python、runtime install、UI 快照均通过。没有手动 import 两个 Mod 的服务端入口，已从 sys.modules 和 OreDetector tick 确认自动运行。启动阶段仍会出现网易离线账号/商城模块的脚本告警，不以这些日志假称在线功能可用。

`product-reopen-check.json` 验证重复 run 复用会话、客户端请求在启动期排队并保留命名空间、服务端 ExtraData 保存重开和退出。`product-cancel-loading.json` 在数据库已打开、尚未出现 HUD 时取消，最终正常保存且 exit_code=0。此前诊断用 get_level_id 在加载中返回 -1 的失败实验已保留，新版加入就绪条件；同时修复在加载途中过早 quit 的竞态。最终无游戏/worker 残留。

测试：两个原生 CTest 通过；mcpy 针对性 120 个用例运行成功（其中 4 个跳过），覆盖后端路由、安装/修复、断点续传、TUI、会话、远程和 Python 通道。扩展全量 430 个用例在此 Mac 上仍有 Windows/PyQt/MCS 专用测试不通过（9 error、1 failure、23 skip），不能声称全平台全量测试通过。Windows 实机、最低 macOS、公开下载后的签名体验和 GitHub CI 尚待对应环境验证。已构建 wheel，并从仓库外加载它运行 engine doctor 成功；仓库与安装目录中的 Skill 验证通过。
