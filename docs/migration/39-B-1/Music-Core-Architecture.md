# Music Core 架构与所有权

最新更新（39-B.4D-3）：QQ移除重复输入/资格判断和身份重复存储，qqovo单一会话管理Cookie，业务代码净减9行。执行资格、录音核验、媒体安全仍各归单一位置，不以简化为由静默发布未确认录音。公共Core不变，详情见[行为对照](../39-B-4D-3/Behavior-Diff.md)。

最新更新（39-B.4D-2）：QQ三条外部协议已独立实现在qq_resolvers，接入原有预算/分发，身份等级和会话材料仍归QQ内部；URL-only不会自动发布为confirmed。当前外部服务使用条件不足，默认只official，不把实现等同于在线验证或启用。公共模型与媒体生命周期不变，见[外部解析器说明](../39-B-4D-2/QQ-External-Resolvers.md)。

最新更新（39-B.4D）：QQProvider内部增加固定有序配置、路线资格及整次Resolve预算，默认仅official。vkeys/qqovo/Tang因当前使用条件和身份依据不足保持禁用，未增加外部运行适配器；不改变来源、公共模型、Store/Lease或恢复状态机。详情见[QQ路线审核](../39-B-4D/QQ-Resolver-Routes.md)。

最新更新（39-B.4C）：四来源均有独立Provider，MiguProvider使用contentId稳定身份，通过原生resourceinfo重建copyrightId及格式目录，再请求原生listen-url。无持久映射或搜索缓存前提，真实更换Provider实例后的重开通过；无需修改公共模型、Store/Lease或RecoveryPlayer。咪咕媒体仅按实测精确主机放行；完整身份对照见[咪咕说明](../39-B-4C/Migu-Provider.md)。下文“咪咕未接入”为历史范围；默认顺序及默认仅酷我保持不变。

最新更新（39-B.4B）：NeteaseProvider复用统一协议、搜索与播放API；采用匿名原生cloudsearch/pc与普通player/url，已验证一个真实MP3样本的播放、Seek和稳定身份重开。没有迁入原库第三方解析、默认账号或加密工具，公共数据契约、Store/Lease与恢复协调器不变。网易云可信媒体主机按真实证据独立管理；详见[网易云Provider与Resolver依赖](../39-B-4B/Netease-Provider.md)。下文“网易云未接入”为历史阶段描述。

最新更新（39-B.4A）：QQProvider已通过相同协议接入固定Provider查找、搜索及播放API；QQ私有凭据/协议留在Provider，公共模型与生命周期不变。可信媒体域按Provider隔离，详见[当前QQ实现](../39-B-4A/QQ-Provider.md)。下文“QQ未接入”文字仅为历史阶段范围。

最新更新（39-B.3C）：原生开发客户端已实现单首有界恢复，状态、书签及用户意图归客户端RecoveryPlayer，复用原open创建新MediaRecord/Lease，不增后端恢复服务；详见[当前恢复生命周期](../39-B-3C/Recovery-Lifecycle.md)。下文“未实现恢复”描述仅是历史阶段边界。

最新更新（39-B.3B）：已新增内存MediaStore/PlaybackLeases、本地播放API与Range代理；原生Chromium真实录音播放/seek已验收，开发页需显式开启。通用模型保持不变，生命周期与当前API以[新说明](../39-B-3B/Media-Lifecycle.md)为准，下文未迁完整媒体服务的表述是历史阶段范围。

最新更新（39-B.3A）：酷我mobi稳定ID解析及四样本前缀探测已成功；Core模型仍无改动，公共Resolve/Store/Stream仍未上线。当前路线及验证边界见../39-B-3A/Kuwo-Resolve-Routes.md。

更新（39-B.2）：基础模型保持不变；新增`app/providers/kuwo.py`、POST `/api/search`与应用lifespan管理的httpx连接池，详见../39-B-2/Kuwo-Provider.md。酷我metadata已在线通过，媒体接口拒绝真实样本；其余来源未接入。以下“本期”描述保留39-B.1交付时的边界，不能当作当前路由清单。

## 当前最小结构

`app/main.py`是薄HTTP层和安全错误转换；`app/models.py`定义JSON契约及显式私有字段；`app/core/providers.py`是唯一异步Provider协议；`app/core/errors.py`定义不依赖Web的业务错误；`app/config/`加载真实来源偏好并构造注册信息。未建立空search/media/download/infrastructure目录：外部HTTP/磁盘/FFmpeg接入尚未实现。

