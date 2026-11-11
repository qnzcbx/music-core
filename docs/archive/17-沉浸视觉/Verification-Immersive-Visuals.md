# 17 沉浸视觉 — 阶段 17：沉浸背景与操作层验收

本期只修改新 Vue 的沉浸视觉及控件呈现，旧实现 只读。没有修改 Provider/Resolver、Playback API、唯一 Audio、RecoveryPlayer、下载模块或队列算法；没有提交 Git 或开始其他任务。

## 调查结论及旧实现复用

旧实现 的相关实现位于 `web/src/utils/ambient-palette.ts`、`composables/useCoverPalette.ts`、`components/AmbientBackground.vue`、`composables/usePlayerTransition.ts`、`views/PlayerView.vue`、`components/VinylPlayer.vue` 与 `BottomPlayer.vue`。

取色链路采用统一的 `ambient-palette` 算法，包含取色、缓存和世代隔离；`AmbientBackground`负责显示环境色。原链路包括 64×64 Canvas 采样、量化直方图代表色、忽略极暗极亮像素、低饱和封面处理、柔和调色、48 项共享缓存、失败缓存 30 秒、4.5 秒超时，以及双层背景的 900ms 透明度交叉淡入。useCoverPalette 只观察封面 URL，根视觉提供者跨路由保留结果，暂停和 Seek 不会触发重新取色。本期保留这些实现，没有另写算法。

已确认影响效果的具体原因：

- 原 defaultAmbientPalette 本身为固定米白、浅绿和浅黄色。无封面的本地歌曲、上游没有提供 cover、图片网络或 CORS 失败都会落到同一组合，并非所有页面都拿到了可读取的封面。
- 新 PlayerView 末尾的全局 Dark 规则另外替换沉浸文字/表面变量，并对整个 ambient-background 应用 `brightness(.24) saturate(.75)`，把已有取色背景再整体压暗、去饱和。该覆盖现已移除。
- 四套模板原来共用同一种 AmbientBackground 结构，差异主要在唱片机、封面和歌词布局；并不是四套独立取色算法。约4秒闲置隐藏逻辑属于本阶段新增的视觉控制。

真实元数据抽样中，普通酷我封面来自 img1.kuwo.cn，HTTP 200 且允许跨域；不能把所有取色失败归因于平台 CORS。浏览器实验也证明合法封面可取色、URL 变化正常响应。跨域不可读的图片仍遵守浏览器限制，使用中性兜底，没有添加代理或绕过 CORS。

## 背景与模板

保持旧代表色和 pastel/mix 算法：取到的颜色经过高明度协调，不把高饱和原色铺满背景；深灰文字、当前歌词及中性控件保证主信息对比。新封面准备期间保留上一配色，完成后沿用双层淡入；同封面不重启淡入。

无封面及失败默认改为中性色，并在 PlayerView 为各模板选择不同的中性底色。全局 Light/Dark/Follow System 继续控制普通页面；沉浸背景、文字和底栏使用自己的变量，Portal 中的模式、音量和队列面板也使用独立中性表面。

| 模板 | 保留的视觉特色 | 背景 |
| --- | --- | --- |
| 经典唱片机 | 左唱片机、右歌词，移动端纵向 | 原有多点径向叠层 |
| 沉浸大唱片 | 大唱片延伸出画面，歌词偏左 | 向唱片一侧聚集的柔和径向渐变 |
| 方形封面 | 完整封面与歌词并排 | 封面侧色晕及斜向渐变 |
| 纯净歌词 | 隐藏唱片视觉，集中呈现歌词 | 中央柔光与宽幅留白 |

## 控制栏与隐藏

顶部只保留始终可发现的收起图标；移除装饰性标题、标语、唱片说明和署名，保留当前曲名、歌手及歌词。顶部和底部返回均调用现有 visuals.close，未另建路由行为。

底栏桌面为三组：左侧返回及歌名/歌手，中间原播放模式、上下首、暂停/继续、音量、进度和时间，右侧衣服样式图标、“词”、队列。样式沿用原卡片及对齐设置，改为底栏衣服图标并向上展开；“词”根据交互验收反馈沿用外部播放器原有的 visuals.open 行为，在已经打开的沉浸页不重复跳转，不新增歌词显隐开关。错误时保留原重试入口。移动端分两行排列，保留安全区与触控尺寸。底栏使用浅色半透明渐变与适度模糊，取代原深绿实心表面。

