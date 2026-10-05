# mcpy macOS 本地开发运行时：产品化设计

调查日期：2026-10-05。状态：设计与下载链路验证；尚未实现 mcpy 的 macOS 启动后端或发布预构建包。本文中的新增 CLI／配置均为提案。

后续已完成本地独立运行包、冷启动兼容修复、保存退出及通用客户端 Python 通道，见 [实现与验证记录](netease-runtime-hardening.md)。自动 APK 安装与完整 `mcpy run` 后端仍属于后续集成。

## 结论

技术上可以将现有成果封装为 `mcpy run` 的 macOS arm64 本地后端：mcpy 负责项目组装、资源安装、实例与调试会话；独立的原生启动器负责运行 Android 开发者 APK；ANGLE 使用 Metal 后端。用户不需要安装 Android、Wine、Homebrew、Xcode 或原来的 Qt 启动器。

发行物只包含我们有权分发的启动器、兼容层和开源依赖。Minecraft／网易的 APK、ELF、Python 运行时、`vanilla.mcp`、原版资源在用户本机从官方取得、校验并组装，不经过我们的镜像，也不进入 wheel、Release、容器或公共 CI 缓存。

用户已明确确认网易方面允许本方案；后续以此作为授权前提，不再将网易授权核查列为待办或发布阻碍。仍按照约定采用官方下载、本地组装，不随产品附带游戏内容；开源组件按各自许可提供源码和通知。

## 1. 已验证的官方资源获取流程

未携带 Cookie／账号凭据访问以下官方接口，均返回 HTTP 200：

