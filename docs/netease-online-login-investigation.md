# 中国版开发者 APK：联网与网易登录接入调研

## 后续实验状态（2026-10-04）

已增加 Dart MPay → 私有 SAuth 文件 → JNI 属性/回调的实验实现和独立测试。在线登录实验未完成，未验证真实游戏登录；当前产品路径为离线 Safaia 调试，详见 `netease-dev-debug.md`。

配置解析补充：`netease_data` 除 Base64 外，还经过 `StrUtil.validate` 的 124 字节字符替换表。原始 `JF_GAMEID=k19` 并非真实产品；还原及 MainActivity 初始化覆盖后为 **x19**，APPID 与 Dart 默认产品对应。不能使用未还原的字段发起注册。开发者 APK 的 MpayApi 自报版本为 3.4.0。

基础网络实验修复了 libc-shim 的 `F_GETFD`、Darwin/Bionic 文件标志转换和 `socketpair`。直接调用 APK 内置 curl 的独立 HTTPS 探针仍返回 `curl=35 / SSL_ERROR_SYSCALL`，指定宿主 CA 后亦如此；根因未解决。游戏正常启动路径停在服务器列表阶段，不能宣称联网登录已经就绪。下文保留最初静态调研记录。

日期：2026-10-04。对象：`dev_launcher_3.9.100.297020.apk`，包名 `com.netease.mctest`，versionCode `840297020`。本轮只做静态分析和公开资料检索，没有解除游戏网络隔离、发送登录请求、读取真实凭据或修改运行代码。

## 结论

**网络层具有可复用基础；直接运行完整 Android Mpay SDK 的成本很高，但用户提供的 `nemc_support_dart` 为替换账号登录层提供了具体可行的接口。** 推荐优先研究“Dart MPay 登录 → SAuth/JNI 桥 → 原有引擎认证与大厅”，保留当前 Cocos、Python 和游戏状态机。

已确认双方凭据字段语义对应，尚未验证这份开发者 APK 的服务器是否接受该实现生成的凭据、版本与渠道参数，以及引擎实际还会读取哪些 SDK 属性。当前结论是**存在明确接入点，值得验证**，不是已经打通在线登录。

已有 Cocos 升级弹窗证明基础场景绘制及脚本路径可用，不能据此推定全部大厅功能可用。Mpay 登录还包含 Android Activity、原生控件和 WebView，属于另一套界面与运行环境。

## 1. APK 的实际认证边界

3.9 APK smali 中的调用链：

```text
MainActivity.unisdkEnvInit → SdkMgr.init(Context)、注册 listeners / properties
MainActivity.unisdkInit → UI 线程 MainActivity$39.run → ntInit
SdkCallback.finishInit(code) → nativeFinishInit("OnFinishInit", code, "")

MainActivity.unisdkLogin → SdkMgr.getInst().ntLogin
SdkNetease.login → MpayApi.authenticateUser
Mpay AuthenticationCallback → SdkNetease$LoginCallback
  User.uid   → UIN
  User.token → SESSION
  User.devId → DEVICE_ID
  nickname / realnameSet / extAccessToken 等 → 其他属性
SdkBase.setLoginSauthInfo → WEB_UID / WEB_SESSION / LOGIN_CHANNEL / SAUTH_JSON
SdkCallback.loginDone(code) → nativeLoginDone("OnLoginDone", code, "")
MainActivity.getSauthJson → getPropStr("SAUTH_JSON")
原生引擎后续游戏认证 → 游戏账号会话 → 大厅初始化
```

这里的回调没有直接携带 token；必须同时实现凭据属性读取，而不是只调用登录成功回调。`getJFSauthJson()` 明确组装 `gameid`、`login_channel`、`app_channel`、`platform`、`sdkuid`、`udid`、`sessionid`、`sdk_version` 等字段，并合并附加属性；`getPropStr("SAUTH_JSON")` 还会处理 `step` / `step2` 等字段。

原生 ELF 中确认存在：

| 符号 | ELF 虚拟地址（仅限当前 APK） |
| --- | --- |
| `Java_com_mojang_minecraftpe_SdkCallback_nativeFinishInit` | `0x5ef69f4` |
| `Java_com_mojang_minecraftpe_SdkCallback_nativeLoginDone` | `0x5ef6b18` |

同一个 ELF 还含有 `getSauthJson`、`getPropStr`、`unisdkLogin`、`unisdkInit`、`/pe-authentication` 字符串。地址和字符串是定位依据，不等于已经恢复完整调用图；后续应按导出名绑定并验证线程、生命周期和调用顺序。

