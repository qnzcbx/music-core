# 14 沉浸播放器与歌词 — 阶段 14 沉浸式播放器、同步歌词与队列视觉验收

日期：2026-11-10。本阶段完成沉浸播放器与歌词界面；下载界面另见[16 下载界面](../16-下载界面/Verification-Download-Interface.md)。旧实现与研究来源仅作只读对照。

## 队列尺寸与交互

保留桌面 Popover、移动 Drawer、共用 QueueList 的方案，没有新装弹层库。桌面宽 400px，高度为 `min(700px, 100dvh - 220px, Popover可用高度)`。1440×1000 下实测 700px；1440×500 下缩至不超过 280px 且顶部不越界。390×844 的 Drawer 高 74dvh，实测约 624.55px，安全区留白包含在主体内。

同一窗口下分别检查 0/1/30 首：桌面外部高度不变；移动端同样检查单首、多首和空态，高度不变。标题固定，只有 `.queue-content` 滚动；30 首时验证内部 scrollTop 可改变、标题坐标不动。没有外层第二重列表滚动条。

顶部只显示标题、较淡歌曲数量、模式图标和垃圾桶。没有“关闭”“清空待播”按钮或额外说明。模式单击按顺序 → 列表循环 → 单曲循环 → 随机 → 顺序切换，与底栏菜单共享 `navigation.mode`；切换不产生 open，并使用原安全持久化。

`useQueue.clear()` 明确清空所有条目及当前位置、重置导航历史，再调用原 stop 关闭会话；不是原 `clearPending()` 的别名。原移除单项、清空待播保留当前的能力仍存在，原队列算法未改。空态只有居中的“空空如也”，无占位曲、搜索按钮或重复解释。

桌面 Escape、外点关闭通过。移动端保留顶部拖动指示条，验证向下触摸拖动关闭、遮罩触摸关闭、Escape 关闭。列表标记 `data-reka-swipe-ignore`，原生滚动不参与 Drawer 关闭手势；触摸向上滚动列表后 Drawer 仍保持打开。键盘用户可 Escape 可靠退出。清空时不额外确认。

## 四套模板来源与依赖审计

实际源码表明四套模板是同一 PlayerView 的布局变体，不是四个各自拥有播放会话的组件：

| 模板 | 本期复用 |
| --- | --- |
| classic 经典唱片机 | 旧 PlayerView 的双栏布局、完整 VinylPlayer 唱片与唱臂、同步歌词 |
| vinyl-wide 沉浸大唱片 | 旧大唱片延伸到视口外的构图、左侧歌词、唱片连续旋转 |
| square-cover 方形封面 | 旧方形容器及 CoverArt Teleport，完整封面和歌词并排 |
| lyrics-only 纯净歌词 | 旧纯歌词留白布局，隐藏唱片视觉，不新造第四套设计 |

`PlayerView.vue`实现沉浸布局；`VinylPlayer.vue`、`LyricPanel.vue`、`AmbientBackground.vue`和`ThemeSettings.vue`负责唱片视觉、歌词行、动态背景与主题设置。组件读取当前Core歌词结构，并复用播放器布局、封面取色、页面过渡和外观偏好工具。

本阶段不依赖旧会话管理、媒体对象、歌词解析和调试导航；播放器只消费当前Core提供的歌词与播放状态。未复制旧网络上下文或新增通用播放器框架。旧第四套实际为纯净歌词，因此保留其歌词对齐能力；没有将其改造成另一套唱片机。

唱片材料、转动时钟、唱臂、背景取色与交叉淡入保留。仅为小屏空间、深色可读性做必要适配，使用原 GSAP，不增加动画库。`prefers-reduced-motion` 减少旋转及非必要过渡，不停止音频。背景计时器、动画帧、布局动画、歌词计时器及 ResizeObserver 都有原有或新增的卸载清理；往返后检查无残留 shared-cover-flight 克隆。

## 唯一 Audio 与共享控制

唯一 audio 仍由根级 `usePlayer()` 创建，本期将其 DOM 从 BottomPlayer 内移到 `App.vue` 的隐藏 `[data-audio-host]` 中。隐藏普通侧栏、搜索栏、底栏时，不卸载或移动音频。

普通底栏封面与“词”按钮可进入沉浸式页面；沉浸式页面使用同一 BottomPlayer 控制界面的 immersive 变体，只重复无媒体所有权的控件，没有第二个 Audio、RecoveryPlayer、续租定时器或 Lease。界面共享时间、播放暂停、音量、Seek、模式、队列与 stop。模板与主题只改变视觉。

