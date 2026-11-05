# QQ Provider：协议、身份与边界

## 有限调用链对照

冻结源码：`C:/Code_Home/2_projects/media-lab/references/musicdl-master/musicdl/modules/sources/qq.py`中_constructsearchurls(:43)、_getsongmetainfo(:398)、_parsewithofficialapiv1(:404)；`modules/utils/qqutils.py`的Credential(:145)、QQMusicClientUtils(:178)、buildcommonparams(:277)、buildrequestdata(:290)。实际旧项目`server/app/qq_adapter.py`给QQ方法绑定私有QIMEI上下文，`qq_identity.py`限制身份请求；`qq_fallback.py:21`及`qq_routes.py`把vkeys→qqovo→Tang作为第三方优先路线。

三类能力明确区分：

| 类型 | 旧实现 | 本期决定 |
|---|---|---|
| QQ平台接口 | u.y.qq.com/musicu.fcg上的搜索RPC、GetVkey；musics.fcg上的GetEVkey | 使用可验证的QQ自身搜索接口及GetVkey，不声称第三方成功是官方成功 |
| 独立第三方 | 原库有多级站点fallback，旧实验进一步锁定三条优先路线 | 仅调查调用关系，不访问/迁入其实现 |
| 旧实验兼容 | FunctionType重绑定、QIMEI复用/timeout、媒体probe和SongInfo文件 | 不迁猴补丁/trace/完整worker；复用新Core已有生命周期 |

冻结库移动搜索`music.search.SearchCgiService.DoSearchForQQMusicMobile`在本次匿名上下文对已知关键词回0条，对照desktop RPC也未取得候选；不同正常客户端上下文仍未解决。新实现最终采用QQ自身的`https://c.y.qq.com/soso/fcgi-bin/client_search_cp`，实测同关键词有结果。没有无界空结果fallback：正式search只请求这一路的一页，不逐首取链。

## 搜索

POST /api/search → 固定provider_for选择QQ实例 → QQProvider.search → client_search_cp → code/data/song/list校验 → candidate_from → SearchPage。

参数w为关键词，p为1基页码，n最多10，format=json、t=0、platform=yqq.json、new_json=1。游标页号:页大小，续页不可改limit，最多10页；用totalnum确认已知总量，真正空页停止。按songmid去重，损坏行跳过，结构异常不冒充空结果。

| 原始字段 | 语义/映射 |
|---|---|
| mid / songmid | 具体录音稳定标识→TrackIdentity(providerId=qq,platformId字符串) |
| id / songid | 数字目录标识，不作为platformId |
| file.media_mid | 媒体文件组标识，可不同于songmid；不放入公共身份 |
| album.mid / albummid | 专辑标识，仅存在时用于平台固定封面路径 |
| title / songname / name | title，缺失/空白记录不输出 |
| singer[].name | 多歌手元组，未知为空 |
| album.title/name / albumname | album，未知null |
| interval | 秒；未知/非法/负数/非有限值保持null |

没有title拼接、随机candidate ID或媒体URL身份，没有playable声明。真实API补验10条均有专辑/封面/时长/歌手，但缺失字段的离线样本仍保留null，不把常见情况写成必需字段。

## Resolve

TrackIdentity → QQProvider.resolve → `music.vkey.GetVkey.UrlGetVkey` RPC → 校验code/midurlinfo/songmid → purl或wifiurl + sip基址（也允许平台直接给HTTP(S)URL）→ 私有ResolvedMedia → 原MediaStore/Lease/Range代理。

稳定songmid足够让平台选择允许的媒体，不需要永久搜索上下文；不按歌名重搜。请求songmid数组、songtype=0、随机十位guid、真实配置uin或匿名字符串0、loginflag和platform。**不构造猜测filename。** 冻结库会拼档位前缀+重复歌曲标识+后缀，新实现不将media_mid或数字songid随意替换进去；由平台返回实际purl，并验证返回行songmid与请求完全一致。

匿名普通web上下文ct=24、cv=0，走非加密musicu端点；无QIMEI生成、请求sign仿造或固定他人uid。guid是请求相关随机值，不是会员身份。GET data只用于匿名公开参数；配置登录Cookie后改POST，认证字段只进请求头/正文，不进URL。RPC禁止自动重定向，整个响应解码预算2MiB、单次总20秒、沿用应用连接池，无无限重试，取消传播且finally关闭响应。

有限调查另对照旧GetVkeyServer/CgiGetVkey及冻结库ct19/版本/filename上下文。出现业务1000或104009时归provider_context_rejected，不能仅凭它们断言“没有会员”；最终请求上下文对四个样本中一个确实返回媒体。没有在正式代码维护多级RPC切换或对权限失败换站点。

GetEVkey涉及另一端点、签名及可能的ekey/加密表示。当前普通GetVkey已能取得合法匿名媒体，本期不引入GetEVkey签名集合或DRM/加密媒体解密；mgg/mflac/m3u8明确不支持，不把它们伪装成可播放音频。

## 私有上下文与凭据

`MUSIC_CORE_QQ_COOKIE`只由服务端读入QQProvider实例，不写文件。基础QQ上下文识别musicid/uin及musickey/qqmusic_key；不是完整OAuth、微信登录或刷新凭据实现，且本期未真实验证登录场景。Cookie、authst只发固定QQ RPC/搜索Host，不写公共DTO；媒体上下文只含普通UA/Referer，没有Cookie或Authorization。

purl中可能含vkey，为短期媒体访问能力，和稳定songmid、账号Cookie、请求sign是不同对象。私有URL归MediaStore，公开API只返回本地能力URL。未知失效期限仍null，平台expiration字段未确认语义前不推算永久有效期；未知格式/codec/文件大小也不从文件名编造。

## 媒体安全与验证

目标策略集中于media_stream.MEDIA_DOMAINS，按media.identity.providerId匹配。酷我仍仅kuwo.cn；QQ仅stream.qqmusic.qq.com域族及**本次实际返回的aqqmusic.tc.qq.com**。不是允许整个qq.com。open及每跳重定向都检查协议、标准端口、userinfo和公网DNS；不可信Host/私网拒绝。

生产默认验证器获得providerId，测试替身仍显式注入；跨Provider域名不互信。媒体请求直接建httpx.Request，不合并浏览器Cookie/Authorization；跨跳去除Referer等上下文。已有DNS检查未绑定到连接IP的限制保持39-B.3B所述，没有因QQ接入删除SSRF边界。

成功样本有限前缀是MP4 ftyp、audio/mp4、206；并未声称已精确识别AAC编码/完整文件。Core表示保持未知，脚本只另报4096字节证据。三个缺purl样本归media_unavailable，不猜测付费、登录或歌曲不存在。

新增依赖：无。全部采用现有httpx/Pydantic和标准库；不安装musicdl/orjson/密码工具集合。平台协议字段与行为独立重组，未复制原类、静态第三方凭据、客户端身份实现或整个utils；旧PolyForm与未来分发授权边界仍需遵守既有说明。
