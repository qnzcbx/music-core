# 04 媒体播放生命周期

后续更新：阶段 05已补单首失效恢复与可控网络验收，见[当前恢复说明](../05-播放恢复/README.md)。本页未实现自动恢复的文字保留阶段 04历史范围。

日期：2026-11-05。已完成歌曲稳定身份→真实KuwoProvider→私有MediaStore→PlaybackLease→本地Stream URL→Chromium原生audio的闭环。

本期实现进程内TTL/容量清理、独立播放租约、GET/HEAD单区间Range代理、取消与异常释放、目标域名和DNS检查，以及开发用原生audio页。搜索观察、Vue前端、队列、下载和自动恢复不在本阶段范围。

**真实酷我录音9942644已通过浏览器播放、暂停/继续、中段与近末尾seek。** Chromium153，时长271.583107秒；播放时间2.027→暂停→3.066秒，seek后分别136.315、255.813秒继续推进。浏览器始终仅访问本地Origin。关闭后新流请求410，媒体记录/活动流均清零。不能把这些结果扩展为所有酷我录音或完整下载成功。

115项旧测试保留，新增40项，155项离线测试通过；pip check正常。详见[生命周期与API](Media-Lifecycle.md)、[验收记录](Verification.md)。

## 启动

在项目根目录打开Git Bash，然后执行 `cd server`：

```bash
cd server
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
MUSIC_CORE_DEV_PLAYER=1 ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

打开`http://127.0.0.1:8001/dev/player`，点击打开并播放。开发页默认关闭，只有环境变量显式开启才提供；与API同Origin，不设CORS。停止服务Ctrl+C。端口冲突时改用其他可用端口，并同步调整前端代理目标。

打开会话：`POST /api/playback/open`，JSON为`{"identity":{"providerId":"kuwo","platformId":"9942644"}}`。返回随机playbackId、本地相对streamUrl、PublicMedia及expiresInSeconds。GET/HEAD streamUrl传输；POST `/api/playback/{playbackId}/renew`续租；POST `/api/playback/{playbackId}/close`关闭。能力ID不要写日志或持久化。

自动浏览器验收需安装可选测试工具：`./.venv/Scripts/python.exe -m pip install -e ".[dev,browser]"`，再用已安装Chromium运行`./.venv/Scripts/python.exe scripts/verify_playback_browser.py --browser <可执行文件路径>`。脚本自行启动/关闭临时服务，不使用旧环境；不传路径则使用Playwright自有浏览器安装。不是日常离线pytest的一部分。

阶段 03仅验证URL与媒体前缀；本阶段验证浏览器解码、播放与生命周期。当前客户端与队列行为见[播放器基础](../14-播放器与歌词/Verification-Player-Foundation.md)和[播放队列](../14-播放器与歌词/Verification-Queue.md)。
