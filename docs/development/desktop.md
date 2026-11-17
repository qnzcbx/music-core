# Windows 桌面版（第一阶段）

当前行为已更新：未配置时启用内置备用路线，无需逐曲目填写 ID；配置覆盖及本轮安装验收见文末“默认备用路线”。前面各阶段描述保留为历史记录。

任务 17 已迁移四来源逐行歌词与来源封面，最新实现和新安装包验收见文末“歌词和封面”。

共用 `web/src`；生产程序内嵌 `web/dist`，不启动 Python、Node 或 Vite。
开发机需要 Node.js 22.12+、pnpm、Rust stable MSVC、Visual Studio C++ 桌面开发工作负载及 Windows SDK、WebView2 Runtime。安装后的用户不需要开发工具。保留 Tauri 默认 WebView2 下载策略，不打包 FFmpeg。

## Git Bash

从仓库根目录执行：

```bash
cd web
pnpm install --frozen-lockfile
cd ../desktop
pnpm install --frozen-lockfile
pnpm dev
# 单独的终端中构建（无需启动后端）
pnpm build
pnpm check
cd src-tauri
cargo test online_search_and_range -- --ignored --nocapture
```

Tauri hooks 的 cwd 相对 `src-tauri`，使用 `../../web` 调用现有的 `pnpm dev/build`。开发地址固定为 `http://127.0.0.1:5174`；生产资源为 `../../web/dist`。

## 实现范围

- 酷我搜索、分页、稳定歌曲身份、mobi 同平台取链；选择它是因为现有实现无需 Cookie，且原生接口链路简单。
- 保留共享 HTMLAudioElement、队列、进度和恢复协调器；轻量调用在 API 层转 Tauri IPC。
- Rust 随机绑定 `127.0.0.1:0`，只提供 UUID 会话的媒体 GET/HEAD。上游地址留在 Rust；按块转发，不整首读入内存；Range 原样传递，状态和 Content-Range 按上游返回，不将 200 改成 206。
- 会话有效期 120 秒，播放器续期；切歌关闭会话并取消旧传输，周期清理过期会话，退出清理全部会话。
- 歌词、其他来源、下载、转码、本机音乐库、目录管理尚未迁移，桌面界面有提示，调用明确失败。网页模式仍使用原 HTTP API。
- 当前媒体重定向拒绝，避免跨域跳转到任意目标；某些酷我资源可能因此不可播放。

## 产物

`desktop/src-tauri/target/release/music-core-desktop.exe`

`desktop/src-tauri/target/release/bundle/nsis/` 下的 x64 安装包。

`target/`、生成 schema、前端 dist 和安装包不提交；Cargo.lock、pnpm-lock.yaml 随源码保留。

## 验证记录

2026-11-16，Windows x64：

- Web 类型检查及生产构建通过；58 项前端测试通过（原有 57 项保留，新增 IPC/媒体地址白名单测试）。
- Rust 格式检查通过，4 项离线测试通过：搜索映射、无效及释放会话、Range 校验、真实本地 HTTP 206 转发及释放后 410。
- 显式在线测试通过：酷我搜索 `test`，首曲身份 `kuwo/668816586`；mobi 取链；通过 Rust 回环代理读取 `bytes=0-1023` 和 `bytes=300000-301023`，均得到 206、Content-Range 和 1024 字节；关闭会话后 410。
- Python 现有 `test_media_stream.py`、`test_media_lifecycle.py`、`test_kuwo.py` 回归通过。
- Windows release 实际 WebView2 窗口通过：内嵌资源首页、浅色墨息、暗色设置、暗色弦外之音钢琴界面及按键交互、首页/搜索/设置跳转。中文输入值“音乐测试”正确显示；未单独验证拼音 IME 候选窗。
- WebView2 实际搜索返回 15 首，首曲 Test / Ade Busy 播放进度从 0 增长；拖动到约 32 秒后继续增长至 57 秒；切换 test / 文宗圣地后进度从 0 增长到 5 秒以上；关闭窗口后进程退出。
- 测试期间 8001 和 5174 均无监听，播放不依赖 FastAPI/Vite。快速连续切歌的极端并发、网络断连后恢复、无 Node/Python 的干净机器安装尚未人工验收；已有恢复协调器回归仍通过。

产物实测（字节数为本次构建目录快照）：

| 项目 | 结果 |
| --- | --- |
| target 总文件大小（debug + release） | 3,540,540,199 字节，约 3.30 GiB |
| release EXE | 12,864,512 字节，约 12.27 MiB |
| NSIS 安装包 | Windows x64 大小为 3.17MiB |
| 本机安装 / 干净机器安装 | 成功 |

`pnpm --dir desktop exec tauri build --no-bundle` 已完成 release 构建。
`pnpm --dir desktop exec tauri build --bundles nsis` 已完成 Windows x64 打包。
生成的 `拾音_0.1.0_x64-setup.exe` 大小为 3.17 MiB。

本机安装后，从已安装的拾音启动，酷我搜索与在线播放验证通过。
上面安装结果为用户补充的第一阶段验收：本机安装 / 干净机器安装成功，安装后酷我搜索与在线播放通过；与前面的独立 EXE 验收分别记录。

安装验收应在关闭 FastAPI 和 Vite 后执行：搜索 → 播放 → 拖到中间 → 确认时间继续增长 → 快速切歌 → 退出；检查浅色/暗色、墨息/字里弦间、中文 IME 和页面跳转。另需在没有 Node/Python 的干净 Windows 上安装验证。

## 第二阶段：四来源（2026-11-16）

第一阶段代码落点：`66e056f`。本阶段保留前面的证据，在 `feat/rust-desktop` 继续实现，没有提交、推送或发布。
接入顺序为网易云 → QQ → 咪咕。仅迁移 Python 现有的原生匿名接口；不引入外部解析、不保存 Cookie，不尝试登录、付费、地区或媒体加密绕过。

| 来源 | 搜索 | 播放 | 跳进度 | 验证条件 / 样本 |
| --- | --- | --- | --- | --- |
| 酷我 | 通过 | 通过 | 通过 | 实际 release WebView2，关键词“晴天”，ID 228908；保留第一阶段样本证据 |
| 网易云 | 通过 | 通过 | 通过 | 原生 cloudsearch/player，匿名；WebView2 ID 2668397359 |
| QQ音乐 | 通过 | 通过（部分曲目） | 通过 | 官方搜索 / GetVkey，匿名；WebView2 ID 003oexNv1WCRL0；另有样本返回空 purl，明确失败 |
| 咪咕 | 通过 | 通过（部分曲目） | 通过 | 原生搜索、详情、listen-url；WebView2 ID 600919000007741344；仅试听 / 加密格式明确拒绝 |

“通过”仅指上面的真实样本，不代表平台全部曲目可播。不同 pageSize 的官方搜索排序可能不同，验收脚本从界面实际返回曲目中挑选匿名可播放样本。

实现：`provider.rs` 统一目录与分发，`providers/` 分来源适配；原酷我逻辑移入 `providers/kuwo.rs`。`common.rs` 仅共享输入、分页、字段映射、有界响应读取、错误信息及媒体域名校验。各来源媒体地址和专用请求头保存在 Rust 会话中，共用原有回环 HTTP、续期、释放和取消。歌曲身份始终保留 providerId + platformId。网页 HTTP API 及 Python 来源行为不变。

仍未迁移：歌词、下载、转码、本机音乐库、目录管理。未调整主题、首页组件、播放器布局；只更新桌面限制提示。

### 验证方式

