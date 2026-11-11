# 11 统一下载

下载由 `server/app/downloads.py` 中的一个 DownloadManager 管理。稳定 TrackIdentity → 当前已配置的 Provider.resolve(purpose=download) → 私有 ResolvedMedia → 完整 GET → 同目录任务临时文件 → 完整性检查 → 原子非覆盖发布。没有经过 MediaStore、PlaybackLease 或浏览器 Range 代理；播放控制器和 audio 未修改。

## 使用

默认目录为项目根目录下的 `downloads/`。可用服务端环境变量 `MUSIC_CORE_DOWNLOAD_DIR` 指定；相对路径相对于启动工作目录。建议从 server 启动并绑定本机：

```powershell
cd server
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

通过 `/docs` 操作，或提交：

```json
{
  "identity": {"providerId": "netease", "platformId": "284617"},
  "title": "飞鸟与鱼",
  "artist": "齐豫"
}
```

title、artist 可省略，只是受限长度的展示名称，不参与歌曲身份解析、不宣称来自平台重新核验。省略时按 providerId-platformId 命名。多歌手由调用方统一连接为 `甲、乙`。仅有 identity 也能下载，不需要先搜索或创建播放会话。

| 接口 | 行为 |
|---|---|
| POST /api/downloads | 202，立即返回 queued 任务；拒绝未知字段及客户端上游 URL |
| GET /api/downloads | 当前进程保留的公开任务列表 |
| GET /api/downloads/{id} | 状态、receivedBytes、totalBytes、progress、文件名、格式、错误码及毫秒时间 |
| POST /api/downloads/{id}/cancel | 幂等取消并等待清理；终态不被覆盖；已完成文件保留 |
| POST /api/downloads/{id}/retry | 仅 failed/cancelled 可重试，创建新 ID 并重新 resolve；保留旧任务结果 |

进度采用轮询，建议 500–1000ms。totalBytes 未知时为 null，progress 也为 null。完成后 filename 是目录中的文件名，不提供任意磁盘路径访问接口。

## 状态、资源与文件

状态为 queued → resolving → downloading → completed；非终态可进入 failed/cancelled。取消会中止等待、解析或传输，等待上游关闭及临时文件清理；晚到响应不得覆盖终态。完成发布与 completed 更新之间没有异步让出点。发布前再次检查取消状态。

默认并发 2，未结束任务最多 20（包含正在执行的任务），记录最多 100；满额时拒绝请求或淘汰最早终态记录。每个任务上限 1GiB、30分钟。设置集中在 DownloadSettings，可由应用工厂注入，不增加调度框架。关闭服务时取消非终态任务，并等待所有 worker 收尾。终态记录只保留 DTO，不持有媒体 URL、网络响应或 Task 引用。

临时文件为 `.music-core-进程ID-任务ID.part`，以排他创建方式打开。启动仅清理符合本实现命名且所属进程明确不存在的残留；其他 `.part`、仍在运行的进程或无法确认状态的文件不删除。PID 重用可能导致保守保留残留，不会当成完整文件。当前任务正常退出一定尝试清理；清理失败报告 temporary_cleanup_failed，可人工检查后处理。进度及历史不跨服务重启恢复，已完成文件保留。

文件名过滤 Windows 禁用字符、Unicode 控制/代理字符、尾部空格句点和设备名，按 UTF-16 截断。临时文件不使用上游名称。完成名依次使用 `歌手 - 歌名.ext`、`歌手 - 歌名 (2).ext`。同文件系统通过 `os.link` 原子发布完整 inode，再去除临时名：这是非覆盖的原子发布，并非 `os.replace` 覆盖式重命名。并发或外部进程抢占名称时继续编号；文件系统不支持硬链接则明确失败，不降级成可能覆盖或暴露半成品的复制。当前已在 NTFS 实测。

## 传输与校验

复用共享 HTTP Client；每跳调用现有 provider 域名白名单及公共 DNS 检查，最多 3 次重定向。不合并共享 Cookie/Authorization，仅继承必要 UA/Referer，跨跳清除上下文。请求为无 Range 的完整 GET、Accept-Encoding: identity。401/403 直接失败，不为下载另建取链路线；现有 Provider 对错 ID、试听、加密及明确权限拒绝的处理保留，QQ/网易云默认解析配置不变。

HTTP 200 正常处理；若携带 Content-Range，同样必须证明覆盖全文件。206 只接受 bytes 0-(N-1)/N，长度声明若存在必须等于 N；部分范围或未知总长范围拒绝。非 200/206、编码传输、非法长度、提前断流、超出大小限制均失败。每次最多接收/写入 64KiB；只保留 4KiB 前缀，更新实际字节进度，写完 flush/fsync 后核对磁盘大小、接收量、HTTP 声明以及 Provider 已知 sizeBytes。

格式以实际前缀为准，支持 MP3、FLAC、M4A/MP4 Audio、OGG；Content-Type 或 URL 后缀不能单独决定扩展名。与 Provider 已明确的容器冲突则失败。未知 Content-Length 可按正常 EOF 完成，但仍要求非空、可信格式前缀、磁盘字节一致、大小及时间上限。该检查证明基本传输完整性，不等于全文件解码、音频指纹或母带品质鉴定；验证脚本另用 Chromium 读取真实本地文件。

普通同步文件写入限于有界块，避免取消后仍在写盘的后台线程。慢磁盘的单次 write/fsync 可能占用事件循环；当前定位本机单进程服务，未扩展为多进程共享任务或网络文件系统产品。

## 访问条件与边界

resolve 成功与完整传输成功是两项独立证据，均不构成资源权利授权证明。当前四来源协议没有统一的、经平台认证的下载授权字段，本期不伪造 DownloadOption.downloadAllowed=true。用户仍应按资源及账号实际允许的用途使用。测试是用户指定的有限个人开发验证；未引入账号身份伪造、DRM、付费解锁或遇明确权限拒绝后换线。GD 仍是已配置的 request_bound 预览路线，不能因完整保存就升级其录音身份或版权证据。

不支持转码、品质选择、标签/封面/歌词写入、Range 分块、断点续传、重启恢复传输、数据库、歌单批量下载、文件服务或正式 Vue 页面。没有新增依赖。本期使用 Swagger、真实单曲脚本和受控浏览器脚本验收，不启动 阶段 12。