新增 useImmersiveControls 仅拥有操作层可见性：

- 正常播放且无待处理状态时，约 4 秒无输入淡出；只改变 opacity / visibility / pointer-events，底栏、音频和播放器不卸载，唱片机和歌词不隐藏。
- 鼠标移动、键盘及触摸唤醒。高频鼠标事件只更新普通时间戳；定时器检查剩余时间，不持续写响应式状态。隐藏时 Tab 先恢复操作层再聚焦可用按钮。
- 鼠标在底栏、键盘焦点在控件、模式/音量 Popover、队列 Popover/Drawer 或样式面板展开期间保持显示。鼠标点击产生的普通焦点不会永久阻止闲置隐藏。
- 暂停、加载、缓冲、错误、自动播放被阻止等需要用户处理的状态保持显示。移动端隐藏后的首个触摸先唤醒并拦截对应点击，避免顺带触发歌词 Seek 或播放切换。
- 尊重 reduced-motion，页面卸载时清除计时器、watch 和 document 监听。顶部收起图标不随底栏隐藏。

## 真实浏览器证据

`server/scripts/verify_immersive_appearance.py` 在独立新 Vue 5186 / Core 8008 运行。使用明确标识的自生成 192 秒 WAV，以及暖色、冷色、有封面但拒绝 CORS、无封面的受控候选；没有以静态示意图代替页面，也没有宣称新增真实平台解析成功。

浏览器验证：

- 暖色与冷色封面生成不同的实际配色。在同一沉浸页点击下一首，直接记录背景三色及淡入中途透明度，确认变的是颜色而非只换了模板结构。相同封面换歌复用缓存；通过 Canvas getImageData 调用计数验证暂停、Seek、换模板和返回页面不重复取色。
- Follow System 下 Light/Dark 实际切换后，沉浸背景图、滤镜和文字色保持一致。无封面与 CORS 拒绝均正确中性兜底。合法跨域封面可正常采样。
- 四套模板均在 390、768、1440px 渲染，无页面横向溢出，实际 Audio 引用始终相同，视觉操作没有多发 Playback Open。进度、暂停/继续、歌词显示和路由返回正常。
- 约 4 秒隐藏，鼠标/Tab/触摸唤醒，鼠标悬停、样式面板、桌面队列与手机 Drawer 展开时不隐藏。暂停与特意挂起的加载、特意注入的错误状态在等待超过 4 秒后仍显示；随后重试正常恢复。
- 页面异常为空，故意拒绝 CORS 和故障注入产生的浏览器资源错误属于预期。结果在 [browser-result.json](browser-result.json)。

实际截图均在被忽略的 screenshots 目录：

- [暖色封面](screenshots/visual-red-controls-visible.png)、[切歌前](screenshots/visual-red-before-next.png)、[冷色封面](screenshots/visual-blue-controls-visible.png)
- [控制栏闲置隐藏](screenshots/visual-controls-hidden.png)、[错误时显示](screenshots/visual-error-controls-visible.png)
- [无封面兜底](screenshots/visual-no-cover-neutral.png)、[跨域失败兜底](screenshots/visual-cors-failure-neutral.png)
- [经典](screenshots/visual-template-classic.png)、[大唱片](screenshots/visual-template-vinyl-wide.png)、[方形](screenshots/visual-template-square-cover.png)、[歌词](screenshots/visual-template-lyrics-only.png)
- [手机经典](screenshots/visual-390-classic.png)、[手机大唱片](screenshots/visual-390-vinyl-wide.png)、[手机方形](screenshots/visual-390-square-cover.png)、[手机歌词](screenshots/visual-390-lyrics-only.png)
- 同目录保留了 768px、1440px 的全部四套模板截图。

## 回归、范围与限制

前端 38 项 Node 测试全部通过，typecheck 与 build 通过。主包约 507KB，保留 Vite 原 500KB 提醒，未提高告警阈值。后端 539 passed、1 skipped，跳过项仍为 Windows 无创建文件符号链接权限；只有既有 Starlette/httpx 提示。

原 Vue D1 受控恢复脚本在隔离 8006/5184 再次通过，只在运行时替换端口与截图目录：续租 204/410、四次打开、同 Audio 故障重开、暂停/Seek/音量静音保持、晚到请求隔离、路由连续及关闭后四个能力均 410。未修改恢复测试或生产播放协议。新增场景亦确认模板、主题、隐藏、歌词入口和返回不重复 Open。

