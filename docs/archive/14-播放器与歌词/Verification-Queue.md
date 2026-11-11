# 14 播放队列 — 播放队列与交互验收

日期：2026-11-10。验证覆盖当前队列控制器、持久化和播放器交互；旧实现仅用于行为对照。

## 队列接线

`web/src/player/useQueue.ts` 是唯一播放器内的队列控制器，由根级 `usePlayer.ts` 创建。复用[13 Vue客户端基础](../13-Vue客户端基础/Verification.md)建立的 `queue-navigation.ts`、`player-persistence.ts` 和 `utils/player-queue.ts`；全局播放器只有一个队列控制器和一个媒体状态。

队列只持有稳定身份、歌名、歌手、专辑、封面和时长。键为 `[providerId, platformId]` 的序列化元组，同名不同平台或不同录音 ID 分开；同一具体版本重复添加会更新元数据，不重复插入。添加不调用 open。点击其他版本只加入该版本，不把搜索结果整体加入。

歌曲操作菜单提供立即播放、添加到播放队列、从队列移除。当前歌曲再次点击仍为暂停/继续，不产生新 Lease。队列条目可选择、移除、清空待播，并标出当前位置。清空待播保留当前条目及正在播放的音频；删除当前条目会明确停止并关闭其会话。

选择条目、上一首、下一首都通过原 `usePlayer.select → RecoveryPlayer.select → /api/playback/open`；队列不读写 generation、session、Lease 或流地址。历史只在仍为当前选择且媒体打开成功后提交。原 `recovery-player.mjs` 本期保持不变，继续使用根级唯一 audio 与续租定时器。

沿用旧纯逻辑的模式名称，UI 对应为：

| 内部值 | 界面 | 行为 |
| --- | --- | --- |
| order | 顺序播放 | 自然结束向后走，末尾停止 |
| repeat_all | 列表循环 | 末尾回到首曲 |
| repeat_one | 单曲循环 | 自然结束在同一 audio 上 seek(0) 后继续；手动下一首仍切歌 |
| shuffle | 随机播放 | 可注入随机源、排除当前曲、使用随机袋；上一首回到实际成功播放历史 |

仅真实 audio 的 `ended` 且当前仍有选曲时推动队列；错误继续交给恢复协调器，不自动无界跳歌。顺序末尾结束后，点击播放能够从头继续。

## 安全持久化

使用现有显式投影、校验与上限工具，保存到 `music-core.queue.v1`。只恢复队列、当前位置、模式及必要导航历史；最多 200 条队列、1000 条历史。恢复时保留随机袋，不把全部歌曲误当新条目再次混入。未知版本、损坏 JSON、不合法身份和无法使用的存储安全忽略。

不序列化 resolved、PlaybackLease、playbackId、streamUrl、Cookie、Token 或解析结果；封面排除带凭据及音频资源的 URL。音量继续使用 D1 的 `music-core.volume.v1` 和原 audio.volume，队列不拥有第二份运行时音量。刷新只恢复队列展示，不 open、不 resolve、不自动播放；首页有恢复队列时也可打开面板。

## shadcn-vue 与原主题

