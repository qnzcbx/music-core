# QQ外部适配器实现

依据：冻结musicdl/modules/sources/qq.py的vkeys、qqovo、Tang原函数，以及旧Lab的qq_routes.py、qq_fallback.py、任务28播放闭环和任务29后续更正记录。保留具体协议思路，不复制完整Client、品质循环、歌词、原SongInfo或AST克隆。历史成功只作为技术依据，不用历史URL或会话代替当前请求。

## 三条协议

| 路线 | 本期实际请求/响应 | 会话与品质 | 当前结论 |
|---|---|---|---|
| vkeys | GET api.vkeys.cn/music/tencent/song/link，mid与quality；解析data.url及可选mid/song_mid | 默认单次quality=14，来自旧路线实际档位；仅开放4/8/10/11/14参数，不循环或请求伴奏档，不据数字声称编码/位深 | 已实现；公开入口200为服务状态JSON；API使用条件未确认 |
| qqovo | POST qqovo.top/api/session/bootstrap，新的随机deviceId；随后GET /api/meting，server=tencent/type=url/id=mid/quality=lossless | 临时apiSignKey、服务Cookie只存本次独立AsyncClient与局部变量；关闭或取消销毁会话；quality是请求档位，不声称返回必为FLAC | 已实现；首页200为OpenMusic听歌页面；自动化取链使用条件未确认 |
| Tang | GET tang.api.s01s.cn/music_open_api.php?mid；核对song_mid、song_name、singer_name | 依次选择sq/pq/hq/普通/standard/fq原曲字段；永不选accom。名称含伴奏/伴唱/翻唱拒绝；可传expected_title/expected_artist核验明确版本 | 已实现；根站200为默认index页，具体API运行状态尚未探测，使用条件未确认 |

qqovo签名函数与网络分离：query按解析后的键值排序，拼接GET、path、query、空body、timestamp、nonce，以换行分隔；当前bootstrap key作HMAC-SHA256，URL-safe Base64去尾部等号。请求头X-OM-Ts、X-OM-Nonce、X-OM-Sign，新的timestamp/nonce每次生成。独立会话不会继承QQ Cookie、默认Authorization或历史Session；不加全局SessionManager或跨调用缓存。签名仅为请求认证，不证明内容访问权限。

## 身份等级与发布

内部RouteResult只保留私有SecretStr URL、route_id、evidence、response_mid和必要元数据，URL不进入repr或公共DTO。URL-only正常返回request_bound、response_mid=None；绝不把请求mid回填为响应证明。提供明确MID且精确匹配时为confirmed；任何明确错配拒绝。当前没有凭标题相似或时长相似自动生成corroborated等级，没有伪造人工确认。

Tang的confirmed含义是响应MID匹配，不是音频指纹认证；未提供可信预期标题/歌手时不能声称完成了独立版本比对。提供预期字段可作精确空白/大小写归一核对。时长/字节正确仍不能代替身份。

QQProvider现有_resolve_route现在分发三个实际模块。构造参数enabled_external_routes可由已核实使用条件的服务端调用方明确授予路线资格；默认空，当前应用初始化不授予。它与MUSIC_CORE_QQ_RESOLVER_ORDER的顺序配置独立，环境顺序不能自行解禁，也没有HTTP入口。无当前外部资格时仍跳过三路并只用official。

有资格且进入适配器后，request_bound不会被当成坏协议，但正式Provider返回media_unavailable并按原规则继续；不会静默采用未经确认的录音。confirmed核验响应MID后，由新media.verify_media沿用QQ目标白名单逐跳校验，再读取最多4096字节；206校验0起始范围/总长/读取长度，拒绝HTML/JSON/压缩正文，识别MP3、FLAC、OGG、MP4前缀，finally关闭连接。实际格式保持未知，不猜后缀；校验后转换为原私有ResolvedMedia，依旧只创建原有一份Lease。

当前没有新增外部CDN规则，非原QQ受信主机继续拒绝，未来需真实证据再扩展；不放行任意互联网域名。API固定HTTPS地址、拒绝自动重定向、最大2MiB、每请求10秒，显式Request/auth=None隔离平台Cookie和认证。qqovo最多两次内部请求，由外层25秒整次Resolve共同约束。

权限401/403立即停止，无规避性回退；业务错误、空URL、会话缺少apiSignKey分别归一已有错误。会话过期不无限bootstrap重试，取消即时传播并关闭响应与独立会话。错MID、非法结构/URL、不同版本继续拒绝；正常成功停止后续路线。没有重新把解析放回搜索阶段。

## 在线边界

本期公开入口实际可访问，纠正4D工具无法读取网页不能推出服务下线的误解。但服务状态页、听歌网站广告说明和默认站点页都不能证明相应API允许本应用自动化取链及指定资源访问。按任务明确服务许可条件，当前没有执行歌曲API、没有bootstrap真实会话，没有声称外部路线verified_online或enabled。实现和Mock验证完成与在线目标未完成分列，不再次把“禁用三路＋official”伪装成多线路收益对照。