没有新增依赖。已有封面 URL 必须可被浏览器安全读取；不允许跨域采样时只能使用兜底，不自动联网补封面，不生成假的歌曲配色。缓存按原实现运行于当前页面生命周期。触摸及安全区验收为 Chromium 仿真，未声称真机 Safari 结果。所有新服务为隔离验收实例，结束后关闭；未重启或终止用户常用服务。


## 阶段 17 最终补丁：真实平台封面、透明操作层与移动精简（2026-11-11）

本节记录最终补丁及用户后续调整。上文的阶段性报告保留；本节的真实平台结果、完全透明底栏与移动精简布局为最终状态。没有修改旧实现、音乐 Provider 解析、PlaybackLease、DownloadManager、唯一 Audio、RecoveryPlayer 或队列算法，没有提交 Git。

### P0：分别证明原因，再修复真实链路

六组实际 Search API 均取得真实歌曲身份及封面，不按歌名补图片或配色。浏览器分别检查普通 Image 展示、anonymous Image、Canvas.getImageData，再检查 HTTP 响应：

| 来源 | 原始图片展示 | anonymous 加载与像素 | HTTP / CORS |
| --- | --- | --- | --- |
| 酷我对照 | 正常 | 可采样 | 200，允许跨域 `*` |
| 网易云对照 | 正常 | 可采样 | 200，允许跨域 `*` |
| QQ《幻听》《灰色头像》 | 正常 | anonymous 失败；普通展示后读取像素抛 SecurityError | 两张均 200，没有允许跨域响应头 |
| 咪咕《庐州月》《我落泪情绪零碎》 | 正常 | anonymous 失败；普通展示后读取像素抛 SecurityError | 两张均 200，没有允许跨域响应头 |

QQ 与咪咕本轮确实同属跨域像素读取限制，但结论来自各自两个真实样本，并非由表象推断。QQ 同资源改为常见 300×300 规格后仍是 200 且无 CORS，不能靠前端改尺寸解决。原地址可展示，封面字段也未丢失；唱片显示地址、取色 key 与搜索行实际 cover 已逐项匹配。酷我 CDN 节点在不同请求间可能变化，比较采用当前搜索行实际地址。

保留旧 64×64 采样、代表色、柔和调色、48 项缓存和请求代次隔离。前端先尝试直接读取，只有指定 QQ/咪咕封面失败后才调用共用 `GET /api/covers?url=...`。不改封面展示地址，不改歌曲身份或取链。开发属性提供 status / via / initialFailure，能区分无封面、请求/超时、decode、Canvas 跨域、采样及调色失败；成功还要核对背景 key 和最终计算样式，失败不会标为正常取色。

新增端点位于 `server/app/covers.py`，在 main 的既有 FastAPI 生命周期中注册和关闭。仅允许 y.gtimg.cn 的特定专辑封面路径及 d.musicapp.migu.cn 的指定资源路径，HTTPS / 443；拒绝其他域名、路径、用户信息、查询参数、片段及非图片。DNS 全量结果必须为可用公网单播，拒绝环回、内网、保留及多播地址；连接层直接拨打经验证的 IP，并核对实际 peer，TLS 按原域名校验证书，避免校验后再次按域名解析。每个跳转重新检查，最多两次跳转。上限 2MiB、4 并发、总读取预算 8 秒，检查声明 MIME 与 JPEG/PNG/WebP 魔数，不接受 SVG/HTML 或压缩包裹的响应。无服务端图片缓存；浏览器响应为 private 缓存。原始独立 Request 不合并 Cookie/认证头，并清理响应 Cookie。

复用已安装的 httpx/httpcore，没有新增依赖。没有复用媒体共享连接池：它无法在不改音乐请求行为的前提下固定解析后的连接地址，也不应把平台 Cookie 带入封面通道。新池仅为这一个受限端点服务。其网络后端挂接依赖当前锁定的 httpx 0.28.1 接口，升级时需重新回归。

补充复测曾出现 `relay-image-timeout`：客户端原 4.5 秒图片预算短于服务端 8 秒读取预算。已将同源读取阶段设为 10 秒，留出响应与解码余量；直接读取仍沿用原预算。修正后六个真实样本再次全部成功，不用默认色冒充结果。

### 真实歌曲及实际背景变量

下表来自正常新 Core / 新 Vue 的最终 Chromium 观测。未替换搜索、取链、音频、封面或播放响应；三色分别为实际 `--ambient-left / --ambient-center / --ambient-right`，相应径向渐变中也读到了对应 RGB。