- Web 类型检查、生产构建通过；59 项前端回归通过，新增同数字 ID 的跨来源快速切歌及迟到 Lease 释放测试。
- Rust 8 项离线测试通过，覆盖三来源映射、分页游标、权限/试听/身份拒绝、咪咕双 ID、无效/释放会话、206 转发、429 错误提示和上游 200 不伪造 206。2 项真实网络测试默认忽略，显式执行的新增来源探测结果单独列出。格式检查通过。
- `cargo test online_sources -- --ignored --nocapture` 是真实网络探测，输出每个来源的成功或失败，不因测试进程退出成功就认定来源全部可用。关键词“晴天”：网易云 3 个样本、QQ 2 个样本、咪咕 2 个样本的起始和中段请求收到 206 + Content-Range；QQ 空媒体和咪咕仅试听样本按限制拒绝。记录不包含上游媒体 URL 或请求头。
- Python `test_netease.py`、`test_qq.py`、`test_migu.py`、`test_media_stream.py` 回归通过。
- `verify_infinite_search.py --controlled` 在无 FastAPI 的 preview 下通过，40 次夹具请求：四来源归属、分页重叠去重、单来源 503 后其他来源继续、独立重试、快速换关键词 / 勾选时丢弃旧结果、滚动定位。一次短分页时序断言失败，重跑通过，保留诊断信息；不把夹具结果计入真实平台播放。
- `desktop/verify_webview.py` 通过临时本地 CDP 端口连接实际 release 的 WebView2，不启动 Chromium 替身。四来源全部勾选后真实搜索；酷我 → 网易云 → QQ → 咪咕 → 酷我，逐次拖动到约一半并检查时间继续增长；前一会话 HEAD 返回 410。随后快速连续跨来源切歌。整个验收保留一个 HTMLAudioElement。
- 运行 WebView2 音频验收前已关闭 preview；8001、5174、5181 无监听。CDP 环境参数仅用于测试启动，不写入配置或安装包。

复现实际 WebView2 自动检查（Windows PowerShell；测试开发机需要现有 server 开发依赖中的 Playwright，用户播放不需要 Python）：

```powershell
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS='--remote-debugging-port=9223'
Start-Process desktop/src-tauri/target/release/music-core-desktop.exe
Remove-Item Env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
server/.venv/Scripts/python.exe desktop/verify_webview.py
```

关闭所有旧实例后启动；CDP 结果与截图放入忽略的 `.runtime/desktop-stage2/`，不含临时媒体 URL。普通启动不设置 CDP 参数。

### 第二阶段安装包与安装后验收

- `pnpm --dir desktop exec tauri build --bundles nsis` 成功。本次 `拾音_0.1.0_x64-setup.exe` 为 **3,376,362 字节（3.22 MiB）**；release EXE 为 **13,024,256 字节（12.42 MiB）**。沿用 0.1.0 阶段版本号，前面的 3.17 MiB 是第一阶段产物。
- 本机安装器退出码 0；从安装目录实际运行更新后的拾音，通过同一 WebView2 验收脚本的四来源播放 / 中间跳转 / 旧会话 410 / 跨来源切回 / 快速切歌；额外确认最后选中咪咕 `600919000007741344`，按钮为暂停且音频时间继续增长。结果、截图在 `.runtime/desktop-stage2-installed/`。
- 本阶段没有再次在无 Node/Python 的干净机器上安装；用户报告的第一阶段干净机器安装成功保留在前文。安装后的程序无需 Python；Python/Playwright 只负责开发验收脚本。
- 本阶段实际验证的是当前网络和匿名可访问样本。QQ 空 purl、咪咕仅试听、加密媒体以及来源限流/权限拒绝均不会改走其他解析服务；这些条件仍可能使特定曲目不可播放。上游重定向仍拒绝，不保证所有平台 CDN 地址都可用。歌词、下载等功能保持未迁移。

## 第三阶段：可配置的同平台备用解析

基线 `13dc7d9`，保留前两阶段记录。本轮未修改 Python 后端行为、歌词、下载或本机音乐库；展示顺序统一为酷我 → QQ 音乐 → 网易云 → 咪咕。

### 先核对的网页版路线

以 `server/app/main.py` 实际创建来源的参数为准，而非类构造器的默认值：QQ 应用默认 `official,vkeys,tang,xunhuisi`，并开启 request-bound；网易云应用默认 `native,gdstudio-preview,jfjt`。类本身默认仅原生。Python 只对来源失败、超时、无媒体继续，权限、身份、格式错误停止。酷我仅有站内 www/mobi，咪咕为站内详情/listen-url，没有可迁移的第三方路线。

| 路线 | 现有协议及触发条件 | Rust 状态 / 差异 |
| --- | --- | --- |
| QQ vkeys | GET mid，默认 quality=14；响应 data 的 MID 可缺失，Python 应用允许请求绑定 | 已接入，默认关闭；桌面必须有匹配 MID，URL-only 拒绝；真实固定样本因缺 MID 拒绝 |
| QQ Tang | GET mid；校验 song_mid，原曲播放字段优先，不选伴奏字段 | 已接入；本轮真实原版《发如雪》通过 |
| QQ 巡回寺 | GET mid/type=json；Python 允许请求绑定，详情链接仅为回显证据 | 已接入；桌面要求独立 MID，只有 link 不能过关；协议夹具通过，未独立在线验收 |
| 网易云 GD | GET types=url/id/source=netease/br；Python ID 可缺失；特定 cf-mitigated 挑战允许后续路线，不解挑战 | 已接入；要求响应 ID 匹配；403 保守停止，不作挑战处理；协议夹具通过，未独立在线验收 |
| 网易云 jfjt | POST url=原平台ID/level=standard/type=json；Python 还查官方详情核对标题歌手 | 已接入；桌面更保守地要求响应本身带匹配 ID，拒绝 URL-only、试听及明显版本替换；协议夹具通过，未独立在线验收 |

“接口存在”不等于任何曲目都有服务使用资格。配置仅限定已有服务及精确曲目，不接受任意服务地址、跨平台替代、关键词匹配或通配符。

### 配置和边界

进程环境变量 `MUSIC_CORE_DESKTOP_FALLBACKS` 为 JSON。默认不设置，保持第二阶段仅原生行为。`routes` 数组决定备用顺序；每项 `provider`、`route` 和精确 `tracks` 指定已确认允许该服务处理的曲目范围。原生永远先执行；不可通过配置前置第三方。配置错误在启动时明确报错，不悄悄启用其他路线。

本轮用户指定样本的有限复现（PowerShell，从仓库根目录启动）：

```powershell
$env:MUSIC_CORE_DESKTOP_FALLBACKS='{"routes":[{"provider":"qq","route":"tang","tracks":["0027oMO61wWi55","0037WF7I0yUPLu"]}]}'
Start-Process desktop/src-tauri/target/release/music-core-desktop.exe
Remove-Item Env:MUSIC_CORE_DESKTOP_FALLBACKS
```

它不会永久修改安装版设置，也不是为所有周杰伦曲目授权或保证可播。仅应为已核实服务使用条件和曲目适用范围的 ID 增加配置；不把会员、登录、地域或 DRM 限制当作可兜底条件。空地址本身不推断为会员限制，也不证明获得使用资格。

- 只在原生明确返回空媒体时进入已配置备用；原生网络错误、有地址但坏媒体、回环会话/转发/播放器错误不会改走第三方，避免掩盖桌面回归。
- 备用响应必须回传匹配原平台 MID/ID；缺失、错配、明显伴奏/翻唱/Live/现场版本或明确权限/试听/加密标志均拒绝。与网页版宽松的 request-bound 行为有意不同。
- 每条备用路线最多 7 秒、一次请求链，无自动重试；整个解析最多 28 秒。原生成功完全不调用备用服务。每次实际备用调用创建无 Cookie、无认证、无来源默认头的独立客户端。
- 仅接受原平台已允许的 CDN 域名；不自动追随重定向。发布会话前有界读取最多 4096 字节，确认音频特征；整首媒体仍通过原 Rust 回环会话按块传输，Range 不伪造。
- Open 响应只额外提供 `resolver` 路线名，不提供私有上游地址或头。配置中不存放凭据，验收输出不记录媒体 URL。

### 同一组真实样本前后对照

关键词“发如雪 周杰伦”固定 QQ ID，不以 Live、合唱版或同名曲替代原版：

| QQ platformId / 版本 | 原生（接入前） | Python 应用现有配置 | Rust 配置后 |
| --- | --- | --- | --- |
| 0027oMO61wWi55 / 周杰伦《发如雪》，《十一月的萧邦》，299 秒 | 空 purl，无匿名播放地址；尚未进入媒体传输 | Tang，confirmed，媒体前缀验证通过 | Tang，同 MID；起始和中段均 206 + Content-Range |
| 0037WF7I0yUPLu / 周杰伦、李安 Live，229 秒 | 原生有媒体，206 | official | native，配置了 Tang 仍原生优先；起始及中段均 206 |
| 0039MnYb0qxYhV / 第二阶段保留的不可用对照身份 | 空 purl | vkeys，request_bound，媒体前缀通过 | vkeys 缺少响应 MID，明确拒绝，不冒充同版本成功 |

