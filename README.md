# Music Core

Music Core 是一个本地运行的音乐搜索、播放与下载客户端及其 API 服务。它将多个来源的搜索和媒体能力汇入同一套客户端流程，便于统一浏览、播放和管理下载。

## 能力与技术栈

客户端使用 Vue 3、TypeScript 和 Vite，后端使用 Python、FastAPI。当前实现包括：

- 酷我、QQ 音乐、网易云音乐、咪咕四个来源的搜索，并将结果整理为统一曲目数据。
- 在线媒体解析、单一 Audio 播放、队列与播放失败恢复。
- 在线歌词获取和播放进度同步。
- 下载品质选择、下载任务管理，以及可选的 FLAC 转 MP3。
- 本地音频索引、流式播放和下载文件管理。

不同来源、歌曲和品质的可用情况会变化；搜索或解析成功不代表其媒体链接长期有效，也不保证所有曲目都能下载到指定品质。

## 目录

- `web/`：Vue 客户端、Vite 配置及客户端测试。
- `server/app/`：FastAPI、来源 Provider、媒体生命周期、歌词、下载和转码。
- `server/tests/`：后端自动化回归测试。
- `server/scripts/`：按来源或功能执行的长期专项验证工具。
- `docs/architecture/`：当前架构及数据流。
- `docs/development/`：环境准备、启动与验证说明。

## 启动

在 Git Bash 中准备 Node.js、pnpm 和 Python 环境后，分别打开两个终端启动：

```bash
# 终端一：后端
cd server
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.lock.txt
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

```bash
# 终端二：前端
cd web
pnpm install --frozen-lockfile
pnpm dev
```

开发环境、非 Windows 安装方式、配置及检查命令见[开发环境与验证](docs/development/setup.md)。

## 文档入口

- [系统架构概览](docs/architecture/overview.md)
- [开发环境与验证](docs/development/setup.md)
- [后端专用说明](server/README.md)

## 使用限制

来源服务可能调整接口、访问策略和媒体品质。仅在符合来源服务条款、版权要求及所在地法律的前提下使用解析和下载功能。项目默认将服务绑定到本机地址；当前配置适用于本地开发，不包含面向公网部署所需的认证和访问控制。

项目整体分发许可证尚未确定；分发项目本体前应先明确许可范围。
