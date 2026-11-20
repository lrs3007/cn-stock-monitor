# 观澜 Android 独立版 0.3.1

## 在这台电脑上预览

双击项目中的 `预览安卓App.command`，或执行 `./scripts/preview-android.sh`。入口会打开已安装的 Android 15 ARM64 模拟器、安装当前 APK 并进入观澜；鼠标点击相当于触摸，拖动相当于滑动。它运行真正的 APK，模拟器数据与电脑网页版分别保存。

也可直接打开 `.toolchain/Guanlan Test Emulator.app`，在模拟手机的应用列表点击“观澜”。预览启动器只包装项目已安装的官方 SDK 模拟器，不修改手机 APK。0.3.1 会自动尝试备用真实行情源；两个接口均不可用时保留缓存并暂停信号。

本机已创建 `Guanlan_Test`。新环境需安装 `emulator`、`system-images;android-35;default;arm64-v8a`，再设置项目 `ANDROID_HOME`、`ANDROID_USER_HOME` 和 `ANDROID_AVD_HOME`，用 `avdmanager create avd --name Guanlan_Test --package 'system-images;android-35;default;arm64-v8a' --device pixel_5` 创建。预览脚本使用专用 ADB 端口 5038，只操作名称匹配的项目模拟器。

电脑切换 Wi-Fi 后，如果模拟器提示域名解析失败，可退出模拟器再重新打开，刷新其网络状态。本次遇到该问题后重启恢复，无需更改手机 App 的数据源设置。

## 安装与使用

1. 将 `dist/android/guanlan-0.3.1.apk` 传到手机安装。支持 **Android 8.0+、ARM64**，不支持 32 位手机。当前 NumPy / Pandas 原生依赖按 4 KB 内存页构建，16 KB 内存页机型尚不兼容；已验证 Android 15 ARM64 / 4 KB 模拟器。保持 Android System WebView / Chrome 更新。与 0.2 / 0.3.0 使用同一签名，可覆盖安装。
2. 打开即进入手机工作空间，不需要电脑、服务地址、配对码或同一 Wi-Fi。首次启动解压 Python 组件，需要稍等。
3. 默认使用免 Token 真实行情，东方财富失败时自动切换新浪；交易日历来自新浪；真实行情需要手机联网。在“数据与设置”可切换演示数据、Tushare 和计算间隔。
4. 在自选中添加股票 / ETF，为单只或多只标的配置规则；“盘中筛选”列出满足已启用规则的标的。休市只复核最近行情，不新增报警。
5. 需要离开 App 后继续监控时，打开顶部 **运行 → 开启本次后台监控**，允许通知。在同一页面可测试通知、停止监控和进入系统电池设置。

手机采集行情、计算指标和组合规则、保存 SQLite 数据、生成系统通知。电脑可以关机。断网时保留已有历史；行情不完整或延迟时暂停新的真实信号，不用演示行情代替真实行情。

## 每只标的的个性化规则

在“自选监控”的“当前标的”下拉框选择股票 / ETF，点击“配置该标的规则”。新建规则会默认只勾选该标的。设置指标、周期、阈值或直接编辑表达式，填写名称并保存为监控规则。每只标的可保存多条不同参数的规则；“全部自选”通用规则仍会共同参与判断。

例如 `RSI(14, tf="15m") < 30` 是一个 15 分钟 RSI 阈值示例。可视化条件改动后先点“生成表达式”，再保存；保存的是表达式框中的条件。进入“盘中筛选”可查看任一已启用适用规则命中的标的，休市时只复核最近数据。后台系统通知还需在顶部“运行”开启。

## 后台监控边界

应用在前台自动按设置的间隔监控。后台会话须手动开启，有常驻通知，每次最长 **5 小时 45 分**，午休不结束会话；每天开盘前开启一次可覆盖通常的交易时段。到时需重新打开应用开启。Android 15 对 dataSync 前台服务有累计时长限制，系统提前通知超时时也立即停止，并保存停止原因。

手机重启、强制停止、进程被清理后不自动恢复。系统省电 / Doze 或厂商后台限制可能推迟调度，不能保证锁屏后严格每 60 秒运行；请在系统设置允许后台运行。未授权通知仍能在站内查看已保存的报警。规则只在交易时间内首次命中或由假变真时提醒，持续满足不会重复发送。