第一项失败属于“匿名接口没有给地址”，不是“Rust 有地址但代理或播放器损坏”。第三项是桌面身份保证的保留限制，不能据此宣称该曲付费或服务整体不可用。明确权限拒绝、DRM 和试听停止由可控测试覆盖，本轮未使用受限制账号或试图获取受限媒体。

### 验证

- Rust 11 项离线测试通过，3 项在线探测默认忽略；新增原生成功/权限/网络错误不调备用、超时 7 秒内收尾、独立授权范围、错 MID、缺身份、版本替换、权限/试听拒绝以及五路线协议响应夹具。
- 显式执行 `cargo test online_fixed_samples -- --ignored --nocapture`：同一组三 ID 得到上表结果，成功的两项通过共用 Rust 会话读取 `bytes=0-1023` 和 `bytes=300000-301023`，206 / Content-Range / 1024 字节均核实。
- Web 类型检查、生产构建及 60 项回归通过（保留原有 59 项，新增 QQ 备用解析晚到后切回原生仍保持正确曲目并释放迟到 Lease）。Python 相关 QQ/网易云路线回归 102 项通过。
- 本轮新增 `desktop/verify_fallback.py`，连接真实 release WebView2 的临时 CDP 端口；只记录歌曲身份、最终路线和 seek 结果，截图和结果保存到忽略的 `.runtime/desktop-stage3/`。

要执行桌面脚本，按第二阶段方法为测试进程临时设置 CDP 端口，同时设置上面的有限备用配置，启动 release 后运行 `server/.venv/Scripts/python.exe desktop/verify_fallback.py`。普通用户播放无需 Python 或 Vite。

最终 Windows release 实测通过：8001、5174、5181 无监听；同 ID 预检确认 Tang / native 路线后，通过原界面的试听按钮播放原版《发如雪》，拖到约一半并观察时间继续增长；再切回原生 Live 对照曲，同样跳转后继续播放，旧会话 HEAD 为 410。只有一个 HTMLAudioElement。Tauri 的 invoke 属性不可写，脚本不再尝试改写内部调用，而是先用独立短期会话核实该 ID 的解析路线并立即释放，再执行 UI 播放；结果字段明确称为 `preflightResolver`，不声称拦截到了 UI 的 IPC 响应。

本轮交付更新的独立 release EXE；没有重打 NSIS 或更新已安装应用。前文的安装包与安装后验收仍属于第二阶段。备用配置默认关闭，未独立在线验收的巡回寺、GD、jfjt 不标记为覆盖率提升；本轮只对 Tang 的固定《发如雪》原版样本验实改善。

## 默认备用路线（任务 16，2026-11-16）

继续保留第三阶段未提交实现。本节替代前文“默认关闭、全局逐曲目白名单”的当前行为；历史验收证据不覆盖。

`fallback.rs` 的 `DEFAULT_ROUTES` 集中维护默认备用顺序和有效路线名称：QQ 为原生 official → vkeys → tang → xunhuisi，网易云为原生 native → gdstudio-preview → jfjt。原生由统一协调器先执行，配置不能把第三方放到原生之前。酷我、咪咕不变。Python 和网页行为不变。

### 普通启动及配置覆盖

**普通启动不需要设置任何备用环境变量或歌曲 ID。** 未设置 `MUSIC_CORE_DESKTOP_FALLBACKS` 就使用上述内置顺序；配置中省略某路线的 `tracks` 表示该路线不作额外逐曲目范围限制。若服务确有曲目范围，只给该路线设置 `tracks`；空数组表示该路线不适用于任何曲目。

显式 JSON 是整体替换，不与内置路线合并。例如仅启用 Tang、无需歌曲 ID：

```json
{"routes":[{"provider":"qq","route":"tang"}]}
```

完全关闭备用并恢复纯原生：

```powershell
$env:MUSIC_CORE_DESKTOP_FALLBACKS='{"routes":[]}'
Start-Process desktop/src-tauri/target/release/music-core-desktop.exe
Remove-Item Env:MUSIC_CORE_DESKTOP_FALLBACKS
```

配置在启动时读取，需要关闭旧实例再启动；无需修改系统永久环境变量。普通启动不执行这段关闭示例。

### 无效路线结果与明确限制

缺少响应 MID、错 ID、版本替换、坏媒体、协议格式异常均拒绝当前结果，不把它绑定成会话；随后允许按顺序尝试下一条备用。明确权限、试听、加密限制依旧停止，HTTP 401/403 仍按现有保守规则处理。原生成功不创建备用请求；原生网络/会话/传输/解码问题不以备用掩盖。7 秒单路线 / 28 秒总时限、无凭据隔离、原平台 CDN 限制、有界媒体检查和共享会话保持不变。

新增回归明确验证 vkeys 缺身份后 Tang 能接续，而权限/试听拒绝不会继续；原生成功不调用任何备用、错误配置和可选单路线曲目范围均有覆盖。所有旧身份及媒体拒绝测试保留。

### 同组样本实测（无备用配置与显式关闭）

| 来源 / platformId | 改前普通启动 | 本轮无备用配置 | 显式 routes=[] |
| --- | --- | --- | --- |
| QQ 0027oMO61wWi55，原版《发如雪》 | 原生空 purl；上一轮需手动配置 Tang | Tang，起始和中段均 206 / Content-Range | 原生空媒体错误 |
| QQ 0037WF7I0yUPLu，Live 对照 | 原生可播 | native，起始和中段均 206 | native |
| QQ 0039MnYb0qxYhV | 原生空媒体；上轮 vkeys 缺 MID 被拒绝 | Tang，起始和中段均 206 | 原生空媒体错误 |
| 网易云 2668397359 | 原生可播 | native，起始和中段均 206 | native |
| 网易云 186016 | 原生未返回成功媒体结果 | 同样失败，未标记改善 | 同样失败 |

`online_fixed_samples` 分别在移除环境变量与显式 `routes=[]` 的新进程执行，输出 `fallback_config_present=false/true`。每个成功样本验证 0–1023 和 300000–301023 两段请求、Content-Range 及 1024 字节响应；输出不包含上游媒体地址或敏感头。

独立 Windows release 普通启动通过实际 WebView2 验收：不设置备用配置，原版《发如雪》同 MID 预检命中 Tang，随后界面播放、拖到中间继续播放；切回 Live 对照曲命中 native，旧会话为 410。另用显式 `routes=[]` 重启 release，原版恢复原生空媒体错误。证据分别在 `.runtime/desktop-stage4-default/` 和 `.runtime/desktop-stage4-disabled/`。验收脚本只使用临时 CDP 参数，不将它写入安装配置。

检查通过：Rust 格式检查及 13 项离线测试（3 项在线探测默认忽略）、Web 类型检查和生产构建、60 项前端回归。本轮未修改 Python，保留前轮 102 项路线回归证据。仍只有 Tang 获得新增第三方真实播放与进度证据；vkeys 当前样本缺身份不能作为可播放成功，巡回寺、GD、jfjt 的第三方成功仍只有协议夹具证据。网易云原生可播不代表 GD/jfjt 在线通过。

### 本轮新包及安装后的默认播放

`pnpm --dir desktop exec tauri build --bundles nsis` 成功生成本轮 Windows x64 新包：`desktop/src-tauri/target/release/bundle/nsis/拾音_0.1.0_x64-setup.exe`，**3,395,032 字节（3.24 MiB）**；release EXE **13,095,424 字节**。仍沿用 0.1.0 阶段版本，不能仅凭文件名区分旧包，以本节大小及本轮构建结果为准。

本轮安装器退出码 0，已更新原有本机安装目录。确认正在运行的是安装目录中的 EXE，非工作区 EXE。清除进程的 `MUSIC_CORE_DESKTOP_FALLBACKS` 后启动新安装程序（仅验收时添加临时 CDP 参数），通过实际 WebView2：

- 原版《发如雪》QQ `0027oMO61wWi55`，同身份预检为 Tang；界面播放、拖到中间后时间继续增长。
- 切回 QQ `0037WF7I0yUPLu` Live 对照，预检为 native；播放与跳进度继续，旧会话 HEAD 返回 410。
- 只有一个共享 HTMLAudioElement，8001、5174、5181 无监听，未启动 FastAPI 或 Vite。结果和截图在 `.runtime/desktop-stage4-installed/`。

