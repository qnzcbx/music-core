# 39-B.4D-4：真实协议与串行链实验

2026-11-06。本期没有修改正式Provider、资格配置、身份发布条件、媒体白名单或播放器。新增一个隔离实验脚本，不再进行架构重构。实验采用用户要求的有限真实调用；匿名公开接口未发现明确自动化禁止说明，不绕过登录/会员/DRM限制。公开可达不等于获得长期、商业或全部曲库授权，实验结果不用于无条件启用默认路线。

## 核心新结果

1. 三条外部Adapter都真正执行了相关API，不再是歌曲API零请求的审计。
2. **周杰伦《蒲公英的约定》官方取链无URL；串行链第一路vkeys取得可访问FLAC，并通过真实Chromium播放、Seek及稳定身份重开。** 后续三路未调用，证明这一个固定样本存在实际媒体/播放增益。
3. Tang对另一固定样本取得MP4且通过浏览器播放与重开；qqovo当前bootstrap明确要求登录，不是笼统的“条件未知”或“第三方失效”。

## 实验方法与访问边界

先核对具体接口而非根页：vkeys旧歌曲接口不带参数时返回HTTP200、业务110000（上游返回空），不能代表有效MID失败；qqovo robots.txt公开Allow:/（仅说明抓取规则，不等同于资源授权）；Tang具体PHP接口最初ConnectError。随后对一个已知官方可访问的普通样本逐路调用现有正式Adapter构造代码，得到下表。没有使用旧Cookie、历史URL、服务密钥或Fixture。遇到qqovo明确登录要求后未请求meting、未伪造key或登录身份。

用户随后指定周杰伦《蒲公英的约定》及“失败才下一条、成功停止”的实际链路。仅新增这一个用户指定样本，通过QQ元数据搜索一次最多10条，固定原唱录音MID=004Yi5BD3ksoAN，歌手周杰伦、标题无Live标记、官方时长247秒，未改用翻唱/现场版本凑成功。保留原单路样本001e7VNQ43nv4W为协议对照。

脚本API响应最多2MiB、每请求10秒、外部整次调用25秒；qqovo两次请求共用总预算。媒体探测每次最多4096字节，沿用QQ域名与逐跳DNS校验，关闭响应，不保存媒体文件。只有正常公开接口调用，没有更改TLS、代理到任意URL或对登录屏障重试绕过。

## 同一个普通样本的四条独立路线

固定MID=001e7VNQ43nv4W，官方详情显示《牵丝戏》，歌手银临、Aki阿杰，时长239秒。执行`./.venv/Scripts/python.exe -m scripts.verify_qq_external_protocol`。

| 路线 | 实际API请求 | HTTP/协议结果 | URL与有限媒体 | 身份证据 | 本期浏览器/Seek | 取链/含探测耗时 |
|---|---|---|---|---|---|---|
| official | 是，GetVkey | 200，code=0，MID匹配 | MP4，206/4096字节，2925618 B | 官方MID回显 | 本期此模式未重跑浏览器，4D3已有；不能当外部证据 | 316/413ms |
| vkeys | 是，song/link，mid及quality=14 | 200，code=0，data.url兼容 | FLAC前缀，206/4096字节，162248754 B，ws.stream.qqmusic.qq.com | request_bound，未回填response_mid | 此普通样本未测浏览器；下方另测用户指定曲 | 291/377ms |
| qqovo | 是，bootstrap；meting否 | 200，响应只有authenticated/loginRequired，无apiSignKey | 未取得URL/媒体 | 无 | 否 | 3111ms，停在会话阶段 |
| Tang | 是，music_open_api.php | 200，MID及名称/歌手字段可解析 | MP4，206/4096字节，2925618 B，isure6.stream.qqmusic.qq.com | MID匹配；完整元数据并非全一致，见下文 | 是/是，隔离实验 | 2973/3048ms |

上述各路线只调用一次Adapter、单路独立执行，不隐含回退。official、vkeys、Tang各一次API+一次媒体探测，qqovo一次bootstrap。vkeys返回Content-Type=audio/x-ogg，但实际前缀为fLaC；没有据MIME或后缀将其判为OGG，也没有按quality=14编造位深。

qqovo另做一次有限bootstrap确认，真实布尔值为authenticated=false、loginRequired=true、apiSignKeyPresent=false。因此缺少的具体条件是**该服务允许的当前已登录会话/合法账号和签名材料**。没有调用签名meting，无法声称当前签名成功或失败；现有协议的匿名bootstrap预期与当前服务登录流程不一致。没有尝试复用旧Lab Session，也没有修改Adapter绕过登录要求。

## Tang身份证据与真实浏览器

按现有Adapter响应MID可记confirmed，但它不是录音指纹认证。额外从QQ自身get_song_detail_yqq取得元数据：官方标题《牵丝戏》、歌手银临与Aki阿杰；Tang标题相同、MID相同，但歌手仅银临。传入完整expected_artist时**严格核对实际失败**。这是新发现的元数据完整性差异，不能说全部元数据一致，也没有为了通过而放宽比较。

两次补充“官方/Tang对象路径及前缀摘要对比”均因Tang API超时停止，没有得到摘要一致证据，不能用相同大小或文件名替代。Tang此前实际成功与之后的超时并列记录，说明有波动，不能宣称永久稳定。

