# 39-B.4D-2验证记录

2026-11-06，新项目Windows/Python3.10.10/.venv、Node22.22.2、Playwright1.63.0、Chromium153.0.8010.12。开始工作区干净，旧项目与冻结musicdl只读。

## 离线协议与编排

先实现协议及离线测试，再有限请求公开服务入口。最终`./.venv/Scripts/python.exe -m pytest -o addopts= -q`：389项通过（原352保留、新增37）。唯一警告仍为Starlette/httpx弃用提示。`node --test tests/recovery.test.mjs`：17/17通过，已有pytest包装，不重复计数。

人工脱敏Fixture位于tests/test_qq_external.py。覆盖vkeys精确mid/quality、URL-only等级、空/异常JSON/业务错误/URL/错MID、超时与取消关闭响应；qqovo当前bootstrap、设备标识、服务Cookie隔离、固定时间/nonce签名核对、参数排序、会话关闭/过期与取消后无第二次请求；Tang严格MID、缺失元数据、原曲字段选择、跳过accom、翻唱与版本不符拒绝；Provider真实分发函数的request_bound不发布及confirmed转原ResolvedMedia；媒体检查200/206、音频前缀、非音频拒绝、权限错误与连接关闭。既有18项编排测试和全部Core测试保留。

HMAC确定性向量：key为人工test-key，timestamp=1700000000，nonce=nonce-1，固定meting query得到`4ohQ-umoxzw5l67JkI5T2gYNAPv6tv8ml25ae8BClmo`。该值为离线合成数据，不是服务真实签名。网络测试全部Mock，不声明真实三路已可播。

## 当前服务检查

`./.venv/Scripts/python.exe -m scripts.verify_qq_external_conditions`只GET三个公开根入口，不发送歌曲、QQ凭据、bootstrap或历史Session；每站最多65536字节，连接5秒、读8秒，不自动重定向。另有限复核页面可见文本以辨识页面类型，不保存原页面。

| 路线 | HTTP/读取字节/耗时 | 页面实况 | 当前适配器状态 |
|---|---|---|---|
| vkeys | 200 / 820 / 6316ms | 服务运行信息JSON，欢迎使用API-V3；不是歌曲接口条款 | 已实现，当前使用条件不足 |
| qqovo | 200 / 13134 / 6757ms | OpenMusic一起听歌首页，描述免费在线听歌平台；未确认本应用自动化API使用条件 | 已实现，当前使用条件不足 |
| Tang | 200 / 917 / 3954ms | 默认站点创建成功index页；不能推出music_open_api.php可用或失效 | 已实现，当前使用条件不足 |

三条均有实际协议代码和专项测试，但verified_online=false、enabled=false。入口可访问与歌曲接口、资源身份、使用条件是不同阶段。当前歌曲API请求0，外部媒体URL/字节/身份/播放/Seek均未测试，不能统称接口失败或服务不可用。

## 官方基线与有意义对照边界

本期官方基线以001e7VNQ43nv4W直接open，真实取链与播放通过。新外部策略无当前可执行服务资格，故**未再次运行official对“禁用外部＋official”的伪多线路收益对照**。两组同批合法样本的真实外部对照未完成，外部URL取得率、字节验证率、录音确认率、浏览器成功率均为未测试，而非0%或成功。

URL-only的request_bound在离线确实可被正常Adapter返回，但未计入confirmed，也未通过不可信URL或模糊时长自动提升等级。没有新外部媒体、格式或CDN事实。后续当前服务条件明确后，才可对同一组正常有权访问样本运行实际多线路、媒体验证及浏览器，使用官方失败样本衡量增益，不靠已成功的官方样本制造改进。

## 四来源真实浏览器回归

执行原`-m scripts.verify_playback_browser --browser <已有Chromium路径> --provider <来源> --track <稳定ID> --recover`，没有修改播放器或其他来源业务逻辑，也没有在浏览器测试前用搜索缓存。

| 来源 | 稳定ID | duration | 初播/继续 | 中段/近末尾Seek | 重开恢复位置 |
|---|---|---:|---|---|---:|
| QQ官方 | 001e7VNQ43nv4W | 239.420952 | 2.050681/3.113638 | 120.234165/225.583824 | 225.643397 |
| 酷我 | 9942644 | 271.583107 | 2.087956/3.154139 | 136.315319/255.802043 | 255.846268 |
| 网易云 | 30352891 | 239.302336 | 2.047612/3.089445 | 120.169126/225.457641 | 225.494919 |
| 咪咕 | 600929000006452915 | 206.4 | 2.067582/3.138255 | 103.721432/194.541804 | 194.576012 |

四者全部通过metadata、时间推进、暂停1.1秒保持、继续、两处Seek，error=null。旧Lease关闭后相同身份重开，新playbackId、同audio，paused=true、volume=.3/rate=1.2保持；正常Resolve1次，总2次。metadata=2、playing=4、pause=4、seeking/seeked各4，无浏览器error事件。关闭后410，最终MediaStore记录0、活动Stream0，浏览器仅本地Origin。咪咕更换Provider实例后重开通过。

本轮四来源脚本全部退出0，QQ退出期间出现既有Windows Proactor WinError10054远端关闭提示，未影响媒体事件及清理断言，不因该提示修改生产逻辑。外部路线浏览器未测，不能借四来源官方成功替代。

## 受控恢复

原`scripts/verify_recovery_browser.py --browser <已有Chromium路径>`：自生成48秒WAV，8项均通过（Lease到期、暂停与重复合并、上游过期Seek、响应头后断流、自动预算/手动恢复、恢复中stop/switch/pause）。观测MediaError2，预期固定RuntimeError断流日志；结束记录/活动Stream/活动Lease均0，singleAudio=true。

## 文件与Git

新增app/providers/qq_resolvers/{__init__,vkeys,qqovo,tang,media}.py，tests/test_qq_external.py，scripts/verify_qq_external_conditions.py及本目录三文档；修改app/providers/qq.py接入实际分发、服务资格参数、confirmed结果媒体检查与转换。同步server/README和长期架构说明。

未修改TrackIdentity、SongCandidate、公共ResolvedMedia、Store/Lease、Range语义、RecoveryPlayer、其他三个Provider或来源默认顺序。无新增运行依赖，HMAC使用Python标准库。没有完整下载、旧Session复用、QQ Cookie外发、TLS放宽或敏感URL/密钥落盘。

结束工作区保留本期修改，未git init/建分支/commit/push，未清理用户文件，未开始39-B.4E。默认路线official，外部实现保留但未启用。未达成额外真实媒体、真实三路录音身份确认和覆盖率提升目标；当前阻塞为服务使用条件尚未确认，不是适配器缺失或已经证实接口失效。
