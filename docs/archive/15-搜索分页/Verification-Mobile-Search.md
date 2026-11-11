# 15 移动端搜索与普通底栏 — 验收记录

## 移动端搜索与普通底栏精简

根据移动端验收反馈，在 600px 以下隐藏搜索歌曲项第三行“专辑名 · 时长”（保留歌名、歌手、来源和真实错误信息），普通歌曲项最小高度由 84px 收为 72px。搜索、下载、设置页共用顶栏的历史前进 / 后退按钮隐藏；搜索框占满第一行，四来源直接显示在下方并按可用宽度自然换行。SourceSelector 只保留 SearchBar，删除来源弹窗及其定位、全局事件和按钮，无需点开来源。

普通页底部播放器在手机断点保留封面、歌曲信息、Lucide play / pause 与队列按钮；模式、上一首、下一首、音量、进度、时间、歌词按钮以及常驻重试 / 关闭不再占位。真实播放失败仍显示状态消息，中央播放按钮在 error / network / blocked 时复用重试动作。使用原 player.toggle / retry / QueuePanel，不新增播放状态。封面仍可打开沉浸页；桌面完整控件与移动沉浸页的五按钮和上方进度条保持原布局。

验证：前端 41 项测试、vue-tsc 与 Vite build 通过；主包约 508KB，既有 500KB 告警保留。真实 Chromium 检查 320 / 390 / 600px 的 Light / Dark：四个来源全部可见，来源盒位于搜索框下方，320px 自动换到第二行，无横向溢出；结果项附加元数据隐藏，普通底栏只有两个操作按钮，进度控件不挂载。播放 / 暂停、队列 Drawer、下载 / 设置 / 搜索导航可用，纯视觉和导航操作不增加 Open，同一 Audio 连续播放。切回 1440px 后恢复历史按钮、完整传输区与歌词入口。四来源选择仍可勾选并触发原搜索；受控服务仅提供酷我人工歌曲，临时勾选其他真实 Provider 的上游请求出现 500，不将此记作真实多平台搜索验证。

随后原 D1 恢复流程继续通过：renew 204 / 410、四次 Open、关闭后四条流均 410，Seek / 音量静音 / 暂停继续 / 路由连续性 / 晚到隔离 / 单 Audio 通过，页面异常为空。未修改后端、队列算法或媒体恢复链路；未自动提交 Git。

截图：[390px Light](screenshots/mobile-search-search-390-light.png)、[390px Dark](screenshots/mobile-search-search-390-dark.png)、[320px 自动换行](screenshots/mobile-search-search-320-light.png)、[600px](screenshots/mobile-search-search-600-light.png)、[下载页](screenshots/mobile-search-page-下载-390.png)、[设置页](screenshots/mobile-search-page-设置-390.png)、[桌面完整布局](screenshots/mobile-search-desktop-unchanged.png)。

补充：真实 Chromium 点击普通底栏封面，路由进入具体歌曲的 /player/:id，鼠标 / Tab 唤醒后移动沉浸操作层仍为五个按钮、进度条可见，无页面异常。[移动沉浸页保持原布局](screenshots/mobile-search-immersive-retained-390.png)。明暗截图在主题切换稳定后重新采集，避免截到主题过渡的中间帧。
