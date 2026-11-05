# 39-B.3B：最小播放传输闭环

日期：2026-11-05。已完成歌曲稳定身份→真实KuwoProvider→私有MediaStore→PlaybackLease→本地Stream URL→Chromium原生audio的闭环。

本期实现进程内TTL/容量清理、独立播放租约、GET/HEAD单区间Range代理、取消/异常释放、目标域名与DNS检查、开发原生audio页。没有迁移旧ResultStore全套实现、请求观察、Vue、队列、下载或自动恢复。

**真实酷我录音9942644已通过浏览器播放、暂停/继续、中段与近末尾seek。** Chromium153，时长271.583107秒；播放时间2.027→暂停→3.066秒，seek后分别136.315、255.813秒继续推进。浏览器始终仅访问本地Origin。关闭后新流请求410，媒体记录/活动流均清零。不能把这些结果扩展为所有酷我录音或完整下载成功。

115项旧测试保留，新增40项，155项离线测试通过；pip check正常。详见[生命周期与API](Media-Lifecycle.md)、[验收记录](Verification.md)。旧项目/冻结源码只读，未commit/push。

## 启动

Git Bash在新项目server目录：

```bash
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
MUSIC_CORE_DEV_PLAYER=1 ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

打开`http://127.0.0.1:8001/dev/player`，点击打开并播放。开发页默认关闭，只有环境变量显式开启才提供；与API同Origin，不设CORS。停止服务Ctrl+C。8001占用时改空闲端口，未改旧8000/5173服务。

打开会话：`POST /api/playback/open`，JSON为`{"identity":{"providerId":"kuwo","platformId":"9942644"}}`。返回随机playbackId、本地相对streamUrl、PublicMedia及expiresInSeconds。GET/HEAD streamUrl传输；POST `/api/playback/{playbackId}/renew`续租；POST `/api/playback/{playbackId}/close`关闭。能力ID不要写日志或持久化。

自动浏览器验收需安装可选测试工具：`./.venv/Scripts/python.exe -m pip install -e ".[dev,browser]"`，再用已安装Chromium运行`./.venv/Scripts/python.exe scripts/verify_playback_browser.py --browser <可执行文件路径>`。脚本自行启动/关闭临时服务，不使用旧环境；不传路径则使用Playwright自有浏览器安装。不是日常离线pytest的一部分。

39-B.3A只证明URL与前缀可访问，本期才验证浏览器解码/播放与生命周期。下一阶段建议补充本地可控音频的浏览器网络中断/恢复测试，再考虑按稳定身份失效重解析；不要直接引入完整队列/多来源或下载系统。本次未自动开展下一阶段。
