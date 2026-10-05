# 开发包 JSON UI 重载

2026-10-05：已在 macOS arm64 / ANGLE Metal 上验证同一进程、同一离线世界中修改 JSON UI 定义并重新创建界面。开发包版本为 3.9.100.297020，运行包 local6 开始声明 `json_ui_reload_protocol: 1`。

## 入口与边界

产品入口为 `mcpy --local --project <项目> runtime reload ui --session <会话> --json`。CLI 和 Qt 共用部署、会话检查和结果处理；后端只提供客户端执行代码。Windows 保留现有按键路径，macOS 使用启动器提供的客户端 Python 模块：

```python
import _mcpy_launcher
accepted = _mcpy_launcher.reload_ui()
```

该模块只属于本地开发启动器，不能成为 Mod 业务代码的依赖。函数无参数，返回 bool：True 是引擎已接受请求，False 是不在游戏主线程或引擎对象不匹配。它不是解析成功、异步完成或界面已更新的回执。mcpy 返回 `triggered / effect_verified=false`；缺失模块返回 unsupported，拒绝请求返回 failed。

重载会使现有自定义控件和 Python 控件句柄失效。此 APK 实验中没有收到 `UiInitFinished`，不能依赖这个事件自动恢复 Mod UI。需要通过 Mod 自己的界面入口重新 RegisterUI/CreateUI、绑定回调，并恢复所需状态。启动器不模拟该事件、不遍历和重建业务对象。已验证现有文件中的文字、颜色和新增按钮；新增 UI 文件、复杂继承关系、所有 Mod 的界面状态恢复不在本次验收范围内。

## 为什么需要原生适配

`gui/_gui` 没有公开重载定义函数；`check_ui_def` 是检查路径。Android 包也没有 `_ui_editor`，不能使用旧版 `ui_editor.reload_ui_file`。此前真实/模拟 Ctrl+R、ForceReloadResourcePack 和 reload_user_pack 都没有更新测试定义缓存。

动态符号中没有 MinecraftGame 重载方法。由二进制保留的 RTTI 字符串 `MinecraftGame::handleReloadUIDefinitions` 回溯到处理函数；`button.reload_ui_definitions` 的输入处理代码确认其通过 MinecraftGame 虚表 0x78 调用。实际重载由原引擎执行，适配器不修改机器码、不替换 UI 解析器、不使用 host libc++ 对象调用 Android C++ ABI。

所有剥离符号的 ABI 信息只集中在 `mcpelauncher-client/src/developer_ui.cpp`，仅当磁盘 ELF SHA-256 为 `a0f5332d443f20063cc0adce5cf935597cccf6c790ea6a9a7e79ec8a067b72f3` 才启用。它仍是版本相关适配，升级 APK 必须重新验证，不能只修改版本号或指纹。文件哈希核对后，还在调用时验证游戏对象虚表和目标函数地址。

| ELF 相对地址 | 本次反汇编确认的用途 |
|---|---|
| 0x94c305c / 0x94c3768 | 原 Python GUI 包装层使用的上下文及 MinecraftGame 获取器 |
| 0x12583cd0 / 0x6364d14 | MinecraftGame 虚表及 handleReloadUIDefinitions |
| 0x123e5a28 / 0x123e5a00 | 原包装层使用的游戏主线程检查 |
| 0x1228461c | CPython 2.7 Py_InitModule4，API version 1013 |
| 0x12143f6c | PyBool_FromLong |
| 0x12288454 / 0x122884ec | PyGILState_Ensure / PyGILState_Release |

在第一次成功的现有 JNI Python 回调后获取 GIL 并注册模块；方法描述符保留到进程退出。模块安装、重载均限制在游戏主线程。没有新 socket、服务端协议、ctypes 或系统 Python 扩展依赖。标准库模块初始化（如 `_json`）和 `math.isnan` 的反汇编用于确认 CPython API；游戏始终使用自己的 CPython。

## 验收

- 实验 PID 49548、世界 `ui-reload-test`：红色旧文字 → 绿色 `AFTER A` → 蓝色 `AFTER B` → `AFTER C`，通过 JSON 文件修改、原生 reload、重新创建 UI 完成；Label.GetText 与窗口截图一致，未调用 SetText 伪装重载。
- 故意写入错误 JSON，请求仍返回 True；进程继续运行，修正后重新加载、注册 UI，可读到 `AFTER B`。不承诺无效 JSON 的自动回滚或解析诊断回执。
- 重建按钮并绑定正式 ModSDK 回调，通过 mcpy 的引擎触控实际点击；重载前后累计点击计数为 1、2，没有重复触发。
- 产品 PID 51903、世界 `83396a80237a4efdb4afd3d0b0345cae`：local6 经安装器安装，公开 `runtime reload ui` 部署文件并调用原生能力，重新创建 UI 从 `AFTER C` 读到 `PRODUCT OK`；进程与世界不变。
- mcpy 测试共 457 项，24 项跳过，其余通过；原生构建及两项 ctest 通过。所有实验均未登录，测试游戏与 worker 保存关闭。

本地证据位于 `build-macos-arm64/stability/ui-*.json`；关键文件为 ui-native-baseline、ui-native-after-a、ui-native-after-repair-register、ui-button-click-two、ui-product-baseline、ui-product-reload、ui-product-after、ui-product-status、ui-native-stop、ui-product-stop。安装目录为 `build-macos-arm64/release-json-ui/catalog.json`，未对外发布。