| 接口 | 本次返回 | 验证状态 |
| --- | --- | --- |
| [`download/pe`](https://mc-launcher.webapp.163.com/users/get/download/pe) | `dev_launcher_3.10.100.299889.apk` | 下载签名与 Range 请求通过；引擎运行未验证 |
| [`download/pe_old`](https://mc-launcher.webapp.163.com/users/get/download/pe_old) | `dev_launcher_3.9.100.297020.apk` | 下载签名与 Range 请求通过；同名本地 APK 已完成前序运行测试 |
| [`download-version`](https://mc-launcher.webapp.163.com/users/get/download-version) | `pe=3.10beta`，`pe_old=3.9stable` | 仅作为展示标签，不能替代二进制兼容性检查 |

### CDN 签名

直接访问接口返回的 APK URL，HEAD、普通 GET、Range GET 均返回 403，响应头包含 `denied by req auth: no <encoded> or <plain>`。原因已通过官方页面代码查明。

页面：<https://mcdev.webapp.163.com/#/square?channel=cnt>。

跟踪页面 HTML → app 路由 → webpack manifest → square 的 chunk 4，下载组件 `ApkDownload` 实现了以下步骤；布局 chunk 1 中也有相同实现：

1. `downloadUrlGet()` 调用 `getDownload(appVersion)`，获取官方 APK 地址。
2. `generateKey1(url)` 使用页面内置的公开常量和当前时间生成参数。
3. 下载按钮 `toAdr()` 打开带参数的 `downloadUrl`；二维码也使用同一 URL。

算法为：

```text
expires = floor(Date.now() / 1000) + 43200
key2 = lowercase_hex(expires)
key1 = MD5(frontend_constant + apk_path + key2).hexdigest()
download_url = official_url + "?key1=" + key1 + "&key2=" + key2
```

官方当前实现通过删除固定的 `https://g79.gdl.netease.com` 前缀得到路径。`frontend_constant` 来自下载组件的 `privateKey` 字段；虽然字段名如此，它是公开下发的前端常量，不是用户账号、MPay token 或需要登录接口签发的个人凭据。实现应限制到已核验的官方主机／路径；不能把这一算法当作任意域名的通用签名器。

本次源文件：<https://mcdev.webapp.163.com/static/js/4.05713153ba17aea6db53.js>。这是本次构建的 chunk URL，不能将其当成永不变化的 API。

实测结果：

- 用户提供的示例 `key1` 与该算法完全吻合。
- 独立生成新的签名，不带 Cookie、账号、MPay token，两个 APK 均返回 **206 Partial Content**。
- 3.9：`bytes 0-255/2209990170`；3.10：`bytes 0-255/2315617832`；均具有 ZIP/APK 文件头。
- 3.9 远端前 256 字节与用户提供的本地 APK 相同；**未重新下载全部 2.21 GB，不能据此声明远端完整 SHA-256 已验证**。
- 前端设置的有效期为 12 小时；未进行持续 12 小时的过期边界测试。

本次尝试 Chrome 控制时报 `Codex auth token is unavailable`，因此上述结论来自官方公开 JavaScript 的静态调用链和真实 HTTP 验证，不是 Chrome DevTools 抓包。证据见 [download probe](research/netease-download-probe-2026-10-05.json)。

产品中无需把 Chrome 作为安装依赖。实现一个小型、版本化的官方下载 provider 即可；常量／算法变更时更新 provider。首次实现可固定已核验规则；后续若自动发现官网新规则，应采用严格的格式识别和失败提示，不执行任意下载到的 JavaScript。403 时有界刷新签名，仍失败就提示官方下载／本地导入，不无休止重试。

签名 URL 不写进锁文件，缓存以文件摘要标识；日志省略 query。续传前重新获取有效 URL，核对资源版本、长度及 ETag 等可用元数据；服务端忽略 Range 时重新下载到新的临时文件，不能把整个响应追加到残缺文件后面。

## 2. 许可与分发边界

### 启动器及依赖

主仓库本次基线提交为 `91220f0f7ccfd460090d14056ab1bf12e82869b1`，另有尚未提交的兼容改动；不能仅给出该提交便宣称覆盖实际运行的二进制源码。

| 部分 | 本次查证 | 发行要求／待办 |
| --- | --- | --- |
| `mcpelauncher-manifest` | 根目录 [LICENSE](../LICENSE) 为 GNU GPL v3 全文 | 启动器发行按 GPLv3 基线处理；提供实际修改版的对应源码、许可与构建／安装脚本 |
| `mcpelauncher-client`、`core`、`common`、`libc-shim` 等 | 当前子仓无顶层 LICENSE，部分源文件有单独版权声明 | 核实主项目许可覆盖范围及文件来源；不能把所有子仓统一标成 MIT，也不能仅凭 GPL 文末模板断言每个文件均为 GPL-3.0-or-later |
| `libjnivm`、`mcpelauncher-linker` 自身、game-window、file-picker、ImGui 等 | MIT；linker 内还有 AOSP 等第三方来源 | 保留各自版权／许可／NOTICE；递归审计实际编入的内容 |
| SDL3 | zlib 许可；目录内部分第三方代码另有许可 | 随实际构建的依赖生成通知清单 |
| `osx-elf-header/include/elf.h` | LGPL-2.1-or-later 源文件声明 | 保留声明，并审计头文件及实际产物适用义务 |
| ANGLE | [上游 LICENSE](https://github.com/google/angle/blob/main/LICENSE)，BSD 三条款形式 | 可以按条件分发；同时审计固定版本实际编入的 third_party 依赖 |
| OpenSSL、curl、GLFW、JSON、其余辅助库 | 必须按最终选择的精确版本盘点 | 提供对应许可、来源及构建选项；不能只审计顶层可执行文件 |
| mcpywrap | 当前 `pyproject.toml` 与 LICENSE 标为 MIT | 独立调用 GPL 启动器，不直接复制 GPL 实现进 MIT 模块；新写的集成代码单独说明来源 |
| `mcpelauncher-mac-bin` | 有预构建 ELF 和原生 FMOD；顶层没有完整许可清单 | 不能整目录打包。每个实际必要文件追溯到来源和许可；开发者路径已禁用 host FMOD，优先不带该库 |

GPL 允许商业分发，但要求满足相应条件。“我们提供一个 upstream 链接”不足以替代修改版的 Corresponding Source。建议每个 launcher Release 同时发布完整源码包（含子模块源码）、精确提交清单、我们自己的改动、构建配方、LICENSES／NOTICE 和依赖清单，并在下载入口提供源码链接。GPLv3 第 6(d) 节提供网络分发的一种履约方式；并非所有分发方式都一律套用“三年书面承诺”。

mcpy 与启动器采用独立进程和明确的 CLI／JSON 契约，有利于分离工程与许可边界；仅仅“另开一个进程”并非任何组合都免责的法律保证。不随运行时分发专有游戏文件。

上游 [FAQ](https://minecraft-linux.github.io/faq/index.html#can-i-play-with-an-apk) 还明确反对在没有有效 Google Play 许可时方便导入付费 APK。它描述的是上游国际版的产品／支持政策，不能直接推导网易开发者版的授权条件，也不能假设上游愿意接纳本方案。建议使用独立产品名／fork，并清楚标明非官方；不把上游预构建版本当作已包含我们的网易适配。

### Minecraft／网易资源的产品约定

用户已确认网易方面允许，后续不继续调查或要求重复确认。此次先前查阅的一手资料仅留作来源记录：[Minecraft EULA](https://www.minecraft.net/en-us/eula)、[Usage Guidelines](https://www.minecraft.net/en-us/usage-guidelines)、[网易游戏协议](https://mc.163.com/m/news/update/20180619/29176_719812.html)、[开发者平台协议](https://mcdev.webapp.163.com/static/%E7%94%A8%E6%88%B7%E5%8D%8F%E8%AE%AE.html)。

产品维持用户提出的分发方式：APK 由终端直接向网易 CDN 下载，ELF、`vanilla.mcp`、Python／Cocos 和原版资源仅在本机提取。我们的 Release 只发布启动器／适配器及允许分发的依赖；研究用的恢复脚本产物、旧版 `3.5.zip`、游戏缓存与包含原版资源的测试存档不进入发行物。首次安装可以展示官方来源与适用条款入口，但不再将其作为本任务继续工作的审批流程。

## 3. 建议的产品结构

```text
mcpy run
  → 现有 DependencyService / AddonProjectBuilder
  → 选择运行后端与固定的兼容配置
  → ensure_runtime（首次引导、下载、验证、本地组装）
  → 现有 sessions / worker
      → macOS 后端 → 原生 arm64 launcher → 用户本地 APK 内容
      → 现有 SafaiaChannel / RuntimeControlServer
  → readiness 检查 → logs / runtime py / ui / player / stop
```

三个独立版本维度：

| 组件 | 作用 | 来源 |
| --- | --- | --- |
| mcpy | 项目、依赖、CLI、下载管理、会话和调试 | 现有 Python 包 |
| macOS runtime | launcher、libc/JNI/ELF 兼容、ANGLE 等宿主库 | 我们构建并分发的独立签名发行包 |
| game profile | APK 身份／摘要、桥接 ABI、源码 loader、能力与测试矩阵的对应关系 | 我们发布的兼容元数据；APK 内容由网易提供 |

先支持 `darwin-arm64 + netease-dev + 3.9.100.297020 + ANGLE Metal`。3.10 可下载不代表可运行；正式版、Windows、Intel Mac、联网登录不纳入首个 profile。保留现有 Windows 和远程路由，显式远程失败时不改成本机执行。

### 复用点与改造位置

| 已有实现 | 产品化处理 |
| --- | --- |
| mcpy `commands/run_cmd.py::_setup_dependencies`、`AddonProjectBuilder` | 继续解析锁文件、QuMod、依赖、行为／资源包；macOS 后端消费已组装的产物，不新增另一套构建器 |
| mcpy `mcstudio/discovery.py` | 保留 Windows 发现逻辑；引入运行后端选择，避免要求 macOS 伪装成 `Minecraft.Windows.exe` |
| mcpy `mcstudio/sessions.py`、`session_worker.py` | 复用会话 ID、进程身份、日志、控制端口；worker 委托后端启动／查询就绪／保存退出 |
| 本仓 `tools/run_netease_dev.py` | 将 APK 组装、包部署、世界命令整理成版本化适配逻辑，去掉源码树和用户机器的固定路径 |
| `tools/netease_source_loader.py` | 随适配器版本固定，仅允许显式选中的项目源码；保留原 MCP 导入器，不把所有目录改成源码优先 |
| `tools/attach_netease_debug.py` | 复用已验证的 Safaia 流程，最终合并进正常 worker 生命周期，不长期维护另一个附加 worker 产品入口 |
| `tools/stop_netease_debug.py` | 将保存退出、确认世界 DB 关闭、核验进程身份、关闭 worker 的语义并入后端 stop |

会话通用接口只需要覆盖 `prepare / launch / readiness / stop` 等当前需求，先避免搭建泛化插件生态。macOS 使用独立实例元数据，不硬套 Windows cppconfig；可以共享世界设置的上层模型，由后端翻译为已有网易桥接命令。

`mcpy runtime` CLI、现有 Safaia 通道与游戏内注入的 `mcpy.*` 保持调试用途；业务 Addon 继续只依赖正式 ModSDK／项目框架。默认能力如 `python-client`、`python-server`、`source-addons`、`runtime-ui` 按验证结果报告；Windows 专属桌面录制／键鼠／热更不能因为新增 macOS 后端就全部宣称支持。

## 4. mcpy run 的首次体验（提案）

用户在已配置的 Addon 项目中执行原有 `mcpy run`：

1. 依照 CLI、项目配置和既有路由规则选择本地 macOS 后端；核对 CPU、OS、项目兼容版本。
2. 若资源未安装，展示将安装的运行时版本、官方 APK 版本／来源、磁盘需求及条款入口。用户确认一次后自动执行后续步骤；已安装且条款状态未变化时直接复用。
3. 从我们的 Release 获取启动器包；从网易获取签名 APK 下载地址；两类下载独立验证并展示进度。
4. 校验 APK 身份和完整摘要，安全解包到临时目录，再原子安装。资源安装成功后构建／部署项目包、启动独立世界。
5. 就绪后进入前台日志，或通过 `--detach --json` 返回 session；下次使用同一实例和固定的 runtime。

保留一个清楚的本地导入入口，方便已有 APK、断网开发和官方 CDN 故障。以下均为**拟新增**命令，不是当前可直接使用的 CLI：

```sh
mcpy engine list
mcpy engine install --profile netease-dev-3.9.100.297020
mcpy engine import --apk /path/dev_launcher_3.9.100.297020.apk
mcpy engine doctor
```

自动化环境沿用全局 `--non-interactive`。缺少条款确认或必须的选择时返回结构化 `setup_required`、原因和可执行下一步；不悬挂等待输入。可设计显式的 `--accept-game-terms` 安装选项并记录条款标识，普通 `--yes` 不暗中代表所有协议确认。

下载发生在 `run` 所需资源缺失或显式 `engine install` 时；`sync/build` 继续只处理项目依赖，避免构建一个 Addon 就意外下载数 GB 游戏。

## 5. 固定版本、缓存与更新

不能把 `pe_old` 当作“永久的 3.9”：它只是会滚动的渠道。项目固定兼容 profile，profile 固定 launcher、适配器、APK 的完整摘要／身份。接口结果用于发现下载位置；版本不匹配时不擅自升级项目。允许继续使用已校验本地缓存，官方不再供应该版本时明确说明并提供用户本地导入。

建议兼容清单记录：

```text
profile_id、schema_version、platform、min_macos（实测值）
launcher: release/version、sha256、签名身份、protocol_version、源码位置
apk: package_name、version_name、version_code、abi、size、sha256
     官方 origin/path、signing_certificate_digest（独立建立的可信基线）
engine: libminecraftpe_sha256、vanilla_mcp_sha256
adapter: bridge_revision、source_loader_revision、renderer、capabilities
validation: tested_os/hardware、通过的测试、已知限制
```

本机已测试的 **用户提供** 3.9 APK 基线：

```text
package = com.netease.mctest
version = 3.9.100.297020
bytes = 2209990170
sha256 = 932c32cf15dab669020e9f07ab7d1e574549d2e583e5fbd2fe79b098fe3f3417
```

此摘要已从本地完整文件计算，尚未通过重新完整下载官方文件来独立核对；APK 签名证书验证也尚未完成。以上字段不能仅根据文件名填充。下载完成后应校验 Android Manifest、ARM64 ELF、必需资源、全文件 SHA-256，并采用可验证 APK v2/v3 等签名的实现；仅查看 META-INF 证书不等于验证整个 APK 签名。

建议目录：

```text
~/Library/Application Support/mcpy/
  runtimes/<runtime-id>/      # 签名的宿主运行时，只读
  engines/<apk-sha256>/       # 用户本机提取的官方资源，只读
  acceptance/                # 条款确认记录，不含账号密码
~/Library/Caches/mcpy/
  downloads/<sha256>.part     # 可续传缓存
<project>/.runtime/
  instances/<id>/             # 世界、独立可写数据、固定版本记录
  sessions/<id>/              # 沿用 session、日志、控制记录
```

解包校验绝对路径、`..`、符号链接、重复／大小写冲突路径和异常解压大小；清理失败的 staging。引擎共享目录不写入项目包或世界；采用独立可写实例目录，不用可写硬链接连接共享游戏文件。避免旧 `vanilla.mcp` 与新 ELF 混用。

3.9 按现有提取规则选出 41,602 个成员，展开共 3,883,509,388 字节；加上 APK 已约 6.09 GB（十进制），尚不含启动器、部署的包、世界和升级暂存。首次安装应测算真实可用空间；更新时同时保留旧版和 staging，不能只按压缩包体积判断。

更新采用并排安装和显式迁移；不替换正在运行的引擎。升级世界前备份／复制，不能假设引擎回退也能回退世界格式。卸载运行时／缓存不连带删除用户世界。

## 6. 原生预构建包需要完成的工作

当前实验产物不是可直接发布的运行时包：

- `otool -L` 显示 launcher 依赖 `/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib` 和 `libssl.3.dylib`。
- ANGLE 来自用户已经安装的 `/Applications/Minecraft Bedrock Launcher.app/Contents/Frameworks`。
- 当前可执行文件 `LC_BUILD_VERSION` 的 `minos` 为 **26.6**、SDK 为 27.0。不能把“macOS arm64 能运行”宣传为“所有 Apple Silicon 系统均支持”。
- CMake 的普通 install 会复制 `mcpelauncher-mac-bin` 目录；它包含并非都需要的预构建／专有内容，不可原样作为产品发布包。

建议提供独立的原生 `.app` 运行时包（可装在 Application Support，不强制放到 /Applications）：固定依赖版本，从可追溯源码构建 ANGLE Metal、launcher 和必要支持库，附许可文件，修正 `@rpath`／`@loader_path`，关闭开发路径查找。按实际需要裁剪 Qt、WebView、MSA 界面等组件，不能简单假设关闭某个 CMake 选项就没有相关链接依赖。

CI 在不安装游戏的条件下产出开源运行时和对应源码；发行包采用明确文件白名单。含 ELF 的支持库按来源判断，不能按 `.so` 扩展名一刀切：游戏 ELF 禁止随包，允许分发且可追溯的支持 ELF 才可以随包。

需要验证 Developer ID 签名、公证、Gatekeeper 隔离属性、Hardened Runtime 与 ELF 可执行内存映射的兼容性。当前依赖 `DYLD_LIBRARY_PATH` 和动态装载行为；签名后可能需要改变库发现方式，并审核实际必要的 entitlement。不能承诺公证必然通过，也不把“关闭 Gatekeeper／SIP”当作正常安装步骤。

最低 macOS 版本通过指定 deployment target、实际依赖及干净机器测试确定；首版可选择较窄支持范围，但要在下载前准确检查。无需用户自己装 Homebrew；也不依赖现有 Qt Launcher 应用。

## 7. 运行可靠性与验收

当前 `sessions` 中的 running 首先代表进程存在。产品新增独立 readiness 字段，区分引擎就绪、世界进入 HUD、客户端／服务端 Python 可用、项目系统初始化。不能把 `play_world` 返回一个非空字符串（例如失败的 `"-1"`）当作成功，也不能把 Safaia TCP 已连接当作服务端 Mod 已运行。

同一世界持有跨进程锁，运行前不覆盖活跃实例的包。重复 `run` 返回已有 session 或明确 busy；重新运行须保存退出旧实例后再启动，不遗留老窗口。`stop` 使用游戏正常退出世界入口，确认 DB 已关闭再终止宿主／worker；不静默强杀尚未保存的世界。现有 attach 工具的善后流程是起点，但需合并到统一 worker，并覆盖启动失败／控制通道失效。

首版范围是离线本地世界，下载器能联网，游戏继续仅允许必要回环调试通信。对外公开的控制端口不在默认能力中；保存控制 token 的目录使用严格本地权限。

发布验收至少包括：

1. 干净 macOS arm64 用户环境，无源码树、Homebrew、预装 Launcher、Android SDK；一次引导安装并进入世界。
2. APK 下载中断续传、签名过期、官方渠道变化、磁盘不足、摘要失败、导入错误版本，都不会留下被当成完整安装的资源。
3. 最小源码 Addon 的客户端／服务端自动启动；修改源码后重新构建／启动能观察到变更；不依赖手工 import 才“成功”。
4. 两个现有 Mod 的真实操作回归：探测鞋服务端扫描→RPC→粒子／声音；物资发放机 UI→库存事务→保存重开。已知的 Android `time.clock` 与按钮回调兼容改动应保留在 Mod 自身，不作为全局引擎补丁强制施加。
5. 世界保存重开、重复启动、异常退出、升级后保留旧世界；每项测试结束关闭自己的窗口和 worker。
6. 现有 Windows／远程 `run`、依赖构建、会话命令保持回归通过。

目前仍有首次新数据／新世界偶发 native SIGBUS。已有世界重试成功不等于根因解决；它是从实验版走向稳定版的实际阻碍，需在首次安装验收中解决或明确作为实验版限制呈现，不做无限自动重启掩盖。

## 8. 建议实施顺序

1. **本地后端 MVP**：先用已验证 APK + 本地 runtime 接入 `mcpy run/status/logs/runtime py/stop`，消除手工脚本拼装和残留窗口，统一就绪判断。
2. **可搬运的 runtime**：固定源码和依赖，移除绝对机器路径，独立构建 ANGLE，完成许可清单、源码发行物与签名／公证实验。
3. **首次自动安装**：实现网易下载 provider、签名 URL、完整校验、安全提取、缓存／锁、条款引导、本地导入和非交互式错误契约。
4. **稳定性与发行**：完成新世界冷启动、干净机器和两个 Mod 的验收，发布实验版本后再扩大 OS／APK 支持矩阵。

这些步骤均以现有 launcher 和 mcpy 的真实框架为基础。第一版无需增加账号登录、完整网易启动器 UI、另外的 Mod 构建格式，或一套新的调试协议。