API依赖Core/模型；Core不依赖FastAPI Request/Response。只有四个固定来源，注册信息不是动态插件工厂，不创建四个返回假数据的空客户端类。

## Provider边界

`async search(query,limit,cursor) → SearchPage`只返回元数据和可空下一页游标；`async resolve(identity,options) → ResolvedMedia`返回服务端私有媒体。附加歌词/品质能力用注册能力字段描述，当前全部false；将来按平台独立实现，不强制统一档位或签名方法。上层只有一套async协议，同步第三方库的worker适配留边界内部。

本期仅协议和合成fixture调用测试，没有平台转换器；不同来源fixture代表统一DTO预期，不能视为已测试真实原始响应映射。39-B.2需对四来源各写raw白名单转换与协议fixture。解析所需私有上下文由Adapter短期持有，未来以稳定identity查找，必要时引入明确候选handle；本期不创建无实际用途的context store。咪咕identity.platformId是contentId，copyrightId仅供Adapter解析，不能合并或公开伪装成稳定ID。

## 所有权矩阵

| 数据类型 | 创建者 | 所有者 | 是否持久化 | 前端暴露 |
|---|---|---|---|---|
| TrackIdentity | Provider映射/输入校验 | 应用与未来队列 | 可以 | 可以 |
| SongCandidate | Provider metadata转换 | Search应用状态 | 默认临时 | 安全元数据 |
| 私有Provider上下文 | Adapter | Adapter/未来候选仓库 | 不持久化 | 不暴露 |
| ResolvedMedia | Provider解析，未来Media Core接管 | 服务端媒体仓库 | 临时 | 只能public_view |
| PublicMedia | 私有媒体显式投影 | API | 不持久化 | 可暴露；本期无媒体路由 |
| DownloadOption | 未来Download Core | 短期选项上下文 | 不持久化 | 可暴露，选项绑定mediaId |
| PlaybackLease | 未来Media Core | 服务端 | 不持久化 | 仅给持有者能力token，不记录日志 |
| QueueEntry | 未来客户端选版本 | 客户端队列 | 可存identity/metadata | 可以 |
| 下载任务 | 未来Download Core | 服务端 | 未定 | 仅安全状态；本期不建空任务类 |

Lease防止选中媒体被本地TTL/LRU回收，不能延长上游签名寿命；选中时创建、切歌/关闭释放、续期超时自动失效；stream/download应各有独立引用。当前只建Lease数据模型，token默认不序列化；将来仅在专用创建响应中显式交给持有者，不能把该模型直接作为token发放接口。

QueueEntry的顺序由未来客户端数组/导航管理，不把列表位置编码到稳定身份；本期不迁QueueController。`TrackIdentity.key`包含来源命名空间，相同数字ID跨平台不冲突。临时媒体id与身份分开，不把媒体写回队列持久化。

## 数据语义与安全

JSON字段采用camelCase。platformId始终字符串；QQ字母数字1–64，Kuwo/网易正数字1–20，咪咕contentId正数字1–32，沿用旧恢复边界。格式校验不能判断某个形状合法的ID是否真是平台录音；禁止Adapter传入candidate UUID需要通过来源转换测试保证，不能只靠正则宣称来源真实性。

持续时间秒，码率bps，大小bytes，时间戳epoch毫秒。未知duration/album/cover/codec/size/validUntil是null；未知有效期不代表永不失效。公开模型extra=forbid、拒绝非有限数字；下载可用性与允许下载分开，unknown不可声明允许下载。

私有URL/headers使用SecretStr且排除序列化/repr。`public_view()`显式构造PublicMedia，不含上游地址与headers；当前不生成不存在的streamUrl。39-B.2/后续代理上线后再增加同源stream能力链接，不直接传外部URL。

输入/未知Provider/找不到录音/暂不可用/上游失败/媒体过期/内部错误分别映射422/400/404/409/502/410/500。统一`{error:{code,message,retryable}}`，HTTP404/405保持标准状态，不回显请求值或异常详情。模型校验中的未知provider由Pydantic拒绝；未来Provider选择服务可抛unsupported_provider。错误路由仅在测试进程动态添加，不部署调试入口。

OpenAPI目前只描述已上线health/providers及错误响应。领域模型可用Pydantic生成JSON schema，但未暴露的业务不能为了让schema出现而创建假API。未来TS/Java只需保留JSON字段、单位、可空语义和HTTP/SSE行为；Task/锁/Session/worker/SecretStr都是内部实现。
