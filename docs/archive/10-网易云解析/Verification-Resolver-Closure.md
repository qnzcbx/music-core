# 10 网易云解析收口 — 阶段 10：具名候选复验、jfjt正常集成与收口

2026-11-06。本期只新增一条有真实播放证据的jfjt，不以线路或测试数量为成果。它是研究来源网易云L1的第9条，能够在GD之外通过正常播放API取得普通MP3。没有新增Registry、资格层、评分系统或依赖，没有修改公共媒体生命周期。

## 旧成功记录的追溯结论

对照既有网易云样本验证数据和研究来源路线顺序，并核对旧实现的候选解析行为。样本数据继续作为本目录实验记录，不引用其他任务工作区路径。

前两份真实播放记录的稳定ID分别为416388799、440240192，但路线记录仅标记官方编排入口；没有品质循环记录而媒体探测成功，说明结果可能来自外部解析，不能确定叶函数。叶子采样列表中的L1/L2多条urlObtained=false，最后统一记录fallback成功。观察脚本public字段白名单不保存叶函数来源，后期wire记录只保留category/stage/HTTP/Range等、不含Host或解析函数。因此这批历史证据仍无法可靠命名成功路线。

L1实际顺序为tmetu、xuanluoge、kangqiovo、chksz、znnu、xiaoqin、vincentzyu233、bileizhen、jfjt。L1被尝试不等于历史L1已成功；本期jfjt成功是新取得的具名证据，不反推它就是旧fallback的来源。

## 候选与有限实际结果

最初只选两条：jfjt（L1，表单POST）和rrvenn（L2，JSON POST）。两者都有研究来源实现、接受歌曲ID、无历史Session/嵌入密钥需求，服务域不同于GD。用户随后要求再测另一候选，追加chksz和xuanluoge的有限请求；没有扩展到其余30条。

| 路线 | 两个固定样本167691 / 416388799的实际结果 | 处理 |
|---|---|---|
| rrvenn | 向music.rrvenn.cn/Song_V1发JSON POST，两次ConnectError，215/6ms，无HTTP响应 | 未采用，不认定永久失效 |
| jfjt | 向dm.jfjt.cc/Song_V1发普通档位表单POST，两次HTTP200，414/206ms；success=true，返回id/name/ar_name/duration/url | 采用这一条，并继续媒体和正常API验收 |
| chksz | api.chksz.com/api/163_music，两个样本均HTTP429、code429，1641/566ms，无URL | 不采用、停止连续请求 |
| chksz单次补试 | 同一167691仍429，Retry-After=3600；消息为“今日站点通道额度已用完（每IP10次/天）”，1247ms | 具体阻塞是当前通道配额；不换IP或凭据绕过，之后不再请求 |
| xuanluoge | music.qinglvai.top/api/index.php，route=/music/url、level=standard、use=play、source=netease；两次ConnectError，1409/866ms | 无HTTP/URL，不采用，不继承旧实现verify=False |

没有把429当成永久下线，也没有将未返回HTTP的ConnectError猜成具体版权拒绝。追加候选未获得可用证据，因此不为了“再找一个稳定的”继续扫描。jfjt在本期单路API、正常浏览器初次open/重开以及最终独立复核均成功，但有限窗口不能证明长期稳定。

## 实际采用的jfjt协议与核验

新增netease_resolvers/jfjt.py，仅执行一次`POST https://dm.jfjt.cc/Song_V1`，表单url=稳定ID、level=standard、type=json。保留普通UA/Referer，不发网易云或QQ Cookie，显式Request/auth=None；请求最多10秒、响应最多2MiB、取消和错误关闭响应。不复用旧实现中的品质循环、文件大小推算、歌词或完整歌曲对象。

响应success/status/data按实际结构处理。若提供id，必须精确匹配；URL-only仍可解析为request_bound，不把请求ID回填。正常jfjt路径还使用网易云自身/api/v3/song/detail按相同ID取得详情，核对ID、完整标题与实际返回歌手集合：明确其他歌手或版本冲突拒绝，部分缺失不冒充完全一致。没有新增身份评分或全局状态。

真实167691响应为《天龙八部之宿敌》/许嵩，duration=263340；416388799为《明月天涯》/五音Jw，duration=241999。当前两个样本均有实际响应ID，且通过原生详情标题/歌手核对；这是响应和元数据证据，不声称完整音频指纹、母带或平台授权永久有效。

媒体直接交现有core/media_probe.py，逐跳目标/DNS安全检查、最多4096字节、不落盘媒体；没有新增Host规则，当前m701/m801.music.126.net已受信。第三方返回其他目标仍拒绝。

## 当前独立对照及价值

