# 14 歌曲行与播放队列状态 — 验收记录

## 歌曲行与播放队列状态视觉统一

搜索结果移除常驻“正在播放 / 已暂停”文字，仅保留 error、network、blocked 的真实状态消息。普通、播放、暂停保持原有信息布局；封面复用 Lucide play / pause / loader-circle，状态直接读取现有全局播放器。当前项即使没有 Hover 也显示遮罩和选中背景，Hover / 键盘焦点保留反馈。未新增播放器状态、Audio 或 Lease。

QueueList 将背景与交互范围扩展到整个 article，包含封面、文字和右侧移除区域；左右 Padding 统一为 8px。播放按钮的透明命中范围覆盖整行，移除按钮独立位于其上层并停止冒泡。封面点击与文字点击执行同一操作，当前项暂停继续选中；固定高度、内部滚动、空状态、播放模式和队列算法保持原实现。使用现有条目 key / selectedId 判断身份，不按歌名匹配。

根据范围验收，确认当前 Core 搜索来源只有酷我、QQ、网易云、咪咕四个；删除 SearchBar 的研究来源分组、primaryOnly / researchOnly 参数，以及首页、设置页和 SourceSelector 的相应调用分支。保留四来源选择、至少一个来源限制、原偏好存储，以及窄屏来源弹层。未扩展解析器或改动后端。

### 验证结果

- 前端 41 项测试通过，vue-tsc / Vite build 通过。现有约 510KB 主包告警保留，未调整阈值。
- 真实 Chromium 在受控 WAV 音频与新 Core / Vue 上检查搜索行正常、播放、暂停的 boundingBox 高度，差值小于 0.1px；play / pause 图标与队列同步。队列封面实际坐标点击可以暂停 / 继续，切换 B 后只高亮 B，移除当前 B 不会误播放，清空后显示空状态且 Audio 暂停。
- 390px / 1440px、Light / Dark 均有截图，无横向溢出。截图中的人工测试歌曲用于隔离 UI 和媒体恢复行为，不冒充新的真实平台成功记录；之前的六张真实封面验收完整保留。
- 独立运行原 D1 播放恢复脚本通过：4 次 Open、renew 204 / 410、关闭后四条流地址均为 410；暂停 / Seek / 音量静音 / 路由连续性 / 唯一 Audio / 旧异步响应隔离通过，页面异常为空。主动制造的 410 / 503 与取消请求属于该脚本的恢复场景。
- 扩展队列交互检查与原 D1 分开验收：移除和清空提前释放媒体记录后，末尾旧地址可能已返回 404，不能套用原脚本“四条仍有记录的租约全部返回 410”的前提。上述队列行为断言已完成，原 D1 的断言未被放宽或改写。

截图：[桌面暂停队列](screenshots/row-status-desktop-paused-queue.png)、[桌面 Light](screenshots/row-status-queue-1440-light.png)、[桌面 Dark](screenshots/row-status-queue-1440-dark.png)、[移动 Light](screenshots/row-status-queue-390-light.png)、[移动 Dark](screenshots/row-status-queue-390-dark.png)、[真实错误状态](screenshots/row-status-controlled-error.png)。

本节只修改必要前端组件及其调用处，没有新增依赖；没有自动提交 Git。仓库已有的其他阶段修改与用户格式调整继续保留。

补充 DOM 验收：队列当前项实际背景为 rgb(237, 237, 237)，封面距行左缘与删除按钮距行右缘均为 8px；键盘 Tab / Shift+Tab 聚焦时整行伪元素显示 solid 轮廓。Hover 时封面遮罩 opacity 为 1；打开队列、Hover 和焦点移动没有增加 Open，Audio 引用及播放状态不变。[搜索行 Hover 截图](screenshots/row-status-search-hover.png)。
