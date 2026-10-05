# macOS arm64 开发者版：Safaia / mcpywrap 调试

直接 Metal 图形后端现已实测进入世界，并保留独立调试会话，见 [Metal 测试说明](netease-metal.md)。

2026-10-04 实测：原生 arm64 客户端已进入离线单人世界，复用 `mcpywrap` 的 Safaia 通道执行客户端和服务端 Python、采集日志、读取 HUD 节点和玩家状态。运行脚本来自当前 3.9 APK 的 `vanilla.mcp`；3.5 源码仅作接口参考。

## 启动与连接

本机已有 `mcpy` 0.3.19，解释器为 `<mcpy-python>`。连接适配器加载相邻源码仓库 `<mcpy-repository>`；可用 `--mcpy-source` 指定其他路径。

```sh
<mcpy-python> \
  <launcher-repository>/tools/attach_netease_debug.py --launch
```

已有运行中的调试会话会直接返回其信息。新启动时，打开独立调试数据目录中的离线世界，并启动 Safaia worker。初次返回 `attached` 仅说明 worker 已启动；连接建立及世界加载完成后才能执行代码。不要同时用两个进程打开同一个存档。

若游戏由其他方式启动，可显式附加到指定 PID：

```sh
<mcpy-python> \
  <launcher-repository>/tools/attach_netease_debug.py --pid <游戏PID>
```

目标须是以 `run_netease_dev.py --debug-loopback` 启动的开发者客户端。普通离线模式禁止全部 IP 网络，无法连接 Safaia。

当前交接信息保存在 `build-macos-arm64/netease-debug/session.json`。本次已验证会话：

- project：`<launcher-repository>/build-macos-arm64/netease-debug/mcpy-project`
- session：`52361a377c504955bbdcde0053ee76fc`
- 游戏 PID：`53879`；worker PID：`54634`。重启后以新交接结果为准。
- 世界：`codex-arm64-smoke`，位于 **netease-debug/data**，与此前 **netease-dev/data** 的离线存档分开。

## 日常命令

```sh
DEBUG_PROJECT=<launcher-repository>/build-macos-arm64/netease-debug/mcpy-project
DEBUG_SESSION=52361a377c504955bbdcde0053ee76fc

mcpy --local --project "$DEBUG_PROJECT" --non-interactive \
  status --session "$DEBUG_SESSION" --json

mcpy --local --project "$DEBUG_PROJECT" --non-interactive \
  runtime py --session "$DEBUG_SESSION" --side client --code '1 + 1' --json

mcpy --local --project "$DEBUG_PROJECT" --non-interactive \
  runtime py --session "$DEBUG_SESSION" --side server \
  --code "import server.extraServerApi as api; _result = api.GetPlayerList()" --json

mcpy --local --project "$DEBUG_PROJECT" --non-interactive \
  runtime py --session "$DEBUG_SESSION" --side client --file /absolute/path/probe.py --json

mcpy --local --project "$DEBUG_PROJECT" --non-interactive \
  logs --session "$DEBUG_SESSION" --source game --tail 100 --json
```

表达式返回 `value`；多行代码用 `_result` 指定返回值，`print` 对应 `stdout`，异常对应 `error`。游戏使用 **Python 2.7.13**，外部 CLI 使用 Python 3。客户端 globals 的临时变量实测可跨请求读取。`unknown` 表示结果未能确认，不自动重复有副作用的脚本。

游戏 `mcp.log` 大部分行经过 Base64 编码；Safaia 转发后，`mcpy logs --source game` 直接提供文本日志。原生客户端日志用 `--source engine`。原始位置：

- `build-macos-arm64/netease-debug/run.log`
- `build-macos-arm64/netease-debug/data/mcp.log`
- `<project>/.runtime/sessions/<session>/game.log`

## UI 与玩家调试

```sh
mcpy --local --project "$DEBUG_PROJECT" --non-interactive \
  runtime install --session "$DEBUG_SESSION" --json
mcpy --local --project "$DEBUG_PROJECT" --non-interactive \
  runtime ui snapshot --session "$DEBUG_SESSION" --json
mcpy --local --project "$DEBUG_PROJECT" --non-interactive \
  runtime player snapshot --session "$DEBUG_SESSION" --json
```

实测安装原有 `mcpy.ui` / `mcpy.player` / `mcpy.api` 成功，无须修改游戏资源或重写控制层。`mcpy.*` 仅供当前会话临时调试，不能写进 Addon 业务代码或当作游戏发布依赖。

本轮验证：

