# 13 Vue客户端基础 — 搜索接入与页面结构

日期：2026-11-10。建立 Vue 客户端入口、页面布局、路由、主题和 Core 搜索接入。

## 开发与运行

从项目根目录分别打开两个终端。

```powershell
# 终端一：启动后端
Set-Location server
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

```powershell
# 终端二：启动前端
Set-Location web
pnpm install
pnpm dev
```

Vite 地址为 `http://127.0.0.1:5174`，`/api` 请求代理到 8001。可通过 `web/.env.local` 中的 `MUSIC_CORE_API_TARGET` 指定后端代理目标；凭据不通过 `VITE_` 环境变量暴露给浏览器。生产部署需要同源 `/api` 反向代理和 SPA history 回退；本阶段未部署。

前端使用 Vue 3、vue-router、GSAP、Vite、Tailwind 和 Lucide。新增 `@vueuse/core` 15.0.0，仅用于持久化来源搜索偏好；没有新增播放器状态管理框架。

## 页面与接口

客户端包含首页、搜索、下载和设置路由。AppShell 负责桌面侧栏、移动导航、顶部搜索和播放器插槽；SearchView 通过统一 Core 客户端请求搜索，不直连音乐来源。

`web/src` 按 API、类型、composables、views、app、components、features、appearance、styles 和 player 工具组织。根组件组装提供者、Shell 与 Router；主题在入口启动时加载。播放器插槽在本阶段仅提供基础底栏布局，未接通播放会话。

| API | 本阶段处理 |
|---|---|
| `GET /api/providers` | 读取来源顺序、默认来源和能力；映射为来源选择控件 |
| `POST /api/search` | 按 providerId、关键词、limit 和游标搜索；不解析媒体 |
| `POST /api/playback/open` | 类型与请求模块已准备，尚未接入底栏 |
| 播放会话、歌词、下载 | 类型与 API 边界已核对，本阶段页面未发起相关请求 |
| 错误处理 | 统一解析 `error.message`，支持 JSON、取消和 20 秒超时 |

`TrackIdentity`、`SongCandidate`、`OpenResponse`、`LyricDocument` 与下载任务类型根据 FastAPI 路由和 OpenAPI 契约建立。列表展示模型保留完整 `identity`，按 `[providerId, platformId]` 区分来源内录音；标题或歌手分组只改变展示，不合并版本身份。

## 搜索行为

选中来源分别发起搜索请求，最多四个并发，先返回的结果先展示。每个来源单独保存游标；加载下一页时只请求仍有游标的来源。新搜索会取消旧请求并增加代次，合并结果前再次核对代次，防止迟到响应覆盖新结果。跨页按稳定身份去重；失败来源保留已有结果并单独提示。

真实酷我搜索以“齐豫”为关键词，首批返回 10 条，加载下一页后数量增加。标题、歌手、专辑和时长来自实际响应；缺少封面时使用占位显示。四来源请求、旧响应隔离和单来源失败场景使用受控响应验证，不代表四个平台均已完成真实搜索验收。

## 浏览器验收与截图

使用 `server/scripts/verify_vue_search.py`，连接本地 FastAPI、Vite 和 Chromium 153.0.8010.12。验收覆盖首页、真实搜索与分页、Home/Search/Downloads/Settings 路由、深色模式、移动导航、来源选择、本地偏好、迟到响应隔离和单来源 503 错误。

在 390、768、1440 像素视口检查横向溢出、桌面侧栏、移动导航、搜索框与来源选择控件。浏览器错误列表为空；控制台中的 503 来自刻意注入的失败响应，取消请求产生的 `ERR_ABORTED` 属于预期行为。全程没有发起媒体解析请求。

- [桌面首页](screenshots/desktop-home.png)
- [桌面搜索](screenshots/desktop-search.png)
- [移动首页](screenshots/mobile-home.png)
- [移动搜索](screenshots/mobile-search.png)

截图保留当时页面状态，作为浏览器验收证据，不代表设计稿或媒体播放结果。

## 构建与回归

`pnpm install`（pnpm 11.1.2）、`pnpm build` 和 `pnpm typecheck` 均通过；构建产物约 301 KB JS、47 KB CSS。后端测试为 513 passed，保留一条既有 Starlette/httpx 弃用警告。新增依赖只有 VueUse 及其传递依赖。

本阶段没有部署生产环境；播放、歌词与下载页面仍待各自任务接入对应 API。有限真实搜索结果不代表四来源长期可用。
