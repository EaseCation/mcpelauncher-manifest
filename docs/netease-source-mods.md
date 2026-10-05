# 明文 Python Mod 接入与两款 Addon 实机验证

后续运行包、首次建世界 SIGBUS 修复及客户端 Python 通道见 [运行时加固记录](netease-runtime-hardening.md)。本页保留当轮测试细节及当时限制；历史会话已关闭。

2026-10-05：已实现显式开发源码加载，并在 Android `3.9.100.297020`、macOS arm64、ANGLE Metal、离线单人世界中自动加载矿物探测鞋和物资发放机。验证覆盖下述具体功能，不代表两款 Mod 的所有功能、多人和所有设备均已通过。

## 使用

先用 mcpy 对项目执行 `sync` / `build`，再把组装目录传给启动工具：

```sh
python3 tools/run_netease_dev.py --angle-backend metal --debug-loopback \
  --source-addon /absolute/path/addon-one/build \
  --source-addon /absolute/path/addon-two/build \
  --world-id addons-playtest \
  --data-dir build-macos-arm64/addons-playtest/data \
  --cache-dir build-macos-arm64/addons-playtest/cache \
  --log build-macos-arm64/addons-playtest/run.log
```

本机已生成 `build-macos-arm64/NetEase Addon Test.app`，其启动脚本固定加载本轮构建的两款 Mod 和最小测试 Mod，重新启动会更新安装副本。更改源码后先重新 `mcpy build`，再保存退出并重新启动游戏。

`--source-addon` 可重复，接受含 `behavior_pack` / `resource_pack` 的 mcpy 构建目录；只用于离线开发，不与在线登录或自定义命令队列混用。源码项目保留在原目录，启动器按 manifest UUID 复制到隔离数据目录。为防止同时打开同一存档或覆盖正在使用的包，数据目录使用跨 exec 继承的文件锁。

## 实现方式

- `tools/netease_source_loader.py` 使用 Python 2 导入协议，仅接受本次指定的行为包根及其子目录。
- 源码通过解释器原生 `imp.find_module / imp.load_module` 加载；要求 `.py` 或带 `__init__.py` 的源码包，不写 `.pyc`，拒绝越出允许根的链接。
- 只在这些目录前置源码 finder；游戏自身 `vanilla.mcp` 和其他路径继续由原 MCP importer 处理。
- 服务端的 `LoadWindowsAddonPy` 对选定目录使用相对行为包路径构造模块名，之后仍调用原 `ImportModAndInit`。非选定路径交回原方法；`loadingWindows` 状态有 finally 恢复。
- 客户端继续原有 `LoadMoblieAddonPy`，由源码 finder 解决导入。
- 适配在世界启动前通过现有 JNI/Python 桥安装；没有手动导入两款 Mod 的业务入口，没有用 `runtime install` 或 `mcpy.*` 来注册业务系统。Safaia 只用于加载后的观察、测试夹具和交互。

## 自动加载证据

最小项目由 mcpy init/mod 生成原生 ModSDK 模板，随后设置独立日志标记。SOURCE_A 在客户端/服务端都自动注册，GetSystem 读取到 `.py` 文件路径。将 config.py 改为 SOURCE_B 后重新构建、重新启动，双端读到 SOURCE_B。

三份行为包同时安装：

| 行为包 | 明文 Python 数量 | MCP/MCS/PYC/PYO |
| --- | ---: | ---: |
| 最小 SOURCE_B 探针 | 7 | 0 |
| 矿物探测鞋（含 QuMod） | 80 | 0 |
| 物资发放机（含 QuMod） | 87 | 0 |

原生 Pack Stack 和 SERVER/CLIENT addon list 均包含三份行为包；`OreDetector.Server/Client`、`Ration.Server/Client/Runtime/Sources/Protection` 自动出现在运行时。源文件清单见 `build-macos-arm64/addons-playtest/evidence/source-inventory.json`。

## 矿物探测鞋

开始时用户观察不到效果。服务端已经识别装备并持续 tick，但每帧在 `time.clock()` 报 AttributeError：Android 的 time 模块不提供该函数。

在参考仓库的开发副本中，将扫描计时改为 `getattr(time, 'clock', time.time)`，保留 256 次读取的独立预算上限。Windows 继续使用 clock，Android 使用 time；time 是墙钟，时钟跳变可能影响当帧时间预算，但计数上限仍限制工作量。未把空扫描结果伪造成矿点。

冷启动后实测：

- 装备 `ore_detector:gold_detector_boots_4` 自动触发扫描。
- 放置的真实金矿 `(-2,-59,18)` 出现在服务端 target_records，扫描 index 持续推进。
- 客户端收到同一坐标、矿种和鞋类型，产生矿点标记、方向粒子、声音调用。
- 画面可见石墙前的黄色矿点星光和方向粒子。
- 保存重开后装备和矿点保留，扫描、RPC、渲染反馈自动恢复。

