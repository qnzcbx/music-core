# 39-B.4C验证记录

日期2026-11-06。唯一写入工程为`C:/Code_Home/2_projects/musicdl-lab`。环境为Windows、Python3.10.10、新工程.venv、Node22.22.2、Playwright1.63.0、Chromium153.0.8010.12。没有使用旧虚拟环境、安装完整musicdl或新增依赖。

## 离线测试

先完成离线请求、字段映射和解码测试，再开始有限真实验证；根据真实双ID、目录及安全证据补充离线用例，最后执行：

```powershell
cd C:/Code_Home/2_projects/musicdl-lab/server
./.venv/Scripts/python.exe -m pytest -o addopts= -q
node --test tests/recovery.test.mjs
```

最终334项pytest通过，保留原260项，新增74项。17项Node状态机测试全部通过，已有一个pytest包装入口，不能另算为17项pytest。唯一警告为既有Starlette TestClient使用httpx的弃用提示，未为此升级依赖。

新增覆盖：搜索正常/空结果、元数据缺失、多歌手、秒单位、非法和重复ID、相同名字及copyrightId下不同contentId不合并、分页及数字字符串totalCount；明确的请求参数和凭据隔离、双ID重建、全新Provider直接resolve、错配ID、空媒体、未知格式/大小/有效期、权限/业务错误、缺失资源、加密/试听/HLS拒绝、无效品质、响应上限、超时、取消关闭连接；明文与固定二进制解码向量及HTTP集成；四来源相同platformId的MediaRecord/Lease隔离、200/206/416、关闭与过期回收、恶意重定向与精确CDN/DNS规则。既有流取消、断流、恢复逻辑测试继续通过。

## 原生接口与身份核验

原生搜索：c.musicapp.migu.cn/v1.0/content/search_all.do。新增元数据重建：同域/v1.0/content/resourceinfo.do，resourceId=contentId、resourceType=2。取链：同域/strategy/listen-url/h5/v2.4，使用真实重建的contentId、copyrightId及所选目录项resourceType。冻结咪咕Client没有第三方Resolver链；未调用第三方服务、合成listenSong地址、迁入固定userId或改写音质路径。

只读冻结源码及旧Adapter后，验证详情接口可以精确重建双ID。四个录音的contentId/copyrightId/songId对照已记录于[Migu-Provider.md](Migu-Provider.md)。其中copyrightId包括6005861N5Z8和6005861N5Z9，真实证明不是只能保存为数字，也不能互换为contentId。详情与取链回显相同双ID；本期未尝试按歌名替换录音。

首样本详情length=00:03:26、needEncrypt=0；取链song.duration=206、audioFormatType=PQ、freeListenType=0；浏览器duration=206.4秒。公开搜索没有duration，不补造时长或在搜索时逐首resolve。响应version未作为身份、认证或有效期使用。

## 真实搜索、取链与有限字节探测

命令：`./.venv/Scripts/python.exe -m scripts.verify_migu`。每轮两个关键词各10条，每页前两条组成四首样本；每次最多读取4096字节，响应立即关闭，不落音频文件。共运行三轮相同四样本：初轮取链后媒体因尚未登记主机被安全策略拒绝；第二轮完成前缀验证；补充格式/试听拒绝与身份规则后最终复核。另对同一组ID作有限元数据字段核验，未扩展歌曲集合或线路扫描。

最终搜索记录：

| 关键词 | 耗时 | 返回/有效稳定ID | 有歌手 | 有专辑 | 有封面 | 有已知时长 |
|---|---:|---:|---:|---:|---:|---:|
| 银临 | 695ms | 10/10 | 10 | 10 | 10 | 0 |
| 许嵩 | 511ms | 10/10 | 10 | 9 | 10 | 0 |

最终四次取链和探测：

| contentId | 解析 | 实际档位 | 字节探测 | Content-Range总大小 |
|---|---|---|---|---:|
| 600929000006452915 | 成功 | PQ | HTTP206、4096字节、MP3 | 3303760 |
| 600919000009441501 | 成功 | PQ | HTTP206、4096字节、MP3 | 4433086 |
| 600929000002040501 | 成功 | PQ | HTTP206、4096字节、MP3 | 3613886 |
| 600929000002040505 | 成功 | PQ | HTTP206、4096字节、MP3 | 4155979 |

均为audio/mpeg、0次重定向、实际媒体主机freetyst.nf.migu.cn。每首使用新MiguProvider直接resolve，没有调用其search。Core中的codec/container/contentType/sizeBytes仍按Provider可证事实保持未知，表内大小来自媒体HTTP响应，不是以目录单位或文件后缀推断。4/4仅是选定样本结果，不代表全曲库。没有执行完整下载或授予下载能力。

## 咪咕真实浏览器播放与重开

```powershell
./.venv/Scripts/python.exe -m scripts.verify_playback_browser --browser C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe --provider migu --track 600929000006452915 --recover
```

脚本启动新临时服务，不使用已有服务，不先搜索。完整运行两次，最终一次在重开前更换MiguProvider实例，用同一contentId重新查询双ID。

