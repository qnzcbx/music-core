# 16 下载界面 — 阶段 16 统一下载页面与四来源接线验收

日期：2026-11-10。旧实现 和研究来源只读。

## API、生命周期及文件边界

实施前读取实际 `server/app/downloads.py`、Pydantic 模型、运行服务 OpenAPI 和 阶段 11 报告。真实接口如下：

| 接口 | 作用 |
| --- | --- |
| POST /api/downloads | 202 创建任务；请求为 identity、可选 title/artist |
| GET /api/downloads | 返回当前进程任务列表 |
| GET /api/downloads/{id} | 查询单个任务，不存在返回 404 |
| POST /api/downloads/{id}/cancel | 返回服务端实际状态；已完成时保持 completed |
| POST /api/downloads/{id}/retry | 202 新建任务，返回新 ID，重新 resolve |
| GET /api/downloads/files | 本期新增，只读列出安全下载目录中的已保存音频 |

实际状态只有 queued、resolving、downloading、completed、failed、cancelled，没有独立 verifying。前端在 downloading 且真实已接收字节达到已知总长时提示“正在校验文件…”，不自行将任务改成 completed；解析阶段不显示虚假的下载百分比。

DownloadManager 仍为原实现：默认并发 2、最多 20 个非终态任务、容量 100。容量满时淘汰已终态且 worker 已释放的旧记录，没有按时间自动过期的任务 TTL。默认单任务超时 1800 秒、最大 1GiB。任务只存在内存，服务关闭会取消未完成任务并清理临时文件；重启不恢复在途任务或任务历史。浏览器刷新可重新查询仍在运行服务中的任务，浏览器关闭不等于服务端取消。

阶段 11 没有独立文件清单。本期只补 `SavedDownloadFile` 与 `/files`：返回 filename、sizeBytes、format、modifiedAt，不返回绝对路径或 TrackIdentity。只检查配置下载目录的直接音频文件，跳过子目录、隐藏/临时文件、符号链接与 Windows 重解析点；读取有界文件前缀确认格式，不支持调用者指定目录或路径穿越。目录不可读时返回固定安全错误，不暴露私有异常内容。未增加文件下载、删除或文件管理器操作接口。

“下载歌曲”来自文件清单，存在性不依赖任务历史；只有当前服务中 completed 任务的 filename 能与清单对应时，才展示其歌曲/歌手/来源元数据。没有任务元数据的旧文件仅显示真实文件名和“本地文件”，不从文件名猜平台身份。未建立 localStorage 下载数据库。常用 Core 重启后实测任务为 0，但 12 个保存文件仍可展示，见 [重启后文件列表](screenshots/download-restart-file-list.png)。

默认目录是运行FastAPI的项目根目录下 `downloads/`，不等于浏览器默认下载目录。界面只提供复制文件名，没有伪造本地路径 URL、文件管理器按钮或浏览器直接读取项目目录的能力。

## 前端接线与旧 UI

下载页使用 `.downloads-view`

组件目录使用单数 download，避免现有 `.gitignore` 中通用 downloads/ 规则误忽略源码。真实音频、临时文件和截图继续遵守原 ignore 规则。

SongItem 的具体版本下载图标直接调用根级 `useDownloads.create(song)`，只投影该版本的 TrackIdentity、标题与歌手；click.stop 阻止播放冒泡，不下载整个组，不先播放或重新按名字搜索。API 模块只发任务请求，Vue 不消费上游媒体流。

同一客户端用稳定身份合并在途创建请求，并复用已经查询到的任务；快速重复点击不会创建多个任务。已完成记录提示到下载页查看，失败/取消记录提示在任务页重试。跨客户端没有新增服务端幂等系统，仍由 DownloadManager 原子非覆盖发布保证文件不被覆盖。

取消和重试调用原 API。重试保留旧终态行，显示“已重试”，按返回的新 ID 添加新任务，不把新任务写回旧 ID。按钮在操作期间禁用，重复操作合并。404 在任务操作上下文显示“任务不存在或已过期，请刷新”，表示可能被容量淘汰或服务重启清空，不冒称后端存在固定任务 TTL。访问拒绝、资源不可用、超时、上游网络、文件校验及文件保存等错误按实际 errorCode 分开呈现。

## 状态更新与播放隔离

`useDownloads.ts` 在现有根提供者创建一次。任务列表和操作属于下载状态，不进入 usePlayer、RecoveryPlayer、队列或歌词状态。下载仍由服务端 Provider.resolve(purpose=download) 独立取得媒体，不共享 PlaybackLease，也不由前端选择 official 或备用解析路线。

