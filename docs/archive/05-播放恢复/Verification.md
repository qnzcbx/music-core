# 05 播放恢复 — 阶段 05 验收记录

日期2026-11-05；Windows Python3.10.10、本项目独立server/.venv；Chromium153.0.8010.12、Playwright1.63.0；可选Node22.22.2。

## 离线测试

运行`./.venv/Scripts/python.exe -m pytest`：保留原155项，新增3项恢复API测试、1项客户端状态机包装测试，合计159 passed，1条原有Starlette/httpx弃用警告。包装测试调用`node --test tests/recovery.test.mjs`，内部17项均通过；不把它们再重复加到pytest数量里。无Node时此包装测试明确skip，Node不是后端运行依赖，浏览器验收脚本仍能直接覆盖真实客户端逻辑。

状态机测试包含稳定identity/new playbackId、时间/volume/muted/rate、暂停保留、一次自动预算、手动再试、重复请求共享、停止/切歌/暂停、失败书签保留、新旧Lease清理、NotAllowedError、abort/decode/权限不自动恢复、waiting/stalled不触发、续租失效及再次故障、时长夹取和未完成seek书签。

API测试以自有WAV上游验证同身份新开得到不同MediaRecord/Lease、旧close不影响新会话、已失效URL后新资源可访问、解析失败不创建孤立记录；原200/206/416、流取消/截断、安全目标等测试全部保留。本期无新增后端恢复API。

## 可控Chromium故障

运行（server目录）：

```bash
./.venv/Scripts/python.exe scripts/verify_recovery_browser.py --browser $env:CHROMIUM_PATH
```

自有48秒330Hz WAV由标准库在内存生成，无音乐下载或FFmpeg转换。HTTPX Transport替身真正分块产出字节并能在响应头之后抛ReadError，经真实FastAPI代理和Chromiumaudio加载。fixture不是酷我，生产白名单没有放开。

测试配置media_ttl=.4秒、lease_ttl=5秒、清理=.1秒；生产300/180/30未改。页面原60秒续租没有改成产品快速轮询：Playwright初始化脚本仅捕获其回调，在Lease实际到期后调用同一个续租入口，从真实410触发恢复；不是伪造audio error。

| 场景 | 浏览器/服务端证据 |
|---|---|
| Lease到期 | 稳定身份重开，比较new/old playbackId不同（不记录值） |
| 书签及设置 | 最终复核故障前7.567341秒→恢复后7.598680秒；volume=.4、muted=true、rate=1.25均保持，继续播放 |
| 暂停及重复重试 | 最终复核7.632112秒→7.632112秒、paused=true；重复点击合并，仅1次open |
| 上游失效后远端seek | 旧URL返回410，实际waiting/error，MediaError.code=2，自动重开成功；恢复到此前0.947418秒有效书签，未把未完成的43秒seek伪称成功 |
| 中途断流 | 先发送响应头与部分WAV，再ReadError；Chromium实际error code2；只自动open1次，重新取得新版本资源 |
| 自动预算/手动 | 再次失效不自动open；手动open故意失败后显示error，解除故障再手动可成功 |
| 恢复中停止 | 延迟open响应，先停止，晚到Lease关闭，audio不再播放 |
| 恢复中切歌 | 延迟A，打开B，A晚到后不会覆盖B；B稳定identity=2且自己的Lease有效 |
| 恢复中暂停 | 恢复完成仍paused，未被内部play意图覆盖 |
| 收尾 | 同一个audio DOM节点；remainingRecords=0、activeStreams=0、activeLeases=0 |

实际还观察到abort/emptied/waiting等浏览器事件，不将它们单独当成永久故障。断流时后端会出现固定的RuntimeError安全错误日志，这是已发响应头后的连接中断，不是改回JSON500；上游响应仍在finally关闭，引用最终归零。脚本最终按fixture版本明确检查断流响应aclose，brokenStreamClosed=true；8组场景及三类资源归零断言均通过。

期间修复：失败后src清空会导致手动重试错误捕获0秒；现在仅有效当前会话更新书签。原生fetch赋为对象方法会触发浏览器调用绑定问题，改为闭包调用。最初远端seek验收错误要求恢复到尚未完成的43秒目标，已改为核对真实错误及旧有效书签。测试Lease从2秒改为5秒以避免切歌验收过程中自身提前过期，不改生产TTL。这些问题都未以Mock结果掩盖。

## 真实酷我正常回归

在受控故障通过后运行原`verify_playback_browser.py --browser ...`，临时端口52799，真实Provider和网络。录音kuwo/9942644：时长271.583107秒，初始2.046940秒，暂停后继续到3.072322秒；中段seek后136.306251秒、近末尾255.800686秒，seeking=false、error=null。

本地代理实际206：`bytes 0-4346544/4346545`，后续`65536-4346544/4346545`与`4063232-4346544/4346545`，末段Content-Length=283313。浏览器只访问本地Origin；关闭后新流410，记录/活动流归零。正常流程计数ResolveCalls=1，未误触发恢复。未在真实酷我上批量制造故障或下载整曲。

## 文件与范围

新增app/player-controller.mjs；修改app/player.html、playback.py（仅开发JS资源路由）、pyproject.toml（打包mjs）、scripts/verify_playback_browser.py（适配模块化页面及Resolve计数）。新增scripts/recovery_fixture.py、scripts/verify_recovery_browser.py、tests/recovery.test.mjs、test_recovery_controller.py、test_recovery_api.py。更新运行/架构文档，本目录仅三份说明。

KuwoProvider、MediaStore、Stream代理、模型、TTL/取链优先级与其他Provider状态不变；无新运行依赖，无Vue/队列/观察历史。测试故障只在独立脚本/测试中注入，没有产品故障API。所有能力仅在内存比较，未写进报告或fixture。

## 限制

自动恢复不是任意错误必成功：权限/解码/不支持需要用户处理，缓冲不直接重取链；浏览器HTTP信息不完整，一次HEAD也不是永久可用性证明。媒体定位等候上限12秒，未定位成功则失败并暂停。打开请求沿用现有Provider网络预算，客户端为能回收晚到Lease不abort此fetch；页面整体销毁、close网络失败仍由TTL最终回收，无法承诺即时删除。

自动播放策略分支已通过状态机NotAllowedError测试，受控/真实Chromium使用允许自动播放测试参数，未另测各浏览器交互策略。长后台计时器节流、浏览器崩溃及跨平台实现未验收。pip check和git diff --check均通过。
