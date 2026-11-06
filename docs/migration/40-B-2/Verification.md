# 40-B.2：巡回寺验证与最小接入

2026-11-06。唯一写入业务工程C:/Code_Home/2_projects/musicdl-lab；旧Lab、冻结库仅读取。开始已有未跟踪docs/research/调查报告，保留未动。没有新增依赖、提交Git或开始下一阶段。

## 公开条件与协议

查看[巡回寺官网](https://api.xunhuisi.store/)及其首页实际调用的[公开接口清单](https://api.xunhuisi.store/api/list.php)。首页提示部分接口要登录获取key，不能据此统一认定所有接口匿名。QQ接口条目id=3，status=normal、require_key=0；当前参数文档列name/id、n/list、type、quality，未明确列出旧mid别名；未发现该条目的明确QPS数值。首页要求勿将免费接口倒卖收费。本期仅有限个人开发调用，不据此断言音乐版权、所有资源下载或商业用途授权。

冻结qq.py:250–265的_parsewithxunhuisiapi使用GET /API/QQMusic/Song.php?mid=...&type=json，读取music_url/title/singer等。本期真实匿名调用证明mid别名仍工作，无Cookie、Token或API Key，也没有登录申请步骤。HTTP200与code200之外，还验证了媒体字节；没有仅凭网站宣传的FLAC能力猜实际格式。

## 两个固定样本

| QQ songmid | 返回title/singer | HTTP/业务码 | 实际媒体 | 字节总量 |
|---|---|---|---|---:|
| 001e7VNQ43nv4W | 牵丝戏 / 银临 | 200/200 | M4A，ftyp，audio/mp4 | 5805847 |
| 00319yHq0w3PUX | 飞鸟与鱼 / 齐豫 | 200/200 | M4A，ftyp，audio/mp4 | 6706802 |

仅2首，不扩展曲库、不调查备用候选。返回字段为code/msg/title/singer/cover/link/music_url/quality/lyric/trans/ck_info/api。未保存完整歌词、ck_info内容或签名媒体地址。两个目标均为isure6.stream.qqmusic.qq.com，现有QQ域名规则可直接验证；未新增白名单，复用core/media_probe.verify_media取得4096字节证据和上述representation。

响应无独立mid/song_mid字段；link回显对应y.qq.com/n/ryqq/songDetail/MID。Adapter核对该链接ID；若显式mid字段出现，也按现有result严格核对。链接不回填response_mid，证据维持request_bound，不冒充confirmed。牵丝戏响应歌手只银临，原录音资料可能包含Aki阿杰，不宣称完整歌手集合完全一致；未做声学指纹鉴定。没有明显伴奏/Live标题；Adapter拒绝此类版本标记。

## 最小接入

新增server/app/providers/qq_resolvers/xunhuisi.py，只有请求、响应/链接核验、错误处理及现有RouteResult映射。复用request_json的10秒/2MiB限制、认证隔离、取消关闭和固定错误分类；不携带客户端Cookie。QQProvider分发和现有允许路线列表增加xunhuisi；main.py既有服务配置启用逻辑同步增加该名字。默认仍official，既有vkeys/Tang/qqovo不删、不改协议。

配置示例：

```powershell
$env:MUSIC_CORE_QQ_RESOLVER_ORDER='official,vkeys,tang,xunhuisi'
```

线路按配置串行、成功停止，临时失败才回退，明确401/403不回退，整体25秒预算不变。页面开关不决定线路执行；URL-only结果仅沿用现有受限预览scope，配置不授予平台资源权限。

## 正常API与浏览器

执行原scripts/verify_playback_browser.py --provider qq --track 001e7VNQ43nv4W --recover，临时Uvicorn的普通create_app、正常POST /api/playback/open及开发页，无替换Provider、无隔离URL播放。

MUSIC_CORE_QQ_RESOLVER_ORDER=xunhuisi,official：实际路由调用xunhuisi两次（初次及手动重开），未请求official，scope=development_preview、identity=request_bound。duration239.420952；初始推进2.044186，暂停继续3.068396，中段Seek120.237608、近末尾225.571449，seeking=false、error=null。重开225.605158、paused=true、volume=.3、rate=1.2、新Lease/同audio。关闭后410，records=0、streams=0，仅本地Origin。

另对00319yHq0w3PUX执行同一正常API浏览器脚本并通过：duration277.408798，初始2.045963、继续3.057230，中段139.219047、近末尾261.271617、重开261.308335；正常resolve1次、重开后2次，实际仅xunhuisi；error=null，同audio且暂停/音量/速率保持，关闭410、records/streams=0。该QQ录音时长不同于此前网易云284617，不按同名跨平台自动互换。此前40-A该QQ录音official为空媒体，而巡回寺本轮取得可访问媒体，说明提供了另一当前可用路径；未对所有歌曲、长期成功率或必定优于vkeys/Tang作推断。

## 测试及回归

518项pytest全部通过（504基线+14项），仅既有Starlette/httpx弃用警告。新增人工Fixture覆盖正常、空URL、错误结构、错MID/错链接、URL-only、明显其他版本、非法媒体URL、HTTP拒绝、超时及取消；原正常API测试增加页面开/关的xunhuisi组合，确认成功后停止、媒体不泄露、关闭回收；另测xunhuisi503后按配置进入official。已有整体预算、取消及权限停止测试保留。17项Node恢复用例由已有pytest包装执行，不另算pytest数量。

本轮四来源原播放脚本--recover均退出0：kuwo9942644、QQ official001e7VNQ43nv4W、netease30352891、migu600929000006452915；播放/暂停/Seek、新Lease同audio恢复及关闭回收通过。原8项受控恢复场景通过，最终records/streams/leases=0、singleAudio=true。故障fixture没有get_lyrics，额外歌词500日志与播放隔离；受控断流RuntimeError为预期，不改变生产逻辑。

下载原专项保留，另执行verify_download_browser.py：接收851968字节后取消，取消/断流响应均关闭，临时成品均无，audio从1.031881推进到2.074397，同audio、Lease及open次数不变，结束records=0。没有重复下载四平台完整文件，不把40-A结果当本期新下载。

Git修改为QQProvider、main.py、QQ应用路由测试及新增xunhuisi.py/test_xunhuisi.py/本报告；已有docs/research/保留。未修改公共ResolvedMedia、MediaStore、PlaybackLease、DownloadManager或恢复控制器。无新框架或依赖。当前独立录音指纹、内容授权和长期稳定性仍无充分证据，故保留原证据等级和访问边界。
