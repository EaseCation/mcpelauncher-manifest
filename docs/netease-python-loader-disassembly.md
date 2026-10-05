# 源码 Mod 加载链：MCPK 解包、Python 字节码与 AArch64 定位

后续适配和真实 Addon 验证已完成，见 [源码 Mod 接入](netease-source-mods.md)。本文保留适配前定位证据。

本轮为 2026-10-04 至 10-05 的跨日调查。样本仍是 Android 开发者 APK `3.9.100.297020`，使用原始 `vanilla.mcp` 和原始 `libminecraftpe.so`。没有修改 APK、解释器机器码或生产模块导入策略。

## 结论

**源码执行能力没有被从原生解释器中整体移除，正常 Mod 启动也确实进入了源码分支。** 自动加载失败的直接证据是两次不同的 ImportError：

1. 服务端进入 `LoadWindowsAddonPy`，把 macOS 的绝对路径截成错误模块名：`games.com.netease.behavior_packs.source_load_probe.sourceLoadProbe.modMain`。
2. 客户端进入 `LoadMoblieAddonPy`，使用正确的 `sourceLoadProbe.modMain`，但行为包目录被 `.mcs` 导入器接管，不能找到明文 `.py`。

同时，`imp.get_suffixes()` 返回 `.py` / `.pyc`；原生 `imp.load_source` 成功读取并执行独立 `.py` 探针，返回 VALUE=42。这是底层源码能力的验证，**不是**把手动加载当作 Mod 自动初始化通过。

因此，“当前默认启动链未自动加载源码 Mod”仍成立；更准确的技术解释是**导入路径与路径导入器不适配**，不是已经证明开发者 APK 完全删除了源码能力。本轮检查的路径中，没有发现一个无条件禁止源码 Mod 的总开关。

## 1. 实际解包 vanilla.mcp

已新增独立工具 `tools/unpack_netease_mcp.py`，只使用 Python 标准库，解析索引并提取原始成员，不执行其中代码。

```sh
python3 tools/unpack_netease_mcp.py \
  build-macos-arm64/netease-dev/game/assets/assets/vanilla.mcp \
  --output build-macos-arm64/python-analysis/vanilla-unpacked
```

输出目录需为空，避免覆盖先前证据。该样本：

| 项目 | 数值 |
| --- | --- |
| 文件 magic | MCPK |
| 总长度 | 22,486,772 字节 |
| 桶表起点 | 57 |
| 文件表起点 | 5,733 |
| 数据区起点 | 67,781 |
| 桶表记录 | 473，每条 12 字节 |
| 文件记录 | 3,878，每条 16 字节 |

桶记录为 hash、文件表相对偏移、记录数量；文件记录为 hash、数据区相对偏移、长度、一个尚未解释的辅助字段。工具验证全部桶范围、3878 条记录的完整且不重复覆盖，以及全部 payload 的文件边界。

文件名在索引中以 hash 表示。因此这里生成的是带索引号和 hash 的 `.bin` 原始条目及 `index.json`，**不把这些原始条目称为恢复的 Python 源码**。

已通过游戏自带 `fop.get_file_with_iid` 读取关键成员，并与静态解包结果逐字节/摘要交叉验证：

```text
mod/common/minecraftMod.mcs
  file index: 1160
  bucket hash: b3d3c366
  name hash: c73d8427
  absolute offset: 19,507,173
  encrypted length: 16,354
  decoded marshal length: 33,444
```

读取后复用当前运行时的 rotor 解密、zlib 解压和 `_reverse_data` 变换，再用当前解释器的 marshal 解码成 code object；不执行解出的模块。当前原始 marshal 使用定制布局，不能直接交给标准 CPython marshal 当成普通 pyc。

已保存 `minecraftMod.encrypted`、`minecraftMod.marshal` 和递归 code-object JSON。`redirect.mcs` 的原始条目用同一解密步骤未通过 zlib 检查，故没有把它强行解释；其 `find_module/load_module` 是从当前已经加载的 `redirect` 代码对象导出并单独还原。尚未解密或反编译全包的每个成员。

