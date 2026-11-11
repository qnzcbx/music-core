# 02 酷我搜索 — 酷我 Provider：调用链与边界

后续状态见[阶段 03路线说明](../03-酷我媒体解析/Kuwo-Resolve-Routes.md)：已新增同平台mobi普通参数路线，模型不变。本文未实现mobi/未成功的表述仅为阶段 02历史。

## 有限源码调查

研究来源仅用于核对酷我搜索字段、请求参数与调用顺序。旧实现曾组合搜索结果映射、媒体取链、歌词编码与缓存；通用模型和网络工具不属于酷我平台协议。

新实现没有复制这些代码、加密工具、静态凭据或第三方站点路径。搜索只借鉴参数/字段语义，改用HTTPS与异步httpx；媒体选择酷我站内www/music/playUrl路径并真实验证，**并未复现旧mobi加密路线**。当前路线被平台拒绝；有限历史样本不代表当前可用性，也不构成继续尝试其他来源的依据。

## 搜索链

POST /api/search → SearchRequest校验/来源选择 → 应用唯一KuwoProvider.search → HTTPS www.kuwo.cn/search/searchMusicBykeyWord → 有界读取 → JSON或单引号字面量解码 → candidate_from → SearchPage。

query去首尾空白、1–80字符；limit为1–10整数；每次只取一页pn/rn。游标为页号:页大小，页号1–9；改变limit拒绝，最多十页；有TOTAL时按总数判断，否则用真正空页终止。不按过滤后结果数补发请求。超额行截断、同ID去重、损坏行跳过；顶层结构变化报错，不假装空结果。不会为列表逐首resolve。

实际接口返回单引号字典、Content-Type text/plain；使用标准库ast.literal_eval只解析字面量，不能执行函数。响应最多2MiB解码字节；超限、无效结构/编码、过深字面量报安全错误。

| 平台字段 | 公共契约 |
|---|---|
| MUSICRID/musicrid | identity.providerId=kuwo，platformId去MUSIC_，始终字符串 |
| SONGNAME/name/songName | title，HTML实体还原，缺失或无效行不输出 |
| ARTIST/artist | artists，实体解码后按&/分号拆多歌手 |
| ALBUM/album | album，缺失为null |
| DURATION/duration | durationSeconds，非法/负数/非有限为null |
| hts_MVPIC/albumpic/pic | HTTP(S) cover，否则null |

没有playable字段，搜索不提供媒体可用性保证。当前酷我仅凭稳定ID取链，不需要搜索私有上下文仓库，不保存整份平台JSON。

## Resolve链

本地验证脚本 → KuwoProvider.resolve(TrackIdentity) → 校验provider与选项 → HTTPS www.kuwo.cn/api/v1/www/music/playUrl，mid=platformId、type=music、httpsStatus=1 → 校验code/data/url → 私有ResolvedMedia。

只支持默认playback，无指定品质与下载选项；不按歌名重搜、不换录音。传普通User-Agent与站内Referer，无Cookie/登录令牌、无签名仿造或权限绕过。Client若接收到服务器Set-Cookie只在其临时cookie jar内，不写入DTO/磁盘。平台拒绝立即返回access_denied，不fallback到第三方。

成功路径只表示站内接口给出HTTP(S)地址；没有媒体字节probe，所以container/codec/contentType/sizeBytes/lossless与有效期均保持未知，不用URL后缀伪证编码。m3u8明确不支持。没有HEAD200推定可播放的逻辑，也没有下载音频。私有URL/headers由ResolvedMedia持有、repr/序列化隐藏，public_view投影沿用阶段 01；本期无需改变核心模型。

## HTTP与错误

FastAPI lifespan创建一个AsyncClient连接池并在结束关闭：连接超时5秒、读取12秒、每次Provider请求总期限20秒，最大10连接/5保持连接，不重试、不跟随重定向。取消传播并关闭stream上下文。独立验证脚本自行管理同样边界的Client。Core不依赖Web对象。

新增upstream_timeout(504)、access_denied(403)、upstream_invalid_response(502)、provider_not_integrated(501)、capability_unsupported(415)。平台HTTP404为track_not_found，其余异常HTTP为upstream_failure；HTTP200业务success=false在resolve中为拒绝访问，具体是否缺认证/权限/反滥用不能凭该消息再细分。异常不含URL、原始响应/参数、Header或堆栈。其他来源不触发任何上游请求。

httpx 0.28.1由开发依赖提升为锁定运行依赖，其他包未新增。研究来源仅用于协议调查，不视为取得源码复制或分发授权；许可边界见[核心架构实现范围](../01-核心架构/Implementation-Scope.md)。
