# Music Core 后端

后端使用 FastAPI，负责各来源的搜索与媒体解析、播放代理、歌词、下载及可选转码。入口是 `server/app/main.py`。

第一次安装和启动整个项目，请看[根 README](../README.md#启动)。环境变量、FFmpeg 和常规测试见[开发环境与验证](../docs/development/setup.md)，模块与数据流见[系统架构概览](../docs/architecture/overview.md)。

## 单独启动后端

依赖已装好时，从仓库根目录打开 Windows Git Bash：

```bash
cd server
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

启动后打开 [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) 查看并试用接口，OpenAPI JSON 在 `/openapi.json`。

## 常用 API

| 路径 | 用途 |
| --- | --- |
| `GET /api/health`、`GET /api/providers` | 检查服务状态和来源配置。 |
| `POST /api/search` | 按来源搜索曲目。 |
| `POST /api/playback/open` | 解析媒体并创建播放会话。 |
| `GET/HEAD /api/playback/{key}/stream` | 读取播放流，支持字节范围请求。 |
| `GET /api/lyrics`、`GET /api/covers` | 获取歌词和封面。 |
| `POST /api/downloads/options` | 查询可用下载品质和保存方式。 |
| `POST /api/downloads`、`GET /api/downloads` | 创建下载任务、查看任务列表。 |

完整请求和响应字段以运行中的 `/docs` 为准。默认网页模式由后端暂存成品、浏览器保存到当前设备。本机模式（`MUSIC_CORE_LOCAL_MODE=1`）才会将成品写入音乐库，并提供本机文件管理。开发服务默认只监听本机地址，不适合直接公开部署。

## 专项验证工具

脚本位于 `server/scripts/`，按要排查的问题选择。它们需要手动运行，不在常规测试命令中自动执行。

| 要查的问题 | 脚本 |
| --- | --- |
| 某个来源能否搜索、解析和取流 | `verify_kuwo.py`、`verify_qq.py`、`verify_netease.py`、`verify_migu.py` |
| 能否播放，流出错后能否恢复 | `verify_playback_browser.py`、`verify_recovery_browser.py`、`verify_vue_player.py`、`verify_vue_queue.py` |
| 下载品质、保存方式和真实交付 | `verify_download_quality_ui.py`、`verify_download_saving_ui.py`、`verify_download_browser.py`、`verify_vue_downloads.py`、`verify_download_online.py` |
| 本机文件列表和本地播放 | `verify_local_files.py` |
| 搜索分页、歌词、封面和沉浸式外观 | `verify_infinite_search.py`、`verify_lyrics_browser.py`、`verify_e1_real_covers.py`、`verify_immersive_appearance.py` |

第一次跑浏览器专项时，在 `server/` 用已安装依赖的虚拟环境准备 Chromium：

```bash
./.venv/Scripts/python.exe -m playwright install chromium
```

脚本输出默认写入仓库根目录的 `.runtime/verify-*`，可通过 `MUSIC_CORE_VERIFY_OUT` 覆盖。需要指定浏览器或服务地址时，查看相应脚本的参数及对 `CHROMIUM_PATH`、`MUSIC_CORE_API_URL`、`MUSIC_CORE_WEB_URL` 的支持。运行真实下载验证前，先确认脚本的目标目录。线上来源结果会随资源和服务状态变化。