普通底栏保持挂载并视觉隐藏，沉浸式控制区独立显示。关闭页面回到来源路由，不停止音频；返回搜索后原小播放器继续操作。无当前歌曲时显示简洁空态，不根据 URL 参数恢复受限媒体。`recovery-player.mjs` 和 `usePlayer.ts` 本期未改。

## 新歌词契约与生命周期

核对运行服务的 `/openapi.json`，接口为 `GET /api/lyrics?providerId=...&platformId=...`，直接使用 `api/lyrics.ts` 和 `types/core.ts` 的 LyricDocument。响应状态为 synced/plain/instrumental/unavailable；同步行字段为 startMs、endMs、text、translation、romanization，另保留 plainText 和未对齐翻译。前端未重新解析 LRC，不通过歌词请求触发 Provider.resolve。

根提供者创建唯一 `useLyrics`，`player/lyrics-state.ts` 的小型请求生命周期工具按稳定身份去重，切歌取消并以代次忽略旧结果，同时校验返回身份。歌词错误与没有歌词分开，失败显示重试入口；请求失败不会阻止或暂停媒体。换模板、页面进入退出和相同身份的媒体恢复不重新请求。退出沉浸页面只卸载展示和滚动监听，根级歌词仍供当前歌曲使用；根销毁取消在途请求。

时间线二分查找，按 audio.currentTime 换算毫秒；处理起始前、结束间隙与快速 Seek。相同时间戳使用最后一行的索引，展示整组行高亮，不冒充逐字时间。原文、对齐翻译、罗马音独立显示并保留换行；无时间戳文本使用 pre 保留段落，instrumental 显示纯音乐，unavailable 显示暂无歌词，网络失败不被归入无歌词。

沿用旧三秒恢复跟随策略：只有滚轮、触摸移动、滚动键等用户输入暂停自动跟随；程序滚动不触发暂停。用户滚动停止三秒后恢复，也可点击“立即恢复”。自动居中只在活动行、行数据、窗口尺寸或对齐变化时更新，没有每次 timeupdate 创建 Tween。隐藏滚动条但保留滚轮、触摸及键盘滚动。

前三套歌词默认分别为居中、居左、居中，与旧实现的默认对齐一致；用户选择优先。对齐偏好沿用旧实现的版本兼容存储方式，按模板保存；设置页卡片与实际模板共用同一选择器。切换对齐只改变歌词文本对齐并重新居中当前行，不更改音频。

## 真实浏览器验收

`server/scripts/verify_vue_immersive.py` 连接真实 Vue 5174、新 Core 8001，使用 Chromium headless。页面搜索“银临”，按实际返回的稳定身份定位酷我 `7075956`《狐言》，不依赖结果顺序。本轮真实播放时间推进，歌词 API 返回 90 行同步歌词；原歌词内容只在浏览器渲染，不保存整份响应。

验证 50 秒附近活动行、暂停 600ms 高亮保持，连续 Seek 至 70/140/100 秒后最终活动行正确，继续播放时间推进。切换四套模板、前三套左右对齐、用户滚动与三秒恢复、390/768/1440 宽度、深色与跟随系统、减少动态效果、返回搜索均通过。所有转换保持原 audio 身份；切四模板与主题后成功 open 和歌词请求都仍为 1。返回页面后没有旧封面飞行动画残留。

队列检查三条歌曲、固定高度、模式循环、清空及移动手势；真实 Lease 关闭后其流能力 HEAD 为 410。结果见 `immersive-real-result.json`：pageErrors=[]、consoleErrors=[]、单一根 Audio，未保存能力 URL。另验证无选曲直接访问沉浸式页面、非默认模板和对齐刷新恢复，均不发新的媒体或歌词请求。

本轮歌词可用性探测（仅保留状态和数量）：

| 来源/ID | HTTP | 结果 |
| --- | --- | --- |
| 酷我 9942644 | 502 | 本期《东风志》歌词上游失败，媒体仍可播放 |
| 酷我 7075956 | 200 | synced，90 行，本期新 Vue 真实同步样本 |
| QQ 001e7VNQ43nv4W | 200 | synced，49 行，仅独立 API 探测 |
| 网易云 30352891 | 200 | synced，40 行，仅独立 API 探测 |
| 咪咕 600929000006452915 | 200 | synced，66 行，仅独立 API 探测 |

没有将四个平台的独立 API 探测声称为四次新 Vue 播放验收。真实《狐言》没有翻译，翻译展示由下述人工 Fixture 单独验证。

## 受控实验与回归

`verify_vue_immersive.py --controlled` 在专用 8002/5175 注入自生成 WAV 和按新 LyricDocument 构造的人工歌词，返回 30 个稳定身份，用于面板滚动、翻译与生命周期验证；没有修改生产配置。为避免长验收中夹入自然结束切歌，WAV 为自生成 192 秒；自然 ended 的四模式验证继续由 D2 的 8 秒 Fixture 承担。

