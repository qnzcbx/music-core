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
| NSIS 安装包 | 未生成，不能报告大小 |
| 本机安装 / 干净机器安装 | 未执行 |

`pnpm --dir desktop exec tauri build --no-bundle` 已完成 release 构建。
`pnpm --dir desktop exec tauri build --bundles nsis` 完成 Web/Rust 构建，在下载官方
`https://github.com/tauri-apps/binary-releases/releases/download/nsis-3.13/nsis-3.13.zip`
时失败：`timeout: global`；curl 重试同一地址也收到 `Recv failure: Connection was reset`。
网络恢复后重跑上述命令；本次不将 NSIS 打包或安装验收标记为通过。

安装验收应在关闭 FastAPI 和 Vite 后执行：搜索 → 播放 → 拖到中间 → 确认时间继续增长 → 快速切歌 → 退出；检查浅色/暗色、墨息/字里弦间、中文 IME 和页面跳转。另需在没有 Node/Python 的干净 Windows 上安装验证。