这是本轮新安装包上的验收，与前两阶段旧包记录分别保留；本轮没有再次验证无 Node/Python 的干净机器安装。普通安装启动不需要备用配置、逐曲目 ID 或测试端口，验收 Python/Playwright 不属于用户运行依赖。

## 歌词和封面（任务 17，2026-11-16）

### QQ 封面丢失的实际层级

QQ 原版《发如雪》`0027oMO61wWi55` 的搜索响应带专辑 MID `0024bjiL2aocxT`；Live `0037WF7I0yUPLu` 为 `0025lZrx23oozS`。Python 按专辑 MID 构造官方封面，Rust 原先在 `qq::candidate` 固定传 `Value::Null`，因此封面在数据映射层就丢失，前端没有图片请求。这是首要原因，不能归咎于 CSP。

已恢复 Python 相同的 QQ 专辑规则；封面来自原来源搜索，不使用备用媒体服务或同名曲。原版和 Live 两张官方图均 HTTP 200、JPEG，分别为 46,582 / 56,754 字节；上游没有 Access-Control-Allow-Origin。普通非匿名 img 显示和 Canvas 匿名像素读取分别检查，不把 src 非空算加载成功。

四来源搜索封面统一在 Rust 注册为不透明令牌，复用现有动态端口的回环服务 `/covers/{token}`。QQ 按专辑 MID 生成请求；其他来源先保留真实封面字段，再按来源域名和路径校验。前端没有任意 URL 下载命令。相同图片共享令牌和一次并发读取的缓存，最多 128 条、1 小时；单图最多 2 MiB、等待最多 8 秒，拒绝跳转。失败或令牌过期使用原占位图，历史队列过期封面需重新搜索取得新令牌。

实际响应差异：网易云搜索可能返回 HTTP 图片，升级为同一已确认 CDN 的 HTTPS；咪咕除 `/data/oss/resource/` 外，还返回 `/data/resource-service/file-down/` 的无扩展名图片，MIME 为 application/octet-stream、实际头为 JPEG。仅该已确认咪咕路径允许通用 MIME，所有图片仍检查 JPEG / PNG / WebP 文件头。回环图片带 CORS 头以供 Canvas 读取，未放宽 Tauri CSP。列表、底栏、播放页使用同一 cover 字段与现有 CoverArt；图片元素按 src 换 key，防止旧元素事件影响新封面。

### 歌词数据与交互

`lyrics.rs` 按原 providerId + platformId 请求 Python 已有四来源原生歌词端点：QQ Base64 LRC/trans、网易云 lrc/tlyric、酷我 lrclist、咪咕精确 contentId 详情中的 lrcUrl（仅允许官方固定歌词 CDN）。备用解析不改变取词身份。输入、响应体和行数有上限，取词最多 12 秒；歌词错误与音频会话独立。

复用 LyricDocument / LyricLine：synced、plain、instrumental、unavailable 和请求错误分别保留；支持 LRC 多时间戳、offset、重复时间合并、下一行结束时间、20 ms 内唯一翻译对齐及未对齐翻译原文。保持现有逐行内容和前端高亮、滚动；本轮真实样本只取得逐行 LRC，未取得或宣称逐字时间戳，不按字符虚构时间。

统一 API 层将桌面的歌词查询转成 IPC，网页继续 HTTP。已有 createLyricsLoader 按来源+ID 换代、AbortSignal 标记及代次丢弃迟到响应；IPC 上游请求可能继续到 12 秒截止，但旧结果不能写回。播放实际时间、暂停/恢复及 seek 沿用共享 HTMLAudioElement。

### 真实来源样本

| 来源 / 精确样本 | 歌词实测 | 封面显示 / Canvas 像素 |
| --- | --- | --- |
| QQ 原版《发如雪》0027oMO61wWi55 | synced，69 行 | 列表、底栏、播放页均通过；Canvas 及主题色成功 |
| QQ Live 0037WF7I0yUPLu | synced，51 行，未套用原版歌词 | 独立专辑封面显示、像素读取通过 |
| 酷我《晴天》228908 | 成功时 63 行；多次请求也出现上游无 lrclist 的错误，界面可重试 | 显示、像素读取通过 |
| 网易云《晴天》2668397359 | synced，63 行 | HTTPS 官方图片显示、像素读取通过 |
| 咪咕《晴天》600919000007741344 | synced，28 行 | 识别官方无扩展名 JPEG 后，显示、像素读取通过 |
| 酷我 Test / Ade Busy 668816586（缺封面对照） | 本轮取词失败，没有冒充无词 | 搜索封面字段缺失，沿用占位；未用同名图补齐 |

无词、纯文本、纯音乐和请求失败的区分另有离线协议/状态回归，未把这些夹具记为真实平台成功。酷我一次失败或一次成功均不外推整个平台。

### 验证与本轮安装包

- Web 类型检查、生产构建及 61 项回归通过；包含桌面歌词 IPC 身份映射、同数字 ID 跨来源迟到歌词隔离，以及既有歌词时间线、错误、取消、旧主题色不覆盖和空封面回退测试。
- Rust 16 项离线回归通过，原有 13 项保留；新增 LRC/翻译/状态、图片白名单/格式/去重及并发缓存 HTTP 测试。4 项在线探测默认忽略，独立执行的结果单列，不将探测函数退出成功当作每个平台可用。
- Python 原有 `test_lyrics.py` / `test_covers.py` 共 52 项回归通过，后端代码未修改。
- 真实 release WebView2：QQ 原版列表/底栏/播放页的 img.complete、naturalWidth>0 均断言通过；播放页 data-palette-status=success，Canvas getImageData 可读。拖到约 55% 再回拖到约 20%，当前歌词时间与实际音频时间匹配，音频持续播放。截图与结果在 `.runtime/desktop-stage5-final/`。
- 受控 WebView2：中断图片请求后原占位图可见；注入 Canvas SecurityError 后封面仍 naturalWidth>0，主题色 evidence=fallback，失败诊断 canvas-cors-denied。证据在 `.runtime/desktop-stage5-image-failure/` 和 `.runtime/desktop-stage5-pixel-failure/`，仅测试注入，非真实上游成功。
- 新增 `desktop/verify_metadata.py`，连接实际 WebView2 临时 CDP 端口；`--pixel-failure` / `--image-failure` 用于上述受控失败。输出仅保存身份、状态和断言结果，不记录凭据或临时媒体地址。`verify_webview.py --check-metadata` 可追加快速跨来源切歌后的歌词、封面和配色一致性检查。

本轮重打 NSIS `拾音_0.1.0_x64-setup.exe`，**3,792,332 字节（3.62 MiB）**，release EXE **14,848,000 字节**。安装器退出码 0，已更新本机安装目录。本轮新安装程序再次通过同一 QQ 原版列表/底栏/播放页封面、Canvas、歌词向前/向后跳转检查；四来源真实元数据结果见 `.runtime/desktop-stage5-installed/`。验证时没有 FastAPI/Vite，Python 仅为开发验收工具；未重新验证干净机器安装。版本号仍为 0.1.0，前文安装包大小属于历史阶段。

安装版还通过 `verify_webview.py --check-metadata`：四来源实际播放与 seek、旧会话 410、快速跨来源切歌后，最终咪咕曲目的歌词行数与原身份取词结果一致，播放页封面及配色 key 均匹配当前曲目图片。结果/截图在 `.runtime/desktop-stage5-rapid/`；可控迟到响应由上述单元回归验证，没有把它伪称为真实上游延迟。

## 第六阶段：原格式下载、命名规则与中断续验（任务 18，2026-11-16）

### 中断边界与证据

本节保留第五阶段及更早记录。开始续验时分支为 `feat/rust-desktop`，保留当前工作树，没有提交、推送、合并或发布。

上一轮 `.runtime/desktop-download-validation/result.json` 已记录真实安装版任务 completed：酷我 `151826227`《贝多芬：致爱丽丝》/ Various Artists，standard，MP3、128000 bps、44100 Hz，3,769,364 字节。它只证明当时下载和整文件校验完成。`sample.mp3` 是验收操作手填的名称；当时应用代码只建议“歌名.mp3”，未接入命名偏好。不能用该样本推断命名规则已经正确。

中断前 Windows 媒体播放器已出现“打开”文件对话框，但没有成品实际播放的确认，不计为通过。已有 `playback/result.json`、`regression/results.json` 可支持上一轮安装版播放/歌词/封面检查；未完成的步骤没有补写为通过。本次重新执行安装版切歌回归并单列结果。

