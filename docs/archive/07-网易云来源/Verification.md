# 07 网易云来源 — 阶段 07 验证记录

日期：2026-11-06。Windows、Python 3.10.10、Node 22.22.2、Playwright 1.63.0、Chromium 153.0.8010.12。使用项目隔离环境；旧实现与研究来源只读，未安装额外依赖。

## 离线验收

先实现并运行离线测试，再请求真实接口。最终执行：

```powershell
cd server
./.venv/Scripts/python.exe -m pytest -o addopts= -q
node --test tests/recovery.test.mjs
```

结果：260项pytest通过（原193项保留，新增67项），17项Node测试全部通过。pytest内含调用Node的一个包装测试，17项不能再加到260中当作pytest数量。唯一警告仍为Starlette TestClient对httpx的弃用提示，没有为消除警告升级依赖。

新增离线覆盖：多歌手、缺失可选字段、毫秒转换、数字/字符串歌曲ID、重复/非法ID、分页、空结果、结构异常、业务错误；精确搜索与取链表单、ID核对、空URL、权限、未知大小/格式/有效期、错误码、试听与HLS拒绝、无效选项、超时及取消时关闭响应、无第三方回退；共享客户端凭据隔离、统一search/open/stream/close、新旧Lease/MediaID不同、过期释放、跨Provider生命周期、CDN边界、公共/私网DNS与重定向拒绝。原有200/206/416、取消、断流、连接关闭、容量和恢复测试继续通过。

## 有限真实搜索与取链

命令：`./.venv/Scripts/python.exe -m scripts.verify_netease`。每轮固定两词各10条、四个不同ID、每次探测最多4096字节，不保存完整媒体URL或音频文件。本期为了收敛实际CDN主机与补充安全统计，共进行了三轮相同四样本验证；没有扩大样本集合或扫描其他线路。另有下述浏览器必要的打开/重开请求。

最终一轮搜索：

| 关键词 | 请求耗时 | 返回数/有效ID数 | 歌手/专辑/封面/时长完整条数 |
|---|---:|---:|---|
| 银临 | 319ms | 10/10 | 各10条 |
| 许嵩 | 187ms | 10/10 | 各10条 |

仅搜索元数据，没有按可播性过滤。选择每页前两条，共四个录音：

| 稳定ID | 取链结果 | 媒体探测 |
|---|---|---|
| 30352891 | 原生普通player/url成功 | HTTP206，4096字节，MP3前缀，audio/mpeg，Content-Range总大小3829804字节，与取链接口size一致，0次重定向 |
| 28188434 | 平台单项code=-110，映射upstream_failure | 未发媒体请求 |
| 167691 | 平台单项code=-110，映射upstream_failure | 未发媒体请求 |
| 167655 | 平台单项code=-110，映射upstream_failure | 未发媒体请求 |

成功样本br=128000，expi提供有效期；Core中的container、codec、contentType依然为空，因为Provider不以URL后缀猜测格式，MP3证据单独来自探测。没有把探测结果写成可下载授权或完整下载成功。三首-110的具体成因未确认，不推断会员、地区或版权状态。

开发初轮解析观察到m701.music.126.net，代理按设计拒绝尚未登记的域名；第二轮观察到m801.music.126.net，再按证据补入。没有扩大到126.net整域。早期浏览器一次重开等待超时；补全实际主机后复测通过，最终又加事件计数复核成功。第三方30条路线和原生EAPI均未在线调用，其可用性仍未知。

## 网易云Chromium验收

```powershell
./.venv/Scripts/python.exe -m scripts.verify_playback_browser --browser $env:CHROMIUM_PATH --provider netease --track 30352891 --recover
```

真实平台接口和媒体经原有本地Range代理送入Chromium原生audio。最终记录：