3.5 脚本辅助说明：`LoginManager.start_login()` 发送 `cpp.reenter` / `cpp.relogin`，经 `react_native.send_event_to_cpp` 进入 `_rnmodule.sendEventToCpp`。`LoginConst` 将更新、SDK 登录、`USERAUTH_CHECK`、`LOGIN_FINISH` 分开；登录完成后才初始化大厅数据。这是旧版参考，3.9 的完整顺序仍须验证。

## 2. nemc_support_dart 能替代什么

仓库：`<nemc-support-dart-repository>`，本轮只读。

`lib/src/channel/mpay/client.dart:177` 已经实现 `getSAuthJson()`，比传递一个裸 token 更接近 APK 的 JNI 接口。

| Dart 数据 | APK SDK 对应 | SAuth 字段 | 判断 |
| --- | --- | --- | --- |
| `MPayClientCreds.id` | `User.uid` → `UIN` | `sdkuid` | 语义对应 |
| `MPayClientCreds.token` | `User.token` → `SESSION` | `sessionid` | 要接入此层的 token |
| `MPayClient.remoteDeviceId` | `User.devId` → `DEVICE_ID` | `deviceid` | 应与这次登录配套，运行时还需验证一致性 |
| `getSAuthJson()` 返回的对象 | `SAUTH_JSON` | 完整 JSON | 最合适的首选边界 |
| `NEMCClientCreds.uid` | 游戏认证返回的 `entity_id` | 非 `sdkuid` | 属于游戏业务身份 |
| `NEMCClientCreds.token` / `sead` | `/pe-authentication` 后的业务会话 | 非 MPay `sessionid` | 不应填入 SDK 的 `SESSION` |

库已经具备设备注册、密码登录、短信登录、实名认证网页 URL 和 SAuth 序列化。依赖为 Dart HTTP/密码学/JSON 等包，当前代码未要求 Android Activity 或 Flutter Android 插件；因此可考虑在 macOS arm64 的 Dart 辅助进程中复用，无须将算法重写为 C++。本轮未编译该辅助进程。

### 推荐边界：替换 MPay，保留游戏认证

```text
用户完成 Dart MPay 登录
  → MPayClient.getSAuthJson() + 必要 SDK 属性
  → 本地进程间通信
  → FakeJni 的 MainActivity.getSauthJson / getPropStr 等适配
  → 在正确阶段回传真实 SDK 登录结果
  → 原有 libminecraftpe 执行游戏认证、处理响应和初始化大厅
```

这样保留 3.9 引擎原有的请求构造、状态转换、认证响应处理和大厅初始化，最大限度减少移植面。Cocos 登录入口可继续触发宿主登录流程，账号表单由宿主承担。

JNI 桥仍需明确初始化、取消、失败、退出、切换账号、重新登录的语义；不能仅发送 `OnLoginDone(0)`。会话通过受控 IPC 传递，避免放入命令行、通用日志和已提交配置；实际实现时还应处理现有 HTTP 调试日志输出请求头的问题。

### 不优先：替换到游戏认证结果层

`NEMCClient.login()` 已调用 `/pe-authentication`，但目前公开保存的是 `uid/token/sead`。`NEMCAuthResp` 还定义了 `accessToken`、`unisdkLoginJson`、`verifyStatus`、`autopatch`、`env`、最低版本等字段。这说明只把业务 token 写入引擎，未必足以建立完整登录状态。

若未来替换到这一层，还需恢复原生认证响应入口和所有状态更新，并明确谁负责刷新会话，避免 Dart 与游戏引擎分别更新同一会话。当前复用 MPay 层更容易与现有代码边界对齐。

### 复用前已发现的差异

