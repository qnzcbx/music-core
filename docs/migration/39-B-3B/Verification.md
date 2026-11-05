# 39-B.3B 验收记录

日期2026-11-05；Windows Python3.10.10；新项目独立server/.venv；开始git status干净。旧项目与冻结reference仅只读参考，未修改。

## 离线测试与安装

原115项保留，只扩展OpenAPI路径断言。新增40项：MediaStore/Lease六项及媒体HTTP/安全/取消34项；最终`./.venv/Scripts/python.exe -m pytest`为**155 passed**，1条原有Starlette/httpx TestClient弃用警告。

覆盖虚拟时钟TTL/容量、保护与重复释放、续期/遗失close/墓碑清理、多会话/多Range/重启、100次线程并发票据一致性；200/206/416与实际字节、开放/起止/后缀范围、HEAD、忽略Range、无效多范围、安全错误、不可任意代理、重定向目标验证、私网DNS拒绝、已知上游过期不请求、Cookie/Authorization隔离、流读取中断/截断、响应发送失败/取消的上游关闭与引用释放。控制数据为自有字节序列，不是酷我录音，不把这些结果当作真实播放。

执行`pip install -e ".[dev,browser]"`成功；anyio由传递依赖显式列为运行依赖，版本未改；Playwright1.63.0只在browser可选组，新增pyee/greenlet为其测试依赖。`pip check`正常，无musicdl。依赖快照更新为本次环境，不含editable机器路径。

## 真实浏览器验收

运行：

```bash
./.venv/Scripts/python.exe scripts/verify_playback_browser.py --browser C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe
```

脚本在同一进程开独立Uvicorn线程，使用真实Provider/网络，自动选择本地端口并在finally停止。没有使用旧服务或外部媒体直连HTML。第二轮最终验收端口57787，Chromium版本153.0.8010.12，headless原生audio。脚本有自动播放测试启动参数，同时通过点击页面按钮打开会话。

| 场景 | 真实观察 |
|---|---|
| 稳定录音 | kuwo / 9942644，经未修改的39-B.3A解析路线取得媒体 |
| metadata | 时长271.583107秒 |
| 初始播放 | currentTime到2.027162秒，无错误 |
| 暂停 | 等待1.1秒时间不推进；Store仍有1记录 |
| 继续 | currentTime推进至3.066310秒 |
| 中段seek | 目标约135.792秒，seeking结束后继续至136.315012秒，error=null |
| 近末尾seek | 目标约255.288秒，继续至255.813417秒，error=null |
| 首次流 | 206，Content-Range=bytes 0-4346544/4346545，Content-Length=4346545 |
| 后续随机访问 | 206，Content-Range=bytes 4063232-4346544/4346545，Content-Length=283313 |
| 关闭 | 新Range请求410；开发页清空audio src并取消传输 |
| 清理 | remainingRecords=0、activeStreams=0；验收设置media_ttl=4秒/清理间隔1秒，Lease180秒；生产默认300/30/180 |
| 隐私 | 浏览器所有请求都在127.0.0.1同Origin，未持有上游地址 |

第一轮播放/seek亦通过（端口54764），其后增加严格Range/已知失效校验及开发页开关，故重跑最终这一轮。不是只见206就宣称seek：断言浏览器seeking=false、readyState>=2、目标附近时间准确且play后再推进。

中段可利用浏览器已有缓存，不必强求每次seek都发新Range；近末尾实际观察到新的Range。上游响应长度声明不是Python预读量或浏览器已完整接收量，代理始终逐chunk转发；浏览器可为缓冲自行取完整MP3，此次未将其保存为下载文件或先读入Python大bytes。

关闭后无明显记录/引用泄漏；连接池统一lifespan关闭。真实浏览器取消路径表现为audio取消后引用归零；离线取消/发送失败进一步直接断言上游aclose执行且release仅一次。未在公网人为断网验证恢复，不把可控上游中断测试称为真实平台网络恢复验收。

## 文件与Git

新增业务：app/core/media_store.py、app/media_stream.py、app/playback.py、app/player.html。修改业务：app/main.py（装配/清理/安全日志）、core/errors.py（稳定错误类别）。KuwoProvider与通用媒体模型无修改，另外三Provider状态无修改。

新增tests/test_media_lifecycle.py、tests/test_media_stream.py、scripts/verify_playback_browser.py；修改tests/test_api_config.py、pyproject.toml（anyio/browser组/HTML资源）、requirements-dev.lock.txt及运行/架构文档。本目录仅三份说明，无真实媒体URL/能力标识或凭据。

未迁入完整musicdl、前端/队列/下载/观察系统。工作区修改未提交或推送，无运行时缓存被追踪。验收线程与浏览器都已停止；新开发页面默认关闭，需显式开启。`git diff --check`及依赖检查结果在交付时核对。

## 限制与下一步

仅一首真实录音的浏览器场景通过，不保证平台全量稳定或完整下载成功。会话是本地持有即用的随机能力，不是用户账号鉴权；进程重启全部失效，长时间暂停且续租受阻会过期。上游失效明确报错，不自动重解析恢复。DNS检查未绑定连接IP，安全域仅受信任酷我域，不应直接开放成公网任意URL服务。

下一阶段建议以自有短音频与可控网络补足浏览器断网/中途失败，再设计按稳定身份刷新媒体及播放位置恢复；继续复用当前契约，暂不同时展开其他平台、队列或下载。未自行开始下一阶段。
