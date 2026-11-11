# 12 歌词消费一致性 — 阶段 12：QQ路线收敛与消费一致性

2026-11-07。历史报告保留。

## 收敛与配置

删除app/providers/qq_resolvers/qqovo.py及QQProvider导入/分发/有效路线项，删除10项仅验证旧签名、Bootstrap、Session及旧停用行为的测试。保留有价值的调查记录。三个独立验收脚本也清理qqovo调用，避免删除模块后残留ImportError；server/README.md更新当前配置说明。含qqovo的route_order会明确报“qqovo 已移除，请从 MUSIC_CORE_QQ_RESOLVER_ORDER 删除该名称”，不静默跳过。

最终路线只有official、vkeys、tang、xunhuisi。**无配置时默认顺序与实际启用均为official**，不是看似四条而实际只执行一条。未自动把三条外部路线设为全局默认：既有有限协议成功和巡回寺require_key=0只能证明当前技术调用/公开匿名接口，不能等同完整内容授权、长期服务条款或所有用户资源权限。今日重新尝试通过浏览工具查看三站根页均未取得完整条款，故不编造其默认使用授权。

在已确认对应服务及目标资源使用条件的本机环境，可直接显式设置：

```powershell
$env:MUSIC_CORE_QQ_RESOLVER_ORDER='official,vkeys,tang,xunhuisi'
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

无需MUSIC_CORE_DEV_PLAYER；该开关只开放/dev/player。服务初始化在明确配置外部路线时启用已有受限请求绑定处理；Provider内部enabled_external_routes/available_routes控制调用资格，allow_request_bound控制缺独立MID回显时是否允许受限使用，二者是不同判断，没有引入新管理层。直接构造Provider的调用方不启用对应条件时，仍不执行外部路线或不接受URL-only，不能因脚本实例化和服务配置不同误认为播放/下载配置不同。

将development_preview构造参数改为allow_request_bound、诊断scope改为configured_preview，明确它是证据受限状态，不表示开发页面已开启，也不声称正式身份或版权授权。当前正常API与开发页没有两套URL-only规则。无响应MID不判成协议格式错误；允许条件下探测媒体并保留request_bound，未允许时原有MEDIA_UNAVAILABLE处理保留。错MID、明显其他版本、具体目标/DNS规则及明确401/403停止均未删除。链接回显不冒充独立response_mid。

策略始终是**首个合格结果优先，不是最高音质优先**；前一条MP3成功后不继续寻找可能的FLAC。串行、成功停止、取消、25秒预算及错误分类保留。

## 播放与下载源码追踪

main.py在lifespan只创建一份state.qq。playback.py经provider_for(state,identity.providerId).resolve使用该实例；downloads.py同样取同一state实例、以稳定身份及ResolveOptions(purpose=download)重新解析。两种purpose进入同一QQ路线循环，只有消费者不同。下载不读播放URL、Lease、audio、队列或搜索Session；失败重试创建新任务并重新resolve。按实际前缀识别扩展名，核对HTTP及实际磁盘大小，不按搜索或quality猜格式。

**没有发现新Core必须先播放才能下载的问题，因此未改DownloadManager。** 旧实现现象的根因本期未追查，不能用新Core结论反推旧实现。也未把播放成功自动变成资源保存授权，明确上游拒绝仍停止。

## 本期新真实验收

### 直接下载先于播放

全新create_app，无预先open/搜索、无Lease，运行verify_download.py --provider qq --track 001e7VNQ43nv4W --title 牵丝戏 --artist 银临。默认official，正常POST /api/downloads从queued→resolving→downloading→completed，多次进度增长。

实际保存downloads/银临 - 牵丝戏 (2).m4a，2925618字节，与总长度一致，前缀00000020667479706d70343200000000。SHA256为dc7bb37453301b31d563ed835b6e1fb2fb2a5a8d480210b442a9d90c9c82466c。本地Chromium时长239.420952、error=null。activeWorkers/MediaStore/PlaybackLease/part全部0。文件为本期新传输，非沿用阶段 11；已有同名文件未覆盖。

这证明技术上的完整保存；没有独立新增的平台版权许可证明。受控自有字节测试另验证合法模拟媒体直接下载及备用回退，不以在线可播放推断普遍可下载。

### 正常多线路自然回退

设置四条顺序后，对QQ齐豫《飞鸟与鱼》00319yHq0w3PUX运行原verify_playback_browser.py --recover。本期真实观察到两次解析均按official→vkeys→tang→xunhuisi：official无媒体、vkeys upstream_failure；Tang初次upstream_timeout、重开upstream_failure；巡回寺成功。不是人为构造的在线失败、不是仅适配器单测；受控完整失败矩阵另见下文。

媒体M4A，6706802字节，277.408798秒；初始2.028264、继续3.054441、中段139.221872、近末尾261.281621；error=null。重开261.315905、新Lease/同audio、paused=true/volume=.3/rate=1.2保持。初次resolve1次，重开后总2次，成功后不再执行其他路线；scope=configured_preview、identity=request_bound。关闭410，records/streams=0。这里QQ录音不等同网易云同名录音。

## 受控验证与回归

新增test_qq_consumers.py：同一个正常应用，先创建下载再open，人工_route替身只控制各路线结果、传输走真实DownloadManager及MockTransport自有ID3字节。官方成功、官方无媒体→vkeys、官方无媒体→vkeys临时失败→Tang临时失败→巡回寺、官方ACCESS_DENIED四组，分别断言download/playback的准确串行调用序列、成功后停止和无重复resolve；下载前后Store/Lease为空、实际文件字节一致。该替身验证编排，不冒充第三方协议成功。另有qqovo配置明确失败测试。原URL-only证据/受限处理、取消/预算、媒体目标、下载清理测试继续通过。

最终pytest **513 passed**：518减10项废弃测试，加5项一致性/配置测试。17项Node恢复测试经已有pytest包装通过，不重复累加。一个既有Starlette/httpx弃用警告。app/scripts compileall通过，git diff --check通过。

四来源默认正常播放回归均运行原--recover脚本并退出0：kuwo9942644、QQ official001e7VNQ43nv4W、netease30352891、migu600929000006452915；暂停/继续/Seek/稳定身份重开、新Lease同audio及关闭回收通过。8项受控恢复全部通过，records/streams/leases=0、singleAudio=true。受控下载取消/断流并行脚本退出0，文件清理与响应关闭、audio推进、同audio及Lease/open次数不变。故障fixture无get_lyrics会产生隔离安全500；预期断流RuntimeError及既有WindowsProactor10054不影响验收断言。

## 文件及边界

业务修改仅QQProvider与main.py；删除qqovo模块。修改三个旧验证脚本及四份QQ测试、server/README.md；新增test_qq_consumers.py和本报告。公共模型、MediaStore、PlaybackLease、DownloadManager、恢复协调器及其他Provider未改。保留相关研究记录和Git历史。

仍无完整外部资源授权或长期可用保证，故不默认开放三条外部路线。不新增品质系统、并发竞速或缓存；显式配置的当前调用与请求绑定证据不等于所有歌曲均获正式身份及访问确认。
