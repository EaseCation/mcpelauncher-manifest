# 安卓开发包 F3 / 调试 HUD 调研

2026-10-07。mcpywrap 已快进到 `fb902e5`（0.4.1），本机 editable 安装元数据也同步到 0.4.1。本文调研的是 Minecraft 游戏内调试 HUD / 顶部菜单，不是 mcpy 的 Qt 日志小窗，也不是启动器自身的 File / Mods / View 菜单。

## 结论与验证范围

**安卓包保留了 HUD 设置、Python 接口和原生按键动作，但尚未找到能直接显示完整 Windows 顶部调试菜单的可用调用路径。** 不能把 `SetDebugImGuiShow` 的存在或选项读回成功，报告成菜单已经可用。

- 静态对比：开发者 APK 3.9.100.297020 和 3.10.100.299889 的 ARM64 `libminecraftpe.so`。
- 运行时：3.10.100.299889，macOS 原生运行包 0.4.0 / Metal，独立测试世界。未修改游戏二进制、全局构建标志或正式运行包。
- 3.5 Python 原始逻辑只作为参考；`minecraft/game_ruler.py` 已有相同的薄封装。
- 没有对对应版本的 Windows ModPC 可执行文件做并排反汇编，不能据字符串缺失断言整个菜单代码必然不存在。

## 已确认的入口

| 层 | 入口 | 证据 |
| --- | --- | --- |
| Python 封装 | `game_ruler.show_hud_info(t)` | 直接调用 `_game_ruler.ShowHudInfo(t)`；参数是 HUD 页面编号 |
| Python 原生绑定 | `MUI.SetDebugImGuiShow(bool)` | 解析 Python 对象真假，再设置同一 Options 接口；false → 0，true → 2 |
| 配置读回 | `setting.get_option('dev_debug_hud')` | 3.10 实测 0 → 2 → 1 → 0，均可读回 |
| 网易自带 QA 逻辑 | `gui_2d.ui.easy_debug_ui.actions.debug_ntes_render.debug_ntes_render` | 3.10 已加载；`DebugImguiToggle.execute` 使用 `show_hud_info`，自身常量 OFF=0 / IMGUI=2 |
| 原生动作 | `button.cycle_next_debug_overlay_page` / `button.cycle_previous_debug_overlay_page` | 动作回调最终以 +1 / -1 调用同一页切换函数；3.10 循环范围 0…18 |
| 原生 UI | `debug_screen.debug_screen` / `debug_screen_renderer` | JSON 定义、RTTI/vtable 和渲染调用链存在 |

以下地址仅用于重现本次分析，不是运行时 lookup 表：

| 内容 | 3.9 ELF VA | 3.10 ELF VA |
| --- | --- | --- |
| SetDebugImGuiShow 绑定引用 | 0x0f1e04e4 | 0x0e5697f0 |
| Python wrapper | 0x0f1e1d0c | 0x0e56b018 |
| bool 到 0/2 的实现 | 0x0f1df9b8 | 0x0e568cc4 |
| DebugScreenRenderer vtable | 0x1257e608 | 0x11bc0698 |
| renderer delegate | 0x07b9cf48 | 0x07d5a7ec |
| `$pre_release` 绑定引用 | 0x05fb1888 | 0x061373c0 |
| 只读 prerelease 字节 | 0x031d76ff = 0 | 0x032c41c0 = 0 |

3.10 的 F3 动作注册可追踪到 callback `0x0702dc00` → `0x06c8f534` → 页切换 `0x066537cc`；F4 对应 -1。说明动作代码保留，不等于安卓按键映射与桌面构建相同。启动器现有 F1–F12 映射会转换到 Android keycode，F3 没有像 F11 那样被启动器特判消费。

## 运行时实验

1. 调用 `game_ruler.show_hud_info(2)`，设置值确实变为 2；未出现顶部菜单。
2. 调用 `MUI.SetDebugImGuiShow(True)`，设置读回仍为 2；同样未出现菜单。
3. 切到页面 1，未出现预期基础 HUD。
4. 通过游戏已有 `gui.simulate_keyboard_event(114, True/False)` 提交 F3，返回 accepted；随后设置仍为 0。accepted 只表示事件被接收，不能证明动作绑定生效；本实验不等价于物理按键链路验收。
5. 屏幕栈最初只有 `hud.hud_screen`。用已有 `gui.push_screen('debug_screen.debug_screen', False)` 加入原生调试屏幕后，下一帧确实进入屏幕栈，画面出现空的 access 按钮；仍无顶部菜单。
6. 实验结束将页恢复为 0，移除本次插入的调试屏幕，正常保存退出。无遗留测试游戏窗口。

## 渲染门槛及不能过度推断的部分

