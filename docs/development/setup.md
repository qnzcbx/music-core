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
| `MUSIC_CORE_LOCAL_MODE` | 仅设为 `1` 时启用本机永久音乐库、文件/目录管理；默认正式网页模式，下载成品交浏览器保存。 |
| `MUSIC_CORE_DOWNLOAD_DIR` | 显式部署覆盖；设置时网页目录更改被锁定。更改此环境变量需重启后端。没有覆盖时使用持久化目录，新安装 Windows 默认系统音乐目录本身。 |
| `MUSIC_CORE_DATA_DIR` | 独立应用数据目录，默认项目 `.runtime/app-data`；保存 downloads.sqlite3。切换音乐库时保持此目录不变。 |
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


## 下载库与命名

保存目录是后端所在机器上的位置。普通本机操作者可通过设置页的“更改目录”即时保存，无需 CLI 或重启。显式部署覆盖的 PowerShell 示例（设置后网页目录更改会锁定）：

```powershell
$env:MUSIC_CORE_DOWNLOAD_DIR = Join-Path ([Environment]::GetFolderPath('MyMusic')) 'Music Core'
# 也可使用其他已挂载磁盘上的目录，例如操作者自己的音乐库。
# 可选：独立数据目录只配置一次，之后切换音乐库不要更改它。
$env:MUSIC_CORE_DATA_DIR = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Music Core'
cd server
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

在显式本机模式下，环境变量不会自动从 .env 加载；仅变更部署环境覆盖需要重启，网页更改立即对新任务生效。默认仅更改保存目录，旧文件不移动、不改名，原 fileId 在文件未变化时继续可用。首次发现的旧项目 downloads 和操作者配置的目录会登记进索引；只扫描这些已知库，不搜索其他文件夹。手动复制进当前库的音频会在下次列表刷新/重启发现；实际移动后原 ID 失效，新位置生成新 ID，不按歌名猜配或续播。

设置页可选择歌曲名、歌手 - 歌曲名（默认）、歌曲名 - 歌手，保存到 SQLite；仅影响新建任务，重试作为新任务使用当时设置。运行中的任务保留创建时的命名规则。原样、转码和有效原文件保底走相同安全命名及不覆盖发布流程。目录不可写时设置页明确提示，下载报保存错误，不回退其他目录。任务状态本身仍为进程内状态，持久化的是成品索引、展示元数据及命名偏好。备份/迁移时同时保留应用数据目录，不能仅迁移音频后期待旧 fileId 不变。


## 图形化目录管理与旧下载迁移（06.1）

Windows 新安装无显式部署覆盖且没有旧安装/索引时，调用 SHGetKnownFolderPath 获取“音乐”目录本身，不追加子目录。已存在的安装保留原位置；非 Windows 保留项目 downloads。已有文件只扫描已知音乐库的当前目录，不递归子目录。音乐或下载快捷项同样使用系统 Known Folder API，不读取浏览器下载设置。

本机正常入口：安装依赖后双击项目根目录的 `打开音乐客户端.vbs`。它通过虚拟环境 Python 在后台执行 `tools/launch_local.py`，启动或复用后端、前端服务，由本机进程读取受 OS 权限保护的私有能力，向后端换取 60 秒有效、一次性使用的启动票据，再打开设置页。页面将票据交回后端，建立 12 小时 HttpOnly、SameSite=Strict 的管理会话并清除 URL 片段。长期私有能力不进入浏览器、普通 HTTP 响应或剪贴板。无需用户找授权文件、复制令牌、打开终端或重启服务。

直接输入普通网址不颁发管理能力，显示只读；有部署覆盖仍锁定。后端拒绝未授权的票据申请、过期或重放票据、带代理转发头的管理请求；不以回环 IP 单独授权。目录路径和更改按钮在同一行。默认仅更改保存位置，只有选择迁移时才展开来源范围。旧的 library-admin.html 不再是使用入口，也不再由后端生成。

启动器默认连接 127.0.0.1:8001 和 127.0.0.1:5174/settings，可通过 MUSIC_CORE_API_TARGET、MUSIC_CORE_ADMIN_WEB_URL 配置其他回环地址；MUSIC_CORE_DATA_DIR 应与后端一致。Windows 私有能力文件 ACL 限制为运行后端的 OS 用户，非 Windows 为 0600。服务日志在 `.runtime/local-launch`，启动失败显示 GUI 错误，不关闭或重启已有服务。非 Windows 可用 `python tools/launch_local.py` 调用相同入口。

从本机入口进入后可选择“音乐”“下载”或粘贴后端机器绝对路径。先检查可写性，再确认。仅更改目录不搬歌；勾选“同时迁移旧下载”会先显示旧目录、目标目录和迁移数量。任务创建时固定目录与命名，后续修改不影响已经排队或正在下载的任务。路径为文件、不可写或相对路径均不替换当前有效设置。

迁移只处理带项目发布来源标记且指纹仍匹配的记录。06 旧索引中只有发布下载时写入的非空元数据可升级为来源证据；扫描到的个人音频、没有来源记录的历史文件不迁移。先复制到目标盘临时文件并 fsync、SHA256 比对，再原子不覆盖发布、提交位置/身份映射，最后删除源实例。同名自动编号。发生部分失败时报告逐文件结果；源文件或已验证副本仍可用。正在下载或仍有文件读取时拒绝迁移，提示停止后再试。

成功迁移保留元数据和隐藏状态，通过 aliases 表保存原 fileId 到新指纹的映射，列表继续暴露最初 ID，故原本地续播能定位到同一份媒体。手动移动文件不等同于此受控迁移，仍遵循“原 ID 失效、新位置新 ID”的规则。请保留/备份应用数据目录，否则别名和来源记录无法恢复。


## 正式网页下载到当前设备（07）

默认不设置 MUSIC_CORE_LOCAL_MODE，即正式网页模式。用户从搜索页确认品质/格式后，沿用现有准备任务；完成后自动交给浏览器保存，页面提示“已交给浏览器”，不保证浏览器已实际写盘。浏览器拦截或未开始时，可直接点常驻提示或下载任务中的“保存到此设备”。不需要管理授权，不显示服务器绝对目录，下载设置只显示“下载位置由浏览器管理”及命名单选。浏览器保存目录由电脑/手机浏览器配置，网页不能读取或扫描它。

后端成品使用应用数据目录下 web-downloads 的独立进程临时目录，不登记到永久库。成品按任务 ID 附件流式交付，支持 HEAD/Range 和有效期内重试，默认发布后 1 小时过期；有读取时延后删除。后台清理过期成品，重启时只清理已退出进程的过期专用目录；不扫描/删除音乐库。过期链接返回 410，需要重新准备下载。任务是原有进程内状态，重启后旧网页任务链接不保证继续有效。

需要原有本机音乐库时显式设 MUSIC_CORE_LOCAL_MODE=1，再按本机入口使用；根目录启动器只在新起本机服务时设置该变量，遇到已运行的网页模式服务不会擅自重启，需为本机模式使用独立端口。永久索引、旧文件和 fileId 不删除或回退。正式网页模式不开放文件删除、音乐库播放、目录修改和本机授权接口。
