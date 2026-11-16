# Windows 桌面版（第一阶段）

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
