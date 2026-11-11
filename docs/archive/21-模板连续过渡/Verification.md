# 任务01：方形封面与沉浸大唱片连续过渡

## 审计与实现

复用 `web/src/composables/playerLayoutTransition.ts` 与根 `usePlayerTransition.ts`，不新建模板切换系统。原 classic / vinyl-wide 的0.76秒GSAP FLIP继续复用，窄屏支持见下方补充；此前 square-cover 只进入0.22秒淡入分支，本期新增 square-cover ↔ vinyl-wide 的共享封面形变。

当前四模板都在 PlayerView / VinylPlayer 中切换样式，实际 CoverArt 经 Teleport 在唱片中心与方形容器间移动；唱片旋转器只是 visibility:hidden，并未卸载。LyricPanel仅随歌曲身份更换而换key，模板不重挂载歌词。

共享视觉元素是同一CoverArt的临时视觉副本。切换前读取方形容器或唱片中心的实际DOMRect、圆角和当前旋转角；Vue完成目标布局后，再读取目标DOMRect。位置、宽高、圆角在0.76秒内以power2.inOut连续插值，正式图片暂时隐藏，因此不会同时显示两张封面；末帧恢复正式节点并删除代理。正向外围唱片按透明度与缩放展开，反向在实际旧唱片DOMRect上绘制纹理副本并收敛淡出，没有硬编码屏幕坐标或依赖中心封面比例推算外框。

旋转器和反光层的CSS动画均不修改，不重启animation、不接管currentTime；代理只衔接当前角度，跨±180度时展开连续角，避免额外整圈翻转。圆角变形时依据旋转角与裁切半径计算最小覆盖缩放，修复图像在中间帧露透明三角、外形像多边形的问题。

歌词列使用同一次capture得到的FLIP状态，按同样时长和曲线过渡位置与尺寸。歌词DOM、当前行、跟随滚动状态继续由原组件管理，没有调用歌词API或修改同步算法。

快速反向时，根协调器先记录当前代理的屏幕几何和角度，再清理旧GSAP上下文；新动画从该画面位置接续。统一cancel恢复原内联样式、删除封面与纹理副本。既有换歌、退出、resize和reduced-motion监听继续负责取消；未加载图像、无有效几何及纯歌词模板仍使用轻量降级。缺省封面也能走共享过渡。

## Chromium验收

脚本：`server/scripts/verify_square_vinyl_transition.py`。在实际新Vue页面中使用受控Core和真实Audio/WAV，封面使用网易云真实专辑图（齐豫《飞鸟与鱼》）；另验证无封面回退图。受控歌曲和歌词仅用于视觉与连续播放检查，不冒充本期新的平台解析结果。

1440 / 768 / 390px均运行双向往返。每个约0%、25%、50%、75%、100%点分别重跑相同路径并按时间采样，避免截图耗时把后面的过程帧挤到动画终点；不是仅两张最终截图。几何见 [frames.json](frames.json)。100%在末帧回调完成后读取；最初验收曾卡在760ms边界，等待最终帧后通过，没有为测试修改生产动画时长。

| 过程 | 起点 | 25% | 50% | 75% | 终点 |
| --- | --- | --- | --- | --- | --- |
| 桌面 方形→唱片 | [图](screenshots/1440-vinyl-wide-0.png) | [图](screenshots/1440-vinyl-wide-25.png) | [图](screenshots/1440-vinyl-wide-50.png) | [图](screenshots/1440-vinyl-wide-75.png) | [图](screenshots/1440-vinyl-wide-100.png) |
| 桌面 唱片→方形 | [图](screenshots/1440-square-cover-0.png) | [图](screenshots/1440-square-cover-25.png) | [图](screenshots/1440-square-cover-50.png) | [图](screenshots/1440-square-cover-75.png) | [图](screenshots/1440-square-cover-100.png) |
| 移动 方形→唱片 | [图](screenshots/390-vinyl-wide-0.png) | [图](screenshots/390-vinyl-wide-25.png) | [图](screenshots/390-vinyl-wide-50.png) | [图](screenshots/390-vinyl-wide-75.png) | [图](screenshots/390-vinyl-wide-100.png) |
| 移动 唱片→方形 | [图](screenshots/390-square-cover-0.png) | [图](screenshots/390-square-cover-25.png) | [图](screenshots/390-square-cover-50.png) | [图](screenshots/390-square-cover-75.png) | [图](screenshots/390-square-cover-100.png) |

