# 40-D.4.1 验收记录

本期修改新项目 `C:\Code_Home\2_projects\musicdl-lab`，旧 Lab 只读，未提交 Git，未开始下一阶段。已完成下载列表交互、本地播放、持久隐藏和受控删除。

## 列表与交互

1. 桌面保留歌曲、大小、状态、操作四列；Copy / Trash-2 为直接可见的 36px 中性图标按钮，无三点菜单。操作标题与每行按钮左对齐，浏览器逐行测量横坐标差小于 2px。操作按钮不触发播放，支持聚焦、aria-label 和轻量反馈。
2. 600px 以下已保存文件仅显示名称及确实存在的歌手；没有任务元数据时只有原文件名。隐藏封面、大小、格式、状态、常驻复制和删除图标，保留当前文件的轻微背景。正在下载的任务仍显示原进度、接收量、状态、取消和重试。
3. 直接复用已安装的 Reka ContextMenu 原语。原语负责长按计时，pointermove / pointerup / pointercancel 取消计时，不另建手势识别器。菜单打开后抑制本次点击播放，下一次 pointerdown 重置；正常短按播放。真实 Chromium CDP 触摸验证了长按不播放、移动取消、短按播放。菜单支持外部关闭、Escape、右键、ContextMenu 键及 Shift+F10；另有平时隐藏、获得键盘焦点时显示的“文件操作”按钮，辅助技术也能进入。
4. 复制优先使用当前完成任务的真实标题；完成任务与清单通过 `fileId` 匹配，避免用同名替换文件冒认旧元数据。无对应任务时复制完整文件名，不拆文件名猜歌手。浏览器分别验证了“真实任务标题”和历史文件名两种复制结果。
5. 右上角刷新为 Refresh-Cw，名称“刷新下载列表”；请求中禁用并旋转，减少动画偏好下取消旋转。继续调用根级 useDownloads 的同一个刷新协调器，不改变播放状态。

## 持久化、文件身份与访问边界

6. `POST /api/downloads/files/{identifier}/remove` 接受 `{deleteFile:false}`，默认仅隐藏记录。下载模块在下载目录写 `.music-core-hidden.json`，只存版本及文件 ID，不存媒体 URL、凭据或文件内容。JSON 有 1MiB 上限，写临时文件、flush/fsync 后 os.replace 原子替换；RLock 串行保护本 Core 的读取、修改和写入。索引损坏或写入失败明确报错，不静默清空隐藏记录。
7. `{deleteFile:true}` 才实际删除音频。文件删除成功本身形成持久移除，不需要再进行可能失败的隐藏索引事务。确认框默认不勾选，勾选后显示无法撤销提示；取消无请求。界面等待后端成功才移除行和显示成功，失败保留行及弹窗原因。这里只移除已保存文件清单记录，不改写仍在内存中的下载任务历史。
8. 清单新增 SHA256 `fileId`，绑定配置目录、实际文件名、设备、文件实例号、大小和纳秒修改/创建状态时间。客户端不提交路径。不同序号文件有不同 ID；同名替换即使内容、大小和修改时间相同，也因文件实例变化而得到新 ID。旧引用返回 404，不会删除新文件；隐藏也绑定原实例，不按模糊歌名匹配。
9. 每次流式读取、隐藏和删除重新在配置目录的直接子文件中查找并验证：扩展名白名单、音频前缀、普通文件、非符号链接、非 Windows 重解析点。打开后比较 fstat，拒绝变化目标。任意绝对路径、穿越字符串、子目录及非法 ID 不成为文件访问入口。Windows 删除使用带 OPEN_REPARSE_POINT 的 CreateFileW，验证句柄后调用 SetFileInformationByHandle，避免检查之后同名替换而删错实例。
10. 新增的流和移除 API 检查客户端及 Host 均为回环地址，检查 Origin，拒绝 cross-site / same-site Fetch Metadata。破坏操作使用 JSON POST，浏览器跨站表单不符合请求契约。公网客户端、恶意 Host、外部 Origin 和跨站请求均通过拒绝测试。此能力供本机使用，不是公开文件管理 API。

## 本地流、唯一 Audio 和队列

