# 14 播放器基础 — 阶段 14：Vue真实播放与会话管理

2026-11-10。本阶段完成播放器基础控件与单一音频状态接入；服务端Provider、Playback API、MediaStore、Lease、Range代理和恢复协调器保持原实现。新增服务端文件仅用于验收。

## 实现与旧UI复用

底栏采用三栏结构、封面组件、Lucide图标、时间/进度布局、主题变量和移动端断点。保留模式/上下首/歌词/队列位置但禁用，本阶段尚未接入队列和沉浸播放器。音量为真实原生Slider和静音按钮，队列交互单独记录于[14 播放队列](Verification-Queue.md)。本阶段未接入转换弹窗或平台Token网络请求。

唯一audio由根provideCoreClient调用usePlayer创建，挂在全局BottomPlayer footer，非路由组件。usePlayer拥有原生事件桥接、音量偏好、当前歌曲展示及唯一续期定时器；RecoveryPlayer拥有媒体会话、播放意图与恢复。Root/AppShell改从该全局player判断首页底栏显隐，不再使用旧store空队列判定。保留的旧视觉模块只提供主题和样式选择，不拥有第二个audio或媒体会话。

SearchView把具体候选交给player.select，按该版本providerId/platformId打开；不按歌名推断，不把全搜索结果加入队列。同一个当前版本再次点击为暂停/继续；选曲立即更新元数据、高亮和状态反馈。实际playing仅由audio事件驱动，不能以点击代替播放成功。

## 会话与恢复

从实际OpenAPI核对OpenResponse为playbackId、streamUrl、media、expiresInSeconds。恢复类通过api/playback.ts的原始HTTP请求出口调用现有open/renew/close；renew/close直接检查HTTP状态，不解析204 JSON。open不在客户端主动abort，接收晚到响应以关闭已创建的Lease，避免“取消请求但服务端已分配”的泄漏。媒体只使用受限本地/api/playback/.../stream，保留服务端查询参数，不读取真实上游URL、不fetch整曲Blob。

续期按真实expiresInSeconds的一半安排，根生命周期只维护一个timer；同一Lease的暂停/继续不会重新推迟已有计划，切歌/关闭/打开中清除旧timer。回调仅在原session仍为当前时继续安排，旧renew晚到不修改新歌曲。关闭失败清理本地状态，服务端TTL兜底，不无限重试。pagehide发keepalive close；真正应用卸载时停止timer、立即移除事件监听并dispose，不等待关闭请求返回才清监听，正常路由切换不会触发销毁。

**直接移植server/app/player-controller.mjs中已验证的独立RecoveryPlayer至web/src/player/recovery-player.mjs**，而非搬旧实现状态机或新建另一套恢复框架。保留代次隔离、书签/音量/静音/速率/暂停意图、HEAD诊断、明确权限与解码错误不自动取链、每次选曲最多一次自动恢复和晚到Lease关闭。

Vue版仅补：持久监听登记/dispose；seek方法与恢复中pendingSeek；响应相对streamUrl查询参数支持。恢复期间新Seek采用最新目标，失败后也保留该目标；没有已知duration时进度条禁用，不猜Seek范围。正在恢复时按钮按最新播放意图显示暂停/播放，用户暂停不被内部play覆盖。waiting仅更新缓冲信息，不触发resolve。

UI进度由timeupdate/metadata/duration/seeking/seeked事件驱动；拖动期间preview独立，change释放时才seek，避免每像素重新发媒体请求。音量UI为0–100，audio为0–1，volumechange回写偏好；muted与音量独立。结束不自动切歌，显示播放结束。

## 新Vue真实浏览器

运行scripts/verify_vue_player.py，访问实际Vite5174和新Core8001，Chromium153.0.8010.12 headless。通过首页搜索“银临”进入新SearchView，点击真实返回的kuwo/9942644版本。本轮搜索元数据显示《东风志》/银临、慕寒，底栏与该候选一致；不根据历史报告中的名字硬编码歌曲。媒体时长271.583107秒。

真实audio时间推进超过2秒，暂停等待600ms时间差小于0.1秒，继续成功；通过进度控件input/change路径到50%及94%，断言seeking结束并位于目标±2秒内。音量30%、muted=true确实作用于audio。依次切Home、Settings、Search，audio实例相同且未暂停；DOM始终只有一个audio。关闭后移除src，并验证已返回的stream能力为410。最终真实轮次pageErrors=[]、consoleErrors=[]，仅4个Seek/关闭产生的预期net::ERR_ABORTED；未保存能力URL。没有创建新歌曲队列或把临时URL存本地。

