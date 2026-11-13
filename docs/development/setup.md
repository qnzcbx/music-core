# 开发环境与验证

本文提供从依赖安装到启动客户端和后端的完整路径。所有示例均使用本机开发地址。

## 工具版本

- Node.js：建议使用 22.12 或更新的 22.x。当前 Vite 7 支持 Node 20.19+ 或 22.12+；前端测试脚本使用 Node 的 `--experimental-strip-types`，使用 Node 22.12+ 可覆盖完整开发命令。
- pnpm：锁文件为 pnpm lockfile v9，使用 pnpm 9 或更新版本；项目未在 package.json 中固定具体 pnpm 版本。当前验证环境为 pnpm 11.1.2。
- Python：3.10 或更新版本。后端项目声明 requires-python `>=3.10`。
- FFmpeg/FFprobe：仅需要转码或相关媒体验证时安装；不是基本搜索、播放和原格式下载的启动前提。

## 安装依赖

### Windows Git Bash

在项目根目录打开 Git Bash：

```bash
# 后端：使用仓库提供的 Windows Python 3.10 开发依赖快照
cd server
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements-dev.lock.txt
```

requirements-dev.lock.txt 是 Windows Python 3.10 的精确开发环境快照，包含 pytest、Playwright 与浏览器验收依赖，不是跨平台通用锁文件。Git Bash 可直接运行 Windows 虚拟环境中的 python.exe，不需要使用 Linux 的 bin/activate。

Windows PowerShell 也可使用相同虚拟环境：

```powershell
Set-Location server
python -m venv .venv
& ./.venv/Scripts/python.exe -m pip install --upgrade pip
& ./.venv/Scripts/python.exe -m pip install -r requirements-dev.lock.txt
```

### macOS / Linux

其他平台使用项目声明的依赖范围：

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
# 需要浏览器专项验证时，再安装可选依赖：
python -m pip install -e ".[browser]"
python -m playwright install chromium
```

前端在独立终端安装：

```bash
cd web
pnpm install --frozen-lockfile
```

不要删除或重生成 pnpm-lock.yaml 来绕过安装错误。

## 启动服务

保持两个终端运行。PowerShell 后端：

```powershell
Set-Location server
& ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Git Bash（Windows）在 server 目录运行：

```bash
cd server
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

macOS/Linux 在激活虚拟环境后运行：

```bash
cd server
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

前端：

```bash
cd web
pnpm dev
```

Vite 默认监听 `127.0.0.1:5174`，并以 `strictPort` 拒绝自动换端口。后端默认监听 `127.0.0.1:8001`。打开 `http://127.0.0.1:5174`；后端健康检查为 `http://127.0.0.1:8001/api/health`，交互 API 文档为 `http://127.0.0.1:8001/docs`。

Vite 将 `/api` 请求代理到 `MUSIC_CORE_API_TARGET`，默认是 `http://127.0.0.1:8001`。可在启动 Vite 的终端临时设置覆盖值，或在 web 目录的本地 Vite env 文件中设置。Vite 只加载此前缀的变量。

## 来源及环境配置

服务端读取操作系统环境变量，不会自动加载 .env 文件。PowerShell 可在启动后端的同一终端设置：

```powershell
$env:MUSIC_CORE_QQ_COOKIE = "本机临时值"
$env:MUSIC_CORE_QQ_RESOLVER_ORDER = "official,vkeys,tang,xunhuisi"
$env:MUSIC_CORE_API_TARGET = "http://127.0.0.1:8001"
```

Git Bash 可在启动后端的同一终端设置：

```bash
export MUSIC_CORE_QQ_COOKIE='本机临时值'
export MUSIC_CORE_QQ_RESOLVER_ORDER='official,vkeys,tang,xunhuisi'
export MUSIC_CORE_API_TARGET='http://127.0.0.1:8001'
```

只设置确实需要的变量。不要把 Cookie、Token、签名媒体 URL 或个人目录写入文档、提交到仓库或复制到问题报告；真实凭据应通过本机环境注入。.env 与 .env.* 已被 Git 忽略，但 FastAPI 不会因此自动读取它们。

