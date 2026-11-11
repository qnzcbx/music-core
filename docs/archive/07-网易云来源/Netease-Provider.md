# 07 网易云来源 — 网易云Provider与Resolver调查

## 本地依据与实际编排

调查依据为研究来源中与网易云有关的搜索、原生取链和外部解析调用记录，以及旧实现的搜索和取链行为。没有导入或复制研究来源代码，也未使用其账号或会话材料。

研究来源中的流程会在搜索后逐首尝试外部解析，再按条件调用平台原生取链，并通过媒体探测筛选结果。外部路线可能先于原生接口执行，因此该流程中的成功不能单独证明原生匿名取链可用。当前Provider搜索只返回元数据，媒体仅在播放请求时按稳定身份解析。

研究来源包含按会话状态选择外部路线、按优先级尝试并在媒体探测通过后停止的逻辑。相关账号和授权条件不属于当前实现；本项目不使用研究来源中的账号、令牌或请求密钥。

旧实现曾复用搜索与取链流程，并将外部解析结果纳入品质选择；它没有把原生取链与第三方路线完全隔离。因此旧实现中的可播结果不能代表匿名原生接口本身可播。

## Provider / Resolver依赖关系表

表内“原生”根据请求的实际网易云域名判断；外部服务即使接受网易云链接或提供同名接口，仍属于第三方。第三方全部未采用、未在线测试：原生普通路线已有可播样本，继续访问它们没有本期必要性。它们的访问限制、运营者授权、返回录音一致性和当前可用性均未确认。

| 路线 | 实际来源与接口 | 输入 | 输出、研究来源作用与条件 | 本期采用 |
|---|---|---|---|---|
| Native Search | music.163.com/api/cloudsearch/pc | s/type=1/limit/offset表单 | result.songs/songCount，搜索元数据 | 是，原接口 |
| Native Detail | interface3.music.163.com/api/v3/song/detail | c中的id/v | songs元数据；仅原搜索信息不足时补充 | 否，按ID取链不需要 |
| Native EAPI Resolve | interface3.music.163.com/eapi/song/enhance/player/url/v1 | ids/level/encodeType/header，部分品质immerseType；EAPI params | data[0].url；循环jymaster至standard，受Cookie权限影响；可能被第三方有效结果替代 | 否，无需高品质及加密 |
| 平台普通取链 | music.163.com/api/song/enhance/player/url | ids数组JSON字符串、br=128000表单 | 返回单项id/code/url/br/size/expi，普通取链 | 是；已在线验证 |
| Native Lyric | interface3.music.163.com/api/song/lyric | id及歌词版本参数 | lrc；原取链成功后补充 | 否，本期无歌词能力 |
| Third-party L1 tmetu | music.tmetu.cn/api/?miss=songAll | id/level/withLyric | JSON媒体URL及元信息，按品质尝试 | 否 |
| Third-party L1 xuanluoge | music.qinglvai.top/api/index.php | route、id、source=netease等 | 媒体URL、detail、lyric；源码部分请求关闭TLS校验 | 否 |
| Third-party L1 kangqiovo | ncm.kangqiovo.com/Song_V1 | url=歌曲ID/level/type | JSON媒体URL；源码关闭TLS校验 | 否 |
| Third-party L1 chksz | api.chksz.com/api/163_music | id/level | JSON媒体URL | 否 |
| Third-party L1 znnu | music.znnu.com/api/key → /api/song | id/level/rawInput、随机IP、时间戳、签名 | 动态keyToken/key、AES-GCM结果；依赖内置签名上下文 | 否 |
| Third-party L1 xiaoqin | 外部歌曲信息与媒体接口组 | 歌曲ID、品质及请求上下文 | JSON媒体及元信息；研究来源提示该路线存在TLS校验限制 | 否 |
| Third-party L1 vincentzyu233 | xwl.vincentzyu233.cn:51217/v2/music/netease（HTTP） | id/quality=9 | data.url | 否 |
| Third-party L1 bileizhen | api.bileizhen.top/api/netease | id/level及X-Api-Key | JSON媒体URL；源码内嵌可解码请求key | 否 |
| Third-party L1 jfjt | dm.jfjt.cc/Song_V1 | url=歌曲ID/level/type | JSON媒体URL | 否 |
| Third-party L2 xunjinlu | api.xunjinlu.fun/apis/wymusic | action/song id/level/key | JSON媒体URL；内嵌请求key | 否 |
| Third-party L2 bugpk | api.bugpk.com/api/163_music | ids/level/type | JSON url，原方法排除outer/url形式；源码关闭TLS校验 | 否 |
| Third-party L2 xingmian | api.xingmian.bbroot.com/API/netease_music_api.php | id/quality/apikey | JSON媒体URL；内嵌请求key及品质映射 | 否 |
| Third-party L2 rrvenn | music.rrvenn.cn/Song_V1 | url=歌曲ID/level/type | JSON媒体URL | 否 |
| Third-party L2 haitangw | musicapi.haitangw.net/music/wy.php | id/level/type | JSON媒体URL | 否 |
| Third-party L2 guyuei | www.guyuei.com/music/163.php | 网易云song链接/yinzhi | 编码媒体地址，原方法自行解码 | 否 |
| Third-party L2 cunyu | www.cunyuapi.top/163music_play | id/quality/api_token | JSON媒体URL；内嵌请求key | 否 |
| Third-party L3 nanorocky | metingapi.nanorocky.top/ | server=netease/type=url/id/br | 直接媒体或重定向，需通过媒体字节检查 | 否 |
| Third-party L3 yutangxiaowu | api.yutangxiaowu.cn/api/music/Song_V1 | url=歌曲ID/level/type | JSON媒体URL | 否 |
| Third-party L3 cocodownloader | cocodownloader.markqq.com/api/url | id/provider=netease/quality | JSON媒体URL | 否 |
| Third-party L3 ff | ffapi.cn/int/v1/netease_url | id/quality | JSON媒体URL | 否 |
| Third-party L3 gdstudio | music-api.gdstudio.xyz/api.php | types=url/id/source=netease/br | JSON url | 否 |
| Third-party L3 qjqq | metings.qjqq.cn/Song_V1 | url=歌曲ID/level/type | JSON媒体URL | 否 |
| Third-party L3 byfuns | api.byfuns.top/1/ | id/level=hires | 文本媒体URL | 否 |
| Third-party L3 xiaot | api.s0o1.com/API/wyy_music/ | id/yz=7 | JSON媒体URL | 否 |
| Third-party L3 xcvts | api.xcvts.cn/api/music/163music | id及apiKey等 | JSON媒体URL；内嵌请求key | 否 |
| Third-party L3 xianyuw | apii.xianyuw.cn/api/v1/163-music-search | id/key/no_url/br | JSON媒体URL；内嵌请求key | 否 |
| Third-party L3 lzmhhh | music.lzmhhh.com/api/music/url | id/type=wy | JSON媒体URL | 否 |
| Third-party L4 rxtool | api.rxtool.top/api/meteasecloudmusic.php | id/level | JSON url及歌词/信息 | 否 |
| Third-party L4 ceseet | m-api.ceseet.me/url/wy/{id}/hires | 歌曲ID | JSON媒体URL | 否 |
| Third-party L4 manshuo | api.manshuo.ink/wyy/Download | id/quality表单 | 直接返回媒体字节，原方法先完整获取 | 否 |