1. Dart 的 User-Agent 固定为 `com.netease.x19/840293531`，MPay 应用信息默认 3.8；目标是 `com.netease.mctest` 3.9.100。开发者包的渠道、产品配置和服务环境要逐项核对。静态读取确认其 `ntunisdk_common_data` 的 `APP_CHANNEL` 为 `netease`，尚不能证明全部配置相同。
2. `NEMCVersionConfig.latest` 指向 `v3_8`。若只使用 MPay 层，不必先移植 Dart 的 3.9 游戏认证签名配置；若使用 `NEMCClient.login()`，就必须处理引擎/补丁/包签名版本以及服务器环境的对应关系。
3. Dart `NEMCAuthReq` 默认 `payChannel = dashen_cloudgame`；不能假定这与开发者 APK 当前渠道一致。
4. `MPayClient` 构造时重新生成本地设备信息，`getSAuthJson()` 的默认 `udid` 也会重新生成。远程设备 ID、SDK 设备标识和游戏 UDID 应分别建模，并在一次会话及重启恢复中保持所需一致性，不能简单将它们全部替换成同一字符串。
5. Dart 登录只保留 `user.id/token`；APK 回调还读取昵称、实名状态、额外 access token 等。实际哪些是当前引擎必需，应按读取调用补全，而不是捏造状态。
6. SAuth 默认值也非逐字段完全相同：如 Dart 默认 `source_platform/source_app_channel` 等于当前平台/渠道，而 APK 会从 `PRI_SP/PRI_SAC` 读取、缺失时置空；`step/step2` 的生成也不同。字段语义相同不代表可以跳过报文差异核对。
7. 密码/短信主流程已实现不等于全部账号挑战均有处理。额外验证、用户取消、重新认证等仍需真实流程支持，不能改成成功返回。

## 3. 网络可以复用哪些部分

| 层 | 已有基础 | 未解决项 |
| --- | --- | --- |
| macOS 系统网络 | 当前是启动脚本的 sandbox 明确禁止 IP 网络 | 本轮维持隔离；没有做游戏联网实测 |
| Bionic socket / DNS | `libc-shim/src/network.cpp` 已适配 socket、地址和 `getaddrinfo`；已有 poll/epoll 兼容 | `developer_compat.h` 的 `socketpair`、部分 resolver 辅助接口仍调用即终止；需按实际路径修复 |
| 引擎原生 HTTP/TLS | APK ELF 导出 `curl_easy_perform`、`SSL_connect` | APK 内置 TLS 的 CA 来源、主机名校验、超时/重试和更新下载路径尚未验证 |
| Java HttpClient 兼容 | `jni/lib_http_client.cpp` 用宿主 libcurl 发起真实请求 | 回调类是 `com/xbox/httpclient`，不能据此证明网易/Cocos 网络已经适配 |
| WebSocket | 现有实现基于 libcurl WebSocket API，受编译宏及运行库能力影响 | 未证明是网易大厅/聊天所走协议；Dart 自带 Chat/Link 是另一条可参考实现 |
| 更新流程 | Cocos 能显示更新/错误界面 | 版本列表、资源补丁、APK 安装/重启分别处理；热更可能改变已验证脚本及 JNI 行为 |

需要特别修正的既有兼容假设：

- `jni/signature.cpp`：`initVerify()` 为空，`verify()` 恒返回 true。
- `jni/cert_manager.cpp`：证书构造与 `StrictHostnameVerifier::verify()` 是占位实现。
- `jni/http_stub.cpp`：旧 HTTPRequest 返回空响应、固定 200；源码注释称为 1.13 前兼容，但中国版分支是否引用仍要确认。
- `isNetworkAvailable()` 恒返回 true，当前包名返回 `com.mojang.minecraftpe`，版本也有占位数据。

这些发现不能外推成“所有 TLS 都不校验”：宿主 libcurl 和 APK 内置 TLS 是不同实现。本轮未发现 `lib_http_client.cpp` 显式关闭 libcurl 默认 TLS 校验，但其 CA 配置与实际连接仍未测试。联网验收要确定真实调用路径，命中占位校验时补真实实现。

## 4. 如果保留完整 Android Mpay SDK

APK Manifest 声明 `MpayLoginActivity`、`MpayLoginActionBarActivity`、`MpayActivity`，以及 UniSDK deep link、扫码、第三方 SSO 等组件。`MpayApi` 构造依赖 Activity；WebView 包中包含 CookieManager、URL 拦截和 `InjectedBridgeApi.dispatch`。

静态统计 `smali*/com/netease/mpay/**/*.smali`：1,578 个文件、205 种不同 `Landroid/...;` 类引用。它包含可选及支付路径，**不是最小登录必需类数量**；但足以说明需要 Android UI、资源、线程、存储和系统服务，而非只装载一个 `.so`。

FakeJni 执行的是宿主注册的 C++ 实现，不运行 APK 的 DEX。增加普通 JVM 也不会自动提供 Android Framework。完整 SDK 路线需要可执行 Java/DEX 的运行环境及大量 Android 能力，或在 Android 伴随设备/虚拟机中运行原 SDK；后一方案的会话传递与设备绑定是否支持仍未知。