11. 新增 `GET /api/downloads/files/{identifier}/stream` 和 HEAD。复用现有 range_header 与 OwnedStream 清理边界，200 / 单区间 206 / 无效、多区间及越界 416，提供 Content-Type、Content-Length、Accept-Ranges、Content-Range、ETag。HEAD 不发送正文。每次最多读取 65536 字节，不将整个 FLAC 放进内存。
12. 正常结束及 ASGI 取消均在 finally 关闭句柄并移除读取计数；HEAD、无效 Range 也立即释放。64MiB 稀疏测试文件验证首块 64KiB、读取期间不能删除、发送取消后可立即删除。没有把仅有格式前缀的测试载荷宣称为可解码音频。
13. usePlayer 在原入口区分本地条目与在线条目。进入本地先清续租计时器并调用原 RecoveryPlayer.stop，关闭旧 Lease、清除旧 src，再由同一 Audio 加载受控文件流。切回在线继续调用原 controller.select。没有第二个 Audio、RecoveryPlayer 或队列；`recovery-player.mjs` 未修改。
14. 本地操作直接控制唯一 Audio 的播放、暂停、Seek、音量；本地错误显示文件无法读取/已变化/格式不支持，不进入 Provider.resolve、Lease open、renew 或在线自动恢复。歌词身份设为 null，不联网匹配历史文件。入口世代隔离旧在线及本地异步结果；加载期间的暂停意图也予以保留。
15. 现有队列最小扩展为在线条目或 `{kind:'local',fileId}`，键为独立的 `['local',fileId]`。上下首、实际历史和四种播放模式共用原导航器。本地队列只保留当前页面生命周期，不写媒体 URL，也不改原在线持久化版本；写盘时只投影在线条目，重载仍兼容原协议。
16. 移除本地文件前先从现有队列清除对应项；若为当前项，原 stop 负责 pause、移除 src、load，释放浏览器引用。后端对尚未结束的响应最多等待约 1 秒，否则返回文件占用失败。Windows 临时真音频测试确认当前播放文件可实际删除，Audio 停止且队列不再含该项；移除其他文件时当前歌曲继续播放。

## 真实浏览器结果

`server/scripts/verify_local_files.py` 使用新 Vue 5185 / 新 Core 8007。历史目录只扫描和播放；前后逐文件 SHA256 比较，9 个历史文件均未改变。所有隐藏和删除发生于系统 TemporaryDirectory 的音频副本，未隐藏或删除历史歌曲。

| 历史样本 | 格式 | Chromium 实测时长 | 验收 |
| --- | --- | ---: | --- |
| 酷我既有样本 | MP3 | 271.583107 秒 | 播放、50% 及 96% Seek |
| QQ 既有样本 | M4A | 239.420952 秒 | 播放、50% 及 96% Seek |
| 网易云既有样本 | MP3 | 264.867800 秒 | 播放、50% 及 96% Seek |
| 咪咕既有样本 | MP3 | 206.400000 秒 | 播放、50% 及 96% Seek |
| 既有无损样本 | FLAC | 263.340408 秒 | 播放、50% 及 96% Seek |

随后验证暂停/继续、路由切换、沉浸式播放器和唯一 Audio 引用不变。本地阶段没有在线 resolve/open；受控在线阶段使用明确标识的自生成 WAV，验证本地→在线→本地、旧 Lease 关闭 204、本地不续租、旧在线慢结果不覆盖本地。该双向故障实验不是新增真实平台解析成功记录。

临时目录内验证任务标题复制、默认不删除文件、取消确认、只隐藏、其他歌曲不中断、真实 Core 关闭并重新创建启动后仍隐藏、浏览器刷新后仍隐藏、503 后行与文件保留、当前文件停止并真实删除。不是只在前端数组或单个 Manager 中模拟重启。

视口 390 / 768 / 1440px 均覆盖浅色与深色，未发生横向溢出。移动设备仿真加 CDP touch 验证长按保持菜单、不误播放、滑动取消、短按、菜单复制/删除、键盘入口、辅助入口、右键、外部关闭及 Escape。页面异常为空。见 [browser-result.json](browser-result.json)。

截图按原忽略规则保存在 screenshots：

- [桌面浅色](screenshots/files-1440-light.png)、[桌面深色](screenshots/files-1440-dark.png)
- [平板浅色](screenshots/files-768-light.png)、[平板深色](screenshots/files-768-dark.png)
- [手机浅色](screenshots/files-390-light.png)、[手机深色](screenshots/files-390-dark.png)
- [移动上下文菜单](screenshots/mobile-context-menu.png)、[删除确认](screenshots/delete-confirm.png)、[失败保留](screenshots/delete-failure.png)

## 回归、依赖及限制

