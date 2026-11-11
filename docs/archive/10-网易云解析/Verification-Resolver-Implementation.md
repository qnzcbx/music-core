# 10 网易云解析 — 阶段 10：网易云少量路线与正常播放集成

2026-11-06。本期实现并接入一条外部网易云URL适配器，已在同一期通过正常NeteaseProvider、open、Store/Lease/Range完成真实FLAC播放与重开。固定ID167691的Native仍返回-110，GD补足了该样本的媒体取得与播放。URL-only独立录音确认仍未完成，路线明确命名gdstudio-preview，未自动改默认native或把请求ID回填成独立证明。

## 快速筛选

调查依据为研究来源中的网易云原生接口与外部路线记录，以及当时的媒体行为验证。该阶段沿用已有的30条路线调查清单，没有重新审计所有下载器。

| 候选 | 实际依据与条件 | 本期处理 |
|---|---|---|
| tmetu（L1首位） | 研究来源GET /api/?miss=songAll，id/level/withLyric；历史记录显示真实尝试未取得URL | 对两个固定ID真实请求均ConnectError；只记连接失败，不认定永久失效，不采用无当前成功证据的代码 |
| xuanluoge/kangqiovo/chksz等L1 | 旧记录多条jymaster尝试无URL；最终只记未具名fallback成功，不能归功给某一条 | 不搬全部函数，不继承关闭TLS验证、密钥或复杂会话 |
| gdstudio（L3） | 研究来源记录了匿名的music-api.gdstudio.xyz/api.php路线

旧实现最终fallback有真实媒体证据，但现有采样记录没有完整标明成功叶路线，因此不宣称GD已有具名历史成功。研究来源把若干外部客户端与网易云原生路线分开记录；本阶段只实现已验证的单一匿名API路线，没有复制完整客户端或额外签名逻辑。

公开文档搜索未找到结果。

## 代码与配置

新增`app/providers/netease_resolvers/gdstudio.py`：GET固定URL和上述参数，10秒请求上限、2MiB响应上限、取消关闭响应、auth=None和显式Request隔离QQ Cookie/默认认证。响应为url/br/size/from，当前没有独立歌曲ID。可选ID若出现则严格核对，空URL、业务/HTTP错误、HLS/非法URL有固定错误类别；私有URL用SecretStr，不依据br或后缀猜格式。

NeteaseProvider只增加一个有序循环，整次25秒，成功立即返回；只有临时失败、超时、无媒体继续。明确401/403、错误录音ID及无权试听等拒绝不会切换外部规避。原生-110保留原业务码和请求上下文，不解释为VIP、地区或下架。

唯一顺序入口：

