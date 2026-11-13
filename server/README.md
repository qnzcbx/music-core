# Music Core 后端

后端是基于 FastAPI 的本地 API 服务，负责来源适配、在线播放解析与流式代理、歌词、下载任务、可选转码和本地文件接口。项目入口为 `server/app/main.py`，Python 要求为 3.10 或更高版本。

完整环境安装、前后端联调和常见问题见[开发环境与验证](../docs/development/setup.md)；模块调用链见[系统架构概览](../docs/architecture/overview.md)。

## 启动

Windows PowerShell 中：

```powershell
Set-Location server
python -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r requirements-dev.lock.txt
& ./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

本地接口默认绑定回环地址。健康状态、来源列表、API 文档分别位于 `/api/health`、`/api/providers` 和 `/docs`；OpenAPI JSON 位于 `/openapi.json`。

## API 入口

| 路径 | 用途 |
| --- | --- |
| `GET /api/health`、`GET /api/providers` | 服务状态与来源配置。 |
| `POST /api/search` | 按来源搜索统一曲目候选。 |
| `POST /api/playback/open` | 解析并打开播放会话。 |
| `GET/HEAD /api/playback/{key}/stream` | 带 Lease 校验的 Range 媒体代理。 |
| `POST /api/playback/{key}/renew`、`POST /api/playback/{key}/close` | 续租与关闭播放会话。 |
| `GET /api/lyrics`、`GET /api/covers` | 独立歌词与封面读取接口。 |
| `POST /api/downloads/options` | 查询可用下载品质及转码能力。 |
| `POST/GET /api/downloads` | 创建下载任务、读取任务列表。 |
| `GET /api/downloads/files`、`GET/HEAD /api/downloads/files/{id}/stream` | 文件清单与本地 Range 流。 |
| `POST /api/downloads/{id}/cancel`、`POST /api/downloads/{id}/retry` | 取消或重试任务。 |
| `POST /api/downloads/files/{id}/remove` | 删除指定下载文件。 |

实际请求和响应字段以源码及运行时 OpenAPI 为准。

## 配置与限制

服务端直接读取进程环境变量，不会自动加载 .env。主要变量为 `MUSIC_CORE_SOURCE_CONFIG`、`MUSIC_CORE_QQ_COOKIE`、`MUSIC_CORE_QQ_RESOLVER_ORDER`、`MUSIC_CORE_NETEASE_RESOLVER_ORDER`、`MUSIC_CORE_DOWNLOAD_DIR`、`MUSIC_CORE_FFMPEG` 和 `MUSIC_CORE_DEV_PLAYER`。来源配置文件默认位于 `app/config/sources.json`；配置异常时使用内置默认值并将健康状态标记为 degraded。所有已实现来源 ID 必须存在，配置修改后需要重启服务。

默认解析路线为 QQ 的 `official,vkeys,tang,xunhuisi` 与网易云的 `native,gdstudio-preview,jfjt`。使用第三方来源及解析路线必须遵守其条款、版权和所在地法律。来源响应、可用媒体和下载品质可能变化，不保证长期可用。开发服务默认只绑定本机回环接口，不应直接视作带有认证和公网防护的生产服务。

下载任务状态和播放会话在服务进程内管理；媒体文件保存在配置的下载目录。原格式下载不写入歌曲标签，FLAC 转 MP3 需要本机 FFmpeg/FFprobe。文件列表不会扫描文件内的音乐标签。详细数据流及只读元数据审计见[系统架构概览](../docs/architecture/overview.md)。

## 自动化测试与长期专项验证

稳定的 pytest 回归用例保存在 `server/tests/`。在 server 目录执行：

```powershell
& ./.venv/Scripts/python.exe -m pytest
```

`server/scripts/` 下当前保留的专项工具如下；它们针对可变来源或浏览器流程，需按脚本参数运行，不属于 pytest 默认集合：

- 来源在线冒烟：`verify_kuwo.py`、`verify_qq.py`、`verify_netease.py`、`verify_migu.py`。
- 播放和恢复浏览器验证：`verify_playback_browser.py`、`verify_recovery_browser.py`、`verify_download_browser.py`、`verify_lyrics_browser.py`、`verify_vue_player.py`、`verify_vue_queue.py`。
- 客户端与本地文件专项：`verify_infinite_search.py`、`verify_vue_downloads.py`、`verify_local_files.py`、`verify_immersive_appearance.py`、`verify_download_quality_ui.py`、`verify_download_saving_ui.py`。
- 真实媒体/封面链路：`verify_download_online.py`、`verify_e1_real_covers.py`。

`recovery_fixture.py` 是恢复浏览器验证使用的本地 fixture 辅助程序。需要浏览器时安装 Playwright 与 Chromium：

```powershell
& ./.venv/Scripts/python.exe -m playwright install chromium
```

脚本输出默认写入项目根目录下的 .runtime/verify-*；可通过 MUSIC_CORE_VERIFY_OUT 覆盖。浏览器路径、API 与 Web 地址分别可通过 CHROMIUM_PATH、MUSIC_CORE_API_URL、MUSIC_CORE_WEB_URL 等参数或环境变量配置。运行真实下载验证前应检查脚本参数和目标下载目录，以免把样本写入不期望的位置。在线验证结果受外部服务、账号状态和测试样本影响。