APK 已有 arm64 的 `libntunisdk.so`、`libenvsdk.so`，但这些是 Android ELF，不是 macOS 原生 SDK。前者导出 `Checker_getRandom`，不包含完整 Java 登录逻辑；仅加载它不能解决账号页面。`EnvManager` 明确有 `reviewNicknameV2` / `reviewWordsV2`，至少承担文本审核功能，不能仅凭名称将它认定为反作弊库。语音、分享、支付、推送、崩溃上报等依赖应根据实际初始化路径分类，不必为最小登录一股脑接入。

现有 `jni/webview.cpp` 只封装 Xbox XAL 的 URL/重定向流程，可复用浏览器基础设施，但不能直接当作 Mpay Android JS bridge。公开检索未获得能确认当前产品可用的 macOS arm64 Mpay SDK 或 Web 登录票据兼容性的官方接入资料；搜索引擎 AI 概览不作为证据。用户现有 Dart 实现比假设存在官方桌面 SDK 更具体。

## 5. 后续验证顺序（本轮未执行）

1. **无账号、无服务器请求的桥接验证**：记录 SDK JNI 方法需求，检查方法签名、属性读取、回调线程及取消/失败路径；用虚拟数据验证传输和序列化，不把它当作真实认证成功。
2. **基础联网单独验收**：使用本地/受控端点检查 DNS、HTTP/TLS、拒绝无效证书、异步回调和资源下载；补齐实际命中的 libc 及校验接口。
3. **核对当前 APK 契约**：固定开发者包对应的渠道、SDK 配置、版本与设备上下文；检查 SAuth 扩展字段及引擎认证所需元信息。
4. **MPay → 原生认证的小范围试验**：由用户完成真实登录，经桥接提供同一次会话的完整 SAuth，让引擎自行认证。验收以服务端真实响应及正确账号/大厅状态为准。
5. **生命周期和更新验收**：取消、失败、过期、重登、退出、保存再开、更新失败；分别观察 Cocos 大厅、资源服务和游戏连接，不以能打开登录页代替完成登录。

优先级：先完成 SAuth 边界和基础网络，再处理首次登录实际需要的设备/实名/协议界面；支付、分享、语音等延后。当前离线世界能力仍见 `netease-dev-offline.md`。

## 证据定位

APK 分析输出位于 `/tmp/apkinspect/developer-smali/`，临时目录可能被清理，因此同时记录类和方法：

- `smali/com/mojang/minecraftpe/MainActivity.smali`：`unisdkEnvInit`（4119）、`getPropStr`（10597）、`getSauthJson`（10673）、`unisdkInit`（20911）、`unisdkLogin`（20936）。
- `smali/com/mojang/minecraftpe/MainActivity$39.smali`：`run`；`SdkCallback.smali`：`finishInit`（215）、`loginDone`（247）。
- `smali/com/netease/ntunisdk/SdkNetease.smali`：`getLoginSession`（2328）、`init`（3994）、`login`（5245）；`SdkNetease$LoginCallback.smali`：用户字段写入（约 198 起）。
- `smali/com/netease/ntunisdk/base/SdkBase.smali`：`getJFSauthJson`（10008）、`getPropStr` 中 `SAUTH_JSON` 分支（16028）、`setLoginSauthInfo`（32856）。
- `smali/com/netease/mpay/MpayApi.smali`、`widget/webview/`；`smali_classes3/com/netease/environment/EnvManager.smali`。
- `/tmp/apkinspect/developer-manifest-tree.txt`：由 Android build-tools 34.0.0 的 `aapt dump xmltree` 生成。网络配置允许 cleartext，基准信任系统 CA，debug-overrides 增加用户 CA；该配置不会自动应用于 FakeJni 宿主或所有原生 TLS 路径。
- `/tmp/apkinspect/python35/gui_2d/game_state/LoginManager.py`、`LoginConst.py` 和 `minecraft/react_native.py`：仅作 3.5 参考，未部署到 3.9。
- Dart：`lib/src/channel/mpay/client.dart`、`type.dart`、`lib/src/channel/sauth_json.dart`、`lib/src/nemc/client.dart`、`types/auth_data.dart`、`version.dart`。

本轮未运行 Dart 登录或集成测试。报告判断来自源码、Manifest 与 ELF 静态分析；仅新增本文件。
