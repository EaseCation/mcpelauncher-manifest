# macOS 无认证服务器连接

2026-10-07，开发 APK `3.10.100.299889`、macOS 26.6.2、Apple Silicon / Metal。

## 结果与交付范围

已通过公开 `mcpy connect` 以及配置了 `[tool.mcpywrap.server]` 的 `mcpy run`，连接本机 Nemisys → SynapseAPI → Nukkit。服务端记录 `LocalDev joined the game`，客户端进入 `hud_screen`，客户端 Python 读取到玩家。`runtime install` 可注入客户端调试工具；服务端 Python 和本地 Mod 热更明确拒绝。

初轮验收使用源码与隔离运行包；发布组合为 mcpywrap 0.4.3 / 原生运行包 0.4.3。旧运行包 0.4.0 没有 `network_connect_protocol=1`，新 CLI 会拒绝用它联机并给出资源升级命令。本轮没有修改 C++、游戏 ELF 或上游子模块。构建脚本会将更新后的 Python 适配器和协议元数据纳入运行包及完整性清单；无需新的二进制地址适配规则。

## 复用的引擎入口

cppconfig 使用 Windows 已有的 `world_info=null`、`room_info.ip/port`、`misc.multiplayer_game_type=100`。Android 启动队列通过现有客户端 Python 通道执行：

```python
application.instance.InitOfflinePlayer(0, 'LocalDev')
engine_notify_handler.instance.set_offline_start('1')
world.join_world(host, port, 'Development server',
                 {'user_name': 'LocalDev', 'user_id': '0'}, None,
                 {'multiplayer_game_type': 100})
```

不获取 MPay/MCS 身份。相同模块和参数结构见 3.5 Python 逻辑，已在 3.10 动态验证；未来版本仍需要实际就绪结果，不能仅凭入口名称存在承诺兼容。

网络会话复用 mcpy worker、日志、客户端 Python、偏好和退出机制，每次连接使用独立会话目录，不创建世界实例、不组装项目 Mod。`connection_verified=true` 表示曾观察到 HUD，并非持续探活。初次连接 90 秒没有进入 HUD 会报告失败、关闭进程并保留日志。

离线单人世界保留原网络策略。联机在 Seatbelt 中放行目标 UDP 端口及 DNS；localhost 目标限制为 loopback，其他目标按端口放行（Seatbelt 此过滤器不接受任意 IP，因此并非目的主机白名单）。默认不放行外部 HTTP 下载。资源包 CDN、服务器跨端口 transfer、公网认证和其他服务端版本没有验收。

## 隔离服务端

工作目录：`build-macos-arm64/network-investigation`（忽略于 Git）。CodeFunCore 原工作区未改动；使用各仓库 HEAD 的归档，包括 build-logic 和 Nukkit 语言子模块。主要源码版本保存在 `server-source/SOURCE_STATE.json`。

唯一源码调整是隔离副本中 `SynapseSharedConstants.FORCE_NETEASE_PLAYER=true`。这使用已有调试开关，确保离线认证链缺少网易身份时仍采用中国版协议。日志仍可能出现“正在解析为国际版”，应以实际 `isNetEaseClient()` 的强制结果为准。

Java 25，构建原有 `:nukkit:shadowJar :nemisys:shadowJar :SynapseAPI:shadowJar`，进程使用 ZGC。插件包含 SynapseAPI 和原有 AuthLibPackage stub。

- Nemisys：UDP `127.0.0.1:29132`，Synapse TCP `127.0.0.1:29305`，`xbox-auth=false`、`enable-network-encryption=false`、`nethernet-signaling=false`。
- Nukkit：本机平坦创造测试世界，禁用外部 RakNet；SynapseAPI 连接上述 TCP 端口。此分支认证由代理完成，不能把 Nukkit 配置中写入 xbox-auth 当作已验证的认证开关。
- 两侧 Synapse password 相同；RCON、query、UPnP、bug report 关闭。配置保留在测试目录，未连接生产服务器。

## CLI 验收

使用隔离的 `MCPY_ENGINE_HOME=.../network-investigation/isolated-home`，运行包由正式 0.4.0 的 APFS 克隆更新适配器、重新 ad-hoc 签名并生成完整性清单；游戏资源复用本机安装。原正式运行包和用户偏好没有被替换。

```sh
mcpy --local --project <会话目录> --non-interactive connect 127.0.0.1 --port 29132 --detach --json
mcpy --local --project <会话目录> status --session <sid> --json
mcpy --local --project <会话目录> runtime py --session <sid> --side client --code "__import__('clientlevel').get_level_id()" --json
mcpy --local --project <会话目录> stop --session <sid> --json
```

固定目标项目：

```toml
[tool.mcpywrap.server]
host = "127.0.0.1"
port = 29132
```

使用 `run --no-gui --detach --json`，不能同时指定新世界选项。结果保留于测试目录的 `public-connect.json`、`public-run.json`、`configured-ready.json`、`network-runtime-install.json`、`server-python-rejection.json`、`reload-rejection.json` 及服务端日志。

`runtime install` 成功不代表每个输入动作可用：测试克隆基于 0.4.0 C++，0.4.2 的统一输入返回 `missing_monotonic_clock`。本轮仅验证 Python 与入服，不将其报告成输入协议验收通过；应依照会话 capabilities。

无人监听的本机端口 29134 实测在 90 秒后返回 failed 和可读错误，并关闭游戏进程；记录见 `unreachable-result.json`。71 个定向单元测试通过（mcpy 65、启动器桥接 6）。测试完成后关闭全部本轮会话、Nukkit 与 Nemisys，保留配置和日志。