`DebugScreenRenderer` 的 delegate 不是一个 `ret` 空函数，保留了实际的基础/额外信息绘制逻辑，不能据此认定包含完整 ImGui 菜单。但其中一条额外信息绘制路径读取 HUD 选项、额外信息选项和只读 prerelease 标志。该标志还能由 `$pre_release` / `Is-Prerelease` 两个语义锚点交叉核对，两个 APK 的文件值都是 0；它位于无写权限的 ELF 段。**这是已确认的构建类型门槛，不足以证明将其改为 1 就能恢复 ImGui 菜单。** 调试屏幕的基础信息和完整 ImGui 顶部菜单还需要分别追踪。

APK 含 `ImGui.material.bin`、ImGui 顶点/索引缓冲区名称、`Debug/ImGui` profiling 标签及 ImguiProfiler 类型；但两个核心中均未找到文档截图中的 `Block Debug`、`Mob Debug`、`Player Debug`、`Level Debug`、`Debug Control` 明文标签。资源和设置残留不能证明完整菜单构建进了当前安卓版本；标签缺失也不能单独证明代码被裁剪。

不建议全局修改 prerelease 标志：同一个字节在 UI、客户端及其他逻辑中有多处引用，副作用远超 HUD。当前也不应绑定一个 F3 快捷键后仅因页码改变就返回“调试菜单已打开”。

## 接入与未来自动适配方案

1. **优先游戏接口。** 客户端通道探测 `game_ruler.show_hud_info`、`MUI.SetDebugImGuiShow`、`setting.get_option`，沿用现有 `DeveloperPython` 主线程队列。确认可用后 F3/F4、小窗操作、CLI 共用一个调试 HUD 控制服务，不再开线程或另一套传输协议。
2. **区分能力层。** 分别报告 `selector`（设置接口）、`screen`（屏幕/渲染器）、`native_menu`（真正可显示且可交互的菜单）。目前证据只能肯定前两者有结构和入口，不能把第三者标记为 supported。
3. **动态枚举与结构识别。** 页编号/范围优先从当前引擎的选项或自带常量取得；不要永久写死 2 和 18。确需原生定位时复用现有 ELF resolver，以 Python 注册名、动作名、RTTI、调用形状交叉验证，不维护按版本号写地址的表。
4. **仅缺少启动挂载时**，可通过已存在的 UI 栈接口挂载已验证的页面；但应先确认该路径确有绘制实现和关闭语义，避免让一个空 modal screen 遮挡游戏输入。
5. **若只有构建门槛**，只考虑已定位的 HUD 局部分支，并验证多个版本的结构与副作用；不修改全局 prerelease。当前调研尚未完成这种局部分支的因果实验，不应进入正式包。
6. **若安卓确实裁剪了菜单**，单纯映射 F3 无法补回。再评估以现有 ModSDK / mcpy 调试接口提供必要检查能力；这将是功能实现工作，不能宣称复用了 Windows 原生菜单。
7. 自动发现到新的 APK 时，HUD 的可选检查与核心启动检查分开。未知/歧义只使 native HUD unavailable，并保留诊断；不阻止正常世界运行，不加载未经验证的地址。

后续按用户要求停止动态加载和解包尝试。下面追加静态分析的最终边界；本轮不继续恢复原生菜单。

## 只读复现工具

```sh
python3 tools/inspect_developer_debug_hud.py /path/to/libminecraftpe.so --output /tmp/debug-hud.json
```

工具复用标准库 ELF/ARM64 resolver，一次扫描语义锚点，报告 Python 绑定候选、动作引用、prerelease 字节和菜单标签。没有硬编码游戏地址，不修改 ELF，不输出可执行 patch。未知结构输出空候选；`runtime_rendering` 始终为 `not_verified`，必须另做实际画面与交互验证。

完整反汇编片段、运行时回执和截图保存在本机忽略目录 `build-macos-arm64/debug-hud-investigation/`，未分发游戏代码或资产。mcpy 0.4.1 本机回归完成 547 项测试，24 项按平台条件跳过，其余通过。

## 全局标志实验（用户授权后）

用户要求先将全局 prerelease 标志改为 1 手动观察。另建隔离实验副本，仅将 3.10 的 ELF VA/file offset `0x032c41c0` 从 0 改为 1；原始库摘要仍为 `e6d624173d5f417ab2149eb52b51c21a1a16a941b61493265b292894f60eaa69`，实验副本摘要为 `d3b2492f9ed5dd8a8b5edb7c5e0e14f60c8253eb2d3bf46504b726a04587163b`。完整逐字节比较确认只有一字节差异；副本独立重新通过结构兼容分析。

这是因果实验，不是产品修复。副本未注册为官方 APK，也未改写正式安装选择或二进制；复用既有 session worker / Python / 日志通道，使用独立 cppconfig、世界和偏好目录。路径位于忽略目录 `build-macos-arm64/debug-hud-investigation/prerelease-experiment/`；重启和补丁记录分别为同级 `start-prerelease-test.py` 与实验目录的 `patch.json`。运行结果与用户手动观察需另外记录。

### 标志为 1 的运行时结果

