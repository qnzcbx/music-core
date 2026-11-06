# 39-B.4D-5：已验证QQ线路进入正常应用路径

2026-11-06。本期新增的应用行为已验证：**不用实验Provider、不替换create_app或QQProvider类，正常POST /api/playback/open可以执行vkeys、Tang，并通过已有Store/Lease/Range播放、Seek与重开。** 正式默认仍official；未把未知录音或外部服务权限无条件推广到默认回退。

## 运行配置与使用范围

复用已有两个配置，没有新增资格框架：

```powershell
cd C:/Code_Home/2_projects/musicdl-lab/server
$env:MUSIC_CORE_DEV_PLAYER='1'
$env:MUSIC_CORE_QQ_RESOLVER_ORDER='vkeys,tang,official'
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

访问/dev/player，选择QQ，输入004Yi5BD3ksoAN，即可通过正常播放API开发试听《蒲公英的约定》。也可向/api/playback/open提交`{"identity":{"providerId":"qq","platformId":"004Yi5BD3ksoAN"}}`。仅在已具备相应访问条件的本机开发测试中使用；这不是对全部曲库、生产或商业使用的授权声明。

已有dev_player开关在正常初始化中传入QQProvider的development_preview：允许执行顺序中实际配置的vkeys、Tang，以及预览request_bound结果；页面明确标记开发试听。只开启开关不设置路线顺序，仍默认official。省略某路线即禁用，成功立即停止，qqovo仍跳过，不尝试缺少登录材料的会话。不启用开发模式时，正常应用仍只执行official；原有经过调用方确认的显式外部资格接口仍保留，URL-only正式发布继续拒绝。

Tang可用`MUSIC_CORE_QQ_RESOLVER_ORDER=tang,official`测试，官方独立可用`official`。未增加新QQ API、HTTP配置修改入口或任意URL代理。原25秒总预算、取消与明确401/403停止规则不变。

## URL-only、媒体与访问条件分开记录

QQProvider只保留一份无URL的私有last_resolution，分别记录resolver、protocol、media、identity和scope。vkeys实际保持identity=request_bound、scope=development_preview，不伪造response_mid或confirmed，也不据此声称平台会员/购买状态已确认。开发页提示需要核对录音；当前仅开发试听可使用该结果，没有自动升级为正式已确认版本。

Tang实际响应MID匹配仍记confirmed，这表示回显匹配，不是完整指纹认证。此前《牵丝戏》歌手只返回银临、缺少Aki阿杰的事实继续保留；部分歌手缺失不能被写成错MID，也没有声称所有元数据完全一致。明确MID不符、伴奏/翻唱字段与可信预期字段冲突的已有拒绝不变。

有限媒体探测现在返回原MediaRepresentation：按实际前缀确认container/codec，按Content-Range或明确Content-Length记录sizeBytes，未知码率和位深不编造。FLAC样本真实为container=flac、codec=flac、sizeBytes=161249673、lossless=true；上游Content-Type实际为audio/x-ogg，照实保留，不能据此误称OGG。lossless仅描述FLAC编码，不声称原始母带或无升采样。无FFmpeg转码。

## 正常API真实验收

仅运行原`scripts/verify_playback_browser.py`，不运行4D4隔离脚本，不替换业务类。它启动普通create_app(dev_player=True)，选择开发页，按钮发起正常open。测试仪表只计数现有resolve/_resolve_route并记录公开representation，不伪造响应或放宽网络规则。

```powershell
$env:MUSIC_CORE_QQ_RESOLVER_ORDER='vkeys,tang,official'
./.venv/Scripts/python.exe -m scripts.verify_playback_browser --browser C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe --provider qq --track 004Yi5BD3ksoAN --recover