| 来源 / 歌曲 | 实际歌曲 ID | 真实封面 | 像素读取 | 实际三色 |
| --- | --- | --- | --- | --- |
| 酷我《东风志》 | `9942644` | [img3.kuwo.cn](https://img3.kuwo.cn/wmvpic/324/14/96/2839896625.jpg) | 直接成功 | `#dedfdb` / `#efefea` / `#e7e8e4` |
| 网易云《飞鸟与鱼》 | `284617` | [p2.music.126.net](http://p2.music.126.net/Qs9WYbQu3TR7zOF3WdRtZw==/109951173976591536.jpg) | 直接成功 | `#fee2cd` / `#fee8d7` / `#feeee1` |
| QQ《幻听》 | `003MUDkf30pS5B` | [y.gtimg.cn](https://y.gtimg.cn/music/photo_new/T002R500x500M000004RbL3b0BDIe2.jpg) | 受限同源通道成功 | `#f6d6d5` / `#f7e3de` / `#f9f0e6` |
| QQ《灰色头像》 | `003cLs112yMAcW` | [y.gtimg.cn](https://y.gtimg.cn/music/photo_new/T002R500x500M000002CJON012PxwU.jpg) | 受限同源通道成功 | `#cdf1fe` / `#daedfb` / `#e6e9f9` |
| 咪咕《庐州月》 | `600902000009209221` | [d.musicapp.migu.cn](https://d.musicapp.migu.cn/data/oss/resource/00/2s/dd/8e7c277729a24232a767f8b281aaa3e2.webp) | 受限同源通道成功 | `#cef3fd` / `#daeefb` / `#e6eaf9` |
| 咪咕《我落泪情绪零碎》 | `600902000003281410` | [d.musicapp.migu.cn](https://d.musicapp.migu.cn/data/oss/resource/00/4t/9m/7ec584eb4beb4194aa6f583f7252329e.webp) | 受限同源通道成功 | `#d4eef7` / `#ddf2f9` / `#e5f5fa` |

酷我本次实际封面像素低饱和，结果为 neutral（成功采样），不是 fallback。其他五张为 cover。两张蓝色图片配色接近属于采样结果，不是按平台写死颜色。

六张实际截图：[kuwo《东风志》](screenshots/visual-real-kuwo-9942644.png)、[netease《飞鸟与鱼》](screenshots/visual-real-netease-284617.png)、[qq《幻听》](screenshots/visual-real-qq-003MUDkf30pS5B.png)、[qq《灰色头像》](screenshots/visual-real-qq-003cLs112yMAcW.png)、[migu《庐州月》](screenshots/visual-real-migu-600902000009209221.png)、[migu《我落泪情绪零碎》](screenshots/visual-real-migu-600902000003281410.png)。

取色成功与歌曲播放成功独立记录。最终隔离默认配置下，酷我、网易云和咪咕《庐州月》实际播放推进；QQ 两首 Open 返回 409/media_unavailable，《我落泪情绪零碎》有 Open 415/capability_unsupported，均未用人工音频替代。用户常用客户端截图明确证明后者可以播放，不能把隔离运行条件下的结果写成歌曲普遍不可播。本期未改这些媒体判定或另扩 Resolver，六张封面的真实采样与 CSS 应用均有独立成功证据。

### P1：透明表面和闲置行为

完全移除 immersive-controls 的整条背景、渐变、backdrop-filter、边框及阴影，父容器和伪元素也清空。真实浏览器对 footer、父容器及两者 before/after 共六项读取计算样式；显示和隐藏时均为：透明 rgba、background-image:none、四边 0px、box-shadow:none、backdrop-filter:none，伪元素无内容。操作层父盒高度为 0，固定 Overlay 不形成底部占位。局部播放按钮与展开面板可以保留自身阅读表面。

沿用 useImmersiveControls：约 4 秒闲置隐藏、鼠标/Tab/触摸唤醒、悬停及面板锁定、暂停和错误保持显示，不卸载 Audio。实际网易云 284617 播放中检验暂停/继续、30 秒 Seek、队列、音量、样式面板和路由返回，唯一 Audio 引用不变，纯视觉操作的 Playback Open 增量为 0。

### P2：Expand / Shrink、共享卡片与移动端

普通 AppShell 封面增加深色半透明遮罩及 24px Expand，Hover / focus-visible 可见，移动端可直接点进；无歌曲不显示有效图标。桌面及中等视口沉浸左侧为 24px Shrink、至少 44px 点击区，仍调用原 visuals.close，保持媒体和进度。顶部收起图标继续可用。

预览退化的原因是底栏 `.player-tools` 对后代 button 统一设置固定高度及 flex 布局，误压了原 layout-card。已收窄为直接操作按钮，并恢复卡片正常块布局与自动高度。没有复制配置或新生成预览图；弹层与设置页仍使用同一个 PlayerLayoutSelector、PLAYER_LAYOUTS 与原有 CSS 图形资产。四套模板选中及歌词对齐状态互通，切模板不重开媒体。弹层隐藏滚动条但保留 overflow:auto，短屏实测 scrollTop 能增加；不是禁用滚动。

根据移动端验收反馈，在 600px 以下的沉浸底栏单独精简：进度和两侧时间在上，下方只有“模式 / 上一首 / 播放暂停 / 下一首 / 播放列表”五项；移除底栏 Shrink、重复歌名歌手、皮肤、“词”、音量和队列计数。主视觉中的歌曲信息与歌词保留，顶部负责退出。中央播放按钮在错误时复用已有重试功能，不额外添入口。普通迷你底栏未套用这套删减。移动端换样式仍可从设置页选择，保持同一全局偏好。跨断点清理已卸载面板的视觉锁，不影响队列或媒体。

最终 1440 / 768 / 390px、全部四套模板通过真实页面验证；移动端确认按钮数为 5、进度区在按钮区上方、没有音量与皮肤入口。Light/Dark 不改沉浸配色，手机播放列表 Drawer 与轻触唤醒正常。样式短屏滚动条隐藏且仍能滚动。实际截图：

- [Expand 悬停](screenshots/visual-patch-expand-hover.png)、[桌面卡片](screenshots/visual-patch-style-cards-1440.png)、[中等视口卡片](screenshots/visual-patch-style-cards-768.png)、[隐藏滚动条](screenshots/visual-patch-style-scrollbar-hidden.png)
- [手机经典](screenshots/visual-patch-390-classic.png)、[手机大唱片](screenshots/visual-patch-390-vinyl-wide.png)、[手机方形](screenshots/visual-patch-390-square-cover.png)、[手机歌词](screenshots/visual-patch-390-lyrics-only.png)
- [隐藏后无底板](screenshots/visual-patch-transparent-hidden.png)、[手机中央重试](screenshots/visual-patch-mobile-retry.png)

### 回归、运行实例与明确限制

前端 41 项通过，typecheck / build 通过；保留约 510KB 主包的既有 500KB 告警，未调阈值。后端 573 passed / 1 skipped，跳过仍为 Windows 符号链接创建权限；覆盖域名路径、恶意跳转、DNS 特殊地址/混合结果、连接 IP 与 peer、响应大小/格式/编码、并发及不转发 Cookie。原 Vue D1 恢复脚本隔离运行再次通过：renew 204/410、故障重开、暂停/Seek/音量静音、晚到隔离、同 Audio，关闭后四个能力均 410。页面异常为空。没有新增软件包，没有改 Provider、Lease、下载或队列算法，没有提交 Git。

用户附件中能显示封面却维持中性背景的问题，还存在运行进程未加载代码这一层：排查时常用 8001 的 `/api/health` 为 200，但 `/api/covers` 为 404，OpenAPI 也没有该端点。不是把图片算法重写一次能解决。排查当时需要重启目标项目的 Music Core 才能加载路由，仅更新前端不够。随后再次检查，常用 8001 已经注册新端点，QQ / 咪咕真实封面读取均返回 200（WebP，分别 20586 / 23328 字节）；当前只需刷新客户端清除此前失败取色的页面缓存，无需重复重启。没有停止用户常用实例。独立新 Core 8009 / Vue 5187 已完成以上真实验证并关闭。

限制：仅覆盖已验证的官方封面域名和路径，未来平台变更会明确拒绝，不放宽为任意 URL 代理；网络/超时/图片解码真正失败时仍如实 fallback，失败缓存 30 秒，不能承诺上游永不波动。没有凭封面成功宣称全部音频可播，没有新增解析路线。触摸为 Chromium 仿真，未声称真机 Safari 结果。旧报告中的人工暖冷色实验只作原算法回归，本节 P0 的成功结论来自上述六张真实封面。