```powershell
cd server
$env:MUSIC_CORE_NETEASE_RESOLVER_ORDER='native,gdstudio-preview'
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

默认native；可单独native、单独gdstudio-preview或调整顺序，省略即停用，未知/重复/空配置拒绝。preview名称明确是受控请求绑定试听，不能以配置名字暗示录音已独立确认。该配置**不依赖MUSIC_CORE_DEV_PLAYER**，没有新增EligibilityManager或第二层启用系统；开发页面开关仍只管理页面是否开放。

普通API请求`{"identity":{"providerId":"netease","platformId":"167691"}}`。真实dev_player=False时/dev/player为404，但open=200；native-first实际HTTP顺序为music.163.com(200)→music-api.gdstudio.xyz(200)→m701.music.126.net(206)，最后私有诊断为gdstudio-preview/request_bound/configured_preview，公开representation为FLAC、50893686字节。没有新平台专属API。

QQ与网易云共用同一种HTTP前缀检查

## Native与外部独立对照

固定两个ID，没有换歌寻找成功。初轮逐路真实API：30352891 Native取得URL；167691 Native失败，row.code=-110；GD对两者均HTTP200、有URL，主机m801.music.126.net，分别声明大小28061275/50893686。未把声明大小直接视为已验证字节。

最终独立复核（含探测的总耗时）：

| ID | Native | GD实际结果 | 身份 |
|---|---|---|---|
| 30352891 | 141ms成功，声明3829804字节/128kbps | 999ms HTTP503、upstream_failure；本轮未请求媒体，不掩盖初轮URL成功后的波动 | Native回显ID；GD未确认 |
| 167691 | 55ms，HTTP200但单项code=-110、upstream_failure | 4154ms，API200，媒体206，bytes 0-4095/50893686，FLAC前缀、读取4096字节 | request_bound，不伪造响应ID |

167691为网易云原生详情返回《天龙八部之宿敌》/许嵩，dt=263340ms；浏览器GD音频时长263.340408秒。时长高度接近是辅助证据，不是独立音频指纹/人工听辨，不能把它升级为已确认相同录音。上游Content-Type=audio/mpeg但字节为fLaC，公开container/codec=flac，sizeBytes=50893686；不据请求br=999或返回br=1546编造母带、采样率或位深。

收益限定：此样本Native无媒体，显式GD受控路线取得并播放音频；这不是全曲库成功率，也不证明全部录音版权/访问条件或未知版本一致。没有完整下载、转码或媒体落盘。

## 正常播放API与浏览器

使用原浏览器脚本，未替换业务Provider、create_app或响应：

```powershell
$env:MUSIC_CORE_NETEASE_RESOLVER_ORDER='gdstudio-preview,native'
./.venv/Scripts/python.exe -m scripts.verify_playback_browser --browser $env:CHROMIUM_PATH --provider netease --track 167691 --recover
```

实际lastResolution为gdstudio-preview，identity=request_bound。两次open的公开媒体均FLAC/50893686字节；duration263.340408秒；初播2.019964、继续3.051136、中段132.186920、近末尾248.066169秒，error=null。关闭旧Lease后相同ID重开恢复248.091900秒，paused=true、volume=.3、rate=1.2，新playbackId、同audio。正常Resolve1次，总2次，成功未继续native。loadedmetadata2次、playing/pause/seeking/seeked各4次；关闭后410、记录0、活动Stream0，浏览器只访问本地Origin。

Native独立模式30352891也通过：duration239.302336，初播2.328729、继续3.526611、中段120.200229、近末尾225.477175、重开225.531585秒；两次诊断均native。正常1次/总2次Resolve、同audio/新Lease、关闭410、最终零引用。

## 测试与其他来源

417项pytest通过，原398保留；19项新增覆盖GD参数与URL-only、异常响应/空媒体/错ID、凭据隔离、配置、无开发页面的正常API命中及成功停止、native失败回退、权限拒绝停止、超时与取消、25秒整链预算。将QQ探测测试的patch位置调整为公共实现，未删除安全断言。17项Node、8项受控WAV恢复场景通过，最后记录/活动Lease/Stream0、单audio不变。唯一既有Starlette/httpx警告。

四来源真实回归均播放、暂停、两处Seek、重开及零引用通过：

| 来源 | ID | 中段/近末尾/重开位置（秒） |
|---|---|---|
| 酷我 | 9942644 | 136.344457/255.807554/255.842672 |
| QQ官方 | 001e7VNQ43nv4W | 120.237831/225.574380/225.608131 |
| 咪咕 | 600929000006452915 | 103.714414/194.532245/194.591376 |

三者正常Resolve1次、含重开2次；咪咕重开更换Provider实例通过。酷我退出有既有Windows Proactor WinError10054提示，脚本退出0且媒体/清理断言正常。上述回归不替代本期GD的新增功能证据。

## 文件与剩余问题

修改main.py、providers/netease.py、原QQ媒体探测兼容导入；新增core/media_probe.py、netease_resolvers小目录和tests/test_netease_routes.py；更新两个QQ测试的目标校验patch位置、原浏览器脚本的网易云脱敏诊断，以及开发页通用请求绑定提示。没有新依赖、Registry、数据库、缓存、队列、下载或恢复框架；公共模型、Store/Lease和HTTP Range语义未改。

仅新增本份阶段报告。剩余问题为GD波动（已见503）、URL-only独立录音与访问条件确认、tmetu连接失败；不因未知永久判死，不扩大到30条扫描，也不无条件开放默认回退。
