# 媒体生命周期与HTTP契约

## 职责与调用

`main.create_app`装配Provider、共享httpx池、MediaStore/PlaybackLeases并启动周期清理。`playback.py`只负责HTTP参数/公共响应；`core/media_store.py`分开定义记录与租约规则；`media_stream.py`只验证目标和Range、打开上游、传输/关闭响应。Core没有FastAPI对象。参考旧项目stream/player_leases/result_store的必要行为，独立重写，没有复制观察或历史兼容层。

创建：身份校验→KuwoProvider.resolve（39-B.3A逻辑未改）→验证目标→Store分配不可预测mediaId→Lease生成另一随机playbackId→返回本地相对URL及PublicMedia。创建Lease失败回滚刚创建的媒体。媒体URL/headers继续只在ResolvedMedia内，公开模型没有上游地址。

Store记录创建/最近访问/到期时间、lease标识集合、stream票据集合。内部时间用monotonic，与公开解析时间epoch毫秒不同。配置统一在MediaSettings：media_ttl=300秒、lease_ttl=180秒、媒体容量128、租约含短期终态容量256、周期清理30秒。满额先清过期，仍满返回503，不淘汰活跃资源。

Store/Lease共用短RLock进行原子元数据更新，网络await期间不持有；读取不深拷贝私有对象，Store仅浅替换临时id。普通读取更新last_accessed_at，不延长媒体原始TTL。Lease有效或stream票据存在时保护过期记录。

## 三个生命周期

| 对象 | 创建/续期 | 结束/清理 |
|---|---|---|
| MediaRecord | 打开会话后put | TTL已过且无Lease/stream才删除；不持久化，重启丢失 |
| PlaybackLease | 打开时create；有效流请求及显式renew将期限设为当前+180秒 | close或TTL到期取消保护，不强行终止已取得引用的响应 |
| 单次Stream引用 | 有效Lease下为每次GET/HEAD发唯一票据 | 响应完成/取消/错误/发送失败均finally关闭上游并释放票据；重复释放安全 |

一次Range结束只释放它自己的票据，不关闭播放Lease。一个会话可以连续多次Range、取消原请求再seek；暂停也不立即释放。close后新Range/renew返回410，已有响应持有自己的票据安全收尾。不同Lease互不干扰，不涉及未实现的下载引用。

开发页存活期间每60秒显式renew，暂停仍续期；pagehide发keepalive close。关闭请求遗失或浏览器崩溃最终由Lease TTL回收，后台标签计时器被节流也可能超过TTL，届时返回410并需重新打开，不假装无限暂停会话。关闭/过期状态保留一个lease_ttl作为有界墓碑，之后404；close对未知或重复标识也返回204，不需要无限保留历史。

本地TTL不等于上游签名有效期。Provider validUntil未知则保持null；若已知期限过了，流请求返回upstream_media_expired，不发上游；上游404/410也归此类。403表示拒绝访问，不能声称一定是过期。暂不自动重解析或恢复时间位置。

## API

| API | 正常行为 |
|---|---|
| POST /api/playback/open | 输入OpenRequest(identity)，返回OpenResponse(playbackId,streamUrl,media,expiresInSeconds)，200/no-store |
| GET /api/playback/{key}/stream | 校验Lease并续期，流式返回上游媒体；只持有单次票据 |
| HEAD 同一路径 | 无正文，保留对应状态与实体头，仍取得并finally释放引用 |
| POST /api/playback/{key}/renew | 有效Lease续期，204 |
| POST /api/playback/{key}/close | 幂等关闭，204 |

QQ/网易/咪咕open明确501，未知来源由TrackIdentity校验422；输入不能提供URL/本地路径。公开能力URL只引用已入Store且已创建Lease的资源。原PlaybackLease数据契约不直接作API序列化输出，token通过明确OpenResponse发给持有者；没有向公共DTO增加私有字段。

错误仍为`{error:{code,message,retryable}}`。playback_missing=404；playback_closed/playback_expired/media_expired/upstream_media_expired=410；media_capacity=503；access_denied=403；upstream_failure/invalid_response/untrusted_media=502；timeout=504；invalid_range=400。已发响应头后的上游中断只能中止连接，不能回头改状态或发JSON假装成功。

## Range和字节传输

支持bytes=start-end、start-、-suffix三种单范围，开放范围与后缀均转上游；多范围、空/颠倒/非法单位明确400，不自建多段拼接。合法但超出资源范围由上游416给出真实`bytes */N`。

仅转浏览器Range与强If-Range（有Range时），不转本地Host/Cookie/Authorization/Connection等。私有请求头目前仅UA/Referer白名单，Accept-Encoding固定identity。httpx直接构造Request，防止连接池Cookie/默认认证自动合并。原始aiter_raw逐块回传，没有aread整曲、没有文本解码或范围重写。

保留200/206/416与安全响应头Content-Type/Length/Range、Accept-Ranges、ETag、Last-Modified。200忽略Range不伪造206，剔除不相符的Content-Range；206校验区间、Content-Length、已知总长和请求起点/后缀语义；即便没有Content-Length也按206区间校验实际字节数。缺字节或超长在传输中止，不能继续宣称完整。HEAD不计正文长度。416只接受合法范围头，不重试。

响应设置no-store/no-referrer/nosniff，不复制Set-Cookie、Content-Disposition或其他私有头。HTML/JSON类型与压缩响应在响应头阶段拒绝；没有把媒体字节解码为文本。该层不承诺验证每种容器的完整码流，浏览器负责实际解码。

## 上游安全与日志

媒体只允许HTTP(S)、标准80/443端口、无userinfo，host必须为kuwo.cn或其子域，DNS解析所得全部地址必须是公网。目标验证在open与每次stream/重定向前执行；最多3跳，跳转去除Referer等上下文，只保留必要字节请求头。重定向到回环/非白名单域在发请求前拒绝，不能成为用户任意URL代理。

这是单平台基本边界，不是通用公网代理；未来换CDN域必须先核真实来源再扩白名单。使用系统DNS/HTTP连接建立，未实现DNS结果与连接的IP绑定，因此不承诺防御受信任平台域名自身被控制后的DNS重绑定；后续扩大到不可信Provider前必须加强这层。

uvicorn访问日志对能力路径作脱敏，httpx/httpcore常规URL日志关闭到WARNING；应用错误仅固定类别，不写签名URL/认证头/能力ID。无请求历史、覆盖率、Timeline或debug轮询接口。验收脚本仅保存安全汇总，在内存直接读取Store计数，没有给产品增加诊断API。
