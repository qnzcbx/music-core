# 01 核心架构 — 实现范围与依赖

Music Core 使用独立的 Python/FastAPI 后端和 Vue 客户端。四个音乐来源分别实现为 Provider，统一返回本项目的曲目身份与媒体结构。播放、下载、歌词和转码均由项目内模块及 API 契约维护。

## 版本依赖

依赖及版本见 `server/pyproject.toml` 和锁文件。
