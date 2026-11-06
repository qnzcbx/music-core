# 39-B.4D-3验收记录

2026-11-06。新工程独立Python3.10.10/.venv，Node22.22.2、Playwright1.63.0、Chromium153.0.8010.12。工作区开始干净，旧工程与冻结库只读。审阅4D、4D2三文档、旧qq_fallback/qq_routes/provider_adapter和后续周杰伦回归更正，具体差异见Behavior-Diff。

## 修改与规模

业务仅修改三个文件：qq.py新增4/删除9行，qq_resolvers/__init__.py新增6/删除4行，qqovo.py新增11/删除17行，共新增21、删除30、净减9行。删除两个重复资格/路由判断、官方分支重复输入验证、不使用的options参数、一层qqovo单次转发函数、重复MID检查、第二Cookie容器和响应Cookie重复提取；evidence不再独立存储。没有删除三条Adapter，也没有增加新抽象层。

新增tests/test_qq_behavior.py四项兼容用例及本目录三文档；server/README、长期架构说明同步当前结构。公共模型、Store/Lease、媒体Range语义、RecoveryPlayer、其他三Provider及默认来源未修改。没有新增依赖或实验常驻服务。

## 离线结果

执行`./.venv/Scripts/python.exe -m pytest -o addopts= -q`，393项通过，原389全部保留。唯一既有Starlette/httpx弃用提示。`node --test tests/recovery.test.mjs`，17/17通过，其pytest包装不重复计数。

新增四项证明：身份等级与回显不能保存相互矛盾的状态；获准vkeys URL-only被真实分发调用，正常解析后因未确认身份继续official（不是协议失败）；获准回显结果只调用一次Adapter和一次probe，不再执行官方；qqovo最小bootstrap只需动态key及当前Cookie，两次请求完成后独立会话关闭。均为人工无敏感信息Fixture，不称为真实服务已恢复。

此前389项覆盖三协议请求/签名/版本核对、权限拒绝停止、25秒预算及取消、禁用零请求、SSRF/重定向、私有Header、响应关闭、Range200/206/416、Store/Lease释放，均继续通过。

## 三路当前协议及使用条件

先搜索官方域名公开文档/使用条件（api.vkeys.cn、qqovo.top、tang.api.s01s.cn的站内搜索），本次没有结果；再运行既有`-m scripts.verify_qq_external_conditions`，各根入口最多65536字节，连接5秒/读8秒，不自动重定向，不带QQ凭据。没有把根站200写成歌曲解析成功。

| 项目 | vkeys | qqovo | Tang |
|---|---|---|---|
| Adapter实现 | 是 | 是 | 是 |
| 冻结/旧Lab请求格式对应 | mid/quality=14单档 | bootstrap、当前会话、排序query/HMAC | mid、原曲字段选择 |
| 本次根入口 | 200，820字节，1361ms | 200，13134字节，1523ms | 200，917字节，177ms |
| 已知公开页面 | 服务状态JSON | 听歌平台首页 | 默认站点页 |
| 本应用API测试许可/资源访问条件 | 未确认 | 未确认 | 未确认 |
| 当前歌曲API/真实bootstrap调用 | 0 | 0 | 0 |
| 当前歌曲响应结构实测 | 未测 | 未测 | 未测 |
| 真实取得媒体/录音确认/字节/浏览器 | 均未测 | 均未测 | 均未测 |

当前阻塞分别是vkeys song/link的本应用测试使用条件、qqovo bootstrap/meting自动化接口使用条件、Tang music_open_api.php的有效说明与测试条件；不是已经证实HTTP失败。既有协议Fixture匹配只能证明静态兼容，不能证明当前服务未改协议。没有复用历史密钥/URL，没有未授权内容实验，也没有再运行两套相同official冒充多路线收益。

## 官方基线和四来源真实回归

官方样本001e7VNQ43nv4W，本次单次直接resolve耗时202ms，含媒体probe共2次请求；206、4096字节、MP4 ftyp、audio/mp4、大小2925618、0重定向、aqqmusic.tc.qq.com。仅官方实际返回songmid匹配，不把媒体字节当歌曲指纹。没有外部对照收益数据。

原`-m scripts.verify_playback_browser --browser <已有Chromium路径> --provider <来源> --track <ID> --recover`，四来源均完成真实metadata、播放推进、暂停1.1秒保持、继续、中段/近末尾Seek、旧Lease关闭后稳定身份重开。

| 来源/ID | duration | 初播/继续 | 中段/近末尾Seek后时间 | 重开位置 |
|---|---:|---|---|---:|
| QQ / 001e7VNQ43nv4W | 239.420952 | 2.111599/3.208430 | 120.238380/225.576235 | 225.610041 |
| 酷我 / 9942644 | 271.583107 | 2.056788/3.092202 | 136.315355/255.814237 | 255.846169 |
| 网易云 / 30352891 | 239.302336 | 2.081347/3.132988 | 120.161006/225.469978 | 225.499970 |
| 咪咕 / 600929000006452915 | 206.4 | 2.093590/3.241339 | 103.725107/194.534357 | 194.568196 |

全部error=null、正常Resolve1次、含重开2次；新playbackId、同audio，恢复暂停、volume=.3/rate=1.2。原生loadedmetadata2次、playing4次、pause4次、seeking/seeked各4，无error事件。关闭后410，最终记录0/活动Stream0，浏览器仅本地Origin，咪咕更换Provider实例后重开也通过。四个脚本退出0，无本期重试替换样本。没有把官方回归视作外部播放成功。

原`scripts/verify_recovery_browser.py --browser <已有Chromium路径>`：8项自生成WAV场景通过，包含Lease真实到期、暂停与重复合并、上游过期Seek、中途断流、自动预算/手动恢复、恢复中stop/switch/pause。MediaError2及预期固定RuntimeError断流日志，最后记录/活动Lease/活动Stream均0、singleAudio=true。

## 当前结论与Git

行为可解释性和重复状态已改善，三协议离线行为没有退化；没有可证实的外部真实播放改善或曲库成功率提升。URL-only仍需合法参考资源、可信独立元数据或人工录音确认；时长接近本身不足。当前缺少服务条件与独立身份依据，后续解决这些具体环节，不再增加身份评分或永久禁用框架。

工作区保留本期改动；没有git init、建分支、commit、push或清理用户文件。git diff --check通过（仅Windows LF/CRLF提示）。未开展下一阶段。