### 实现与能力边界

- 复用 Vue 现有选曲下载、品质对话框、任务列表和统一 API 层；桌面轻量请求走 Tauri IPC，网页继续 HTTP。安装后下载不依赖 FastAPI、Vite 或 FFmpeg。
- `downloads.rs` 仅开放酷我独立下载权限明确允许的录音：收费、试听、加密、禁止下载字段均明确无该限制，并且有录音时长。每次准备和任务取链按原 providerId + platformId 重新检查同 ID 当前元数据、独立下载接口返回的 rid、媒体主机白名单；不调用播放或备用播放解析，不切换来源/版本/品质。
- 当前只验证 standard 原格式 CBR MP3 128 kbps。QQ、网易云、咪咕下载，以及 auto/high/lossless、转码均未开放。受限曲目和未支持来源禁用下载入口；品质不可用时禁用确认，不用试听成功推断下载权限。
- Rust 弹 Windows 原生保存对话框。取消返回空结果，不创建任务、不写临时文件；IPC 不接受任意媒体 URL 或写入路径。用户可在原生对话框手动改名，正式路径只能来自该对话框，扩展名必须为实际 MP3。
- 流式写同目录随机 create_new 临时文件；限制响应状态、范围、编码、大小，按可信 Content-Length 显示百分比，无总长则仅显示已下载量。收完后扫描整文件 MPEG 帧，核对标准品质、完整帧边界、采样率和录音时长，保持原字节，不转码或改写。校验通过后硬链接无覆盖发布，再清理本任务临时文件。
- 准备、下载、校验、完成、失败、取消分别显示；完成后只凭任务 ID 打开其内部关联路径。取消/失败清理仅本任务拥有的临时文件；重试使用同身份、同品质重新解析并重新选择保存位置。退出时取消活跃任务并等待清理。任务仅在本次进程保留，没有下载历史、默认目录、音乐库或迁移。

### 复用网页版命名设置

复用原 `DownloadSettings.vue` 的“设置 → 下载 → 新下载文件命名”入口、三种枚举及默认值 `artist_title`。桌面实现同一个 `/api/downloads/settings` 契约；只将命名偏好保存在应用配置目录，任务、媒体地址及用户保存目录不持久化。网页设置及其服务端命名、同名编号行为不变，桌面文案明确同名不覆盖。

原生保存建议名由 Rust 按可信曲目元数据生成：去除首尾空白/点，将 Windows 非法字符和控制字符替换为下划线，限制 UTF-16 长度，处理 CON/PRN/AUX/NUL/COM/LPT 等设备名，最后附加实际 `.mp3` 扩展名。名字不是写入路径，用户仍可修改。修改命名仅影响之后打开的对话框。

在新打包并更新的本机安装版，使用同一酷我 ID `151826227`，通过原设置界面的单选项逐个切换并读取真实原生对话框的文件名控件，没有先改成 sample.mp3：

| 规则 | 原生对话框实测预填值 | 结果 |
| --- | --- | --- |
| title（歌名） | 贝多芬：致爱丽丝.mp3 | 正确；取消，无任务 |
| artist_title（歌手 - 歌名，默认） | Various Artists - 贝多芬：致爱丽丝.mp3 | 正确；取消，无任务 |
| title_artist（歌名 - 歌手） | 贝多芬：致爱丽丝 - Various Artists.mp3 | 正确；直接保存，不手改名 |

证据：`.runtime/desktop-download-validation/naming-dialog-results.json`、`naming-download-result.json`、`naming-completed.png`。两次取消后任务列表均为空；第三次正式落盘名称与选择的规则一致，文件 3,769,364 字节、standard MP3 128 kbps / 44100 Hz，源时长 235 秒，没有下载临时文件残留。第一次切换 artist_title 时出现过上游检测超时，确认按钮保持禁用；重新检测成功后才打开保存窗口，没有将该次超时记作成功。

复验发现原先 Explorer 参数与路径拼为一个参数时，含空格的新文件名可能只打开“文档”，未正确定位。改为分别传递 `/select,` 和任务关联路径，让 Windows 正确引用路径；没有增加外部路径入口。修复后再次打包安装，直接使用预填的 `Various Artists - 贝多芬：致爱丽丝.mp3` 完成下载，点击任务“打开所在文件夹”，原生资源管理器正确选中该文件。证据为 `final-download-result.json`、`final-completed.png`、`final-reveal-result.json`。两种命名成品的 SHA-256 比较相同，媒体字节完全一致。

### 失败、恢复与回归

- 原生保存对话框取消：上述 title/artist_title 两次均零任务、零新成品。
- Rust 受控本地 HTTP 夹具：首个响应声明完整长度但中途断开，任务 failed，未发布成品且清理自己的临时文件；第二次重新请求完整响应后 completed；第三次写入中取消，任务 cancelled，无成品/自有临时文件，其他任务的临时文件内容保持不变。这些是受控响应，不冒充真实平台网络故障或 UI 重试验收。
- 同名冲突夹具：无覆盖发布返回 file_exists，已有文件字节不变；截断帧、错误时长和实际 192k 冒充标准 128k 均校验失败。非法品质及任意 URL/路径输入被拒绝。真实上游超时的 UI 也保持不可确认。
- 命名测试：三规则、默认 artist_title、偏好重载、非法枚举、Windows 非法字符、设备名与 UTF-16 长度通过。
- Web 类型检查和生产构建通过，61 项前端回归通过；已有大块 bundle 提示仍在。Rust 全套 20 项离线测试通过，5 项在线探测默认忽略；最终 Explorer 改动后下载相关 4 项离线测试再次通过，1 项在线下载探测默认忽略。另单独执行的真实 `live_standard_download` 通过，不将默认忽略项计为成功。
- 初次运行现有 WebView2 验收脚本时，动态版本集合的 nth 索引随展开而缩短导致超时；修为逐次重取首项。另一次在部分来源搜索尚未返回时就选样本，修为等待“搜索完成”和四来源结果。两次未完成执行均不计通过。
- 命名安装版 `naming-installed-playback-retry/result.json` 已完成四来源播放及 seek、旧会话 410、快速跨来源切歌，最后曲目的歌词行数、封面及配色 key 与原身份一致。最终定位修复版的复验结果另见下方最终记录。

### 系统播放器验收与人工接管

先退出拾音，并确认其进程不存在，再打开 Windows“媒体播放器”。自动化在系统“打开”对话框被 PickerHost.exe 窗口边界拒绝，重新激活并重试一次仍失败，因此没有将“播放器窗口已打开”记作播放成功。明确请用户进入验收文件夹，打开 `贝多芬：致爱丽丝 - Various Artists.mp3` 并点击播放。

用户回复“可以播放”。随后实际观察播放器显示该曲目和 Various Artists、暂停按钮，播放时间从 1:29 推进至 1:54，已播放加剩余时间为 3:55，与来源 235 秒一致。该项记录为“用户手动打开并确认可听，自动化随后核对实际播放进度”，不是自动打开文件对话框成功。证据摘要在 `system-player-result.json`；最终默认命名成品与此已播放成品字节完全相同。验收结果不记录凭据、完整媒体 URL 或个人保存路径。

### 最终安装包与复现

最终 Windows x64 NSIS `拾音_0.1.0_x64-setup.exe` 为 **3,875,796 字节（3.70 MiB）**，安装退出码 0，本机已更新。该版本已再次完成不改预填名的真实下载和含空格文件名的文件夹定位；不是仅独立 EXE 通过。版本号沿用 0.1.0，前文包大小属于历史版本；本轮没有重新验证干净机器安装。应用运行验收期间 FastAPI/Vite 未监听，Python 仅是开发验收工具。

复现：安装新包 → 设置/下载选择任一命名规则 → 搜索“贝多芬 致爱丽丝”，选择酷我 `151826227` → 下载并确认标准品质 → 原生对话框检查建议名、选择位置直接保存 → 下载列表查看进度/完成/打开所在文件夹 → 退出拾音后用系统媒体播放器打开成品。来源权限或网络变化可能使之后检测不可用，此时应明确失败。构建命令仍为 `pnpm --dir desktop exec tauri build --bundles nsis`（构建环境需 Rust 工具链）；下载运行时不需要工具链或 Python。安装包、音频、测试输出均位于忽略目录，不加入提交。

