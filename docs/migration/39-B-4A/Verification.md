# 39-B.4A 验收

日期2026-11-05；Windows Python3.10.10、新项目server/.venv；Chromium153.0.8010.12。开始Git工作区干净，使用用户已有分支，未init/branch/commit/push。旧项目与冻结库只读。

## 离线

`./.venv/Scripts/python.exe -m pytest`最终**193 passed**，保留原159项，新增34项QQ测试；原内部17项Node恢复测试继续通过，不重复计入pytest数量。仍有1条已知Starlette/httpx弃用警告。

覆盖真实协议形状的脱敏映射/空与缺字段/多歌手/ID区分、分页/输入/异常结构、业务错误、timeout/cancel单次停止、purl与完整URL、缺地址/错songmid、凭据私有、档位/加密格式拒绝、QQ进入Store/Lease与酷我隔离、同字符串ID跨平台不冲突、域名/公网DNS及跨域拒绝、QQ Cookie不进入酷我请求。原Range200/206/416、关闭、取消、恢复与数据清洗测试不回归。所有普通pytest无公网调用。

## 真实搜索与取链

先离线通过，再运行`./.venv/Scripts/python.exe scripts/verify_qq.py`。未配置登录Cookie。

| 搜索词 | 候选/有效mid | 搜索耗时 | 选定mid |
|---|---|---:|---|
| 许嵩 | 10/10 | 690ms | 001bLkWD2EYA4P、003MUDkf30pS5B |
| 银临 | 10/10 | 436ms | 001e7VNQ43nv4W、003O5FvJ1j8UdV |

四次正式取链结果：前三个表列的许嵩两首和银临第二首均media_unavailable（没有purl）；**001e7VNQ43nv4W成功**。成功1/4是本次选样结果，不是平台客观成功率。没有将搜索成功或HTTP200当媒体成功。

成功路径为QQ自身music.vkey.GetVkey.UrlGetVkey；媒体Host=aqqmusic.tc.qq.com，HTTP206、audio/mp4、前4096字节包含MP4 ftyp，Content-Range总大小2925618bytes，未发生重定向。没有完整下载或精确AAC编码检测，有效期未知。

调查范围：冻结库移动搜索RPC及desktop对照对同一已知关键词返回空列表；QQ自身client_search_cp返回10条，故正式search只采用后者。取链对照中不同上下文曾出现RPC1000或104009，普通QQ平台旧GetVkeyServer路径也没有解决该样本；没有把它们作为权限不足证据。初期终端管道存在中文编码显示歧义，随后用UTF8文件及Unicode转义排除，正式统计只取可复现脚本结果。不扫描第三方站点。

另用实际ASGI API边界（TestClient，但上游为真实网络）POST /api/search选择QQ/银临，200返回10条，10条均有album/cover/duration/artists；/api/providers保持顺序及默认酷我，QQ/酷我search+resolve为true，网易/咪咕均false。这个补验不是浏览器播放证据，浏览器见下节。

## QQ真实Chromium

```bash
./.venv/Scripts/python.exe scripts/verify_playback_browser.py --browser C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe --provider qq --track 001e7VNQ43nv4W --recover
```

脚本实际启动独立Uvicorn，端口51170，走现有open/Stream API。浏览器所有请求均为本地Origin。

| 项目 | 结果 |
|---|---|
| metadata | duration=239.420952秒 |
| 初始播放 | currentTime=2.039836秒 |
| 暂停/继续 | 继续至3.058781秒 |
| 中段seek | 120.230391秒，seeking=false、error=null |
| 近末尾seek | 225.575195秒，seeking=false、error=null |
| 正常Resolve | 1次，无误恢复 |
| 最小恢复 | 服务端显式关闭旧Lease后，点击已有“重新打开当前歌曲”；稳定songmid重新解析，new/old playbackId不同 |
| 恢复结果 | 225.609919秒，保持paused=true、volume=.3、rate=1.2，同一个audio DOM |
| 总Resolve | 2次，第二次对应上述显式恢复，不是正常播放额外取链 |
| 最终关闭 | 新请求410，remainingRecords=0、activeStreams=0 |

实际206范围包括`bytes 0-2925617/2925618`、`bytes 131072-2925617/2925618`以及`bytes 2719744-2925617/2925618`，末段Content-Length=205874。没有在HTML或API响应中暴露上游URL/headers。QQ恢复这里是**已知旧会话关闭后的手动入口验证**，不是人为伪造MediaError后宣称自动恢复；完整自动恢复矩阵另用自有WAV回归。

## 酷我与恢复回归

新代码运行原酷我浏览器脚本，端口56588，录音9942644：时长271.583107秒；播放2.038412→暂停→3.058610；中段136.305731、末尾255.800995秒均继续且无error。正常Resolve1次；关闭后410，媒体/流引用零，浏览器只访问本地。

原verify_recovery_browser.py受控WAV矩阵再次通过：Lease到期7.644785→7.673028秒，volume=.4/muted=true/rate1.25保持；暂停7.703202→7.703202；中途断流实际MediaError2、一次自动open、brokenStreamClosed=true；重复重试、失败再手动、恢复中停止/切歌/暂停均通过；最终记录、活动流、活动Lease为0，唯一audio未替换。预期断流安全RuntimeError日志不是额外产品错误，也未产生JSON替换已开始的响应。

## 文件与依赖

新增：app/providers/qq.py、scripts/verify_qq.py、tests/test_qq.py及本目录三份文档。修改：providers/__init__.py固定两来源查找、main.py装配/搜索分发、playback.py通用Provider分发及返回identity核对、media_stream.py按Provider目标策略、core/errors.py上下文拒绝错误、config/__init__.py真实能力状态、player.html一个来源选择字段、通用浏览器验收脚本及三份原测试的未接入断言。

同步根/后端README和长期架构状态说明。MediaStore、PlaybackLease、PublicMedia/ResolvedMedia、恢复协调器、酷我Provider代码和默认来源配置无修改。无新增依赖；pip check正常。源码不依赖旧目录，无完整musicdl，无新前端/专属QQ播放API/观察系统。

工作区差异待用户审阅，未提交推送；临时验收服务与浏览器已关闭。报告、fixture和日志不保存可复用播放ID、完整签名URL、vkey或Cookie。

## 尚未解决

三个样本没有媒体地址，原因未确认；匿名媒体可用范围不能外推，登录场景未真实验收。GetEVkey签名/加密媒体解密、微信/OAuth凭据刷新、完整下载均未实现。可信Host策略只覆盖当前已确认域，不是所有QQ CDN；新Host需要先核对再扩展，DNS未绑定连接IP的旧限制仍存在。

后续建议按合法访问需求建立少量可回归QQ样本与私有登录配置验收，再推进下一Provider/客户端任务；不靠第三方服务或重写Core掩盖平台适配失败。本次未开展下一阶段。