常用配置：

| 变量 | 用途 |
| --- | --- |
| `MUSIC_CORE_SOURCE_CONFIG` | 指定来源 JSON 配置路径；默认使用 `server/app/config/sources.json`。 |
| `MUSIC_CORE_QQ_COOKIE` | 可选的 QQ 请求 Cookie，属于敏感信息。 |
| `MUSIC_CORE_QQ_RESOLVER_ORDER` | QQ 已实现解析路线顺序；默认 `official,vkeys,tang,xunhuisi`。 |
| `MUSIC_CORE_NETEASE_RESOLVER_ORDER` | 网易云已实现解析路线顺序；默认 `native,gdstudio-preview,jfjt`。 |
| `MUSIC_CORE_DOWNLOAD_DIR` | 下载及本地文件扫描目录；默认是项目下载目录。 |
| `MUSIC_CORE_FFMPEG` | 可选 FFmpeg 可执行文件路径；FFprobe 需与它同目录或位于 PATH。 |
| `MUSIC_CORE_DEV_PLAYER` | 设为 `1` 后启用服务端开发播放器页面。 |
| `MUSIC_CORE_API_TARGET` | Vite 的 `/api` 代理目标；默认后端地址如上。 |

来源配置必须列出四个受支持来源 ID（kuwo、qq、netease、migu），且默认选中列表非空且不重复。配置错误会回退到内置默认值，并可从健康状态看到 degraded。修改配置后需重启后端。配置解析路线不会授予访问第三方服务的权限；使用前需遵守平台条款、版权要求和所在地法律。来源可能限流、失效或改变品质响应，不保证每首歌始终可搜索、播放或下载。

## FFmpeg 与 FFprobe

普通在线播放、原格式下载不要求安装 FFmpeg。当前可选转码为经验证的 FLAC 转 MP3；服务端还会用 FFprobe 检查源/目标媒体并检查转码输出。安装后应确保 ffmpeg 与 ffprobe 可在 PATH 中找到，或通过 `MUSIC_CORE_FFMPEG` 指定 FFmpeg，并让 FFprobe 位于同目录或 PATH。可在终端执行 `ffmpeg -version` 和 `ffprobe -version` 确认安装。没有可用编码器或检查失败时，对应转码选项不可用或下载任务会失败。

## 检查与回归

后端在 server 目录运行。Git Bash（Windows）：

```bash
./.venv/Scripts/python.exe -m pytest
```

PowerShell 可用 `& ./.venv/Scripts/python.exe -m pytest`；macOS/Linux 激活虚拟环境后用 `python -m pytest`。前端在 web 目录运行：

```bash
pnpm test
pnpm typecheck
pnpm build
```

build 命令先执行 TypeScript 类型检查，再生成 Vite 生产构建。在线 Provider 和浏览器专项验证依赖外部来源/Chromium，不属于基础构建；当前长期脚本及使用限制见[后端专用说明](../../server/README.md)。专项输出默认位于被 Git 忽略的项目根目录 .runtime 下。

## 常见问题

- **5174 端口已占用：** Vite 使用 strictPort，不会改用别的端口。停止占用进程后重启，或调整本地 Vite 配置并同步访问地址。
- **前端请求后端失败：** 确认后端在 8001 启动、健康检查可访问；如果地址不同，在启动 Vite 的环境中设置 MUSIC_CORE_API_TARGET。
- **Windows 找不到 Python/虚拟环境：** 确认 python 命令指向 Python 3.10+，然后在 server 目录重建 .venv 并按对应平台安装依赖。
- **pnpm 安装或 Vite 启动失败：** 检查 Node 版本满足项目工具链要求，并用仓库锁文件执行 frozen-lockfile 安装。
- **来源显示 degraded：** 检查自定义来源 JSON 是否包含四个来源 ID 及有效默认选项，然后重启服务。
- **转码不可用：** 检查 ffmpeg、ffprobe 和 MP3 编码器是否安装可用；不需要转码时可继续使用其他可用格式/品质。
