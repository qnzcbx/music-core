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