其余来源本期使用原verify_playback_browser.py适度回归（不是声称都在新Vue搜索中点击）：QQ001e7VNQ43nv4W、网易云30352891、咪咕600929000006452915均退出0；播放暂停继续及中段/近末尾Seek无错误，关闭410、记录/stream归零。QQ当前使用默认official，未改变外部路线策略。

## 受控Vue故障与竞争

scripts/verify_vue_player.py --controlled在独立8002启动正常create_app，用既有FaultUpstream自生成48秒WAV替代平台，独立Vite5175代理该服务，finally停止自己的服务和进程树，不碰5174正常工程。人工搜索返回两个不同稳定ID，不冒称真实曲库。

观察真实renew204；随后主动关闭当前Lease，下一次renew返回410，自动重新open一次。新旧Lease不同，同audio、volume=.3/muted=true保持，恢复至ready。再让B的resolve挂起、立即选择A；A先播放，放行B后它的晚到Lease被关闭，底栏仍为A，服务端仅1个active Lease。最后人为open503使手动恢复失败，错误文字可见、可重试；关闭后所有返回过的流地址均410。控制组最终MediaStore记录为0、active Lease为0，临时Uvicorn与Vite均收尾。

最终受控renewTTL使用30秒，媒体TTL .3秒；生产默认180秒未改。早期2/10秒TTL复测出现初始化/慢流期间租约到期，且暴露暂停/继续反馈重复推迟续期计划的问题，已修为同Lease保留原timer，不用早期失败轮次宣称成功。最终摘要为controlled=true、opened=4（初次、恢复、A/B各一次）、renewStatuses=[204,410]、closedStatuses四个410、pause/seek/volumeMute/routeContinuity/singleAudio全部通过，pageErrors=[]。

真实默认服务的未到TTL媒体记录允许短期保留，不把close等同立刻删除未过期MediaRecord；active能力关闭由410证明，TTL及stream引用回收另由受控短TTL及已有后端测试证明。没有新建调试资源接口或改变Store职责。

## 测试与构建

- pnpm build、pnpm typecheck通过；Vite产物约310KB JS/50KB CSS。
- pnpm test：**21项Node通过**。原17项测试改为导入Vue移植的恢复类，证明这份实际客户端的代次/失败/恢复行为；新增恢复中Seek、dispose清理、旧renew晚到隔离、stream查询参数保留4项。不是把后端测试通过冒称Vue模块已测。
- 后端原513项pytest全部通过，仅一个既有Starlette/httpx弃用警告；后端业务零修改。
- 浏览器页内无JS异常；受控503为故意注入失败，旧Range取消/关闭产生的请求中断和既有WindowsProactor10054不当作平台协议失败。没有保存上游签名URL、Cookie或凭据。
- git diff --check通过。未新增依赖，package.json仅增加Node测试命令。

## 截图

均来自本期实际新Vue运行页；已检查桌面播放、移动底栏和错误截图。390px无document横向溢出，底栏占独立grid行，不遮移动TabBar；封面与标题截断、可触摸原生Seek及40px播放按钮保留。

- [桌面搜索播放中](screenshots/player-desktop-search-playing.png)
- [桌面首页播放中](screenshots/player-desktop-home-playing.png)
- [移动底栏](screenshots/player-mobile-player.png)
- [受控503后的恢复错误](screenshots/player-controlled-error.png)

## 变更与下期边界

新增web/src/player/usePlayer.ts、recovery-player.mjs及声明，web/tests/recovery.test.mjs、server/scripts/verify_vue_player.py和本报告/截图。修改Root、AppShell、Core提供者、SearchView/SongItem、BottomPlayer、api/playback.ts及package测试命令。本阶段未修改旧实现或研究来源。

阶段 14仍需接真实队列、上下首、播放模式、队列抽屉及下一首准备，集中整理Popover/Slider交互；歌词同步、下载前端和沉浸模板尚未接线。本期没有假队列切换、循环模式或歌词按钮行为，没有新增Pinia或第二套播放器状态机。