| 检查项 | 实际结果 |
|---|---|
| duration | 239.302336秒 |
| 初次播放推进 | 2.022312秒 |
| 暂停与继续 | 暂停1.1秒位置保持，继续推进至3.038324秒 |
| 中段Seek后继续 | 120.167788秒，seeking=false、error=null |
| 近末尾Seek后继续 | 225.466179秒，seeking=false、error=null |
| 手动重开 | 关闭旧Lease，以同一netease:30352891调用open；恢复225.492796秒、暂停状态、volume=.3、rate=1.2 |
| 会话与audio | 新playbackId、同一个audio元素，正常resolve1次，含手动重开总计2次 |
| 原生事件计数 | loadedmetadata=2、playing=4、pause=4、seeking=4、seeked=4，无error事件 |
| 关闭后访问 | HTTP410 |
| 最终引用 | MediaStore记录0、活动Stream0；旧Lease已关闭，新Lease关闭，活动Lease0 |
| 请求去向 | 浏览器仅访问临时本地同Origin；上游请求由后端发起 |

实际206包括`bytes 0-3829803/3829804`、`bytes 3571712-3829803/3829804`及重开后的远端范围。播放结论来自事件、时间推进及原生媒体状态，不是只根据206作出。

## 酷我与QQ真实回归

同一脚本分别使用`--provider kuwo --recover`及`--provider qq --track 001e7VNQ43nv4W --recover`。两者都真实请求原平台，无Mock。

| 来源 | 录音ID | duration | 初播/继续 | 中段/近末尾 | 重开位置 |
|---|---|---:|---|---|---:|
| 酷我 | 9942644 | 271.583107 | 2.022537 / 3.051631 | 136.316731 / 255.804024 | 255.838306 |
| QQ | 001e7VNQ43nv4W | 239.420952 | 2.040859 / 3.072270 | 120.221697 / 225.568651 | 225.607699 |

两者暂停、继续、两个Seek和手动稳定身份重开均通过，新playbackId、同audio、暂停状态/音量/速率保持。正常取链各1次、含重开各2次；关闭后410，最终MediaStore记录0、活动Stream0，浏览器仅本地Origin。QQ只证明这一个既有样本，未扩展第三方线路。

部分早期运行出现Windows Proactor远端关闭连接的WinError10054回调提示；通过运行的断言、退出码及引用回收均正常。没有因此修改生产代理或静默忽略媒体错误。最终网易云事件复核无该提示。

## 受控恢复回归

执行 `./.venv/Scripts/python.exe scripts/verify_recovery_browser.py --browser $env:CHROMIUM_PATH`，原自生成48秒WAV，8个场景全部通过：真实Lease到期、暂停和重复重试合并、上游失效后的远端Seek、响应头后中途断流、自动预算限制与失败后手动重试、恢复中stop/switch/pause。观察到原生MediaError2，断流连接关闭；结束时记录/活动Stream/活动Lease均0、单audio=true。受控断流产生预期固定RuntimeError类型日志，无媒体地址。

恢复场景通过直接执行专项脚本完成；期间遇到的模块导入路径问题通过调整启动方式解决，没有改动业务代码。

## 文件与Git状态

本期实现涉及：

- `server/app/providers/netease.py`：独立原生Provider。
- `server/app/main.py`、`providers/__init__.py`、`config/__init__.py`：生命周期初始化、固定Provider选择及已验证能力状态。
- `server/app/media_stream.py`：网易云两个已观察媒体主机；代理逻辑不变。
- `server/app/player.html`、`scripts/verify_playback_browser.py`：开发页网易云选择、三来源验证参数、实际原生事件计数。
- `server/scripts/verify_netease.py`：有限真实验收；`verify_qq.py`仅让有界probe可传来源，补MP3帧/FLAC前缀识别，QQ业务解析不变。
- `server/tests/test_netease.py`：67项新测试；`test_api_config.py`、`test_kuwo.py`、`test_media_stream.py`将尚未接入断言限定到咪咕，增加网易云状态断言。
- 根README、server/README、长期架构文档及本目录三份文档。

本阶段实现范围和验证结果见本目录记录。`git diff --check`通过；一个成功样本不代表全曲库成功率。旧实现与研究来源仅作只读依据。
