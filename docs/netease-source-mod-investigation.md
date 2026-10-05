# Android 开发者版：明文 Python Mod 自动加载实验

2026-10-05 后续：已实现显式源码适配，双端自动加载和两款 Addon 的关键玩法通过，见 [源码接入与实机结果](netease-source-mods.md)。本文记录适配前结果。

后续已完成 MCPK 解包、opcode 还原、关键函数反编译与实际调用跟踪，见 [加载链反汇编报告](netease-python-loader-disassembly.md)。已确认源码分支确实执行且原生 `imp.load_source` 可用，默认自动加载失败仍来自导入链。

日期：2026-10-04。目标：`dev_launcher_3.9.100.297020.apk`，macOS arm64，ANGLE Metal，离线单人世界。此实验检验正常行为包加载，不把 Safaia 的 `exec`、手动导入 Mod 或手动注册系统算作通过。

## 结论

**当前默认启动链能够挂载源码行为包，但未自动导入其中的 Python Mod。** 客户端和服务端均未出现初始化日志，`GetSystem` 返回 None，`sys.modules` 中也没有测试脚本包。不能据此宣称本 APK 已经原生支持与 Windows 测试端相同的源码开发流程。

已定位到具体差异：默认 `redirect.McpImporter` 接管行为包目录，只查找 `.mcs`，无法发现磁盘上存在的 `.py` 包；服务端源码加载器还沿用 Windows 的固定目录深度假设。下一步若要实现源码开发，应增加明确、限定范围的开发加载适配，并重新做自动加载测试。本轮没有修改这些导入/注册逻辑来制造通过结果，也未修改 APK 或 `vanilla.mcp`。

## 最小项目与 API 依据

临时项目：`build-macos-arm64/source-mod-test/project`。

通过 mcpy 公开 CLI 创建：

```sh
mcpy --local --project build-macos-arm64/source-mod-test/project --non-interactive \
  init --name SourceLoadProbe --type addon --json
mcpy --local --project build-macos-arm64/source-mod-test/project --non-interactive \
  mod --name SourceLoadProbe --script-dir sourceLoadProbe \
  --server-system ServerSystem --client-system ClientSystem --framework native --json
mcpy --local --project build-macos-arm64/source-mod-test/project --non-interactive build --json
```

ModSDK MCP 已查询 3.9 开发指导、脚本开发入门，以及以下精确 API：

- `RegisterSystem(nameSpace, systemName, clsPath)`：客户端/服务端分别注册系统实例；类路径从脚本第一层开始。
- `GetClientSystemCls()` / `GetServerSystemCls()`：取得对应系统基类。
- `GetSystem(nameSpace, systemName)`：读取已注册系统，供验证使用。
- `modMain.py` 的 `Mod.InitClient` / `Mod.InitServer` 是正常初始化入口。

项目结构：

```text
behavior_pack/
  manifest.json
  entities/                 # 保留空目录
  sourceLoadProbe/
    __init__.py
    modMain.py
    config.py
    client/__init__.py
    client/ClientSystem.py
    server/__init__.py
    server/ServerSystem.py
```

双端构造函数分别输出 `[SOURCE_MOD_PROBE][CLIENT][SOURCE_A]` 和 `[SOURCE_MOD_PROBE][SERVER][SOURCE_A]`，同时保留 `source_revision` 与 `source_file` 属性。没有引用 `mcpy.*`，没有 `.mcp`、`.pyc` 或 `.pyo`。`pyproject.toml` 的 Python 3 要求属于宿主工具，游戏脚本使用 Python 2.7 兼容写法。

## 运行与实际结果

测试数据：`build-macos-arm64/source-mod-test/runtime/data`。行为包安装到此数据目录的 `games/com.netease/behavior_packs/source_load_probe`，通过既有 `world.play_world` 的 behavior_packs 参数启用 `source_load_probe`，世界 ID 为 `codex-source-mod`。

| 阶段 | 结果 |
| --- | --- |
| `mcpy init / mod / build` | 成功，产物仍是明文 Python |
| 首次冷启动 | 复现此前 native 启动阶段 SIGBUS，尚未进入 Mod 加载；已保留日志 |
| 复用已创建世界再次启动 | 进入 HUD，`world.play_world` 返回 true |
| Pack Stack | 出现 `SourceLoadProbe Behaviors`，UUID `fff61405-1d6a-4669-ad13-6530ab4d4d2d` |
| 双端 addon list | 均包含测试行为包的真实路径与 UUID |
| 客户端 `GetSystem('sourceLoadProbe', 'ClientSystem')` | None |
| 服务端 `GetSystem('sourceLoadProbe', 'ServerSystem')` | None |
| 已导入模块 | 两端都没有 `sourceLoadProbe*` |
| 初始化日志 | 未出现测试标记 |