首次修复测量时，83 次方向粒子、47 次声音、24 次标记创建，失败计数均为 0。最后一次重开观察到方向粒子累计 259、声音 147、标记 73，其中方向粒子失败 1 次、标记和声音失败 0 次；不将其描述为长期零失败。

证据：`ore-server-fixed.json`、`ore-client-fixed.json`、`reopen-client.json`。

## 物资发放机

两款侧挂装置模型与原生界面正常显示，服务端真实箱子归属已建立。将实验箱底换为石块以满足原规则后，通过游戏 UI 完成连接；没有跳过基座、归属或库存检查。

早期接物兜部分按钮不生效。改用临时独立名称的记录包装后有效，恢复原 `on_button` 又无库存变化。针对性修复是在 `PairTerminal` 绑定独立名称的 `on_pair_button`，保留全部原业务逻辑和基类 fallback。没有修改引擎或伪造按钮成功。随后重启进程，确认不存在临时 `_debug_original` 跟踪属性，重新执行实机验收。

| 实际交互 | 可观察结果 |
| --- | --- |
| 管理 → 连接并保护箱子 | 服务端记录真实箱子及石质基座 |
| 公共投递兜：开放 → 保存 | enabled=true 持久化 |
| 投入 1 个面包 | 手持 16→15，箱内 0→1，账本 committed |
| 去掉临时诊断并冷启动，再投入 1 个 | 手持 15→14，箱内 1→2，账本新增 committed |
| 行囊挂袋：连接、选用面包、启用 | 补到 32、每轮上限 64、刷新时刻保存 |
| 点击“补充 2 个” | 背包 14→16，箱内 2→0，剩余额度 64→62，账本 committed |
| 再保存退出、重新启动 | 背包 16、箱内 0、配置及 3 条操作记录保留 |

测试用的 16 个面包由独立探针放入事先确认空的背包槽位；后续扣除、转移、额度变动全部由 Mod 的真实 UI/RPC/业务服务完成。没有直接调用 claim/donate 服务制造 UI 成功。

证据：`donation-transfer.json`、`donation-cold-final.json`、`refill-transfer.json`、`reopen-persistence.json`，以及 `refill-success.jpg`。

注意 mcpy `use_item` 对此 Mod 的拦截交互可能报告 input_rejected，但真实界面已打开：需要结合新 UI 快照确认效果，不能据此重复触发。动态时钟会使旧 UI 快照失效；测试通过重新观察后立即按唯一按钮名字选择执行，未取消快照保护。

本轮未覆盖基础定时发放机的全部配置/搬家/保护矩阵、工作台配方、真实多人、额外维度和平台发布测试。

## 两处 Mod 兼容修复的位置

仓库副本：`build-macos-arm64/netease-addons-reference`，两处源码修改：

- `ore-detector-boots/behavior_pack/OreDetector/Server.py`：Android 计时兼容。
- `ration-box/behavior_pack/Ration/PairTerminal.py`：独立按钮回调。

可复用 diff 已保存到主仓库的 `tools/addon-compat/android-source-mods.patch`。适用性可用 `git apply --check` 检查；没有自动向远端提交或发布 Mod。

## QuMod 依赖锁迁移

两个项目固定的 QuMod 提交保持 `a07430aaaa6dce5f1ef68de3fda52ea4b9366c2c`。旧源码摘要来自 Windows 的大小写排序和 CRLF checkout，而当前缓存使用原始 Git archive 字节。

mcpywrap 新增显式命令：

```sh
mcpy --project /absolute/path/addon --non-interactive sync --migrate-windows-lock --json
```

仅当重新计算的完整 Windows/CRLF 源码摘要与旧锁精确匹配时才迁移；不接受任意源码差异。派生注册目录由当前工具重建，旧锁保存在 `.mcpy/lock-backups/<sha256>.json`，JSON 返回新旧源码/注册摘要。正常 sync/build 仍执行严格摘要检查。迁移在本轮开发副本执行，QuMod 代码未被修改或直接手工拼装。

## 验证与限制

- 源码适配的 Python 2 行为测试通过：普通/包导入、无 pyc、限定根、链接越界、原路径 fallback、重复安装。
- mcpywrap Git 依赖测试：15 项，14 通过、1 个 Windows 条件测试跳过；包含显式迁移、备份和拒绝未知差异。
- mcpywrap 运行时协议测试：14 项通过。
- 矿物探测鞋宿主测试：54 项通过。
- 物资发放机宿主测试：68 项通过。
- 源码及 git diff 检查通过。宿主测试不代替上述真实游戏证据。

仍存在首次新数据/新世界初始化时偶发 native SIGBUS；本轮两次首次冷启动失败后，用已生成世界再次启动成功，多次保存重开通过。已保留 cold-start.log，不能宣称修复了该问题。修改启动命令将创建/配置/进入世界合并到一次调度，但这并非 SIGBUS 根因的完整修复。

本轮结束使用 `tools/stop_netease_debug.py`：先请求游戏退出世界，核对世界 DB 已关闭，再处理未响应的进程退出并停止 worker。默认不遗留测试窗口；需要继续时打开上述独立应用。