$env:MUSIC_CORE_QQ_RESOLVER_ORDER='tang'
./.venv/Scripts/python.exe -m scripts.verify_playback_browser --browser C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe --provider qq --track 001e7VNQ43nv4W --recover
```

| 检查 | vkeys正常入口 | Tang正常入口 |
|---|---|---|
| 固定录音 | 蒲公英的约定/004Yi5BD3ksoAN | 牵丝戏/001e7VNQ43nv4W |
| 实际路线调用 | [vkeys,vkeys]，没有后续路线 | [tang,tang]，没有official |
| 私有身份标记 | request_bound，开发试听 | confirmed回显匹配，开发试听 |
| 公开媒体 | FLAC，161249673字节，已通过真实open再次核对 | MP4，2925618字节，两次open均有该representation |
| duration | 247.199547秒 | 239.420952秒 |
| 初播/继续 | 2.055762/3.103694 | 2.027492/3.057031 |
| 中段/近末尾Seek后推进 | 124.125218/232.892216 | 120.223381/225.573181 |
| 关闭旧Lease后重开 | 232.920712秒 | 225.606092秒 |
| 正常Resolve/含重开总计 | 1/2 | 1/2 |
| 关闭后访问 | 410 | 410 |
| 最终记录/活动Stream | 0/0 | 0/0 |

两者都正常暂停1.1秒保持，Seek后error=null；新playbackId、同一audio，重开保持paused=true、volume=.3、rate=1.2。原生metadata2次，playing/pause/seeking/seeked各4次，无error事件；浏览器只访问本地Origin。每次Resolver只调用一次，必要的一次前缀探测与随后用户Range传输不是重复Resolve，也没有后台请求后续线路。

Tang失败记录：首轮tang,official配置实际路线为[tang,official,tang,official]，最后命中官方，故没有把首轮播放成功算作Tang成功。随后tang单路正常open诊断返回504/upstream_timeout，未收到HTTP响应头，定位在外部API阶段。最后同一MID、tang单路浏览器复验成功，证明当前正常入口可执行，且上游有波动；没有增加无限重试、延长总预算或替换样本。

## 官方、其他来源和回归

official配置下，同一牵丝戏样本实际调用[official,official]，duration239.420952；中段120.232480、近末尾225.568456、重开225.625920秒。正常1次/总2次Resolve，原生播放、暂停、Seek、新Lease/同audio、关闭410和最终零引用通过。非开发应用的离线正常API测试也证明配置中外部名字不会自动解禁。

| 其他来源 | 固定ID | 中段/近末尾/重开位置 |
|---|---|---|
| 酷我 | 9942644 | 136.314036/255.826190/255.879360秒 |
| 网易云 | 30352891 | 120.179455/225.473350/225.579378秒 |
| 咪咕 | 600929000006452915 | 103.731283/194.542578/194.607773秒 |

三者真实播放、暂停/继续、两处Seek、重开与回收通过，正常Resolve1次，总2次，关闭410、记录/活动Stream0；咪咕重新初始化Provider后重开通过。网易云退出有既有Windows Proactor WinError10054提示，媒体断言及退出码正常。没有修改其他三个Provider。

原8项受控WAV恢复场景全部通过，最终记录/活动Lease/活动Stream0、singleAudio=true。故意断流仍产生固定RuntimeError类型日志。Node17项通过；pytest398项通过，原393保留，新增5项有意义的正常应用API行为测试（vkeys/Tang接入、非开发不解禁、权限拒绝停止、qqovo不自动启用）。唯一原有Starlette/httpx警告；git diff --check通过。

## 代码与最终边界

修改main.py把已有开发开关接入正常QQProvider；qq.py在开发试听范围接纳请求绑定结果并保存脱敏诊断；qq_resolvers/media.py返回探测得到的原representation；开发页增加试听性质说明；原浏览器脚本记录实际路线、失败与公开representation。更新两个旧测试的probe Fixture返回值以符合真实函数新返回约定，新增tests/test_qq_application_routes.py。没有新框架、新依赖、新生命周期或新API。

工作区开始时已有4D4报告及实验脚本未提交，原样保护；本期不修改或删除它们。新增本报告，未git init、commit、push，也未开始下一阶段。

现在可操作的能力是正常应用API开发试听，而非仅隔离脚本；vkeys、Tang仍不能无条件成为面向未知资源的正式默认回退。日常正式使用剩余问题是URL-only独立录音确认与相应访问条件；qqovo需要该服务允许的当前登录及签名材料，暂不扩建。QQ架构在此收口，不再新增资格、评分、Session管理框架；后续推进独立任务要求的搜索、播放和下载。