本期受控轮次验证翻译、暂停和 Seek、相同身份媒体恢复时歌词不重取、B 媒体/歌词挂起后切 C 的晚到隔离、打开中清空、恢复中清空、纯文本/纯音乐/无歌词/503 网络错误分别展示。清空后 audio 暂停且无 src，持久化 queue=[]、currentQueueKey=null。最终成功 open 10 个，对应流能力全部 410，MediaStore 记录及 active Lease 均为 0。原生续租观察到 204；故意关闭 Lease 导致一次自动重开，歌词请求数保持不变。受控故障 Console 503 是刻意注入，无 pageError；见 `immersive-controlled-result.json`。

D1 真实播放回归通过：暂停/继续、音量静音、中段及近末尾 Seek、路由连续性、单一 audio、关闭 410。《东风志》新增歌词请求的上游 502 不影响这些媒体断言。D1 受控回归通过 renew 204/410、同 Audio 恢复、晚到 Lease 关闭、人工 open 503 后错误与重试，最终四个能力全部 410。

D2 真实与受控队列脚本也重新通过：真实 A/B 上下首、四模式、音量、触摸、路由和安全刷新；受控自然 ended、列表循环、单曲循环不新增 open、随机历史、快速切歌及晚到清理。受控 12 次成功 open 最终全部 410，无活动 Lease 或媒体记录。D2 真实轮次 Console 中出现《东风志》歌词 502，媒体与队列验收通过。回归结果在本目录 regression-D2-real / regression-D2-controlled，未覆盖以前报告的历史截图。

原 D1/D2 脚本补充新歌词能力的 unavailable Fixture，避免人工 Provider 缺方法产生无意义 500；D2 根据本期移除关闭按钮改为 Escape，通过逐项移除待播验证保留当前曲。原 clearPending 控制器行为仍由既有 Node 测试覆盖。增加 MUSIC_CORE_VERIFY_OUT 输出目录参数，回归截图与旧交付分开；两个受控脚本使用相同专用端口，串行运行。

## 构建、截图和限制

- `pnpm test`：33 项通过，保留原 27 项；新增覆盖歌词边界/重复时间、晚到和取消、错误分类与重试、独立外观持久化、打开中清空。
- 后端 pytest：513 项通过，只有既有 Starlette/httpx 弃用提示。
- `pnpm typecheck`、`pnpm build`：通过。PlayerView 路由懒加载，主 JS 约 492KB，模板 JS 约 14.6KB；不通过调高体积警告阈值隐藏问题。
- 没有新增依赖，没有修改后端业务、Lyrics/Playback API、队列算法或恢复协调器；server 修改仅验收脚本。
- 真实网络失败和受控故障与成功轮次分开记录。早期受控 WAV 过短导致自然结束干扰恢复断言，后改为长人工音频；系统主题事件与遮罩关闭断言改为等待真实异步状态，不将早期失败轮次计为通过。

以下均为新 Vue 运行截图，非静态设计稿，已检查 Light/Dark、弹层位置和移动宽度：

- [桌面固定队列](screenshots/immersive-desktop-queue-fixed.png)、[桌面空队列](screenshots/immersive-desktop-queue-empty.png)
- [移动固定 Drawer](screenshots/immersive-mobile-queue-fixed.png)、[移动空队列](screenshots/immersive-mobile-queue-empty.png)
- [经典唱片机](screenshots/immersive-template-classic.png)、[沉浸大唱片](screenshots/immersive-template-vinyl-wide.png)
- [方形封面](screenshots/immersive-template-square-cover.png)、[纯净歌词](screenshots/immersive-template-lyrics-only.png)
- [经典居左](screenshots/immersive-classic-left.png)、[大唱片居左](screenshots/immersive-vinyl-wide-left.png)、[方形居左](screenshots/immersive-square-cover-left.png)；对应模板截图为居中
- [移动同步歌词](screenshots/immersive-mobile-immersive-lyrics.png)、[深色沉浸播放器](screenshots/immersive-immersive-dark.png)

本期目标完成。实际限制：使用 Chromium 模拟视口/触摸，未声称经过真机 Safari；真实《东风志》本轮歌词失败，真实翻译未验证而以人工译文验证；封面缺失或跨域无法取色时使用已有音乐图案和默认环境色。本阶段未实现下载页面、下一首预解析、品质选择或逐字卡拉OK，也没有建立额外歌词特效引擎。文档和结果不包含完整受版权保护歌词、媒体签名 URL、Cookie 或 Token。
