# Music Core 后端

Music Core 后端基于 FastAPI，要求 Python 3.10 或更高版本。QQ 解析顺序默认为 `official`；可通过 `MUSIC_CORE_QQ_RESOLVER_ORDER` 配置已实现的路线。外部路线须满足相应服务和资源的使用条件。URL-only 结果保留其证据等级，不自动视为已确认媒体。

## 安装与运行

在 `server/` 目录使用独立虚拟环境：

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

访问 `http://127.0.0.1:8001/api/health`、`/api/providers`、`/docs` 或 `/openapi.json`。默认仅绑定本机地址。

## 测试与专项验证

```bash
.venv/Scripts/python.exe -m pytest
```

`server/scripts/verify_*.py` 包含需要访问真实来源或浏览器的专项验证。运行前检查脚本参数；对应结果见 [已完成任务归档](../docs/archive/README.md)。专项有限样本只说明该次测试结果，不代表全曲库长期可用。

开发播放器可通过 `MUSIC_CORE_DEV_PLAYER=1` 启用 `/dev/player`。来源配置位于 `app/config/sources.json`，可用 `MUSIC_CORE_SOURCE_CONFIG` 指定替代 JSON 文件。配置不会热更新；错误配置采用内置默认值并将健康状态标记为 degraded。

主要模块与数据流见[架构概览](../docs/architecture/overview.md)。QQ 路线边界见[QQ 来源验收](../docs/archive/09-QQ解析与接入/Verification-Application-Integration.md)，媒体生命周期见[阶段 04](../docs/archive/04-媒体播放生命周期/README.md)。
