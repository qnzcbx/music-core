# 开发环境与验证

Windows 快速启动、第一次安装依赖和双击入口见[项目 README](../../README.md)。
本文补充 macOS / Linux 的启动差异、开发配置、测试和常见问题。

## 工具版本

| 工具 | 建议 |
| --- | --- |
| Node.js | 使用 22.x，建议 22.12 或更新，以覆盖前端开发和测试。 |
| pnpm | 优先使用项目已验证的 11.1.2。安装依赖时使用 `pnpm install --frozen-lockfile`，不要删除或重建锁文件来绕过安装错误。 |
| Python | 3.10 或更新。Windows 的 `server/requirements-dev.lock.txt` 是 Python 3.10 的开发依赖快照，不用于 macOS / Linux。 |
| FFmpeg / FFprobe | 仅在需要转码或专项媒体验证时安装。搜索、播放和原格式下载不依赖它们。 |

## macOS / Linux 启动差异

从仓库根目录打开终端，安装并启动后端：

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

前端仍按[项目 README](../../README.md#启动)中第二个终端的步骤安装和启动。

## 本地服务地址

| 用途 | 默认地址 |
| --- | --- |
| 前端页面 | [http://127.0.0.1:5174](http://127.0.0.1:5174) |
| 后端健康检查 | [http://127.0.0.1:8001/api/health](http://127.0.0.1:8001/api/health) |
| FastAPI 交互文档 | [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) |

Vite 默认将 `/api` 请求代理到 `http://127.0.0.1:8001`。后端换地址时，在**启动 Vite 的终端**设置 `MUSIC_CORE_API_TARGET`，或在 `web/` 的本地 Vite 环境文件中设置。FastAPI 读取进程环境变量，不会自动读取 `.env`。

## 可选配置

默认启动不需要手动设置下列变量。除 `MUSIC_CORE_API_TARGET` 外，在启动后端的环境中设置。调整后重启读取该配置的服务。

| 变量 | 用途 |
| --- | --- |
| `MUSIC_CORE_SOURCE_CONFIG` | 覆盖来源配置，默认使用 `server/app/config/sources.json`。 |
| `MUSIC_CORE_QQ_COOKIE` | 可选 QQ 凭据。只在本机环境中设置，不写入仓库或问题报告。 |
| `MUSIC_CORE_QQ_RESOLVER_ORDER` | QQ 解析顺序，默认 `official,vkeys,tang,xunhuisi`。 |
| `MUSIC_CORE_NETEASE_RESOLVER_ORDER` | 网易云解析顺序，默认 `native,gdstudio-preview,jfjt`。 |
| `MUSIC_CORE_LOCAL_MODE` | 设为 `1` 时启用本机音乐库和目录管理。默认归浏览器保存，见[项目 README](../../README.md#启动)。 |
| `MUSIC_CORE_DOWNLOAD_DIR` | 覆盖本机音乐库目录。设置后页面不能修改该目录。 |
| `MUSIC_CORE_DATA_DIR` | 应用数据目录，默认 `.runtime/app-data`。它与音乐保存目录独立，切换音乐库时不必改动。 |
| `MUSIC_CORE_FFMPEG` | 指定 FFmpeg 可执行文件。FFprobe 须在同一目录或 PATH 中。 |
| `MUSIC_CORE_DEV_PLAYER` | 设为 `1` 时启用后端开发播放器。 |
| `MUSIC_CORE_API_TARGET` | Vite 的后端代理目标，默认 `http://127.0.0.1:8001`。 |

自定义来源配置必须包含 `kuwo`、`qq`、`netease`、`migu`，默认选中列表必须非空且不重复。配置无效时回退至内置值，健康检查显示 `degraded`。

## FFmpeg 与 FFprobe

需要 FLAC 转 MP3 时，将 FFmpeg 和 FFprobe 加入 PATH，或按上表指定 `MUSIC_CORE_FFMPEG`。可以用 `ffmpeg -version` 和 `ffprobe -version` 检查是否可运行。转码还要求 FFmpeg 有可用的 MP3 编码器。

Windows 上，Uvicorn 的 `--reload` 开发模式可能不支持启动 FFmpeg 子进程。此时只禁用转换，已确认可用的原格式仍可保存。若要验收实际转换，请用支持子进程的后端运行方式。

## 检查与回归

- 后端在 `server/` 运行 `python -m pytest`，使用安装依赖时的虚拟环境。Windows Git Bash 可直接用 `./.venv/Scripts/python.exe -m pytest`。
- 前端在 `web/` 运行 `pnpm test` 和 `pnpm build`。构建已包含类型检查，只检查类型时运行 `pnpm typecheck`。
- 仅在跑浏览器专项时安装浏览器依赖和 Chromium。macOS / Linux 可在虚拟环境中运行 `python -m pip install -e ".[browser]"` 与 `python -m playwright install chromium`。长期脚本和运行条件见[后端专用说明](../../server/README.md)。

## 常见问题

- **5174 端口已占用。** Vite 不会自动换端口。释放端口，或修改 Vite 端口并使用新的页面地址。
- **页面提示连不上后端。** 先打开上面的健康检查地址。若后端使用了其他端口，核对 Vite 的 `MUSIC_CORE_API_TARGET`。
- **虚拟环境装不上依赖。** 先确认 Python 版本。Windows 使用仓库的开发依赖快照时优先用 Python 3.10，macOS / Linux 按本文使用项目声明的依赖。
- **转码不可用，但能保存原格式。** 检查 FFmpeg、FFprobe 和 MP3 编码器。Windows 使用 `--reload` 时，还要检查后端的子进程支持。
- **设置里改不了下载目录。** 默认网页模式由浏览器决定保存位置。要在应用里管理本机目录，请按[项目 README](../../README.md#启动)用本机入口打开。若设置了 `MUSIC_CORE_DOWNLOAD_DIR`，页面仍不可改。更改本机目录默认只影响新下载，只有勾选迁移才会搬动符合条件的旧下载。