因为 SOURCE_A 尚未自动加载，未继续进行“改为 SOURCE_B 后重启”的正向复测，避免把没有初始成功样本的变化当作源码加载证据。

证据：

- `runtime/run.log`：原生 Pack Stack 与 HUD。
- `runtime/data/mcp.log`：Base64 日志中包含 SERVER / CLIENT addon list。
- `runtime/first-cold-start.log`：首次 native 崩溃。
- `runtime/evidence/stock-source-A.json`：双端只读系统查询结果。
- `runtime/evidence/source-A-sha256.json`：7 个 Python 源文件的摘要。

实验结束后已调用游戏自身的退出单人世界接口。普通进程停止请求超时，确认该测试世界的数据库文件已关闭后，才结束本轮测试进程；调试 worker 已退出。项目、存档及日志保留，其他既有游戏会话未停止。

首次冷启动崩溃发生在 Mod 入口之前，与本轮源码导入失败不能混为一谈；此前合并离线初始化调度没有消除全部启动故障。

## 运行时定位

在当前 3.9 游戏中只读检查得到：

```text
GetAllFiles: 找到 source_load_probe/sourceLoadProbe/modMain.py
imp.find_module: 能在磁盘找到 sourceLoadProbe 包
sys.path: 已包含 source_load_probe/
sys.path_importer_cache[该目录]: redirect.McpImporter
McpImporter.Ext: .mcs
该 importer.find_module('sourceLoadProbe'): None
```

实际方法 `co_names/co_consts` 与 3.5 参考中的逻辑一致：`McpImporter.find_module` 查询 `fop` 中的 `.mcs` 内容。路径导入器接管目录后，未提供对普通 `.py` 的回退。这里验证的是导入器查找能力，没有手动执行测试 Mod。

服务端 `MinecraftMod.load_mod` 的源码分支调用 `LoadWindowsAddonPy`。3.9 方法常量包含固定的 `10`；按其逻辑处理本次宿主路径会得到：

```text
games.com.netease.behavior_packs.source_load_probe.sourceLoadProbe.modMain
```

而移动端的入口应为 `sourceLoadProbe.modMain`。这也是宿主目录不能直接套用 Windows 测试端路径算法的证据。

游戏 Python 字节码指令经过定制，标准 `dis.dis` 无法正确解析，已遇到 IndexError；本轮没有根据错误反汇编结果推导控制流。方法名称、常量、路径计算和查找返回值均分别核对。

## 已知可用项目对照

用户提供仓库已克隆到 `build-macos-arm64/netease-addons-reference`，提交：

```text
8577fcd33c10a59e88a951e3e6a6d0af0651eebe
```

| 项目 | 入口 | 对照结果 |
| --- | --- | --- |
| ore-detector-boots | `behavior_pack/OreDetector/modMain.py` | manifest 同为 format_version 2 / data module；QuMod `EasyMod, QMain` 暴露在入口 |
| ration-box | `behavior_pack/Ration/modMain.py` | 同样通过 QMain 与 EasyMod 注册客户端/服务端模块 |
| 最小测试 | `behavior_pack/sourceLoadProbe/modMain.py` | 直接使用官方 Mod.Binding / InitClient / InitServer；脚本同样位于行为包直接子目录 |

未发现最小测试的入口形式错误。QuMod 的 QMain 是其内部绑定类，不要求原生 ModSDK 项目也使用 QMain。两个参考项目都指定 Windows 测试引擎 `3.9.0.401155`；该配置不证明 Android APK 的导入器相同。

### 参考项目依赖恢复限制

两个项目固定 QuMod 提交 `a07430aaaa6dce5f1ef68de3fda52ea4b9366c2c`。对矿物探测鞋执行 `mcpy sync`，既有缓存和本次隔离缓存均未通过原锁文件摘要校验。

已验证：对同一 Git 归档的文件模拟 Windows 路径排序和 CRLF 换行，可重现锁内源码摘要 `480e7e0b…`；当前 Git archive 原始文件摘要为 `ce980e73…`。但注册后的构建内容摘要仍不能完整重现。因此保留锁文件和校验，不把依赖未完整恢复的运行当成已知项目的有效 A/B。

本轮仅完成两个项目的结构与入口对照，**没有声称两个完整 QuMod 项目已在本机加载成功或完成玩法测试**。试验性的摘要兼容修改已撤回；参考仓库的受控文件保持未修改。
