# Fiona 本机窗口监控（macOS）

需要 macOS 14 或更新版本，以及提供 `Testing.framework` 的 Swift / Command Line Tools 工具链。只使用系统框架，不需要安装第三方包，也不需要完整 Xcode。

## 编译与测试

在项目根目录执行：

```sh
cd watcher-mac
swift build -c release
swift test
```

可执行文件路径用 `swift build -c release --show-bin-path` 查询，例如 `"$(swift build -c release --show-bin-path)/fiona-watcher" list-windows`（不同版本的 Swift 构建系统输出目录不同，不要写死路径）。如果 `swift test` 报 `plugin for module 'TestingMacros' not found`，通常是旧的编译缓存导致，先执行 `rm -rf .build` 再重新运行即可。测试采用 Swift Testing（`import Testing`、`@Test`、`#expect` / `#require`），覆盖规范化、新增判定、调度和中英文 OCR；使用提供 `Testing.framework` 的 Command Line Tools 即可运行 `swift test`。限制沙箱中如默认编译缓存不可写，可将 `CLANG_MODULE_CACHE_PATH` 和 `SWIFTPM_MODULECACHE_OVERRIDE` 指向工作区缓存，并传入 `--cache-path .build/swiftpm-cache --disable-sandbox`。此选项仅关闭 Swift Package 自己的编译子进程沙箱，不会改变运行监控所需的系统授权。

## 授权屏幕录制

第一次执行 `list-windows` 或 `run` 前，打开 **系统设置 → 隐私与安全性 → 屏幕录制**，勾选运行它的终端或程序本身。系统可能将这个设置命名为「屏幕与系统音频录制」。修改授权后退出并重新打开终端，再运行程序。缺少授权时程序会显示中文指引并退出。

## 写入设备令牌

登录 Fiona，在设置页「本机监控」生成设备令牌并复制。明文只显示一次，每名用户最多三台有效设备。令牌可访问本用户启用规则，请只存放在自己的 Mac，不要粘贴到聊天、日志或版本库；丢失时在设置页吊销，再生成新令牌。

```sh
mkdir -p ~/.fiona
umask 077
pbpaste > ~/.fiona/watcher.token
chmod 600 ~/.fiona/watcher.token
```

程序要求令牌文件权限恰好为 `600`，否则拒绝启动。

## 运行与停止

```sh
BIN="$(swift build -c release --show-bin-path)/fiona-watcher"
"$BIN" list-windows
"$BIN" ocr example.png
"$BIN" run
"$BIN" run --server https://fiona.example --token-file ~/.fiona/watcher.token
```

服务器默认为 `http://127.0.0.1:8010`，令牌文件默认为 `~/.fiona/watcher.token`。在 Fiona 设置页创建规则后，程序每 30 秒获取启用规则，按规则间隔截取第一个匹配窗口。截图入口会通过 AppKit 初始化 `NSApplication`，进程内只执行一次，并将激活策略设为 `.prohibited`，不显示 Dock 图标，也不抢焦点。第一次截图只建立基线；其后只上报最近三次快照中未出现的行，每次最多 50 行、4000 字。画面不变时跳过 OCR。截图、识别出的整页文字及重试中的新增文字只留在进程内存中。

在终端按 **Control-C** 停止。网络错误会按 1、2、4、8、16、32、60 秒间隔重试，保留基线与待发送内容。HTTP 401 表示令牌失效，程序停止并提示重新生成。日志只包含规则 id、窗口应用名、新增行数、HTTP 状态，以及截图失败时的错误域与错误码、恢复时的一行「截图已恢复」，不包含窗口标题、OCR 文字、摘要或令牌。

`launchd/com.fiona.watcher.plist.example` 提供登录后自动启动示例。复制到 `~/Library/LaunchAgents/com.fiona.watcher.plist` 前，用自己的可执行文件位置和令牌位置替换占位符，确认终端或实际运行程序已有屏幕录制授权，然后执行：

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.fiona.watcher.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.fiona.watcher.plist
```

第二条命令用于停止并移除当前自启任务。样例不保存标准输出或错误日志。

## 数据流与局限

本机 OCR → 只上报新增行 → Fiona 服务端判断 → 提醒摘要写入聊天。关键词、数值规则在服务端本地判断；AI 规则会将新增文字发给阿里云千问或用户启用的 Anthropic BYOK。Fiona 服务端用 `FIONA_LOCAL_WATCH` 开关功能，`FIONA_DAILY_WATCH_JUDGE` 限制每日 AI 判断次数，不扣草莓。

- 只支持 macOS；窗口最小化后无法截图。
- 屏幕锁定或显示器休眠时 macOS 不允许截取窗口，期间无法监控。如果需要离开电脑时也能监控，可以在 系统设置 → 锁定屏幕 中延长自动锁定时间，但要自行权衡安全。
- OCR 可能有错字，只能看到窗口当前显示的内容。
- 根据应用名或 bundle id 及标题进行子串匹配；多个匹配窗口只取第一个，选择顺序随系统窗口清单变化。
- 截图和整页文字不会上传；系统录屏权限会允许程序读取窗口，请只监控自己有权查看的内容。
- 程序重启或规则换到其他窗口时重新建立基线；相同行连续消失三个快照后重新出现，会被视为新增。
- 心跳、截图与新增行发送独立调度；网络重试不会阻塞其他规则的截图或心跳。每批新增内容最多 50 行、4000 字，断网期间保留所有待发送批次，因此长时间断网时内存使用会增长；待发送内容仅保存在内存，进程退出后丢失。规则更新最长等待下一次心跳。
- Fiona 页面关闭时不会实时弹出，提醒照样落库；浏览器通知需要在设置页主动允许。
- `launchd` 中的屏幕录制授权、未签名可执行程序的授权行为，以及真实微信、企业微信、钉钉窗口的效果，需要在真实 Mac 上验证。

截图失败时按规则记录应用名与原始错误域/码，同一规则同一种错误每 60 秒最多一条，恢复成功后记录一次「截图已恢复」；不会记录窗口标题、识别文字或错误描述。每 30 秒的心跳附带 `capture_status`：规则 id、是否截图成功、错误域/码或 `window_not_found`、状态开始时间。后端负责中文提示，设置页逐条显示「监控中」或异常原因；状态超过 5 分钟未更新时显示「监控程序未在运行」。
