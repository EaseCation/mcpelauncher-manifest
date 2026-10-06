# macOS 运行包发布与本地组装

mcpy 内置 EaseCation 的固定发行目录，普通用户直接执行 `mcpy run`。
首次运行自动下载原生启动器和网易 pe 当前返回的最新开发者 APK，校验后在本机提取，完成后
继续启动。交互式 `run` 在终端准备资源后显示紧凑调试小窗；完整管理页和创建确认框通过 `mcpy ui` 使用。

默认目录：
`https://github.com/EaseCation/mcpelauncher-manifest/releases/download/mcpy-runtime-v0.4.0/catalog.json`

该发行以开发者 APK 3.10.100.299889 作为构建验证基线；首次安装实际版本由官方 pe 动态发现。运行包包含 ARM64 兼容、ANGLE Metal、
源码 Mod、Python 调试、JSON UI 重载、实例 cppconfig 和键盘输入适配。
不包含 APK、libminecraftpe.so、vanilla.mcp、存档或账号凭据；APK 由 mcpy 直接
从网易 CDN 获取。首次安装查询 pe，版本检查查询 pe/pe_old，不猜测 CDN 文件名；本地已安装的旧版本继续保留。下载后从 APK 读取实际身份、ARM64 核心与摘要，并进行结构兼容检查，通过后才选择。

## 用户入口

```sh
mcpy --local --project /path/to/addon run
# AI / 脚本：自动安装，进度在 stderr，stdout 为单个 JSON
mcpy --local --project /path/to/addon --non-interactive run --no-gui --detach --json
mcpy --local engine doctor --json
# 人工图形界面
mcpy --local --project /path/to/addon ui
```

普通用户无需填写 catalog 或 APK 路径。`engine install --catalog ... --apk ...`
保留为高级覆盖和离线导入入口。来源优先级为显式参数、MCPY_RUNTIME_CATALOG、
保存的安装计划/已选来源、内置默认来源。已有实例固定运行包和 APK；更新资源
不隐式替换已有世界的绑定。运行时会输出实例 cppconfig 路径和自定义说明。

资源保存在 `~/Library/Application Support/mcpy`，MCPY_ENGINE_HOME 可隔离安装。
下载支持断点续传，APK 整体摘要、关键文件、运行包签名和文件清单均须通过验证。
二进制[结构兼容检查](automatic-binary-compatibility.md)失败时保留原选择并输出诊断。

## 构建和发布

构建端需要 Apple Silicon、Xcode 命令行工具、CMake、Ninja、Python；运行端不需要
Homebrew、Wine 或另一个 Launcher。构建依赖固定来源和摘要。

```sh
python3 tools/build_macos_runtime.py \
  --profile tools/macos_runtime_profile_3.10.json \
  --output build-macos-arm64/McpyRuntime-release.app
python3 tools/package_macos_release.py \
  --runtime build-macos-arm64/McpyRuntime-release.app \
  --version 0.4.0 --output build-macos-arm64/release-preview.1
```

产出 runtime tar.gz、递归源码 tar.gz、catalog.json、SHA256SUMS；四项放在同一个
不可变 GitHub Release 中，相对下载地址即可正确解析。每次改变内容都使用新版本号，
不覆盖已有发行资产。发布后从默认 HTTPS 来源验证全新安装，再更新 mcpy 的默认 URL。
仅上传 CI artifact 不构成普通用户可用的分发入口。

`.github/workflows/mcpy-runtime.yml` 支持手动选择版本及 APK profile；默认只上传
artifact，显式启用 publish 才公开发布；prerelease 默认为 true，正式发行设为 false。运行在 Apple Silicon runner。
也可以本机构建审计后使用同样的资产布局发布。运行包和递归源码必须一起分发。
SOURCE_STATE.json 记录所有子模块提交，大小写冲突的 AOSP 头文件从 Git 原样导出。
维护 fork 和子模块的方法见 [fork-layout.md](fork-layout.md)。

运行包采用 ad-hoc 签名，未进行 Developer ID 公证。编译目标为 macOS 13.0，实际
游戏验证环境为 26.6.2；部署目标不等于最低系统已经实测。CLI 下载并运行不依赖
DMG 安装流程，不应建议用户全局关闭 Gatekeeper。发布说明保留这些实际验证边界。