| 检查 | 实际结果 |
| --- | --- |
| 客户端表达式 | `1 + 1` → `2`，completed |
| 多行代码及 stdout | 设置临时变量 `123`，输出日志标记，下一请求读到 `124` |
| 服务端表达式 | `6 * 7` → `42`，completed |
| 服务端实际 API | `GetLevelId()` 返回当前世界，`GetPlayerList()` 返回本地玩家 |
| HUD 快照 | `hud.hud_screen`，检查 438 个节点，产生按钮语义树 |
| 玩家快照 | 坐标、朝向、饥饿值、快捷栏、维度和准星方块均返回 |
| 玩家动作 | 槽位 1 → 2，独立读取确认 2，再恢复 1 |
| 日志 | 能读取游戏日志和服务端执行回执 |

未验证移动、战斗、资源热更、录屏等所有能力。Windows 原生窗口输入和录屏后端不因 Safaia 可用而自动支持 macOS。

## 协议与本轮改动

```text
Android 内置 MCSSafaia：UDP 26613–26622
  ← mcpywrap 定向发送本机 TCP 调试器地址
  → 游戏建立 TCP 连接，发送 config 帧（3，含 connect_port）
  ← worker 核对端口归属目标 PID，发送 pass（48）
  ↔ 日志帧（4）、客户端脚本（22）、服务端脚本（23）
  ↔ mcpywrap 原有请求 ID、输出捕获与超时处理
```

- `tools/attach_netease_debug.py` 只负责连接已存在的进程、会话交接和 worker 生命周期；协议、脚本封装、UI/玩家控制及日志解析复用 mcpywrap。
- mcpywrap 的 `runtime_debug.py` 改为查询目标进程的 UDP sockets。macOS 全系统 `psutil.net_connections()` 无 root 权限会失败，按 PID 查询实测可用；仍核验握手端口归属，兼容 psutil 5.x 的方法名。
- `--debug-loopback` 的沙盒允许本机绑定、入站，以及到 localhost 的出站；实测 UDP 回环收包成功，向外部 IP 的 TCP connect 返回 EPERM。原有普通离线策略保留，调试模式与 `--online` 互斥。
- 离线身份、离线标志、`world.play_world` 改为一次现有 JNI/Python 调度。原先分三次、各间隔两秒，在本次启动条件下复现了身份设置后的 native 崩溃；合并后完成入世界并持续运行。具体崩溃根因未完全恢复，不能把该调整称为已修复所有启动竞争。
- Safaia 能在启动界面完成握手，但此时 `GetSystem('Minecraft', 'safaia')` 尚不可用，执行请求会产生 `system init failed`。必须等世界脚本系统初始化。

本轮 `mcpywrap` 运行时协议测试 14 项通过；启动器 libc 与认证桥接的独立测试也通过。网络兼容改动包含 socket 非阻塞标志与 `F_GETFD`、`socketpair`，均有行为测试。

## 与 cppconfig 的关系

`mcpywrap/mcstudio/runtime_cppconfig.py` 为 Windows 测试引擎构造启动配置。Android 原生 `_minecraft` 实测没有 `get_cppconfig_path`，其名字包含 `config` 的导出 Python 方法列表也为空。3.5 包装层明确限制该 getter 只在 Windows/no-launcher 模式使用。

但是两端的“描述世界并启动”数据模型有明显对应：

| cppconfig | Android 既有接口/数据 | 验证程度 |
| --- | --- | --- |
| `world_info.level_id` / `name` | `world.play_world(level_id, level_name, ...)` | 启动、读取 ID 已实测 |
| `game_type` / `difficulty` / `permission_level` | `set_world_info` 的 `basic_info`，其中权限字段为 `player_permission_level` | 字段读取已实测；本次设置过模式与难度 |
| `cheat` / `cheat_info` | `cheat_info.enable` 与同名规则字段 | enable 已设置；天气、掉落、随机刻等字段读取已实测 |
| `world_type` / `seed` | `world.create_world` 创建参数 | 平坦世界已验证；不要假设两套数字枚举完全相同 |
| `resource_packs` / `behavior_packs` | `world.play_world` 的两个 pack 参数 | 空列表启动已验证；PC 路径到 Android pack 的安装/标识转换未验证 |
| `skin_info` | `world.play_world` 的皮肤参数 | 有接口，3.5 字段名不同；3.9 自定义皮肤未测试 |
| `room_info` | `world.join_world` 或本地联机参数 | 本轮仅单人世界，未测试 |
| `LocalComponentPathsDict` / `MainComponentId` | 组件装配与资源安装层 | 尚无直接等价入口证据 |

因此后续适合复用 cppconfig 作为宿主侧配置模型，经过小型字段转换调用已存在的 `world.create_world / set_world_info / play_world`；不应给 Android 任意放一份 cppconfig 文件就认为它会读取，更无需重写世界加载逻辑。

当前游戏和调试 worker 保留运行。保存世界应走游戏内“保存并退出”；`mcpy stop` 会终止游戏进程，不等同于存档保存。适配器自身退出只断开调试，不主动杀游戏。