最终定位修复安装版复验已完成：`.runtime/desktop-download-validation/final-installed-playback-retry/result.json` 记录 actualWebView2=true、rapidSwitch=true；酷我 228908 → 网易云 2668397359 → QQ 0039MnYb0qxYhV → 咪咕 600913000007163534 → 酷我 228908 均实际播放并拖动后继续，旧会话释放；`--check-metadata` 的快速切歌后歌词/封面/配色一致性断言全部通过。未通过的首次脚本输出保留，未覆盖为成功。

## 第七阶段：下载入口与网页标准品质对齐（任务 19，2026-11-17）

### 定位及本轮行为

生产路径没有验收歌曲特判。全项目检索 `151826227`，已跟踪内容只出现在 Rust 测试、文档；忽略目录中的脚本和验收结果亦为测试用途。生产前端、Rust 能力判定和安装配置均不按该 ID、标题或歌手放行。开始时 `feat/rust-desktop` 工作树干净，继续修改，未提交、推送、合并或发布。

原先按钮灰的直接原因是桌面额外要求搜索 payInfo 的所有收费、试听、加密字段均为零，才注册可下载录音；任何缺字段也变成 downloadAllowed=false。前端又把这个 false 用于列表和底栏禁用。Python 网页的标准品质探查并不使用这条全局零值规则，而是官方 playUrl → 标准品质 mobi → 媒体字节品质检测。对三首用户点名原版的实测，搜索确有 listen_fragment=1、local_encrypt=1、paytype=3、song/vip 收费标记，但同 ID 的官方标准品质下载探查均返回 MP3 128 kbps。因此旧桌面入口比网页更严格，不能据搜索的概括性标记推断实际返回的标准 MP3 一定不可下载。

用户本轮进一步明确要求“网页能做到的桌面端也能做到，功能至上”。最终按该要求对齐网页实际能力：搜索中的全局收费/试听/加密标记不再作为标准下载的永久禁令。入口仅保留明确 cannotDownload=1 和未支持来源的拒绝；缺失字段为 unknown，允许按需检查，不等于已允许保存。Rust 补迁网页的官方 playUrl 检查，只有确切的 `The request is illegal!` 上下文拒绝可继续到官方 mobi；明确权限拒绝或无效响应不跳过。按原平台 ID 请求 128k MP3，并保留原有流式整文件帧、品质、完整时长、同名无覆盖及取消清理检查。没有改用播放会话地址、备用服务或换版本。

此处最终规则替代第六阶段“所有 payInfo 字段都为零”的旧行为；前一阶段记录作为历史保留。本轮未新增来源、品质、下载历史、默认目录或转码。网页行为、三种命名设置不变。

### 同 ID、同版本、显式 standard 对照

通过真实 HTTP TestClient 调用网页现有 `/api/downloads/options`（真实上游，未 mock），单独选择 standard，结果位于 `.runtime/task19/web-options.json`。不是将旧截图里的 auto 结果当作 standard 成功，也未把选项探查当成整文件完成。

| 酷我身份 / 版本 | 修前桌面入口 | 网页显式 standard | 新安装版列表直接探查 | 新安装版实际保存 |
| --- | --- | --- | --- | --- |
| 晴天 / 周杰伦，228908，原版 | 禁用，不请求 | available，MP3 128 kbps | 可打开、探查通过、确认可用 | completed，4,317,292 字节 |
| 天龙八部之宿敌-《天龙八部3》网游主题曲 / 许嵩，1090336 | 禁用，不请求 | available，MP3 128 kbps | 可打开、探查通过、确认可用 | 本轮未保存，不宣称整文件成功 |
| 唯一 / G.E.M.邓紫棋，321260769，原版 | 禁用，不请求 | available，MP3 128 kbps | 可打开、探查通过、确认可用 | 本轮未保存，不宣称整文件成功 |
| 贝多芬：致爱丽丝 / Various Artists，151826227 | 可探查 | available，MP3 128 kbps | 探查通过 | completed，3,769,364 字节，正向回归 |
| 小星星\|免费听 Twinkle Twinkle Little Star / 儿歌多多，363343188 | 原规则元数据全零可探查，此前未用于验收 | available，MP3 128 kbps | 无需先播放，从列表直接探查 | completed，1,795,426 字节，新样本 |

所有完成任务的实际媒体均为 MP3、128000 bps、44100 Hz，经过整文件校验后才标为 completed。小星星使用原命名设置建议的 `儿歌多多 - 小星星_免费听 Twinkle Twinkle Little Star.mp3`，非法竖线清理保留。随后选择同一小星星播放，从底栏“下载当前歌曲”打开弹窗，仍为 standard、128 kbps、确认可用，和列表一致。两入口继续共享 downloadBlockReason，没有要求先播放才允许列表探查。

安装版证据：`.runtime/task19/*-dialog.json`、`downloads.json`、`footer.json`。网页与桌面当前五个固定 ID 的选项结果一致；前三首旧差异来自搜索全局限制判定，本轮已修复。网络条件、来源权限后续可能变化，以上为当次实测。

### 交互与测试

- 搜索阶段只传元数据，不给整页批量探查。弹窗只检查当前曲目；检测中不可确认。新增“重新检测”，超时或暂时失败可主动重试，不写回永久禁用状态。
- 沿用 AbortController 与 revision：关闭/换曲使旧检查失效；迟到结果不能覆盖另一曲目的选项。未知资格不启用保存，只有所选品质探查 available 才能确认，确认后 Rust 再次解析校验。
- 新增 `desktop/verify_download_entry.py`，连接实际安装版 WebView2，受控替换测试期 IPC 返回，不保存夹具媒体。已验证缺字段可检查、明确禁止禁用、搜索零探查、超时后重新检测成功、甲的迟到拒绝不能覆盖乙的可用结果。首次注入因 Tauri invoke 属性只读未生效，未计通过；修为克隆测试期全局包装对象后重跑通过，reload 恢复真实接口。证据 `entry-fixture.json`，不冒充真实来源。
- Web 新增共享入口规则测试，62 项测试通过；类型检查、生产构建通过，既有大块 bundle 提示保留。Rust 全套 20 项离线测试通过、5 项在线探测默认忽略；扩展缺字段录音注册、明确 cannotDownload 拒绝、全局收费字段不额外封禁的测试。原有取消、网络中断、品质错误和无覆盖发布测试继续通过。

本轮最终 Windows x64 NSIS **3,865,135 字节（3.69 MiB）**，安装器退出码 0，已更新本机安装。上述探查、三个 completed 和底栏一致性均在本轮新安装版完成，不是旧包或独立 EXE。验收时 FastAPI/Vite 没有监听；网页对照用进程内 TestClient，已退出，不作为安装版依赖。没有重测干净机器安装或系统播放器（本轮仅修下载入口，上一阶段播放器记录保留）。包、音频、运行日志在忽略目录，不提交。复现：安装新包 → 选择酷我 → 搜索上述歌名和歌手 → 列表直接下载 → 标准品质检测 → 选保存位置；失败可在弹窗“重新检测”。

## 第八阶段：QQ、网易云、咪咕原格式下载及下载备用路线（任务 20，2026-11-17）

### 这次由第三方补足的真实下载

本轮开始 `feat/rust-desktop` 工作树干净，未提交、推送、合并或发布。QQ《发如雪》`0027oMO61wWi55` 的 **high**：纯原生无匿名媒体，默认路线实际由 **vkeys** 完整保存为 MP3 320 kbps。网易云 `2668397359` 的 **lossless**：纯原生只取得不满足无损要求的媒体，默认路线实际由 **gdstudio-preview** 完整保存 FLAC。两项均在本轮新打包安装的 Windows 版，从搜索列表直接探查和保存，没有先播放或给应用设置特殊路线环境变量，不把前缀探查当作整文件成功。

特别核对实际录音版本：网易云该 ID 是 **RyaVocal《晴天 (原唱 周杰伦)》**，不是周杰伦原版；咪咕 `600913000007163534` 是 **周杰伦《晴天 (Live)》**。保留历史记录，本节按当前来源返回的精确版本记录，不根据检索词“晴天”推断歌手或原版，不把不同 ID/版本混作同一歌曲对照。

### Python 实际启动配置与下载链路

已从 `/api/downloads/options`、创建/重试任务追至来源 resolve，并用真实 TestClient 启动应用核实实际配置（不是只看类默认值）：