外部路线通常以稳定歌曲ID或平台链接为输入；仅凭请求ID或媒体格式无法独立证明返回媒体与目标录音一致。令牌、IP或签名条件也不能证明调用方有权访问内容。当前实现不向未经核验的外部服务发送平台凭据。

## 独立实现的调用链和数据映射

`POST /api/search` → 固定provider_for → NeteaseProvider.search → 原生cloudsearch/pc → SongCandidate。仅元数据，单页1–10条，最多10页，cursor绑定limit；去除非法ID及页内重复，不调用resolve或媒体探测。

`POST /api/playback/open` → NeteaseProvider.resolve → 原生普通player/url → 核验返回单项ID → ResolvedMedia → 已有MediaStore/Lease → 原Range代理。请求仅依赖TrackIdentity，不需要先搜索或保存原始搜索对象。不在失败时切换接口或第三方，不进行自动重试。

| 平台字段 | Core表达 | 处理 |
|---|---|---|
| song.id（正整数或规范数字字符串） | identity.platformId字符串；providerId=netease | 与专辑ID、封面无关；拒绝bool/小数/前导零字符串/非法长度 |
| name/ar[].name | title/artists | 保留多歌手，未知歌手为空元组 |
| al.name/al.picUrl | album/cover | 可空，不从歌曲ID猜图 |
| dt | durationSeconds | 毫秒除1000；非法、负值或非有限数为空 |
| resolve.data[0].id | identity核对 | 不匹配即拒绝，不能静默换录音 |
| url | 私有upstreamUrl | HTTP(S)且无userinfo；不进入公开DTO或日志 |
| size/br | sizeBytes/bitrateBps | 仅采信严格正整数；格式、codec未知保持空 |
| expi | validUntil | 响应给出的正整数秒（最多一天）换算epoch毫秒；否则空，不从URL猜时间 |

当前qualityId=standard表示普通128kbps请求档，不声称无损；实际已验证样本为MP3。拒绝显式品质/下载选项、HLS/DASH地址及freeTrialInfo非空的试听，不做流解密。HTTP401/403、业务301/401/403转access_denied；单项404转track_not_found；200但空URL转media_unavailable；其他业务错误（含实际-110）保留upstream_failure，未确认会员、地区或下架原因。

## 上下文、编码和安全

本期只有URL编码表单与ids的JSON序列化，离线测试校验精确请求，没有密码学依赖。研究来源还记录需要额外协议编码的高品质接口；本阶段未采用这些接口。协议编码不赋予内容权限，账号凭据也不属于稳定歌曲数据。当前实现不依赖这些协议工具或默认账号。

共享httpx连接池，但显式构造Request，阻止客户端默认Cookie、Authorization进入网易云请求；UA和Referer仅为普通公开上下文。响应限制2MiB、总时限20秒，底层连接5秒/读12秒，取消和错误均关闭响应，无递归回退。

媒体主机仅采纳真实观察的m701.music.126.net及m801.music.126.net，按netease隔离；没有允许整个126.net或music.163.com。未知CDN仍会被拒绝，需要后续真实证据再扩充。原代理保留每跳检查、最多三次重定向、公共DNS地址校验、端口限制、请求头白名单，且重定向移除敏感上下文。DNS检查后不绑定连接IP的既有局限仍存在，本期未改该机制。公开接口不接受任意上游URL。

有限探测只读取4096字节并关闭响应，以MP3帧/ID3等实际字节和Content-Type/Content-Range共同验证；不把URL后缀当作音频证据。浏览器另行验收，播放和完整下载的结论分开。