有活动任务且页面可见时每 1500ms 查询任务列表；服务不可用时放慢到 5 秒，没有活动任务时停止轮询。进入下载页、浏览器恢复可见、创建/操作任务后主动刷新；新完成任务或用户刷新时才查询文件清单，不持续扫描目录。单一在途查询合并重复刷新，没有多个页面各建轮询器。

创建、取消、重试提高本地请求代次；旧列表响应不得覆盖操作结果，必要时再刷新一次。任务 updatedAt 也用于避免旧记录回写。页面离开不调用 cancel；根销毁只清理计时器、可见性监听和查询 AbortController，不向服务端发送批量取消。

下载页状态与列表均按任务 ID/文件名稳定渲染，不因进度更新重建整个列表。已接收量来自 receivedBytes，可信 totalBytes 存在时才显示百分比；未知总长显示不确定进度和真实已收字节。文件页的大小来自磁盘 stat、格式来自文件前缀，状态为“已保存”，与任务“已完成”分开。

## 本期真实下载

`server/scripts/verify_vue_downloads.py` 使用独立新 Core 8005/Vite 5183 和真实 Provider，通过新 Vue 搜索“飞鸟与鱼 齐豫”，展开同曲组，选择网易云 `284617` 的具体行下载。当前候选歌手实际返回“齐豫、齐秦”，文件名和界面照实使用返回元数据，没有沿用历史手填歌手覆盖。

首个按钮创建任务成功，再次点击复用任务，未触发 Playback Open，audio 暂停且无 src。进入下载页，观察真实进度从 0/655360/1310720/1835008/2686976 等接收量到 completed。最终文件 `齐豫、齐秦 - 飞鸟与鱼 (4).mp3`，实际 4,238,986 字节；Chromium 本地读取时长 264.8678 秒。SHA256 为 `922fea4a718125f628a7b86cd24ff3d0c8a86cbc16915681ad0124749dd7f912`，与 阶段 11 样本一致。

随后选择另一个录音 `284782` 下载，同时播放 `284617` 并 Seek 到 120 秒；该第二版本实际返回 upstream_failure，未宣称第二项真实并发下载成功或发布了文件。失败任务不影响播放，同一 Audio、流能力仍有效；关闭播放后能力 410，目录无未完成 part。真实进度与文件证据见 [real-result.json](download-real-result.json)，pageErrors/consoleErrors 均为空。

其余来源用 `verify_download_online.py` 经普通 API 做本期在线回归，未注入媒体或替换解析器：

| 来源 | 稳定 ID | 本期结果 | 实际字节 | 新文件 |
| --- | --- | --- | ---: | --- |
| 网易云 | 284617 | 新 Vue 完整下载，MP3 | 4,238,986 | 齐豫、齐秦 - 飞鸟与鱼 (4).mp3 |
| 酷我 | 9942644 | 普通下载 API 完成，MP3 | 4,346,545 | 银临 - 东风志 (2).mp3 |
| QQ | 001e7VNQ43nv4W | 普通下载 API 完成，M4A | 2,925,618 | 银临 - 牵丝戏 (2).m4a |
| 咪咕 | 600929000006452915 | 普通下载 API 完成，MP3 | 3,303,760 | 银临 - 一场雨的瞬间 (2).mp3 |

后三项不是声称都从新 Vue 搜索点过。各文件实际尺寸与任务接收量/总长一致，格式前缀和 SHA256 留于 [online-other-sources.json](download-other-sources.json)，没有保存签名媒体地址或认证头。原四个既有文件重新分块计算哈希，均保持不变，见 [file-checks.json](download-file-checks.json)；同名新文件带序号，旧文件未覆盖。真实音乐保留在被忽略的 downloads 目录，不纳入 Git。

## 受控并发、取消、重试与故障

`verify_vue_downloads.py --controlled` 使用独立 Core 8004/Vite 5182、临时下载目录、自生成可播放 WAV 和带 MP3 前缀的自有下载载荷。人工下载载荷只用于状态机和落盘断言，不冒称可播放的真实 MP3；真正音乐文件证据来自上一节。

验证项目：

