# 中国版开发者 APK：ANGLE Metal 后端

后续已改用独立运行包中的 ANGLE，见 [运行时加固记录](netease-runtime-hardening.md)。以下是首次 Metal 实验的历史记录，所列旧会话已关闭。

2026-10-04，在本机 Apple M1 Max 上验证成功。Android arm64 游戏仍直接执行，图形路径改为 **OpenGL ES → ANGLE Metal backend → Metal**。

使用已经安装的 Minecraft Bedrock Launcher.app 所附带的 arm64 ANGLE，无需下载或编译新的图形库。运行日志确认：

```text
Renderer: ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Max, Version 26.6.2 (Build 25G83))
Version: OpenGL ES 3.0.0 (ANGLE 2.1.24882 git hash: c7068f790980)
```

此前的 OpenGL 后端日志为 `ANGLE (Apple, Apple M1 Max, OpenGL 4.1 Metal - 90.5)`。两者不同；后一字符串里的 Metal 是 Apple OpenGL 驱动描述，不能据此认定 ANGLE 本身使用直接 Metal 后端。

## 启动

本轮生成并打开：

```text
build-macos-arm64/NetEase Metal Test.app
```

应用具有独立的 macOS 标识，启动脚本固定 `ANGLE_DEFAULT_PLATFORM=metal`，使用独立的数据和缓存目录：

- 数据：`build-macos-arm64/netease-metal/data`
- 缓存：`build-macos-arm64/netease-metal/cache`
- 世界：`codex-metal-smoke`
- 原生日志：`build-macos-arm64/netease-metal/run.log`
- 画面记录：`build-macos-arm64/netease-metal/metal-world.png`

当前实例运行中；需要重新启动时，先在游戏内保存退出并关闭当前应用，避免同时打开同一存档。命令行入口：

```sh
python3 tools/run_netease_dev.py \
  --angle-backend metal --debug-loopback --world-id codex-metal-smoke
```

重新生成应用：

```sh
python3 tools/run_netease_dev.py \
  --angle-backend metal --debug-loopback --world-id codex-metal-smoke \
  --make-app --prepare-only
```

`--angle-backend opengl` 显式选择旧后端；不提供参数则保留既有选择方式。Metal 的默认数据与之前的离线/调试目录分开。普通离线和仅开放回环的调试沙盒仍适用，未恢复网易在线登录。

游戏视频设置里显示“OpenGL”是正常的：游戏仍使用其 GLES 渲染器，ANGLE 在宿主端转换为 Metal。本轮没有启用 Windows RenderDragon/DXMT，也没有验证灵动视效。

## 验证结果

- 实际进入单人世界 `codex-metal-smoke`，原生状态进入 `hud_screen`。
- 通过 CUA 观察到加载界面、视频设置页、暂停菜单、玩家模型及背景地形纹理。
- Safaia 连接成功，客户端 Python 读取到当前世界、玩家坐标、维度和快捷栏状态。
- 服务端 Python `GetLevelId()` 返回该世界，`GetPlayerList()` 返回本地玩家。
- 原有 `mcpy runtime install` 成功，可继续使用 UI/玩家调试接口。
- 原生 arm64 客户端重新编译成功。

本轮以兼容性验证为目标，没有进行同场景、同分辨率、单实例条件下的 OpenGL/Metal 性能 A/B。界面中的瞬时 FPS 不能用于计算性能提升。尚未覆盖复杂地图、全部材质、长时间运行以及窗口尺寸切换的完整回归。

用户在本次实际使用中反馈“看起来帧数有明显提升”。这是正向的实际体验反馈；尚无标准化提升百分比。后续开发测试建议优先使用上述独立 Metal 入口。

## 首次启动时序修复

初次 Metal 启动中，`engineIsReady()` 早于 Python 模块初始化完成。原来的两秒延迟仍可能先调用 `world.create_world`，返回 `Reject(-1)`，随后才完成脚本图形初始化。

开发者命令现在还等待运行时状态同时出现 `mtl_level` 和 `top_screen`，即已经完成脚本图形设置并创建启动场景，再调度现有命令队列。本次应用启动中记录了该就绪点，随后 `world.play_world` 返回 true 并进入 HUD。这里的 `mtl_level` 是游戏脚本状态字段，不是用来判断 ANGLE 后端。

## 当前调试会话

交接文件：`build-macos-arm64/netease-metal/session.json`。本轮：

- 游戏 PID：`61670`；worker PID：`61754`。
- project：`<launcher-repository>/build-macos-arm64/netease-metal/mcpy-project`
- session：`67143efd8e724624beecacc3b0031bf5`

重启后 PID 与 session 会变化。附加新进程可使用：

```sh
<mcpy-python> tools/attach_netease_debug.py \
  --pid <Metal游戏PID> \
  --project build-macos-arm64/netease-metal/mcpy-project \
  --engine-log build-macos-arm64/netease-metal/run.log
```

适配器现在把交接文件保存到对应引擎日志目录，Metal 与原 OpenGL 调试会话可分别保留。更多 Python、日志和 UI 命令见 `netease-dev-debug.md`。
