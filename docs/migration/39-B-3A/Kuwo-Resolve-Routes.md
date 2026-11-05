# 酷我解析路线对照

## 三种路线

| 路线 | 旧/新行为 | 本期证据 |
|---|---|---|
| A：站内www playUrl | 39-B.2新实现选择的站内JSON接口；不是冻结库的官方mobi函数 | 正常访问首页取得一个服务器Cookie后仍拒绝，无法确定缺少何种合法条件 |
| B：酷我mobi convert_url2 | 原库用mobi.s及加密q；新实现用同一平台接口的普通参数 | 普通参数得到rid/url/format/bitrate等文本行，四录音前缀探测均通过 |
| C：独立第三方fallback | 原库先尝试外部解析服务，随后原官方mobi/更大资源选择 | 只调查调用关系，未访问或迁移任何第三方解析站点，不将结果冒充酷我自身成功 |

参考根：`C:/Code_Home/2_projects/media-lab/musicdl-lab/server/`。证据为`app/provider_adapter.py:151`及`vendor/musicdl/musicdl/modules/sources/kuwo.py:44,186,217`、`modules/utils/kuwoutils.py:65,87,106`。只读核对：搜索从MUSICRID得到录音ID；resolve先第三方再官方；官方mobi仅需要rid，补取歌曲metadata是为构造SongInfo展示，不是取URL的必要条件。原库官方依次尝试flac/mp3，之后AudioLinkTester检查媒体，并可能用已有更大fallback表示；新实现仅一次mp3请求，不追求最高品质，不抓歌词。

## 最小独立实现

`KuwoProvider.resolve`校验平台/默认playback选项 → 站内playUrl → 成功直接返回；仅`success=false`、无业务code且message精确为The request is illegal!时调用`resolve_mobi` → HTTPS mobi.kuwo.cn/mobi.s → 文本字段解析 → 校验响应rid与输入一致 → media_from_url → 私有ResolvedMedia。

明确HTTP401/403或业务401/403、其他拒绝文本、超时、取消、缺URL、结构变化不切路线，不连续增加请求。mobi本身失败即返回错误，不回第三方或追加FLAC档位。站内接口级拒绝与歌曲权限拒绝不是同一证据；若后续平台给出明确内容权限限制，必须停止，不把另一条接口当规避路径。

mobi请求字段：user=0（匿名）、corp=kuwo、source为原协议客户端版本字符串、p2p=1、type=convert_url2、sig=0、format=mp3、rid=稳定ID；User-Agent为okhttp/3.10.0。不使用会员标识、登录凭据或认证签名。客户端版本字符串只是现有协议参数，不声称代表登录或会员授权。返回sig是平台临时字段，不输出、不存储、不作为稳定身份。

实测HTTPS端点接受普通查询字段。因此未复制整个kuwoutils、置换表、歌词算法或加密实现，也不依赖旧项目。曾短暂安装pycryptodomex3.23.0做标准DES等价性调查，仅执行只读原工具字面量行为对照；未得到简单标准DES等价，随后发现普通参数无需加密，已卸载调查包，最终无依赖变更。这是协议行为独立重组，不把原库PolyForm许可资产改标为自由复制代码。

## 资源与上下文

稳定身份始终是(providerId=kuwo,platformId=rid字符串)，不按歌名重搜，不用数组下标或临时资源ID。URL、sig、请求头是临时上下文；既不进SongCandidate也不进QueueEntry。无需ProviderContextStore。

解析成功必须有合法HTTP(S)地址、无userinfo、不是m3u8，mobi还必须返回精确rid；重复字段/错误编码/错rid报upstream_invalid_response，缺URL报media_unavailable。format/bitrate只是平台声明，未在resolve里probe，故representation与validUntil继续null。独立验证脚本的字节证据不伪装成Provider内部永久缓存。

复用应用连接池，单请求20秒总期限、连接5秒/读12秒、响应最多2MiB、无重试/自动重定向；mobi沿用同一有界读取。两条路线最多两次平台请求；取消立即传播。公开API仍只有搜索/health/providers等，没有把未入库的mediaId当公开能力。私有DTO投影、repr隐藏与错误清洗不变。

## 有限媒体证据

开发脚本发送Range bytes=0-4095和identity编码，最多读取4096字节原始正文，200响应也到预算即关闭；有限重定向最多3次、总探测20秒。拒绝HTML/JSON或压缩编码，结合Content-Type与ID3/FLAC/Ogg等前缀判断明显一致性。206总大小只读可信Content-Range分母，不把4096的Content-Length当整曲大小；200仅在有Content-Length时记录声明的资源大小。无HEAD成败推导。

前缀通过仅证明此次可访问并具有音频特征，不验证完整码流、浏览器解码、整曲无缺失或所有歌曲稳定。[原始115项离线与在线摘要](Verification.md)没有包含媒体URL、Cookie或响应全文。