- 三条具体版本任务同时提交，前两条 downloading、第三条 queued，服务端并发始终不超过 2；取消第二条后第三条继续。
- 未知总长任务实际收到 65536 字节，UI 不显示百分比，progress 无 value；取消不发布半文件。
- 挂起旧任务列表，在真实取消返回后才放行；已取消状态未被旧 downloading 覆盖，后续查询恢复一致。
- 服务端任务恰好已 completed 而 UI 还显示下载中时点击取消，返回并展示真实 completed，文件保留；不强行改成已取消。
- 故意拒绝人工歌曲 4 的第一次 download resolve，UI 显示平台拒绝；重试确实再次 resolve，创建不同任务 ID 并完成，旧任务保留“已重试”。
- 人工淘汰一个失败任务后重试得到真实 404；服务列表故意 503 后保留已有结果，手动刷新恢复。取消、失败和服务不可用分别呈现。
- 全部任务终态后等待 3300ms，任务列表请求数不增加；离开页面、返回页面和刷新均只使用根级查询器。
- 下载中真实 WAV audio 持续推进，暂停/继续、96 秒 Seek、音量保持、切歌正常。取消下载后播放 Lease 仍有效；始终同一 Audio。最终关闭播放后无活动媒体记录，任务 worker 和自身 part 均清空。

受控结果见 [controlled-result.json](download-controlled-result.json)：五次创建请求，重试另新建一个任务；download resolve 记录为 1、2、3、4、4、5。pageErrors=[]，Console 404/503 为刻意故障注入。没有把人工完成文件计入四来源真实下载。

## 浏览器、回归及运行入口

1440、768、390px 通过，移动端改为纵向紧凑信息，并保留实际文件大小；原全局播放器和底部 TabBar 继续显示，无横向溢出。浅色和深色使用现有主题。常用开发 Core 8001 在无活动下载时重启加载文件清单 API，5174 的真实文件页也验证通过；任务为 0、文件为 12，再次证明文件状态独立于内存任务。临时验收服务与进程树已收尾。

截图均来自实际运行新 Vue：

- [桌面文件列表](screenshots/download-desktop-download-list.png)、[真实下载中](screenshots/download-real-downloading.png)、[真实完成](screenshots/download-real-completed.png)
- [失败、取消与重试](screenshots/download-controlled-failed-cancelled.png)、[两并发与一排队](screenshots/download-controlled-downloading.png)
- [移动下载页](screenshots/download-mobile-downloads.png)、[深色下载页](screenshots/download-dark-downloads.png)、[重启后文件列表](screenshots/download-restart-file-list.png)

原 D1 受控浏览器恢复脚本在隔离端口 8006/5184 重新运行，测试逻辑不变、未修改旧脚本：renew 204/410、同 Audio 恢复、晚到 Lease、错误可重试、关闭四个能力全为 410；页面错误为空。原四来源无限滚动受控脚本使用本期隔离服务重新通过 40 个请求的完整验收，保留去重、失败重试、阅读锚点、晚到隔离、补屏上限和移动宽度断言；结果见 [受控结果](../15-搜索分页/controlled-result.json)，截图见[四来源受控页面](screenshots/download-controlled-four-sources.png)和[受控移动端](screenshots/download-controlled-mobile.png)。

`pytest -o addopts= -q`：521 passed（原 518 项保留，新增文件清单边界三项），仅既有 Starlette/httpx 提示。`pnpm test`：35 项通过（原 33 项播放器、队列、歌词测试保留），新增进度和错误展示边界。typecheck/build 通过。下载及设置路由改为懒加载，主 JS 约 499KB，下载页约 6.9KB，没有提高体积告警阈值。

## 改动范围与明确限制

后端只在原 DownloadManager 边界增加只读 files 方法、SavedDownloadFile 和文件清单路由，未改变传输、解析、并发、发布、取消或重试实现。公共 Core 契约增加文件 DTO/端点，原下载 Task/Request 不变。前端增加 useDownloads、DownloadItem 和展示工具，扩展 downloads API/安全错误信息，接入根提供者与 SongItem，恢复 DownloadsView。无新增依赖、Pinia、WebSocket、第二套下载器、转码或播放器改造。

实际限制：没有跨后端重启恢复任务；没有永久准确的平台历史数据库；没有文件删除、受控成品下载到浏览器、OS 文件管理器或本地文件播放入口。复制操作仅复制文件名。目录手动变化需刷新、重新进入页面或恢复可见后查询，非实时文件监听。防重复限当前客户端和当前服务返回的任务，不是跨客户端幂等。真实第二版本 284782 本轮失败，取消与播放并发、失败重试等完整状态覆盖由受控实验完成。视口与触摸环境为 Chromium，未声称经过真机 Safari。

首轮人工 Provider 缺少必填 representation 导致 fixture internal_error，已修正后重跑；默认媒体 TTL 的保留记录也未被误报为生产泄漏，最终受控清理用短 TTL 验证。重复真实验收造成的新增序号文件保留在下载目录，未删除用户既有文件。截图和临时媒体按原 .gitignore 处理，源码组件使用未被忽略的 download 目录。
