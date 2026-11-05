# 39-B.2：酷我独立 Provider

后续更新：39-B.3A已实现酷我mobi路线，四个录音取链及有限前缀探测通过，见[最新结果](../39-B-3A/README.md)。下文保留本阶段历史，不代表当前媒体路线状态。

日期：2026-11-05。已完成轻量异步KuwoProvider、真实搜索API、按ID站内取链实现、连接池生命周期、安全错误分类与离线测试。没有复制musicdl源码或使用第三方替代线路。

**真实搜索成功，成功媒体解析闭环尚未达成。** 银临、许嵩各返回10条SongCandidate；分别选择首条稳定ID执行resolve，两次均access_denied。平台返回HTTP200但业务success=false、message为The request is illegal!。没有媒体URL，不声明播放/完整下载成功。

酷我状态为implemented_unverified_media，search/resolve能力仅表明代码实现；其他三来源仍not_integrated。当前不开放公共Resolve：没有媒体仓库，不向前端发放无法维护生命周期的mediaId或虚假streamUrl。Core返回模型中的id仅限调用方短期持有的对象标识，不是可通过API访问的能力。

运行见[后端说明](../../../server/README.md)，过程见[Provider说明](Kuwo-Provider.md)、[验收](Verification.md)。未迁移前端、Store/Lease、Range、下载、SSE及任何旧观察设施；未提交或推送Git，未修改旧项目。

39-B.3先解决官方站内合法访问条件和当前拒绝原因，验证至少一个可访问录音；在成功证据之前不要声称接入可播放能力。然后再接最小媒体仓库与Range代理、租约及取消释放验收，不扩大到其他平台或第三方兜底。本次未自动开展39-B.3。