再次启动实验副本后，物理 macOS F3（key code 99）能够触发游戏 `OnKeyPressInGame`：键码 114，isDown=1/0，且已在 `hud_screen` 重测。按键事件到达，但 `dev_debug_hud` 仍为 0。因此不是 macOS 吞掉按键，也不能仅靠 prerelease 标志恢复安卓按键动作绑定。

直接 `show_hud_info(2)` 的读回为 2；显式插入 `debug_screen.debug_screen` 后仍仅绘制空 access 按钮，无 Windows 顶部菜单。额外试验了当前二进制中 `enable_debug_screen` 的 FeatureOption 注册 ID 28（由注册代码确认），调用 `setting.set_enable_feature_option(28, True)` 返回 True，但再次启动仍没有自动挂载 debug screen。这些编号只用于本次隔离研究，不应作为产品的固定 API。

最后清理了显式插入的空 modal 页面、关闭了旧进程并再次重启；新进程保持全局 flag=1、通过现有 API 选择 HUD 页 2，屏幕栈仅含正常 HUD。保留窗口供用户手动观察。不宣称调试菜单已经恢复，不向正式版本加入无效快捷键或额外空页面。

## 继续追踪后的收口（仅静态分析）

用户补充了 `/Users/fangyizhou/Downloads/Minecraft.Windows.exe`。文件 SHA-256 为 `9be281dbe08bc591336680d5a50f94d87f3c57ee75b3afcb3cabdf03347e0269`，与 MCDFsteve/mcdev_income 的 [Windows 功能键分析](https://github.com/MCDFsteve/mcdev_income/blob/main/docs/game-function-keys.md) 所记录的 3.10.0.420447 完全一致。

该文件是加壳的 PE32+：原文件约 120 MiB，映像约 467 MiB，14 个节；入口 `0x15c3ae058` 进入 aPLib 解压 stub，之后为 WinLicense 加壳/混淆代码。离线解出的是解包器阶段，不是完整游戏代码。因此不能直接把原始 EXE 字符串缺失与 Android 对照。没有完整还原 Windows 菜单生成函数；遵照用户要求，不再通过 Wine 加载或继续脱壳。本任务创建的 Wine bottle、导入占位 DLL、EXE 副本和临时解包器均已删除，用户提供的 EXE 未修改。

### 新增静态证据

- 对照项目针对同 SHA Windows 映像的运行时节转储，记录 F3/F4 为 `button.render_debug` / `button.render_debug_reverse`，并存在 `[F3]: next, [F4]: prev` 提示。**这是外部参考证据，不是本次重新反汇编得出的 Windows 函数地址。**
- 安卓 3.10 的所有 ARM64 `.so` 中，均未找到上述动作名/提示、`##MainMenuBar`、`Debug##Default`、`##Tooltip`、`imgui.ini` 以及 Block/Mob/Player/Level Debug 等菜单标签。APK 文件表中匹配 ImGui 的资源只有 `ImGui.material.bin`。这组合证据支持“菜单生成层未编入或未接入”的判断，仍不构成数学意义上的代码不存在证明。
- 安卓 3.10 `Debug/ImGui` 字符串引用位于渲染通道函数 `0x09333ad4`，由 thunk `0x0939c96c` 尾调用。函数在取得绘制资源后，会检查空资源、资源启用字节和就绪状态，满足条件才继续上传/绘制。`ImGui Vertex Buffer` 的上传 callback `0x093b22ec` 及索引上传代码存在。这些是**消费已有绘制数据的后端**，不是创建 Block Debug 等窗口的菜单生成器。
- `debug_screen.debug_screen` 工厂 `0x068734bc` 的调用点 `0x065242d4` 受条件分支控制。运行时强制加入该页面已验证只得到空 access 按钮，不能将它等同于 Windows 顶部菜单。
- 之前对两次实验进程的断点观察受原生 `EXC_BAD_ACCESS`（`flockfile`）打断，没有取得有效帧样本；不能把“断点没有命中”用于证明 render pass 不执行。只保留其中直接内存读取证明 prerelease 字节=1 的结果。

### 最终决定

本轮**放弃在当前 Android 3.9/3.10 上恢复 Windows 完整 F3/ImGui 顶部菜单的接入**。已找到选择器、通用动作和渲染基础设施，但没有确认可用的菜单生成/初始化实现；全局 prerelease=1 的真实实验也没有显示菜单。继续修改全局标志、强挂空 modal screen 或反复添加快捷键不能解决已知问题。

正式启动器、正式 APK 和 mcpy 产品代码均未加入这项实验补丁。实验状态不作为新版本可用性的判断依据。未来 APK 仍可使用只读检查器扫描 Windows 专属动作与菜单特征；若出现新的实现证据，再单独验证。单有 Python 接口或材料文件不能自动宣告 `native_menu` 支持。

如未来需要等价开发功能，优先复用已有的 ModSDK 查询、mcpy runtime UI/玩家观察及调试小窗；完整菜单移植属于另一项功能开发，不属于自动恢复原生 F3 的小适配。