在一个单独进程中，仅将该进程的QQProvider构造器替换为`tang`单路线并授予当前实验实例资格，复用原verify_playback_browser；退出后原构造器恢复，未改应用默认配置。真实结果：duration239.420952，初播2.023463、继续3.037080、中段120.223476、近末尾225.570254秒，error=null；重开恢复225.601846秒，paused=true、volume=.3、rate=1.2。新playbackId、同一个audio；正常Resolve1次，含重开2次；关闭后410，记录/活动Stream为0。原生metadata2次、playing/pause/seeking/seeked各4次，无error事件。

因此Tang已取得协议、媒体、原生播放/Seek的真实成功证据；仍保留歌手字段缺失和无完整指纹比对的边界，不扩大为全曲库授权或永久默认资格。

## 用户指定《蒲公英的约定》：真正的串行覆盖实验

同一固定原唱MID=004Yi5BD3ksoAN。先独立执行official：192ms返回media_unavailable（空purl），未把它擅自解释成会员、地区或账号拒绝。随后独立实验链按vkeys→qqovo→Tang→official运行，明确权限拒绝停止，临时失败才继续，整链25秒。

第一路vkeys在236ms返回URL，FLAC前缀、206、4096字节、大小161249673 B、主机ws.stream.qqmusic.qq.com、0次重定向；随后三个Resolver均未请求。这个实验不是“禁用三路＋official”的伪对照。

复现真实串行浏览器实验：

```powershell
cd C:/Code_Home/2_projects/musicdl-lab/server
./.venv/Scripts/python.exe -m scripts.verify_qq_external_protocol --chain-browser C:/Users/86151/AppData/Local/ms-playwright/chromium-1243/chrome-win64/chrome.exe --mid 004Yi5BD3ksoAN
```

该命令只在当前实验进程使用实验Provider，直接调用现有Adapter并探测音频，允许预览request_bound结果；它**不修改正式Provider要求录音证据充分的发布规则**，不持久化URL或权限。每次open仍沿用原Store/Lease/Range，停止后复原构造器。

实际结果：

| 项目 | 实际观测 |
|---|---|
| 正常/重开实际命中 | 两次均vkeys，previousFailures为空、后续路线均未调用 |
| 身份等级 | request_bound；无response_mid，不升级为独立确认 |
| metadata duration | 247.199547秒，与官方搜索247秒近似，仅作辅助 |
| 初播/暂停/继续 | 推进到2.018652秒；暂停1.1秒保持；继续到3.041983秒 |
| 中段Seek | 124.124984秒，seeking=false、error=null |
| 近末尾Seek | 232.887831秒，seeking=false、error=null |
| 稳定身份重开 | 232.919883秒，新playbackId、同audio、paused=true、volume=.3、rate=1.2 |
| Resolve次数 | 正常1次，含手动重开共2次 |
| 浏览器事件 | loadedmetadata2次，playing/pause/seeking/seeked各4次，无error事件 |
| 回收 | 关闭后410，MediaStore记录0、活动Stream0，浏览器仅本地Origin |

真实远端Range包括中段bytes 76152832-161249672/161249673与近末尾bytes 151814144-161249672/161249673。没有完整下载任务或媒体落盘；浏览器按正常Range播放。退出期间出现既有Windows Proactor WinError10054连接关闭提示，脚本退出0，媒体和引用断言通过。

### 能证实与不能证实

- 已证实“当前外部路线无法取得可播媒体”的笼统判断不成立：vkeys、Tang都实际工作，且本曲vkeys补足了official无URL的缺口。
- 本曲URL取得、媒体可访问、浏览器播放/Seek：外部实验链各1/1，官方URL0/1。这是单样本增益，不是整个QQ曲库成功率。
- 本曲独立录音身份确认仍未完成：vkeys只提供请求绑定，时长近似和FLAC字节不是指纹或人工听辨。因此不能把实验预览直接宣传成正式已确认的周杰伦原唱版本或自动解禁默认路线。
- qqovo的具体阻塞已定位到当前登录要求，不是签名公式已证伪，也不是被新Core的正式发布Gate阻断。

## 代码、回归及最终收口

仅新增`scripts/verify_qq_external_protocol.py`：使用现有Adapter做独立协议实验、脱敏HTTP阶段记录及可重复的隔离串行浏览器实验。未修改生产Adapter、任何永久Gate、媒体Host、公共模型、Store/Lease、RecoveryPlayer或其他Provider。没有协议代码修复，因为已取得的结果未证明它们的正常请求构造有错误；qqovo需要当前登录材料，不能靠删检查修复。

393项既有pytest再次通过，只有原Starlette/httpx警告。它仅是回归保障，不作为本期新成果。因生产代码未改，本期不重复跑其他三个无关平台；本期新浏览器证据只列Tang与用户指定曲的隔离链，不冒充四来源全新回归。

新报告和脚本保留工作区，旧Lab只读，未commit/push。唯一仍影响默认正式采用的关键问题是URL-only的独立录音确认，以及qqovo合法当前登录/签名上下文；前者需要可信参考录音或人工确认，后者需要服务允许的账号会话。默认资格未改变；未开展下一阶段。