768px过程同样保存于screenshots。Light/Dark与缺省封面：[浅色](screenshots/fallback-light-vinyl-wide.png)、[暗色](screenshots/fallback-dark-square-cover.png)。

已验证：经典↔大唱片原分支往返；多次新模板往返；原CoverArt与歌词视口的DOM引用保持同一；模板切换不新增Playback Open，同一个Audio持续播放；暂停时切换保持暂停；快速连续切换/反向后无残留代理；resize中途清理；减弱动画直接降级；动画中正常切歌清理旧代理；图像尚未加载时不构造错误共享封面。页面异常为空。

桌面从真实样式入口进入沉浸页；为直接覆盖移动端当前未显示的样式入口，脚本通过Vue组件现有selectLayout处理函数触发同一动作，没有在生产代码增加测试入口或第二份状态。长时间多次采样时验证Audio设置loop以避免受控短WAV自然结束，业务播放器未改。环境为Chromium仿真，不宣称真机Safari结果。

## 范围、检查与限制

前端45项测试、vue-tsc和生产构建通过；约520KB主包保留原500KB告警，未调整阈值。没有新增依赖。实际产品只修改两份既有视觉协调模块，未重构四套组件。唯一Audio、Lease、RecoveryPlayer、队列、Provider、下载、歌词数据/同步和封面取色算法未修改，也未重启用户常用服务。

保留用户已有的组件格式/界面修改与deferred删除，不回滚或提交它们。本期未自动提交Git。截图在现有screenshots忽略规则下，任务按整理后的连续编号归档为21。

限制：未加载图片和无效几何使用降级而非强行形变；窗口变化或换歌会安全结束当前视觉动画。主体角度必须与原持续旋转器衔接，代理不增加整圈旋转或控制播放状态。


## 补充：经典唱片机 ↔ 大唱片扩展至窄屏

移除原 `window.innerWidth >= 1024 && window.innerHeight >= 650` 门槛。现在只要经典/大唱片双方的真实唱片、中心封面、歌词列几何有效，就使用原0.76秒nested FLIP；不再因768px、390px或短屏自动退回0.22秒淡入。变量由desktop改名为vinylFlip，明确该分支不再代表桌面专用。减弱动画、无效几何、resize取消和样式恢复规则保留。

使用 `server/scripts/verify_classic_vinyl_responsive.py` 在1440×900、768×900、390×900、768×600真实Chromium页面中双向采样0 / 25 / 50 / 75 / 100%过程，25/50%实际计算transform均不为none，末帧恢复none；[几何与transform记录](classic-responsive.json)。

[768正向中间帧](screenshots/classic-768-900-vinyl-wide-50.png)、[768反向中间帧](screenshots/classic-768-900-classic-50.png)、[390中间帧](screenshots/classic-390-900-vinyl-wide-50.png)、[短屏中间帧](screenshots/classic-768-600-vinyl-wide-50.png)。所有起点、四分之一、中点、四分之三和终点截图均保存在同一screenshots目录。

验证Audio引用、持续播放、旋转器与歌词视口DOM引用不变，纯模板切换的Playback Open增量为0。暂停后快速往返保持暂停，完成后无transform残留；中途resize与prefers-reduced-motion同样清理正确。前端45项测试、类型检查和构建通过，既有包大小告警保留。没有修改旋转动画、播放业务、下载或后端，没有新增依赖，没有自动提交Git。
