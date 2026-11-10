# 40-C：旧Vue前端迁移与Core搜索接入

2026-11-10。目标工程C:/Code_Home/2_projects/musicdl-lab；旧Lab只读，开始Git干净，未提交或推送。新增web/与本期浏览器脚本、报告/截图；未修改后端业务、公共模型或旧工程。

## 运行与工程

```powershell
cd C:/Code_Home/2_projects/musicdl-lab/server
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001

cd C:/Code_Home/2_projects/musicdl-lab/web
pnpm install
pnpm dev
```

Vue地址http://127.0.0.1:5174，Vite将/api代理至8001；可通过web/.env.local中的MUSIC_CORE_API_TARGET改变服务端代理目标，不使用VITE前缀向浏览器暴露服务凭据。生产构建要求同Origin反向代理/api及SPA history回退；本期没有部署。选择新端口避免影响旧Lab服务。

保留原Vue3、vue-router4、GSAP、Vite7、Tailwind4、Lucide图标和原锁定版本，不安装Pinia、React、Element Plus或HTTP框架。新增@vueuse/core15.0.0，仅用useStorage保存四来源搜索偏好，没有改写播放器状态机。未引入shadcn-vue：原设置样式卡片、来源Popover已有可用实现，本期无需为了验证组件库改动主题；Dialog/Popover基础设施可后续按真实需求评估。

## 先审计再迁移

读取旧package/Vite/main/App、布局和路由、Home/Search/Downloads/Settings、歌曲列表/分组、useLabSession及其搜索/解析/下载/转换/Range/恢复依赖、player/stores/types/api和主题。旧provideLabSession会一次性创建全部旧媒体消费者，不适合直接搬入本期入口。新工程没有为兼容它重建旧后端API。

| 分类 | 处理 |
|---|---|
| A：展示与交互 | 原AppShell、AppSidebar、MobileTabBar、AppTopbar、GlobalSearch、SourceSelector、SearchBar、封面/分组列表、时间问候、ASCII海洋引擎/字体/许可证、主题tokens/themes/Tailwind、播放器样式卡片大体原样复用 |
| B：数据依赖 | 新useCoreClient只提供搜索；SearchView替换脚本及必要操作区，保留列表组件及原CSS；useProviders映射新目录字段；Downloads保留空态布局，移除旧任务轮询；Settings保留主题/4款播放器卡片及来源选择，移除未接入的预准备开关 |
| B：播放器 | AppShell保留播放器插槽；本期底栏为原三栏结构的禁用占位，未复制旧媒体会话。原BottomPlayer、AudioPlayer、VinylPlayer、LyricPanel及队列/Popover视觉源码置于web/deferred，保留动画及样式，不参与当前构建，后续需重新接线依赖 |
| C：实验内容 | 不迁移DebugView/RangeDebugPanel、AmbientDemo实验路由、Range时间轴、请求观察/基准、旧search-jobs/SSE、resolve/stream/token/Lease网络适配、转换弹窗、旧实验会话和预解析开关；导航仅首页/搜索/下载/设置 |

没有将沉浸播放器改写成新模板，也没有宣称它们本期已能运行；deferred为保留视觉源文件，不是可单独编译的播放器包。当前队列没有媒体或持久化恢复接线；原纯队列导航/安全归一化工具随展示依赖保留。原恢复协调器的服务端开发页验证成果仍在server，本期不创建第二套协调器。

实际布局修复：删除实验室导航后，旧AppSidebar固定navigation[4]索引失效，浏览器发现白屏；改为按/settings路径查找。移动导航从5列改4列。其他明暗主题、响应式断点及ASCII渲染策略未重设。

## 文件结构与契约

web/src含api/、types/、composables/、views/、app/layout与app/router、components/、features/home、appearance/、styles/、纯player/utils/store工具。main.ts仍负责主题启动；App.vue只组装根提供者、Shell和Router。旧useLabSession命名已替换为useCoreClient，旧HTTP模块未进入入口。并非把旧web目录含node_modules/dist/tests整体复制；只保留当前入口依赖闭包及上述deferred视觉源码。

直接读取新FastAPI路由、Pydantic模型，并实际调用create_app().openapi()。src/types/core.ts据此生成公开DTO：TrackIdentity、SongCandidate、OpenResponse、LyricDocument、DownloadTask及相关模型。旧列表所需扁平字段作为CandidateRow展示模型保留，不冒充后端SongCandidate；它包含原始identity和provider/platform字段，无已解析媒体格式或playable=true。展示ID是JSON编码的[providerId,platformId]，不是旧随机Token；不同来源相同platformId不合并身份。分组按标题/歌手只影响展示，每个版本保留独立身份。

