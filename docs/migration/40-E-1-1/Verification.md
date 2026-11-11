# 40-E.1.1 默认解析链与客户端反馈

目标项目：C:/Code_Home/2_projects/musicdl-lab。未自动提交 Git，未进入下载品质阶段。

## 默认链与真实正常客户端

仅变更 main.py 默认字符串，保留环境变量覆盖和原 Provider 串行循环、总预算、取消、首个合格结果停止、权限拒绝不回退及媒体校验。QQ 默认 official,vkeys,tang,xunhuisi；网易云默认 native,gdstudio-preview,jfjt。请求绑定身份仍标为 configured_preview，未提升为官方身份确认或永久下载许可。

隔离启动新 Core 8011 / Vue 5189，明确移除进程内两个 RESOLVER_ORDER 环境变量，通过正常 Vue 首页勾选来源、搜索真实歌曲、点结果播放。没有替换搜索、解析、媒体响应，未直接向播放器注入地址。

| 固定录音 | 实际结果 | 请求顺序与停止 |
| --- | --- | --- |
| QQ 周杰伦《蒲公英的约定》004Yi5BD3ksoAN | audio.currentTime > 1，ready，暂停继续通过 | official → vkeys → tang → xunhuisi；巡回寺取得 prefix_verified 媒体 |
| 网易云 许嵩《天龙八部之宿敌》167691 | audio.currentTime > 1，ready，暂停继续通过 | native → gdstudio-preview；GD 成功即停止，未调用 jfjt |

[实际结果及域名顺序](real-defaults.json)、[QQ 正常 Vue](real-qq.png)、[网易云正常 Vue](real-netease.png)。只保存域名、公开录音身份与结果，不保存上游签名地址或能力令牌。隔离服务验证后关闭；没有重启用户常用旧 Core。常用运行进程需重启才能加载此次后端默认值。

## 反馈与下载入口

正常底栏移除常驻“重试 / 关闭”及解释性状态行；搜索结果和本地文件行移除播放状态附加行，搜索结果不再插入下载反馈或旧 DownloadProgress 文本。错误用全局轻量通知显示“歌曲播放失败”或“下载失败”和简短建议，六秒自动消失、可主动关闭，不挤占行布局。没有新增自动重试；不可判断是否可重试时不提供消息重试按钮，error 状态中央播放入口禁用，用户可重新选择歌曲。blocked 状态仍可手动播放。

播放请求的原 HTTP 状态与服务错误保留在 console，任务失败记录 identity / errorCode；不将内部错误直接排进歌曲行。未改 RecoveryPlayer、Lease、传输或 DownloadManager 算法。

普通底栏新增下载图标，复用选中在线歌曲 TrackIdentity 与 downloads.create；本地歌曲及明确下载拒绝不启用。不读取当前 Lease。移动端保留三个图标操作：下载、播放暂停、队列，未恢复时间条和文字操作。

DownloadStateIcon 从现有 tasks / files 派生：等待为钟、下载中为旋转图标、失败为警示、完成且 fileId 确实出现在 files 中为绿色实心勾；completed 但未确认文件时仍为等待确认。状态只依据现有 DownloadManager 快照，不新增下载状态存储，不把解析成功视为可永久下载。

## 验证与限制

- Chromium 受控真实 Audio / Core 验收：桌面与 390px 有底栏下载图标，无常驻重试关闭；暂停继续正常；搜索行播放、暂停、任务变更、播放失败前后 boundingBox 高度不变。
- 以浏览器 HTTP 响应夹具精确覆盖 queued / downloading / completed 无文件 / failed / completed 有文件，分别观察等待、下载中、待确认、失败与绿色勾；这部分证明 UI 协议映射，不宣称人工文件是真实下载成果。
- 注入不可重试 403，页面仅显示简短播放失败通知，不显示 TECHNICAL_ERROR_TEST；没有消息重试入口、没有循环重试。任务失败通知同样验证。[桌面反馈](feedback-1440.png)、[移动反馈](feedback-390.png)。
- 前端 41 项测试通过，vue-tsc / Vite build 通过，约 509KB 主包保留既有告警。后端全量 pytest 通过（含一个原有平台跳过），覆盖四来源、解析权限/取消/预算、下载、歌词、队列相关 API、本地文件与媒体恢复。旧“默认只能官方”测试按新产品默认改为显式 official 覆盖测试，并新增默认链断言；没有放宽媒体或权限断言。
- 本期新增真实播放证据仅上述 QQ、网易云两首；四来源完整浏览器端到端与新真实下载文件未重跑，不以旧记录冒充本期新增成果。原四来源回归依靠现有测试通过，未改其核心实现。未声称所有上游长期稳定。

## 下载状态颜色与常显补丁

按用户“颜色错了.png”修复：Lucide 图标内部为空心绘制，原 SVG fill 未形成绿色实心底。改为完成状态外层明确绘制 #26864c 圆底，内部白色勾线，歌曲行与普通底栏共用同一组件。

等待、解析、下载中、失败、待确认文件与已完成状态均让歌曲行下载状态常显，不依赖 Hover 或焦点。桌面其余歌曲操作仍在 Hover / focus 时出现；取消任务恢复原操作显示规则。不改变完成判定，仍须 completed + fileId 在 files 中存在。

Chromium 使用 HTTP 快照夹具验证：1440 / 390px、Light / Dark 的结果行与底栏完成态计算背景均为 rgb(38,134,76)，所有祖先无 opacity:0；鼠标离开且焦点在搜索框时，完成、等待、下载中、失败状态均可见，其他桌面操作仍隐藏。构建与类型检查通过。截图：[桌面绿色完成态](completed-green-1440-light.png)、[移动完成态](completed-green-390-light.png)、[下载中常显](persistent-downloading.png)。这些是 UI 状态验收，不冒充新真实下载结果。

## 下载成功通知

当前观察到的下载任务完成且 files 返回对应 fileId 后，统一轻量通知显示“下载成功：《歌名》”；多项同时完成合并显示数量。仅加入任务不提示成功，初次加载历史成品不补弹，轮询或手动刷新不重复通知。由现有 tasks / files 和操作反馈派生通知，未修改 DownloadManager。Chromium 390px HTTP 快照验证：历史完成无通知、当前 downloading→completed 但缺文件无通知、补齐文件后提示成功、关闭后重复刷新不重弹。类型检查及前端 41 项测试通过。[成功通知截图](download-success-390.png)。