- 后端 `cd server; .venv/Scripts/python.exe -m pytest -o addopts= -q`：539 passed，1 skipped。原 521 项均保留通过；文件隐藏、重启、真实删除、失败、同名替换、隔离、安全边界、Range、并发索引和取消释放获得新增验证。唯一跳过为当前 Windows 没有创建真实文件符号链接的权限；重解析点属性拒绝分支另有通过的测试。保留原 Starlette/httpx 提示。
- 前端 `pnpm --dir web test`：38 passed，原 35 项通过，新增混合身份、导航/删除以及在线持久化兼容验证。typecheck 和 build 通过。主包约 502KB，触发 Vite 原有 500KB 提醒，未调高阈值；下载页仍懒加载。
- 原 `verify_vue_downloads.py --controlled` 通过；仅将刷新选择器更新为新无障碍名称。仍验证并发、排队、未知总长、取消、重试、旧响应隔离、失败、下载中播放、唯一 Audio 与收尾清理。人工 404/503 为刻意故障。没有新增真实下载文件来替代本地验收。
- 原 Vue D1 在线恢复脚本在隔离端口 8006/5184 通过：renew 204/410、四次打开、暂停/Seek/音量静音、恢复、路由连续、同一 Audio，关闭后四个能力均 410。只在运行时替换端口和截图目录，原恢复测试逻辑不变。原无限搜索脚本受控 40 个请求通过，页面异常为空。歌词及在线队列 Node 回归通过。
- 未新增依赖、Resolver、文件管理框架、数据库或第二套播放器。已有下载解析、限流、HTTP 传输、取消、重试和原子发布流程保持；仅在完成任务中补充与文件清单对应的 `fileId` 元数据。
- 隐藏索引按一个本机 Core 写入者设计，RLock 保护本进程并发；不承诺多个 Core 进程同时修改同一目录的索引。索引有 1MiB 上限，超过或损坏时明确失败。隐藏不等同于磁盘删除，也不是撤销已知文件引用的权限机制。
- 文件目录变化需刷新；没有实时监听、跨重启任务历史或永久歌手/专辑数据库。本地队列不跨浏览器刷新恢复。只扫描配置目录直接子文件；不支持任意目录、批量、标签编辑、转码或自动网络补元数据。OGG 在流白名单中，本期真实解码样本仅验证 MP3/M4A/FLAC。触摸验收来自 Chromium 仿真，未声称真机 Safari 结果。
- 常用 8001 Core 仍为此前进程。尝试先检查下载空闲再重启以加载本期代码时，自动审批拒绝了整条命令，原因为“blocked by policy”，未提供更具体说明；未绕过该拒绝。隔离服务已完成本期验收并关闭，日常 5174 页面使用新文件功能前需由用户重启 8001 Core。

## 40-D.4.1 收尾补丁：播放反馈统一

下载行沿用 SongItem 的 `--app-hover`、`--app-selected`、`--app-focus` 和封面覆盖层尺寸、遮罩、过渡；桌面整行可播放，当前行再次点击使用全局 toggle 暂停/继续。悬停和键盘聚焦显示播放图标，当前播放显示暂停图标，加载中显示旋转图标；普通图片与缺省音乐封面共用覆盖层。播放标记、加载和暂停反馈均由现有 usePlayer 的 selectedId / playing / phase 派生，没有局部播放器状态。Copy/Delete 继续阻止点击冒泡，操作列位置不变。移动端仍隐藏封面与常驻操作，只在当前行显示“正在播放 / 已暂停 / 正在加载”等轻量反馈，长按机制不变；移动行禁用原生文字选择与浏览器蓝色触摸闪光，统一使用当前行反馈，触摸滚动仍正常。

扩展原 verify_local_files.py，在真实 Chromium 1440 / 390px、Light / Dark 中验证悬停色与搜索样式变量相同、默认及图片封面覆盖、点击封面暂停、整行切歌、暂停保留选中、键盘反馈、单行高亮、在线/本地切换及快速切换隔离、删除后反馈清除。通过暂挂本地流请求观察真实全局 loading，再暂停并释放请求，确认没有被晚到加载改回播放。图片封面经受控搜索候选及下载响应夹具进入原 covers 映射，没有真实下载或修改历史文件。原移动短按、长按不播放、滑动取消、菜单复制/删除及辅助入口均再次通过；页面异常为空，历史音频哈希不变。结果追加在原 browser-result.json 的 feedbackPatch 字段。

截图：[图片封面悬停](screenshots/patch-image-cover-hover.png)、[加载状态](screenshots/patch-loading.png)、[手机暂停反馈](screenshots/patch-mobile-paused.png)；原 screenshots 中的六张尺寸/主题截图也已更新。前端 38 项 Node 测试、typecheck、build 通过；保留约 502KB 主包的既有体积提醒。本补丁仅调整两个下载页 Vue 文件、扩展原浏览器验收并更新本记录，没有修改本地流、DownloadManager、RecoveryPlayer 或 usePlayer，没有新增依赖或提交 Git。
