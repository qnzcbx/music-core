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

打开 `http://127.0.0.1:8001/api/health`、`/api/providers`、`/docs`、`/openapi.json`。Ctrl+C关闭。默认仅本机监听。POST `/api/search`输入如`{"providerId":"kuwo","query":"银临","limit":10}`。39-B.3B新增playback/open、stream(GET/HEAD)、renew、close；无下载接口。

开发原生audio页：以`MUSIC_CORE_DEV_PLAYER=1 ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001`启动，访问同Origin `/dev/player`。未设置开关时404。播放API及生命周期见[39-B.3B](../docs/migration/39-B-3B/README.md)。

39-B.3C沿用该页与API：增加“重新打开当前歌曲”和恢复阶段显示；每次逻辑选择最多自动恢复一次，停止/切歌隔离旧异步结果，始终一个audio。受控故障脚本`./.venv/Scripts/python.exe scripts/verify_recovery_browser.py --browser <已有Chromium路径>`使用自生成WAV，和真实酷我回归脚本分开。pytest在有Node时额外包装17项纯JS状态机测试，无Node则明确skip；不需要npm或前端工程。详见[恢复说明](../docs/migration/39-B-3C/README.md)。

`app/config/sources.json` 为真实产品配置；可用环境变量 `MUSIC_CORE_SOURCE_CONFIG` 指定另一JSON文件，启动时读取，不热更新。错误/空/缺失配置采用内置四来源与默认酷我，并使健康状态为degraded；不会输出原始配置内容。酷我状态`implemented_sample_media_verified`表示有限样本已通过取链和前缀探测，不保证所有歌曲可播放；其他来源仍为not_integrated。

运行时依赖FastAPI、Pydantic、Uvicorn、httpx0.28.1和anyio；dev额外pytest，browser可选组提供Playwright1.63.0。`requirements-dev.lock.txt`记录含可选浏览器工具的完整验收环境；需要复现可先安装该文件再执行editable安装。不要安装整个旧项目requirements。

有限在线验收（非日常单元测试）执行`./.venv/Scripts/python.exe scripts/verify_kuwo.py`：启动临时本地服务，两个关键词各至多10条，至多四次按ID取链，各读取最多4096字节音频前缀，不保存媒体URL，最后关闭服务。39-B.3A四样本通过mobi取链/HTTP206前缀检查；尚未验收浏览器播放与完整下载。