可选 Tushare 和 SMTP 由“运行 → 行情密钥与邮件配置”填写，使用 Android Keystore AES-GCM 加密保存，密钥不返回网页。邮件为可选功能，仍需要手机引擎运行，不是外部托管推送服务。

## 从旧版迁移

0.2 的数据实际在电脑上，不在手机 APK 内。电脑“数据与设置 → 导出自选与规则”，复制内容到手机相同页面“粘贴并导入”。导入合并自选和规则，重复内容不会重复添加，保留已有数据；不导入密钥、报警记录或历史行情。旧电脑服务与数据保持原样。

两端分别保存工作空间，没有自动云同步。升级同签名 APK 保留手机数据；卸载会清除本机数据，卸载前先导出自选与规则。备份文本含个人策略，需自行妥善保存。导入文本上限 128 KiB。

## 双端共用与更新

- 界面只有 `web/` 一套，指标 / 规则 / 行情只有 `backend/` 一套。Gradle 每次构建自动复制这两套源文件到临时生成目录，禁止手工维护第二份。
- Android 内置 Python 3.12、NumPy、Pandas、FastAPI 和 TA-Lib C 0.8.3。Java 通过异步桥调用进程内 ASGI 路由；手机不监听 HTTP 端口，也不连接电脑 API。
- WebView 仅加载 APK 内已列入允许清单的静态文件，外部导航和网络资源被阻止。行情网络请求由本机 Python 发出。
- 网页功能新增后必须重新构建并安装新版 APK 才进入独立版。共用代码保证同时实现功能，不代表已安装的 APK 可以自动获取修改。参见 `CONTRIBUTING.md`。

## 构建与验证

工具：JDK 17、Gradle 8.13、AGP 8.13.2、SDK Platform 36、Build Tools 35.0.0、NDK 28.2.13676358、CMake 3.22.1、Chaquopy 17.2.0。构建 Python 为项目 `.venv312/bin/python`；Android 依赖固定在 `android/requirements.txt`。

```sh
sdkmanager 'platforms;android-36' 'build-tools;35.0.0' 'ndk;28.2.13676358' 'cmake;3.22.1'
./scripts/build-android.sh
.venv312/bin/python -m pytest -q
node --check web/app.js
```

本项目 SDK 安装在忽略目录 `.toolchain/`，构建脚本自动发现。需接受官方 SDK 协议。`android/guanlan-release.jks` 与 `android/signing.properties` 是既有个人签名，不能重新生成替换，务必私下备份。产物与 SHA-256 在 `dist/android/`。

TA-Lib 源码位于 `android/native/ta-lib`，来源官方 v0.8.3；CMake 用 NDK 编译，不使用近似替代公式。`backend/native_talib.py` 是 ctypes 绑定，元数据来自相同版本的 Python TA-Lib。自动测试覆盖所有可用 TA-Lib 函数及自定义指标与桌面结果的数值一致性。Sina 日历解码是 MIT 授权代码的 Python 移植，完整 8796 个日期与原 JS 对照。

Android 仪器测试位于 `android/app/src/androidTest`，用临时数据库验证本机全部指标、各周期、个性规则、主动筛选、持久化报警、去重、迁移和 Keystore；不写电脑数据库。可用 ARM64 模拟器执行 `connectedDebugAndroidTest`。可选的 `NetworkProbe` 会实际请求股票和 ETF 行情，并断言数据时效与日线 MACD 就绪；需联网，失败不能当作通过。实际手机的锁屏、省电策略和交易时段连续运行仍需按手机型号验收。

0.3.1 已通过 590 项 Python 测试、5 项 JavaScript 测试、4 项 Android JVM 测试、Lint 和 Android 15 ARM64 模拟器真实行情测试，并人工检查网页 / App 的图表与单只标的规则范围。构建和限制记录见 `dist/android/guanlan-0.3.1-build-report.json`。本次验证在休市时段进行，未宣称盘中延迟或实体手机后台持续运行已验收。

官方参考：[Chaquopy](https://chaquo.com/chaquopy/doc/current/android.html)、[Android 前台服务超时](https://developer.android.com/develop/background-work/services/fgs/timeout)、[后台启动限制](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start)、[TA-Lib 0.8.3](https://github.com/TA-Lib/ta-lib/releases/tag/v0.8.3)。