| 来源 | Python 实际启动路线 | 下载参数与策略 | Rust 本轮迁移 |
| --- | --- | --- | --- |
| QQ | official → vkeys → tang → xunhuisi；available_routes 同此，启动允许精确 ID 请求绑定 | options 和任务均用 purpose=download，显式 standard/high/lossless；vkeys 分别 4/8/10，auto 用原 14；Tang/巡回寺无独立品质参数，返回媒体须匹配所选档 | 已接入同一下载解析器的探查和保存路径；官方原生先试，合格即返回；备用结果按实际媒体校验，不用播放会话 |
| 网易云 | native → gdstudio-preview → jfjt | 原生 br 128000/320000/999000；GD br 128/320/999；jfjt level standard/exhigh/lossless；显式档位不降级 | 已迁移品质参数、备用顺序、范围/格式/权限检查；jfjt 核对本次精确 ID 搜索的官方录音标题及歌手，拆分常见歌手分隔符核对集合 |
| 咪咕 | 原生，无已配置的下载备用路线 | 详情双 ID 验证，standard=PQ、high=HQ，auto 优先普通格式；lossless 明确不支持 | 原生详情及取链复用已有适配代码；按品质选目录；不编造备用服务，隐藏无损选项 |

Python 启动与真实下载选项证据 `.runtime/task20/python-startup-options.json`：QQ high 命中 vkeys，网易云 lossless 命中 GD，咪咕 standard 原生探查通过。没有修改 Python 或网页版行为，也没有将播放路线名单直接等同下载能力。`gdstudio-preview` 是沿用的路线名，不代表将试听片段作为完整成品。

QQ 启动允许的 request_bound、GD/jfjt 的精确 ID 请求绑定与 response_id_matched 分开理解：返回有 ID 时必须匹配；URL-only 只按既有启动策略接受本次精确 ID 请求绑定，仍验证媒体和整文件时长，不声称获得独立响应 ID 证明。唐必须匹配响应 MID、标题、歌手；巡回寺存在详情链接时校验其 QQ 原 ID；明显不同版本不接受。明确权限、试听、加密、登录限制不会被换路线绕过。GD 带明确 cf-mitigated=challenge 的挑战响应只记当前路线失败，不尝试解挑战；普通访问拒绝仍停止。

### 实现范围与保存契约

新增 `download_resolver.rs`：独立于播放会话，复用来源原生适配、媒体域名白名单、备用权限协议和默认路线配置。每次探查、确认后的任务取链、失败重试都从 providerId + platformId + quality 重新执行相同原生优先策略；原生无符合品质的媒体才尝试备用，不缓存或向前端返回媒体 URL。任务和实际媒体记录只增加命中路线名及失败阶段。