阅读并参考官方 [Vite 安装](https://shadcn-vue.com/docs/installation/vite)、[Popover](https://shadcn-vue.com/docs/components/popover)、[DropdownMenu](https://shadcn-vue.com/docs/components/dropdown-menu)、[Slider](https://shadcn-vue.com/docs/components/slider)、[Drawer](https://shadcn-vue.com/docs/components/drawer) 文档，检查当前 Tailwind 4、Vite alias 和主题后，仅执行 `add popover dropdown-menu slider drawer --yes`，没有运行可能覆盖主题的 init。

基础源码位于 `components/ui`，业务组合位于 `components/player`。音量使用 Popover 与原生纵向方向的 Slider；模式及歌曲操作使用 DropdownMenu；桌面队列为底栏右侧 Popover，390px 使用底部 Drawer，共用 QueueList。Drawer 包含滚动上限、关闭入口和 safe-area 留白。没有旋转 Slider、hover 才可用的入口或第二个 audio。

直接新增依赖为 `reka-ui ^2.11.0`、`cn ^0.5.2`；锁文件同步。当前官方生成的 Drawer 也来自 reka-ui，没有额外引入 vaul 或第二套图标库。生成模板中的 Radix 图标引用改用原有 Lucide/Iconify。`components.json` 只记录组件配置，`shadcn.css` 留空，未导入全局重置。新增 `player-layers.css` 仅映射弹层到现有主题变量；原浅灰、白色、绿色及深色变量未被覆盖。底栏使用 deep 选择器把既有按钮样式应用到新子组件，避免出现浏览器默认边框。

根据验收反馈移除了 `tsconfig.json` 中的 baseUrl，保留 `paths: {"@/*": ["./src/*"]}` 与 Vite alias，没有用 ignoreDeprecations 静音。路径映射不要求 baseUrl，参见 [TypeScript 官方说明](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html)。当前锁定 TypeScript 5.9.2 的 typecheck/build 均通过；未升级项目的 TypeScript 版本。

根据交互验收反馈移除“更新搜索”按钮。搜索栏回车和搜索图标提交支持相同关键词重新搜索；新关键词仍由路由同步触发，避免发两次请求。中文输入法合成时的回车保护保留。

## 真实音乐浏览器

`server/scripts/verify_vue_queue.py` 使用真实 Vite 5174、新 Core 8001、Chromium headless，通过页面搜索“银临”。本轮实际元数据为：

| 位置 | 歌名 | 酷我 ID | 本轮用途 |
| --- | --- | --- | --- |
| A | 东风志 | 9942644 | 实际播放 |
| B | 狐言 | 7075956 | 实际播放 |
| C | 棠梨煎雪（纯音乐） | 381746494 | 添加并展示，未声称播放 C |

A 音频真实推进；重复点击暂停/继续不新增 open。用菜单加入 B、重复加入 B、加入 C，队列保持 3 条，添加未取链。队列选 B、上一首 A、下一首 B，UI 与真实 audio 一致。本轮 4 次成功 open，最终 4 个流能力 HEAD 均 410。结果见 `queue-real-result.json`，不记录能力 URL。

切换四种模式未新增媒体请求；音量键盘设到 30%，静音后再调整到 31% 立即取消静音。Escape、外点关闭、模式关闭后焦点返回通过。390px 通过触摸点击纵向轨道改变实际 audio.volume；Drawer 打开关闭正常。Home、Search、Settings 路由与深浅主题切换均保留原 audio；主题切换不新增 open。390/768/1440 无页面横向溢出。刷新后队列可见、audio 暂停且无 src、没有新增 open，随后从队列移除操作生效。相同关键词回车和搜索图标均再次发起搜索，页面没有“更新搜索”按钮。

真实轮次 pageErrors、consoleErrors 均为空。界面截图来自运行中的真实页面，已检查弹层定位、主题和移动端宽度：

- [模式菜单](screenshots/queue-playback-mode-menu.png)
- [音量弹层](screenshots/queue-volume-popover.png)
- [桌面队列](screenshots/queue-desktop-queue.png)
- [深色队列](screenshots/queue-desktop-dark-queue.png)
- [390px Drawer](screenshots/queue-mobile-queue-drawer.png)
- [真实歌曲底栏](screenshots/queue-real-playing-footer.png)

## 受控实验与 D1 回归

`verify_vue_queue.py --controlled` 在独立 Core 8002/Vite 5175 运行，注入自生成 8 秒 WAV，人工歌曲 ID 为 1/2/3。通过真实音频解码及接近结尾的 seek 等待浏览器原生 ended，未用伪造 ended 替代自然结束。验证顺序末尾停止、列表末尾回 A、单曲循环保持现有会话且 open 数不变；随机模式避免立即重复，上一首返回实际历史。

人工挂起 B 的 resolve，用户继续点击下一首到 C，放行 B 后 UI 仍为 C；旧 B Lease 清理，服务端仅一个 active Lease。额外派发 error 验证没有推进队列；不同 MediaError 的恢复与不重解析规则由原恢复测试覆盖。最终 12 个成功 open 对应的能力均为 410，MediaStore 记录和 active Lease 为 0；结果见 `queue-controlled-result.json`。受控短音频不冒充真实平台歌曲。

D1 `verify_vue_player.py` 真实轮次继续通过：播放、暂停/继续、中段及近末尾 seek、30% 音量与静音、路由连续、唯一 audio、关闭 410。D1 `--controlled` 继续通过真实 renew 204、主动关闭 Lease 后 renew 410 自动恢复、恢复后音量/静音保留、晚到请求隔离及人工 open 503 后可重试，最终四个能力 410，服务端清空。D1 脚本只更新音量控件操作方式以适配 Popover/Slider。人工 410/503 在 Console 的网络错误为故障注入预期，无 pageError。

验收过程中发现并修正：连续键盘调音量时异步 volumechange 回写造成增量偶发丢失，现 setVolume 同步回写 audio 的实际值；顺序结束后播放按钮的意图与原生 ended 不一致，现明确从头继续。两个受控脚本共用端口，必须串行；一次并行误跑造成环境冲突的结果已弃用，并增加服务未启动时立即报错，最终以独立串行成功轮次为准。

## 检查结果与边界

- `pnpm test`：27 项通过，含 D1 原有 21 项恢复测试及 6 项实际队列行为测试。
- `pnpm typecheck`、`pnpm build`：通过；构建约 488.2KB JS（gzip 173.1KB）、61.3KB CSS。
- 后端 pytest：513 项通过，保留既有 Starlette/httpx 弃用提示。
- 后端生产代码、Provider、Playback API、恢复模块及 MediaStore 未改；server 新文件仅为浏览器验收脚本。
- 正常轮次无重复 audio，受控轮次收尾无活动 Lease 和媒体记录。真实轮次只通过关闭后的 410 验证能力失效，未宣称检查真实服务内存。

本期目标已完成。未实现拖拽排序、下一首预解析、歌词同步、下载接线或沉浸播放器。浏览器验收为 Chromium 模拟视口与触摸，没有声称通过真机 Safari。旧预准备面板为临近结束获取下一首资源并记录命中/未使用；本期没有创建任何后台预准备 Lease。