最终独立实测，不是把Mock当成功：

| 样本/路线 | API与媒体实况 | 耗时与身份 |
|---|---|---|
| 167691 Native | HTTP200，但单项-110，无URL | 164ms，原业务码保留；不推断VIP/地区/下架 |
| 167691 GD | API200，媒体206，bytes 0-4095/50893686，FLAC | 含探测3595ms，request_bound |
| 167691 jfjt | API200、原生详情200、媒体206，bytes 0-4095/4214326，MP3 | 含详情及探测631ms，response_id_matched，标题/歌手核对通过 |
| 416388799 jfjt | API200、原生详情200、媒体206，bytes 0-4095/3873271，MP3 | 含详情及探测442ms，response_id_matched，标题/歌手核对通过 |

jfjt当前提供不同于GD FLAC的普通MP3，服务入口也不同，确实增加了一条不必调用GD的可访问路径。但最终仍使用网易云CDN，不能声称所有上游故障点独立；也不能把不同表示的大小和少量耗时差推断成普遍性能排名。仅167691新路线通过了浏览器，416388799完成正常Provider独立详情/媒体验证，没有假称两首都做了完整浏览器或下载。

## 顺序、503回退与正常播放

继续唯一配置，默认native保持：

```powershell
$env:MUSIC_CORE_NETEASE_RESOLVER_ORDER='native,gdstudio-preview,jfjt'
```

可省略或调整任一路线，不依赖MUSIC_CORE_DEV_PLAYER。当前全部外部使用仍是操作者明确配置的受控范围，URL-only及权限事实不被自动提升。成功立即返回、共用25秒预算；明确权限拒绝/错录音继续拒绝，不以外部资源规避限制，超时及503仅在预算内进入下一路，无无界重试。

本期没有自然出现一次完整的“Native无媒体＋GD503＋jfjt成功”组合。**用正常API的MockTransport准确模拟该组合**：记录顺序music.163.com→music-api.gdstudio.xyz(503)→dm.jfjt.cc→网易云详情→受信媒体，最后open200、MP3表示入Store；成功后不执行其他路线。将详情改为不同标题时返回502且不探测媒体。Mock仅证明编排，jfjt当前实际可用性由上方真实请求和下方浏览器单独证明。

正常浏览器验收命令（没有替换Provider或响应）：

```powershell
cd server
$env:MUSIC_CORE_NETEASE_RESOLVER_ORDER='jfjt,native'
./.venv/Scripts/python.exe -m scripts.verify_playback_browser --browser $env:CHROMIUM_PATH --provider netease --track 167691 --recover
```

两次open均正常命中jfjt，媒体公开表示MP3、4214326字节。duration263.340408秒；初播2.019189、继续3.035781、中段132.182706、近末尾248.054677秒，error=null。关闭旧Lease后同ID重开恢复248.088761秒，paused=true、volume=.3、rate=1.2，新playbackId、同audio。正常Resolve1次、总2次，未调用后续native；metadata2次、playing/pause/seeking/seeked各4次。关闭后410，记录/活动Stream0，浏览器仅本地Origin。

这证明新增jfjt可通过正常播放链路运行，不是隔离脚本URL成功。独立native模式30352891也通过真实播放、两处Seek及重开：中段120.166912、近末尾225.458213、重开225.517503秒，最终零引用。

## 回归、文件与收口

其他三来源真实播放/暂停/Seek/稳定身份重开都通过：酷我9942644（中段136.320877、末段255.807179、重开255.864809）；QQ官方001e7VNQ43nv4W（120.229339/225.574038/225.609514）；咪咕600929000006452915（103.719743/194.533598/194.567335）。均正常1次/总2次Resolve，关闭410、最后记录/活动Stream0；QQ运行出现既有Windows Proactor WinError10054回调，断言与退出码正常。

17项Node和8项受控恢复场景通过，受控断流产生预期固定RuntimeError，最后记录/活动Lease/Stream0。429项pytest通过（原417保留，12项新增必要协议/API回退测试），唯一既有Starlette/httpx弃用提示。测试数量仅是回归保障，不是本期可用性成果。

相对4E，仅新增jfjt.py、tests/test_netease_jfjt.py，并扩展NeteaseProvider原有循环及必要的原生详情核对，未新增运行依赖、永久资格层或Resolver框架。公共模型、Store/Lease/Range/RecoveryPlayer和其他Provider业务不变。

网易云解析器在此停止扩建：保留Native、GD及本期有当前播放价值的jfjt。未确定的长期服务稳定性、访问条件和独立音频指纹不能靠继续堆解析器解决。当前tasks目录未发现阶段 11任务文件，本期按任务边界未擅自开发下载队列或转码。