新增 `download_media.rs`，使用固定在 Cargo.lock 的 [Symphonia 0.5.5](https://docs.rs/symphonia/0.5.5/symphonia/) Rust 库读取有界前缀、解复用和整文件解码校验；不转码、不改写媒体内容，不依赖外部 FFmpeg。按真实容器/编码确定 MP3、AAC/M4A、FLAC、ALAC/M4A 扩展名；AAC/ALAC 要求实际 MP4 容器。无损按实际编码验证；standard/high 保留已有品质语义，不把酷我 CBR 128k 扫描器套到其他来源。完成前检查整文件时长、解码错误、可用的校验和；MP3 额外扫描 MPEG 1/2/2.5 的全部帧边界，支持不同码率/VBR，截断末帧不当正常 EOF。AAC/ALAC 本轮没有真实在线成功样本，不外推为已在线验收。

QQ/网易云界面开放 auto、standard、high、lossless；咪咕 auto、standard、high；酷我仍仅 standard。每首歌每档独立探查，不代表整个平台每档都可取得。本轮线上得到的 QQ standard 样本未匹配所选档；咪咕该样本 high 也未匹配，不降档冒充成功。无损前缀不显示局部样本推算的平均码率，仅显示格式与可信大小；整文件完成后才记录实际统计。桌面无损弹窗只保留原格式保存，不展示网页的转码选项；网页原选项不变。

复用 Windows 保存对话框、三种命名偏好、扩展名校验、同目录临时文件、流式写入、无覆盖发布、取消/失败清理、重试和文件夹定位。保持列表和底栏共享入口规则，未知可按需检查，不批量探查整页，迟到结果按原代次隔离。任务只在本次进程保留，未增加下载历史、默认目录或音乐库。

### 三来源真实整文件与系统播放器

| 来源 / 精确录音 | 所选品质 | 正式保存命中 | 实际成品 | 系统播放器结果 |
| --- | --- | --- | --- | --- |
| QQ《发如雪》/ 周杰伦，0027oMO61wWi55 | high | vkeys；纯原生同档无媒体 | MP3，320000 bps，44100 Hz，299.285 秒，11,972,641 字节 | 退出拾音后 Windows 媒体播放器打开成品，暂停按钮可见，进度 0:19 → 1:04，总长 4:59 |
| 网易云《晴天 (原唱 周杰伦)》/ RyaVocal，2668397359 | lossless | gdstudio-preview；纯原生同档不满足无损 | FLAC，48000 Hz，270.739 秒，47,185,529 字节 | 退出拾音后系统播放器打开 FLAC，暂停按钮可见，进度 0:38 → 1:29，总长约 4:30 |
| 咪咕《晴天 (Live)》/ 周杰伦，600913000007163534 | standard | native，没有备用路线 | MP3，128000 bps，44100 Hz，249.835 秒，3,997,991 字节 | 退出拾音后打开成品；窗口最小化且自动化恢复时检测到用户输入，未可靠获取进度截图，用户手动确认“可以播放” |
| 酷我《贝多芬：致爱丽丝》/ Various Artists，151826227 | standard | native | MP3，128000 bps，44100 Hz，3,769,364 字节 | 本轮完成下载回归，未重复其系统播放器检查；第六阶段记录保留 |

正式任务证据：`.runtime/task20/qq-high-task.json`、`netease-lossless-task.json`、`final-qq-high-task.json`、`final-netease-lossless-task.json`、`final-migu-standard-task.json`。纯原生/默认路线诊断使用相同 Rust 函数、同 ID、同品质（空备用配置仅用于开发测试，不要求用户设置环境变量），结果摘要 `native-comparison.json`。本轮完整保存的是新安装应用，不是仅测试代码下载或独立 EXE。

首次咪咕保存遇到两个实际断点，未计成功：CDN 返回 HTTP 200 却携带覆盖全文件的 Content-Range；原逻辑一律拒绝该头。现在只接受起点为 0、终点+1等于总长、与 Content-Length 一致的完整响应（200 或 206），收完仍核对总字节数；部分区间、未知总长范围、矛盾长度均拒绝。另一个断点是搜索没有时长，被带成 0；原生详情同 ID `length=00:04:09` 已核实，下载探查和正式取链均读取并验证详情时长，补充有界时:分:秒解析。不是放宽时长校验或拿另一版本替换；修复后同一 ID 成功。

系统播放器使用本轮已完成文件，由 Shell 文件关联打开，没有将“启动播放器 EXE”当成实际播放；EXE 启动未切换文件时不计通过。QQ 和网易云按实际画面记录进度；咪咕按人工确认单列。摘要 `system-player-results.json`，不记录个人保存路径、凭据或完整媒体 URL。

### 各备用路线的实测边界

| 路线 | 在线探查 | 整文件结论 |
| --- | --- | --- |
| QQ vkeys | 发如雪 high 通过，实际参数 8 | 已由安装版完整保存并系统播放，证明补足原生下载 |
| QQ Tang | 同 MID lossless 返回 FLAC，前缀通过 | 收完 36,226,753 字节后校验失败，未发布成品；独立整文件诊断明确 source_checksum_failed。不能记为无损下载成功，不关闭校验和检查以迁就来源 |
| QQ 巡回寺 | 同 MID standard 返回结果未形成可用媒体探查 | 未整文件验实，不将播放曾成功外推为下载成功 |
| 网易云 GD | 同 ID lossless FLAC 通过 | 已安装版完整保存并系统播放，证明补足原生无损 |
| 网易云 jfjt | 按该 ID 实际 RyaVocal 版本标题/歌手核对后，lossless FLAC 前缀通过 | 本轮默认先命中 GD，jfjt 未完成独立整文件验收；只记探查成功 |

单路线和原生对照可通过忽略测试 `live_individual_routes`、`live_probes` 显式复现；`live_tang_full_check` 仅下载临时诊断文件验证错误阶段，不发布成品。测试函数退出成功不等于表中每条路线成功，逐项结果单列。最初用检索词“晴天/周杰伦”作为 jfjt 对照元数据导致不匹配，修为该 ID 的实际 RyaVocal 版本后探查通过，不将错误元数据的那次失败当成路线不可用证据。摘要 `route-status.json`。

### 回归、命名与最终安装包

- Web 62 项回归、类型检查及生产构建通过；既有大块 bundle 提示仍在。Rust 全套 26 项离线测试通过，8 项在线探测默认忽略；在线探查与整文件结果如上单列。新增品质/格式判定、身份/版本拒绝、原生成功/权限拒绝不调用备用、全部备用失败、MP3 末帧截断、完整范围响应及咪咕详情时长测试；原取消、中断恢复、冲突不覆盖、三种命名测试保留并通过。
- 本轮安装版再次运行 `verify_download_entry.py`：搜索缺字段可探查、明确禁止禁用、无整页探查、超时可重试、快速换曲后的迟到结果隔离通过，证据 `entry-fixture.json`；这是受控 UI 回归，不冒充来源下载成功。
- 最终逻辑安装版 `verify_webview.py --check-metadata` 完成四来源播放、seek 后继续、旧会话释放及快速跨来源切歌；最终曲目的歌词行数、封面和配色 key 均与当前身份匹配，证据 `final-playback-regression/result.json` 及截图。酷我真实标准下载也完成，如上表。
- 三种命名均有本轮实际保存：歌手在前、歌名在前的 QQ MP3/网易云 FLAC；只用歌名的最终展示修订安装版再次完成网易云 FLAC 保存。`final-presentation-smoke-tasks.json` 记录 completed，扩展名正确。两种命名下 QQ、网易云成品分别 SHA-256 比较相同，证据 `renaming-identical-bytes.json`；没有覆盖旧成品，临时文件检查零残留。验收后恢复原歌手在前偏好和酷我选择。

最终 NSIS **4,344,281 字节（4.14 MiB）**，安装退出码 0，本机已更新，版本仍 0.1.0。最终展示修订仅去除无损前缀平均码率和桌面转码选项，另外实测其网易云 FLAC 完整保存；三来源完成记录来自本轮的新安装包及其修复版本，未借用旧阶段结果。没有重测干净机器安装。验收时 FastAPI/Vite 未监听，Python 只用于开发探测/实际 WebView2 验收，应用启动没有额外路线环境变量。最后已退出拾音。安装包、音频、运行日志不提交；保留历史验收记录和本轮失败记录。

复现：安装新包 → 直接选择相应来源搜索上表歌曲 → 在原平台 ID 对应的版本行点击下载 → QQ 选择高品质、网易云选择无损、咪咕选择标准 → 原生保存对话框确认 → 任务完成后打开文件夹 → 退出拾音，用 Windows 系统媒体播放器打开成品。路线和权限可能随上游变化，以每次探查与整文件校验为准；失败可重试，不静默换品质或曲目。

## 第九阶段：保留原格式改为轻量完成校验（任务 21，2026-11-17）

本轮开始分支 `feat/rust-desktop` 工作树干净。按用户要求只修改 Windows 桌面原格式保存完成条件，未提交、推送或发布。第八阶段及独立 FLAC 诊断记录保留为历史，不再代表当前原格式保存门槛。

### 当前检查与完成含义

用户选择“保留原格式”时，沿用既有下载资格、精确曲目身份、路线及所选品质的按需探查。实际接收仍检查 HTTP 状态、响应编码、完整范围响应、非空及容量限制；显式读取有效 Content-Length，并与客户端长度提示及 Content-Range 核对，可信总长必须与实收字节一致。未知总长本身不构成拒绝，也不伪造下载百分比。

写入仍使用同目录随机临时文件，传输正常结束并同步写入后，`download_media::inspect_original` 仅读取最多 256 KiB 的前缀：检查音频文件头、必要格式信息，并复用现有有界前缀品质判定。错误页面、空内容、已知长度不足、非法状态、格式/扩展名不符、明确不符合所选品质的内容不能生成正式文件。酷我标准品质仍沿用已开放的 MP3 128k 条件；其他来源沿用已有品质语义，没有按歌曲、ID、Tang 路线或尾部长度特殊放行。

原格式保存**不再要求整首解码、全帧扫描、整首时长比对或 FLAC PCM MD5 通过**。`save_response` 统一调用轻量入口，不再调用酷我整文件扫描器或通用深度检查。旧深度检查函数仅保留用于独立诊断及其测试，不参与生产保存完成判定。不会通过裁剪尾部、修复内容或重编码来让文件通过；正式成品包含所收到的全部字节。

“下载完成”现在表示文件已正常接收并保存，不表示拾音已验证每一帧。没有给正常保存增加警告，没有改变下载弹窗、在线播放、Python 网页版或正式转码规则，未增加 FFmpeg 依赖。原有临时文件、取消/失败清理、重试、同名不覆盖及文件夹定位行为保留。

### 仅本轮相关的本地验收

没有重新取链或下载音频，没有启动来源网络探测，没有重跑四来源在线播放、试听或自动控制系统播放器，也没有进行耗时比较。

1. **已有 Tang FLAC 原样保存**：直接读取 `.runtime/tang-retained-20261117-8b1d94a3/QQ-0027oMO61wWi55-Tang-original.flac`，通过内存构造的流式响应（每块最多 64 KiB，无 HTTP 网络访问），进入与实际任务共用的 `save_response` → 轻量检查 → 无覆盖发布 → `finish` 完成/清理流程。任务为 completed，格式 FLAC，36,226,753 字节，不再因 source_checksum_failed 拒绝。逐块比较全部字节，包含原文件的异常尾部；保存前后 SHA-256 均为：

   `694FE81ABF2ACB54D28F175E0CA6EF8E9BC195FF898D27A39FF9B9852D935167`

   保留结果文件：`.runtime/task21/original-roundtrip-908d567f-5b81-4aca-b3b1-282ffa3cacc4/QQ-0027oMO61wWi55-Tang-original.flac`。这是已有字节的本地保存回放，不宣称本轮安装版重新在线下载或安装验收。

2. **已有正常 MP3 原样保存**：复用同一诊断目录中已完整解码验证过的 320 kbps MP3，经同一保存流程完成，11,972,527 字节，保存前后 SHA-256 均为 `F881D1CE32F9853C6DF84EDA4C50718B0BFCC588879AF8FF6127A00756525279`，没有重新转码。

3. **针对性基础回归** `original_response_basics` 通过：正常 MP3 有可信总长/未知总长均保存成功，未知总长任务保持 totalBytes=null；HTML 错误页面、空响应、有可信总长但提前结束、失败 HTTP 状态、所选品质不符和目标格式扩展名不符均失败，无正式文件，任务自有临时文件清理。提前结束样本验证了显式 Content-Length 核对，检查不依赖客户端是否提供内部 body 长度提示。

4. **相关清理回归** `interrupted_retry_and_cancel_clean_only_owned_parts` 通过：真实本地受控连接中断后不发布半成品，完整响应恢复成功，途中取消清理本任务临时文件，其他任务文件保持原样。未运行无关的在线播放或在线来源测试。

显式执行的本地文件回放测试为 `original_retained_file_roundtrip`、`original_normal_file_roundtrip`，默认忽略，避免普通测试依赖诊断目录。它们不取链、不访问网络，保留输出供复核。结果与 SHA-256 汇总位于 `.runtime/task21/original-save-results.json`，原诊断文件及此前验收资料均保留。

### 交付给用户手动试用的 Windows 构建

`pnpm --dir desktop exec tauri build --bundles nsis` 完成，构建内置的 Web 类型检查/生产构建通过，既有大块 bundle 提示仍在。没有安装本轮构建，安装和使用体验由用户手动确认，不记为安装版通过。

- NSIS：`C:\Code_Home\2_projects\music-core\desktop\src-tauri\target\release\bundle\nsis\拾音_0.1.0_x64-setup.exe`，**4,349,815 字节（4.15 MiB）**。
- Release EXE：`C:\Code_Home\2_projects\music-core\desktop\src-tauri\target\release\music-core-desktop.exe`，**17,175,040 字节**。

安装包、音频、测试产物不提交。命名、来源解析和正式转码保持既有实现，本轮只交付原格式保存的轻量完成校验。
