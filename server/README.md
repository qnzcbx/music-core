# 独立后端

QQ当前仅保留official、vkeys、tang、xunhuisi。默认仅official；具备相应服务与资源使用条件时可显式设置MUSIC_CORE_QQ_RESOLVER_ORDER=official,vkeys,tang,xunhuisi。配置独立于开发页面，首个合格结果优先，不是最高音质优先。URL-only保持request_bound；qqovo已删除，含该名称的配置启动报错。历史调查文档保留。详见../docs/migration/40-B-3/Verification.md。

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

39-B.4A支持同一API选择QQ：search的providerId改为qq；open的identity可为`{"providerId":"qq","platformId":"001e7VNQ43nv4W"}`。开发页仅增加来源选择，单audio/恢复机制不变；QQ本次仅部分样本可播放。真实边界见[QQ报告](../docs/migration/39-B-4A/README.md)。可选自有QQ Cookie仅从服务端环境变量MUSIC_CORE_QQ_COOKIE读取，不写示例或日志；本次在线验证为无凭据匿名请求。

39-B.4B新增网易云：search使用providerId=netease；open的identity可为`{"providerId":"netease","platformId":"30352891"}`。匿名原生搜索/普通128kbps取链已实现，真实MP3样本通过播放、暂停、Seek与重开。未采用原库默认账号、EAPI或第三方解析；四样本中的三个返回平台-110，原因未确认。运行`./.venv/Scripts/python.exe -m scripts.verify_netease`执行有限在线验收，运行`./.venv/Scripts/python.exe -m scripts.verify_playback_browser --browser <已有Chromium路径> --provider netease --track 30352891 --recover`执行真实播放及重开。详见[网易云报告](../docs/migration/39-B-4B/README.md)。

39-B.4C新增咪咕：search使用providerId=migu；open的identity可为`{"providerId":"migu","platformId":"600929000006452915"}`。通过原生resourceinfo按contentId重新取得copyrightId及格式目录，再由listen-url/h5/v2.4取链，不需要先搜索、不保留双ID缓存。运行`./.venv/Scripts/python.exe -m scripts.verify_migu`执行有限在线验收；浏览器脚本使用`--provider migu --track 600929000006452915 --recover`，会在重开前更换Provider实例。四样本MP3前缀和一个样本真实播放/Seek/重开通过，无新增依赖，详见[咪咕报告](../docs/migration/39-B-4C/README.md)。

开发原生audio页：以`MUSIC_CORE_DEV_PLAYER=1 ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001`启动，访问同Origin `/dev/player`。未设置开关时404。播放API及生命周期见[39-B.3B](../docs/migration/39-B-3B/README.md)。

39-B.3C沿用该页与API：增加“重新打开当前歌曲”和恢复阶段显示；每次逻辑选择最多自动恢复一次，停止/切歌隔离旧异步结果，始终一个audio。受控故障脚本`./.venv/Scripts/python.exe scripts/verify_recovery_browser.py --browser <已有Chromium路径>`使用自生成WAV，和真实酷我回归脚本分开。pytest在有Node时额外包装17项纯JS状态机测试，无Node则明确skip；不需要npm或前端工程。详见[恢复说明](../docs/migration/39-B-3C/README.md)。

`app/config/sources.json` 为真实产品配置；可用环境变量 `MUSIC_CORE_SOURCE_CONFIG` 指定另一JSON文件，启动时读取，不热更新。错误/空/缺失配置采用内置四来源与默认酷我，并使健康状态为degraded；不会输出原始配置内容。四来源状态`implemented_sample_media_verified`表示实现并有有限真实样本验证，不保证所有歌曲可播放；默认选择仍仅酷我，歌词/下载能力未开放。

运行时依赖FastAPI、Pydantic、Uvicorn、httpx0.28.1和anyio；dev额外pytest，browser可选组提供Playwright1.63.0。`requirements-dev.lock.txt`记录含可选浏览器工具的完整验收环境；需要复现可先安装该文件再执行editable安装。不要安装整个旧项目requirements。

有限在线验收（非日常单元测试）执行`./.venv/Scripts/python.exe scripts/verify_kuwo.py`：启动临时本地服务，两个关键词各至多10条，至多四次按ID取链，各读取最多4096字节音频前缀，不保存媒体URL，最后关闭服务。39-B.3A四样本通过mobi取链/HTTP206前缀检查；后续真实浏览器播放与恢复证据见39-B.3B至39-B.4B报告，完整下载仍未验收。