| 项目 | 最终实际记录 |
|---|---|
| metadata时长 | 206.4秒 |
| 初播推进 | 2.024394秒 |
| 暂停/继续 | 暂停1.1秒位置保持；继续到3.047652秒 |
| 中段Seek后推进 | 103.723903秒，seeking=false、error=null |
| 近末尾Seek后推进 | 194.538621秒，seeking=false、error=null |
| 旧会话关闭 | 直接关闭旧Lease后，以相同TrackIdentity重开 |
| Provider重建 | providerReinitializedBeforeRecovery=true，不存在搜索映射或之前取链缓存 |
| 重开状态 | 194.564758秒，paused=true、volume=.3、rate=1.2 |
| 身份和audio | 新playbackId、同一个audio元素；返回媒体仍核对原contentId/copyrightId |
| Resolve次数 | 正常播放1次，含手动重开总计2次 |
| 浏览器事件 | loadedmetadata=2、playing=4、pause=4、seeking=4、seeked=4，无error事件 |
| 本地代理 | 实际206及远端范围；浏览器只访问临时本地同Origin |
| 最终关闭 | 旧/新Lease均关闭；新stream访问410；MediaStore记录0、活动Stream0 |

实际范围包括bytes 0-3303759/3303760、bytes 98304-3303759/3303760、bytes 3080192-3303759/3303760。播放结论来自原生事件、时间推进和Seek后的状态，而非仅凭206。两个独立进程的新服务均可直接按相同ID打开，服务进程内的搜索上下文不构成依赖；本期未验证长期离线后平台ID仍有效的时间保证。

## 三个既有来源真实回归

使用同一个浏览器脚本及`--recover`，分别传入kuwo、qq、netease及既有成功录音ID。均请求真实上游，没有Mock。

| 来源 | 录音 | duration | 初播/继续 | 中段/近末尾Seek | 重开位置 |
|---|---|---:|---|---|---:|
| 酷我 | 9942644 | 271.583107 | 2.050668 / 3.086515 | 136.310765 / 255.806410 | 255.846892 |
| QQ | 001e7VNQ43nv4W | 239.420952 | 2.041682 / 3.079788 | 120.224465 / 225.576753 | 225.611169 |
| 网易云 | 30352891 | 239.302336 | 2.054739 / 3.107467 | 120.171834 / 225.455249 | 225.490931 |

三者暂停/继续、两处Seek、新Lease/同audio重开、音量及速率保持均通过。正常Resolve各1次，总计各2次；原生metadata=2、playing=4、pause=4、seeking/seeked各4，无error事件。关闭后stream410，最终记录0、活动Stream0，浏览器仅本地Origin。网易云运行出现一次既有Windows Proactor远端断开WinError10054回调提示，脚本退出0且全部媒体/清理断言通过，没有为此关闭代理校验或忽略浏览器错误。

## 八项受控恢复场景

执行：`./.venv/Scripts/python.exe scripts/verify_recovery_browser.py --browser C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe`。

自生成48秒WAV，全部通过：真实Lease到期后续租恢复、暂停和重复重试合并、上游失效后的远端Seek、响应头后中途断流、自动预算及失败后手动恢复、恢复中stop/switch/pause。观察到原生MediaError2，中断上游连接被关闭；结束时MediaStore/活动Stream/活动Lease均0，singleAudio=true。故意断流产生预期固定RuntimeError类型日志，不含地址。该受控证据与四平台真实媒体证据分开。

## 文件、架构与Git

新增文件：

- server/app/providers/migu.py：原生搜索、精确详情重建、响应解码、双ID核验及普通取链。
- server/tests/test_migu.py：74项离线用例。
- server/scripts/verify_migu.py：有限真实搜索/取链/探测，无搜索缓存前提。
- docs/migration/39-B-4C/README.md、Migu-Provider.md、Verification.md：三份主要交付文档。

修改文件：

- server/app/main.py、providers/__init__.py、config/__init__.py：共享连接池初始化、固定四Provider分发、按真实样本更新咪咕状态。
- server/app/media_stream.py：新增咪咕实测精确主机策略，其他来源既有规则保留。
- server/app/player.html：已有开发页增加咪咕选项，不增加第二套播放器。
- server/scripts/verify_playback_browser.py：第四来源参数及咪咕重开前实例替换验证。
- server/tests/test_api_config.py、test_kuwo.py、test_media_stream.py：更新尚未接入假设，保留错误输入与生命周期断言。
- 根README、server/README、docs/migration/39-B-1/Music-Core-Architecture.md：同步四来源当前状态。

models.py、MusicProvider协议、MediaStore、PlaybackLease、RecoveryPlayer、来源顺序与默认选择均未修改。无新增依赖、数据库、持久映射、字节缓存、下载或Vue项目。

开始时Git工作区干净，结束时上述文件为工作区改动与新增文件；未重置已有内容，未git init、建分支、commit或push。git diff --check通过，仅有Windows LF/CRLF提示。旧项目和冻结版仅作只读参考。

## 已知限制与下一阶段

当前仅普通目录及渐进媒体；未知CDN继续拒绝，无法确认的双ID或媒体回显继续报错。更多歌曲、高品质、登录、同曲版本及版权ID全局基数、长时间后重启的外部有效性、完整下载均未验证；搜索时长缺失保持未知。DNS预检查和实际连接未绑定的历史局限仍在。下一阶段按新任务逐条优化覆盖率和必要解析路线，不自动开展聚合搜索、第三方扫描、队列或下一首预解析。
