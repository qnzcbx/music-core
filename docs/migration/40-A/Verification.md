# 40-A 验收记录

日期 2026-11-06；唯一写入业务工程为 `C:/Code_Home/2_projects/musicdl-lab`，旧 Lab 与冻结 musicdl 仅读取。开始 git status 干净。Python 3.10.10、新工程 .venv、Node22.22.2、Playwright1.63.0、Chromium153.0.8010.12；无新增依赖或 FFmpeg 调用。

## 实际成果

正常下载 API 已分别取得四来源完整文件，另取得一个 50.9MB FLAC；不把播放成功或响应头长度当成完成文件。`scripts/verify_download.py` 通过普通 create_app、POST /api/downloads、轮询 GET 验收，调用真实 Provider 和网络，不替换解析器。全文件按块计算 SHA256，并让 Chromium 直接打开本地文件读取 metadata。脚本未保存上游 URL、Cookie、认证头。title/artist 为调用方文件展示信息，未凭文件名冒称完整录音指纹验证。

| 来源 / 路线 | 稳定 ID | 文件 | 实际字节 / totalBytes | 本地时长（秒） | 总耗时 |
|---|---|---|---:|---:|---:|
| 酷我原有原生链路 | 9942644 | 银临 - 锦鲤抄.mp3 | 4346545 / 4346545 | 271.583107 | 31.19s |
| QQ official | 001e7VNQ43nv4W | 银临 - 牵丝戏.m4a | 2925618 / 2925618 | 239.420952 | 11.81s |
| 网易云 native | 284617 | 齐豫 - 飞鸟与鱼.mp3 | 4238986 / 4238986 | 264.8678 | 23.33s |
| 咪咕原生 | 600929000006452915 | 银临 - 一场雨的瞬间.mp3 | 3303760 / 3303760 | 206.4 | 1.98s |
| 网易云 gdstudio-preview（额外大文件） | 167691 | 许嵩 - 天龙八部之宿敌.flac | 50893686 / 50893686 | 263.340408 | 25.28s |

全部实际经过 queued/resolving/downloading/completed，轮询观察到 receivedBytes 持续增长；本地文件尺寸、接收字节和总长度一致，progress=1。MP3 前缀 ID3，M4A 前缀含 ftyp/mp42，FLAC 前缀 fLaC；本地 Chromium error=null。每次完成后 activeWorkers=0、MediaStore记录=0、PlaybackLease=0、自身临时文件=0。共享 HTTP Client 在应用 lifespan 退出时关闭；受控测试另直接断言每个响应 aclose。

保存位置为 `C:/Code_Home/2_projects/musicdl-lab/downloads`，被已有 .gitignore 排除。文件仍在本地，未提交媒体。

| 文件 | SHA256 |
|---|---|
| 银临 - 锦鲤抄.mp3 | f4eb772341a45ab70d37afd18d62e72082a56b90aa3dad3e58598fa0994c32b0 |
| 银临 - 牵丝戏.m4a | dc7bb37453301b31d563ed835b6e1fb2fb2a5a8d480210b442a9d90c9c82466c |
| 齐豫 - 飞鸟与鱼.mp3 | 922fea4a718125f628a7b86cd24ff3d0c8a86cbc16915681ad0124749dd7f912 |
| 银临 - 一场雨的瞬间.mp3 | 02911c8b51e31b6ea5eba315a54194e982ef160f877f7d3517c95eeaceaf534a |
| 许嵩 - 天龙八部之宿敌.flac | 5deba3a3bdb56473db9d8fcbcd80c38fb9a12ec9af5babd754aae693934bfe33 |

这是技术完整保存及本地可读证据，没有取得独立的平台版权/下载许可声明，不将“可取链”写成“已认证下载授权”。GD 额外实验仅使用原有配置 `MUSIC_CORE_NETEASE_RESOLVER_ORDER=gdstudio-preview`，未改默认 native 或新增路线；原 request_bound 局限保留。

## 《飞鸟与鱼》及真实失败

优先有限搜索用户指定歌曲。QQ 搜到齐豫稳定 MID 00319yHq0w3PUX，official 返回 media_unavailable；没有为该拒绝自动开启外部路线，改用已有普通样本验收 QQ 下载。酷我两次有限搜索（歌手+标题、标题）前10条均无标题及歌手同时精确匹配项，不拿翻唱替代。咪咕该搜索 upstream_timeout，改用原已验收稳定 contentId。

网易云搜索精确匹配到 284617；首次解析后目标校验报 untrusted_media。只检查原生返回主机，确认为 `m10.music.126.net`，因此补入这一明确 CDN，不放开整个 music.126.net。仍逐跳检查主机和 DNS，离线验证公共地址可通过、127.0.0.1及伪后缀拒绝。随后普通下载 API 成功保存用户指定录音。

