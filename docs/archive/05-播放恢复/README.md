# 05 播放恢复

日期：2026-11-05。本期在原生开发播放器增加客户端恢复协调器，继续使用同一个audio、原有open/stream/renew/close API及阶段 04后端生命周期。没有新增恢复API、后端恢复管理器、队列或Vue应用。

恢复保存稳定TrackIdentity、最近有效时间、独立播放意图、volume/muted/playbackRate；重新open后使用新的Lease/MediaRecord，在原audio上等待metadata及seek完成，再继续或保持暂停。自动恢复每次逻辑播放最多一次，失败或再次失效后停下，按钮“重新打开当前歌曲”允许显式再试。

已通过：Lease真实到期、上游失效、响应头后中途断流、暂停恢复、重复重试合并，以及恢复中暂停/停止/切歌和晚到Lease清理。自有48秒WAV故障浏览器结束时记录/活动Lease/Stream引用全部归零，audio DOM未替换。真实酷我9942644正常回归通过，Resolve仅一次，没有误恢复。

不自动恢复：首次waiting/stalled缓冲、用户中止、明确解码失败、HEAD观察到的权限/不支持错误。MediaError没有完整HTTP信息，其他不明确网络故障最多一次受限验证；不会把403推断为签名过期。自动播放策略拒绝时保留已恢复的位置和会话，提示手动继续。

运行仍按[后端说明](../../../server/README.md)，显式开启MUSIC_CORE_DEV_PLAYER后访问/dev/player。恢复中可使用页面“暂停/继续”按钮改变意图，原生控件仍用于正常播放/seek。暂停按钮在metadata重绑阶段也有效，内部load引发的pause不会覆盖用户意图。

验证：159项pytest通过（包含一个Node状态机包装测试），其内部17项Node测试通过；另有8组可控Chromium场景和独立真实酷我回归。详细边界见[生命周期](Recovery-Lifecycle.md)、[验收记录](Verification.md)。没有修改旧实现、提交或推送Git。不要同时引入队列、下载、多级重试或新的取链服务。