## 2. opcode 恢复方法与反汇编可信度

当前运行时报告 Python 2.7.13，但其 opcode 编号经过重映射；内置 `opcode.opmap` 仍是标准编号。因此前一轮标准 `dis.dis` 的输出和 IndexError 不能作为真实指令证据。

本轮发现两套不同编号：

| 指令 | 标准 Python 2.7 | 游戏即时 compile | MCP 打包代码 |
| --- | ---: | ---: | ---: |
| LOAD_CONST | 100 | 93 | 222 |
| LOAD_FAST | 124 | 226 | 140 |
| LOAD_GLOBAL | 116 | 150 | 136 |
| RETURN_VALUE | 83 | 59 | 81 |
| SETUP_EXCEPT | 121 | 212 | 209 |

验证方式：

- 本地从 Python 官方源码构建 CPython 2.7.18，仅作为参考编译器；配置脚本补充 arm64 识别，没有修改其编译器/opcode。它不是启动器运行依赖。
- 同一份只编译、不执行的语法样本分别交给标准编译器和游戏编译器，逐个 code object 对齐指令长度及操作数，验证了 106 个即时编译 opcode 对应关系。
- 对 MCP 的另一套编号，使用用户提供的 3.5 参考函数作为已知结构样本。42 个函数的名称表、局部变量表、常量数量、代码长度及所有操作数字节一致，得到 50 个无冲突对应关系；额外按明确局部指令序列补充 SLICE+3 / BUILD_CLASS 两项。
- 将这些映射应用于**当前 3.9 样本导出的实际 code object**，恢复标准 Python 2 pyc。`tools/restore_netease_python.py` 遇到未知 opcode、截断指令或未知常量类型会停止，不猜测填补。
- 标准 CPython 成功读回并反汇编目标函数；uncompyle6 成功反编译以下 11 个关键函数。产物为单独函数体片段，不是可直接替换进游戏的完整模块。

```text
LoadServerAddonScripts   load_mod
LoadClientAddonScripts   LoadMoblieAddonPy
LoadWindowsAddonPy       ImportModMain
ImportModAndInit         GetAllFiles
GetModModulePres         McpImporter.find_module
McpImporter.load_module
```

没有将全部未知代码标为已还原。例如模块末尾的 `GetModModulePres_furtureVersion` code object 未按本轮映射解码；本轮目标加载路径及有效跟踪未依赖它。3.5 参考用于验证 opcode 对应关系，不用于替代 3.9 的分支内容。

## 3. 还原出的源码分支

客户端的实际顺序为：

```text
GetAllFiles → 收集 modMain.py 和 .mcp
LoadAddonMcp → 没有 MCP 时返回 False
notify.add_mod_runtime_path → 加入包路径
非 Windows → LoadMoblieAddonPy → ImportModAndInit → ImportModMain
```

服务端的 `load_mod` 在 MCP 路径未加载到内容后，最终进入 `LoadWindowsAddonPy`。该函数保留 `filePathName.split('/')[10:]`，不能正确处理我们当前宿主数据目录。

加载器确实有一个提前返回条件：

```python
if modGameCfg.B_PRESET_EDITOR and not modGameCfg.EDITOR_CODE_ENABLE:
    return
```

本轮运行时 `B_PRESET_EDITOR=False`、`EDITOR_CODE_ENABLE=False`，因此这个条件不成立。`B_NO_LAUNCHER=False` 在所查服务端入口影响的是 ptvsd 调试初始化，没有在这里无条件跳过源码。

`ImportModMain` 的核心仍为 `__import__(modMainPath, fromlist=[''])`，随后发现带 `MOD_NAME` 的绑定类、构造对象并调用对应 InitClient/InitServer 方法。ImportError 会被捕获并记录，函数返回；`LoadMoblieAddonPy` 又只依据是否找到了 modMain 路径返回 True，而不检查初始化成功，解释了“行为包已挂载但系统未注册”的表现。