| 新API | 实际契约/本期处理 |
|---|---|
| GET /api/providers | order/defaultSelected/capabilities，不再读取旧enabled/defaultEnabled作为线上字段；前端映射为选择控件需要的属性 |
| POST /api/search | providerId/query/limit=10/cursor；响应items和nextCursor；搜索不解析媒体 |
| POST /api/playback/open | identity → playbackId/streamUrl/media/expiresInSeconds；api/playback.ts准备入口，未绑定底栏 |
| GET/HEAD stream，POST renew/close | 服务端相对streamUrl及独立Lease；renew/close为204，不能按JSON解析；不使用旧/api/stream/{resolvedId} |
| GET /api/lyrics | providerId/platformId → 标准LyricDocument；接口已准备，未绑定旧LRC解析器 |
| POST/GET /api/downloads，cancel/retry | identity创建独立任务，poll状态；领域API已准备，下载页尚未调用 |
| 错误 | 读取error.message；HTTP模块统一JSON、取消与20秒超时，使用同Origin/api，不持有平台Cookie或解析配置 |

播放/歌词/下载API只是已核对的函数，不自动执行。前端没有/api/search/jobs、/api/resolve、旧媒体token入口、SSE或任意上游媒体直连。旧展示类型中的兼容字段不作为新公开契约或网络调用依据。

## 搜索行为

每个选定来源独立POST，最多四个并发，先返回先展示；某来源失败不清空其他结果。新搜索中止旧请求并增加代次，响应合并前复核代次，避免旧结果覆盖。每来源单独维护真实nextCursor，加载更多只请求尚有游标的来源，并按稳定身份去重；无伪造页码。loading/empty/error/来源失败和更新搜索可观察。保留版本展开，所有播放/下载/下一首按钮禁用并标记下一阶段接入，不能拿元数据当已可播放。

本期真实新Core搜索关键词齐豫、来源kuwo，首次返回10条；点击加载更多后实际行数超过10。歌名/歌手/专辑/时长来自真实响应；酷我本次未给封面则保留原封面占位，没有编造封面。四来源配置请求、旧响应隔离和部分失败保留其他来源使用独立人工Fixture验证，不声称四来源都完成本期真实搜索。

## 浏览器与截图

运行server/scripts/verify_vue_search.py；真实Vite5174、新Core8001和Chromium153.0.8010.12，headless。测试首页输入Enter到搜索列表、真实分页、Home/Search/Downloads/Settings路由、设置深色模式、移动底部导航、来源设置、本地偏好、旧请求晚到和单来源503。

检查390/768/1440宽度无document横向溢出；桌面侧栏、窄屏底栏、搜索输入及来源Popover可用。4张截图来自当前新工程，并已视觉检查首页及移动搜索：

- [桌面首页](screenshots/desktop-home.png)
- [桌面搜索](screenshots/desktop-search.png)
- [移动首页](screenshots/mobile-home.png)
- [移动搜索](screenshots/mobile-search.png)

截图保留旧灰白主题、透明搜索框、音符/简谱ASCII鱼背景及分组歌曲列表，不是设计稿。截图截取于真实搜索阶段，后续人工响应不冒充真实歌曲。脚本最终pageErrors=[]；Console只有故意注入的人工503，失败请求为切换关键词产生的4个预期ERR_ABORTED；初轮favicon404已通过内联图标修复。没有真实媒体解析请求。来源模拟四个均发POST，旧响应不能覆盖新查询；模拟咪咕失败时其他结果仍存在。

## 构建、依赖和回归

pnpm install成功（11.1.2）；pnpm build与pnpm typecheck均通过；构建约301KB JS/47KB CSS，未作全播放器接线或性能基准承诺。Vite实际启动，与FastAPI代理联通。后端未改，pytest513 passed，一个既有Starlette/httpx弃用警告，含原Node恢复测试包装。未为纯前端骨架重复请求四来源整曲播放/下载。

新增依赖仅VueUse及其传递依赖，锁文件已记录。未安装shadcn-vue，不覆盖旧主题。旧复制注释保留原文，新说明使用中文。旧项目及references未变。Git只有新增web、本期脚本和报告/截图，未提交。

## 40-D明确边界（未开始）

下一阶段按稳定身份接新Core open/renew/close及唯一audio；复用已有恢复协议并恢复原BottomPlayer/沉浸模板；将LyricDocument按currentTime映射旧歌词视觉，避免再解析LRC；把Downloads页接任务列表/进度/取消/重试；恢复队列交互与安全持久化，只存identity/元数据/用户偏好，不存媒体URL或Lease。预准备应在真实会话链路明确后再接线。不能直接启用deferred中的旧Lab网络与随机Token逻辑。
