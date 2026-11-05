# 独立后端

要求 Python 3.10+；本次在 Windows Python 3.10.10 验证。VSCode Git Bash：

```bash
cd /c/Code_Home/2_projects/musicdl-lab/server
py -3.10 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

安装与测试的同等命令已从新环境执行；实机启动验证使用临时空闲端口，避免干扰旧项目8000端口。8001若占用请选择其他端口。开发时可追加 `--reload`；此次验收未测试自动重载。

打开 `http://127.0.0.1:8001/api/health`、`/api/providers`、`/docs`、`/openapi.json`。Ctrl+C关闭。默认仅本机监听；无搜索、Resolve、Stream或下载接口。

`app/config/sources.json` 为真实产品配置；可用环境变量 `MUSIC_CORE_SOURCE_CONFIG` 指定另一JSON文件，启动时读取，不热更新。错误/空/缺失配置采用内置四来源与默认酷我，并使健康状态为degraded；不会输出原始配置内容。注册不等于可播放，四来源能力当前均为false。

运行时依赖仅FastAPI、Pydantic、Uvicorn；dev额外pytest/httpx。`requirements-dev.lock.txt`记录本次完整环境版本；需要复现可先安装该文件再执行editable安装。无Provider依赖组：当前无实际Provider实现，39-B.2再按真实用量添加。不要安装整个旧项目requirements。