`McpImporter.find_module` 把名称转换成路径后，仅查询 `fullname/__init__.mcs` 和 `fullname.mcs`；没有对 `.py` 的回退。Python 路径已经被这个 importer 接管时，也不会自动再用普通源码 finder 搜一次同一目录。

## 4. 正常世界启动的实际调用跟踪

在独立实验进程中，给原有源码分支和该模块的 `__import__` 名称加记录包装；调用仍交给原函数，异常原样抛回。不调用测试 Mod 的初始化函数，不手动注册系统，不替换源码导入器。

有效记录保存于 `import-trace-valid.json` / `final-runtime-evidence.json`：

```text
windows_source_branch, InitServer
  → ImportError: No module named
    games.com.netease.behavior_packs.source_load_probe.sourceLoadProbe.modMain
  → modGoodsMain 的同类路径错误

mobile_source_branch, InitClient
  → ImportError: No module named sourceLoadProbe.modMain
```

这直接证明源文件加载分支被执行了。首轮跟踪包装函数误用了 webview 调用局部作用域，未能正常记录；已保留为 `trace-invalid-scope.log` 并排除。有效重跑显式使用独立 globals，避免该探针错误影响结论。

## 5. 原生 AArch64 证据

从 ELF 重定位和 Python 方法表定位，地址只适用于本样本：

| 入口 | ELF 虚拟地址 | 证据 |
| --- | --- | --- |
| builtin `__import__` | `0x121c47a0` | 参数解析后，在 `0x121c4814` 调用 `0x12208e90` 的导入实现 |
| imp `load_source` | `0x1220c0e0` | 保留文件获取/打开及源码加载调用；在 `0x1220c190` 调用 `0x1220aa30` |
| imp `get_suffixes` | `0x1220b7b0` | 实测返回 `.py` / `.pyc` |

函数内部被去掉了符号名，内部调用的语义通过入口方法表、参数布局和运行验证交叉判断，未将所有内部地址都冒充已恢复的原始符号。

独立原生源码探针：`imp.load_source` 直接读取自己的 `.py` 文件，stdout 输出 `[NATIVE_SOURCE_CAPABILITY] loaded a .py file`，属性 VALUE 返回 42。探针使用临时模块名，禁止写 pyc，结束后移除该模块并恢复原标志。结果在 `native-source-capability.json`；这是诊断能力测试，`automatic_mod_load=false`。

## 6. 产物与边界

产物目录：`build-macos-arm64/python-analysis/`。

- `vanilla-unpacked/index.json` 与 3,878 个 `.bin`：完整索引和原始 payload。
- `extracted/minecraftMod.json`：当前包解密得到的 code object。
- `opcode-map.json` / `packed-opcode-map.json`：两套映射，不能混用。
- `restored/*.pyc` / `*.dis.txt` / `*.py`：关键函数的标准字节码、反汇编和函数体片段。
- `native-import.dis.txt` / `native-load-source.dis.txt`：AArch64 入口反汇编。
- `import-trace-valid.json`、`native-source-capability.json`、`evidence-manifest.json`：运行证据与样本摘要。

vanilla SHA-256：`af63f2d1843b432efaaa52cdee42557f25006ce765d375b14d4e761c5bd55749`。

libminecraftpe SHA-256：`a0f5332d443f20063cc0adce5cf935597cccf6c790ea6a9a7e79ec8a067b72f3`。

后续最小适配方向是仅为指定开发源码目录提供标准 Python 源码 finder，并把服务端路径解析改为相对脚本根/复用已有移动端解析；游戏自带 MCP 导入器和原有系统注册生命周期可以继续保留。当前还没有实施这些适配，因此没有把“可诊断出修复方向”写成“源码 Mod 已自动加载成功”。

本轮结束已调用退出单人世界保存，停止调试 worker。普通停止请求超时后，确认测试世界数据库已关闭，再结束未响应的实验进程。最终检查没有遗留的 mcpelauncher-client 测试进程。后续默认在每轮验证结束清理实验窗口和 worker，只有明确要求保留的会话例外。