酷我9942644及咪咕既有样本首次直接下载均在解析阶段 upstream_timeout、0字节；各一次独立重试后成功。无无限自动重试，失败不产生成品。一次并行验收时目录中曾有另一进程正在写的 .part，不能把全目录临时文件数当成当前失败任务泄漏；最终所有脚本收尾后无残留。临时名加入所属进程 PID，启动清理只删除明确已退出进程的文件，避免另一个活跃服务的临时文件被误删。

## 大文件与内存

真实 FLAC 为 50,893,686 字节，轮询从458752、1048576逐步推进至50593792再完成，前缀与容器一致；Windows GetProcessMemoryInfo 测得 Python 进程 RSS 从51,466,240到峰值56,311,808字节，增量4,845,568，未随约51MB文件线性增长。浏览器启动在传输完成后，不计入该 Python 进程采样。

另用按块实时生成的 **128MiB 自有传输载荷** 验证超过100MB的路径：134217728字节完整落盘，1026个不同进度采样，tracemalloc峰值363285字节。它只有受控 FLAC 前缀，不冒称真实有效FLAC录音；完整真实音频的证据来自上一项。测试不预先构造128MiB大 bytes，也不访问公网。取消另用可控慢速流完成，没有重复下载大文件来模拟取消。

## 取消、断流与播放并行

`scripts/verify_download_browser.py` 使用自生成48秒WAV、真实 FastAPI/Uvicorn 和 Chromium，不访问音乐平台。原生 audio 已播放至1.019342s时启动独立慢速下载；接收851968字节后取消：downloading→cancelled，上游响应关闭，临时及最终文件均无。再创建另一个任务，已产出媒体字节后抛 ReadError，任务 failed，连接关闭且无成品。

audio 同一 DOM 节点，继续到2.065909s、paused=false、error=null，原 Lease集合及播放 open次数不变，没有触发恢复。播放器关闭后 MediaStore清零。离线同时覆盖排队取消、解析取消、重复取消、关闭服务、临近发布的取消传播竞争，以及 completed 后取消不删文件。

## 回归与专项测试

最终 `./.venv/Scripts/python.exe -m pytest -o addopts= -q` 为 **484 passed**，仅1条既有Starlette/httpx弃用警告。原429项用例保留对应职责，下载从不支持变为支持，因此旧purpose=download拒绝断言更新为不支持的品质选择；四平台原有成功解析用例都增加 download purpose 对照，共多4项。新增下载专项51项，包含200、完整/部分206、长度不符、未知长度、格式、提前断流、读取超时、403/404/429/503、大小上限、重定向/目标拒绝、进度、身份/有效期/格式/已知大小冲突、取消传播及响应关闭。

文件专项覆盖Unicode/保留设备名/穿越/长名称、并发同名及已有文件保护、不可作为目录的路径、PermissionError、写入磁盘错误、fsync及原子发布失败、临时文件清理、重启残留。两任务同时执行、第三任务等待、排队容量、重新resolve重试、终态和发布边界竞争、下载失败不释放已有播放 Lease 均验证。普通pytest全部离线MockTransport；未增加在线测试依赖。

17项 Node恢复测试全部通过（其中已有一个pytest包装，不重复计数）。原8项受控浏览器恢复场景全部通过，断流响应确实关闭；最终 records/streams/leases=0，singleAudio=true。测试故意中断时出现固定安全 RuntimeError 日志，属于预期故障观察。

四来源真实播放回归均运行原 verify_playback_browser.py --recover，使用既有原生样本：

| 来源 | 中段 seek | 近末尾 seek | 重开位置 |
|---|---:|---:|---:|
| kuwo 9942644 | 136.310226 | 255.800963 | 255.861134 |
| qq 001e7VNQ43nv4W | 120.229213 | 225.588866 | 225.651909 |
| netease 30352891 | 120.169931 | 225.463521 | 225.529527 |
| migu 600929000006452915 | 103.722663 | 194.560542 | 194.676021 |

四者初次resolve各1次，手动重开后总计2次，新Lease/同audio、暂停状态/volume=.3/rate=1.2保持；关闭后410，records/streams=0，error=null。咪咕回归仍重建Provider，证明不依赖旧搜索Session。Windows在并行浏览器收尾偶见既有Proactor WinError10054，脚本断言及资源清理均通过。

## 文件、依赖与限制

新增 app/downloads.py、scripts/verify_download.py、scripts/verify_download_browser.py、tests/test_downloads.py 及本目录两份文档。修改 main.py 挂载及关闭管理器、config/__init__.py 下载能力标记、四Provider允许download用途、media_stream.py补充实测m10主机，以及对应原有契约/Provider测试。没有修改播放器控制器、MediaStore或Lease实现。无新增依赖，pip check通过。

开始Git干净；结束改动均为本期上述文件，媒体及运行产物由现有ignore排除。未git init、提交、推送或修改旧项目。任务历史只在内存；不支持转码、品质选择、标签、续传、批量歌单、跨重启恢复及正式Vue界面。未知长度采用受限正常EOF与前缀检查，不提供全文件音频CRC保证；文件系统必须支持硬链接，已验证Windows NTFS。更完整的API、限制及运行方法见同目录 README.md。不自动开始40-B。
