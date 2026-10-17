# macOS 游戏内输入单调时钟

旧运行包只导出 `_mcpy_launcher.reload_ui()`。游戏使用 Python 2，没有
`time.monotonic()`；非 Windows 的 `time.clock()` 是 CPU 时间，不能驱动真实持续时间的输入计划。
因此 mcpywrap 的统一输入会正确返回 `missing_monotonic_clock`。

启动器现在按经过验证的绑定导出 `_mcpy_launcher.monotonic()`，返回
`std::chrono::steady_clock` 的秒数。它是临时调试能力，不是 ModSDK 或业务 Addon 依赖。
不依赖 RPC 轮询、渲染帧数、游戏 tick、系统日期或 Python 墙钟。

游戏剥离了 CPython 导出，必须使用游戏自己的 `PyFloat_FromDouble` 构造结果。
`analyze_developer_binary.py` 从 CPython 的 `fabs` 和 `ceil` 方法注册表分别定位包装函数，
验证二者汇合到同一个 `math_1_to_whatever`，再验证其浮点返回路径与完整的
`PyFloat_FromDouble` 构造函数（包括空闲链表、分配和对象初始化）。规则由受审计的
3.9 ELF 导出，仅存储规范化指令摘要；运行时不使用版本地址表。

结构检查已覆盖 3.9.100.297020 和 3.10.100.299889，识别出的构造函数分别位于
`0x12160a0c` 和 `0x11828d3c`。这些地址只记录审计结果，不作为运行时输入。
未知或歧义结构不注册时钟，并保留已有 UI 重载能力。

构建元数据标记 `input_monotonic_clock_protocol=1` 表示启动器包含适配；具体游戏是否
识别成功仍以当前会话 `runtime input capabilities` 中的 `clock_source` 和动作支持为准。
旧包升级后必须显式创建新实例；不要直接修改已签名运行包或旧世界绑定。

验证入口：`python3 -m unittest discover -s tests -p test_binary_rules.py`；构建和安装遵循
[运行包构建流程](mcpy-runtime-release.md)。实机输入验收使用 mcpywrap 的
`tests/manual_runtime_input_unified.py`，在专用世界验证空闲/暂停计时、Python 墙钟独立性、
移动跳跃叠加、取消释放、移动中攻击、聊天和 UI 点击。该脚本不会修改系统时间。

2026-10-17，本地运行包 `macos-arm64-0.4.5-input-clock.1` 在 Apple Silicon / macOS 26.6.2 /
3.9.100.297020 的 8 项实机用例全部通过，实际时钟源为 `launcher.steady_clock`。
跳跃高度约 1.252 格，释放 SPACE 后 W 继续移动 4.95–5.60 格；攻击确认服务端生命值
100 → 95，取消释放及聊天/设置界面切换通过，测试会话已保存退出。
证据保存在相邻 mcpywrap 仓库的 `test/macos-input-clock/final-acceptance/`。
3.10 目前仅完成结构检查，未在本次任务中完成其全套游戏操作验收。
