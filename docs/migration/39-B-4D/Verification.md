# 39-B.4D验收

2026-11-06，新工程独立.venv，Python3.10.10、Node22.22.2、Playwright1.63.0、Chromium153.0.8010.12。开始工作区干净；旧Lab与冻结源码只读。

## 离线

`./.venv/Scripts/python.exe -m pytest -o addopts= -q`：352项通过，原334保留，新增18项。一个既有Starlette/httpx弃用警告；无新增依赖。`node --test tests/recovery.test.mjs`：17/17通过，pytest包装已包含在352中，不重复计数。

新测试涵盖默认/自定义顺序、未知/重复/空配置、时间预算非法值、禁用路线零网络请求、成功停止、临时错误继续、权限和身份错误停止、错曲拒绝、全部失败、取消及总预算关闭在途工作、关闭继续策略。人工路由子类只验证编排，不能当作三条外部服务离线适配器或在线成功证据。既有QQ搜索/取链、私有数据、Host、Range、Store/Lease与恢复测试继续通过。

## 同样本对照

执行`./.venv/Scripts/python.exe -m scripts.verify_qq_routes`，固定001e7VNQ43nv4W（既有成功样本）与0012mUEO3j7Xwj（旧明月天涯样本）。只调用QQ自身及原受信任CDN；没有向外部服务发送受限曲目取链请求。运行两轮，第二轮补纯resolve计时；以下为第二轮。

| 指标 | 原生基线official | 审核策略vkeys,qqovo,tang,official |
|---|---|---|
| 固定样本数 | 2 | 2 |
| 可执行路线 | official | official（三条禁用） |
| 返回URL/身份回显确认/字节验证 | 各2/2 | 各2/2 |
| 实际成功路线 | official | official |
| 平均/P95取链耗时 | 801/1128ms | 296/367ms |
| 含探测平均/P95 | 1746/2518ms | 1069/1237ms |
| API+媒体请求数 | 4 | 4 |
| 外部服务请求/额外请求 | 0/0 | 0/0 |
| 本轮错误 | 无 | 无 |
| 真实浏览器播放/Seek | 1/2已测 | 同一首1/2已测 |

两个样本均206、4096字节、MP4 ftyp、audio/mp4，大小分别2925618和2925419字节，主机aqqmusic.tc.qq.com，重定向0。身份依据为官方返回songmid精确匹配，字节前缀不是歌曲指纹。没有执行完整下载。

N=2的P95采用最近秩即最大值，不具总体统计意义。两种策略执行相同官方逻辑，顺序运行共享连接池；时间差可能来自网络/连接复用，不能解释成新策略优化。外部路线未启用，覆盖率收益为未证实，不能把URL返回率称作整个曲库可播放率。

## 浏览器与回归

使用既有`-m scripts.verify_playback_browser --browser <已有Chromium路径> --recover`，分别选择四来源。审核策略QQ另在服务端设置MUSIC_CORE_QQ_RESOLVER_ORDER=vkeys,qqovo,tang,official后运行相同样本。开发页、公共API和恢复状态机无修改。

| 来源/模式 | ID | 时长 | 中段/近末尾Seek后时间 | 重开恢复时间 |
|---|---|---:|---|---:|
| QQ原生 | 001e7VNQ43nv4W | 239.420952 | 120.232092/225.562309 | 225.601669 |
| QQ审核策略 | 同上 | 239.420952 | 120.217514/225.574302 | 225.609290 |
| 网易云 | 30352891 | 239.302336 | 120.173579/225.453867 | 225.480752 |
| 咪咕 | 600929000006452915 | 206.4 | 103.721804/194.527719 | 194.600211 |

上述均完成metadata、初播时间推进、暂停1.1秒保持、继续、两处Seek（error=null）、关闭旧Lease后稳定身份重开。正常Resolve1次，含重开2次，新playbackId、同audio、paused=true、volume=.3/rate=1.2保持。metadata2次、seeking/seeked各4次，无error事件；关闭后410，MediaStore记录/活动Stream归零，浏览器只访问本地Origin。咪咕重开前更换Provider实例也通过。

酷我首轮已通过初播、暂停、继续及两处Seek，手动重开等待ready超时；没有修改酷我逻辑，单独有限复核结果见下方补记。不把该失败直接判为QQ代码回归。

酷我补记：9942644单独复核退出0；时长271.583107，初播2.039435、继续3.061103、中段136.310747、近末尾255.803785、重开255.837369秒。新Lease、同audio、音量/速率/暂停状态保持，正常Resolve1次、总2次，关闭后410，记录和活动Stream为0。metadata2次、seeking/seeked各4次，无error事件。

`scripts/verify_recovery_browser.py`的8项受控WAV场景全部通过：Lease到期、暂停/重复请求合并、上游失效Seek、中途断流、自动预算/手动恢复、恢复中stop/switch/pause。观察到MediaError2和预期固定RuntimeError断流日志；最后记录/活动Stream/活动Lease均0，singleAudio=true。

## 文件与边界

修改server/app/providers/qq.py（固定路线资格、配置顺序、总预算与错误边界）、server/app/main.py（读取QQ顺序环境变量）；新增server/tests/test_qq_routes.py、server/scripts/verify_qq_routes.py及本目录三文档。server/README与长期架构说明同步更新。其他三个Provider、媒体Host、公共模型、Store/Lease、RecoveryPlayer及来源策略不改，无第三方Cookie、服务密钥、TLS放宽或完整媒体URL落盘。

未执行git init、建分支、commit、push或清理用户文件。未开始39-B.4E。额外路线当前播放目标未达成；后续需要可核验的服务使用条件和足够录音身份信息，才有依据迁入相应适配器。本期不是三条外部路线恢复成功的交付。
