# 03 酷我媒体解析 — 阶段 03 验收记录

日期2026-11-05；独立Windows Python3.10.10；本项目server/.venv；

## 真实路线调查

有限地GET酷我首页，再用同一临时httpx Client请求站内playUrl：两者HTTP200，首页设置一个Cookie，但playUrl仍success=false、message=The request is illegal!。只证明正常首页上下文未恢复该请求，不能推断账号或内容付费状态。

随后验证同平台mobi HTTPS普通参数，录音9942644得到rid一致的文本媒体响应。未运行研究来源完整客户端、未调用第三方fallback，未打印媒体URL或响应sig。只读原工具模块用于有限标准密码算法等价性调查，没有修改旧库，最终不依赖其运行。

## 新实现真实验收

在server执行`./.venv/Scripts/python.exe scripts/verify_kuwo.py`。脚本实际启动新后端`python -m uvicorn app.main:app --host 127.0.0.1 --port 54990`；通过本机HTTP搜索，不是Mock：

| 搜索 | 返回数量 | 稳定platformId | 路线 | Resolve | 媒体探测 | 前缀/Content-Type | 总大小声明bytes |
|---|---:|---|---|---|---|---|---:|
| 银临 | 10 | 9942644 | playUrl→mobi | 成功 | 206，4096字节 | MP3特征/audio-mpeg | 4346545 |
| 银临 | 同上 | 7075956 | playUrl→mobi | 成功 | 206，4096字节 | MP3特征/audio-mpeg | 3380649 |
| 许嵩 | 10 | 236362975 | playUrl→mobi | 成功 | 206，4096字节 | MP3特征/audio-mpeg | 4042287 |
| 许嵩 | 同上 | 5358830 | playUrl→mobi | 成功 | 206，4096字节 | MP3特征/audio-mpeg | 3878370 |

成功解析4/4，有限媒体探测4/4，总计读取16384字节。大小来自Content-Range分母，是服务端声明的完整资源大小，不是完整下载的实际验收大小。Content-Type原值audio/mpeg。URL未保存；Provider representation的codec/container/size/有效期仍未知，未以脚本证据写回运行缓存。浏览器播放及完整下载均未执行。

health/providers/openapi/docs均200，搜索200。首次该脚本输出providers仍为旧implemented_unverified_media；之后根据上述证据将实现状态更新为implemented_sample_media_verified并由API离线测试固定。这个状态是样本验收记录，不代表每次health都探测酷我。

脚本最终关闭验收服务，旧实现8000/5173服务未触碰。调查额外一次mobi取链仅用于确认文本协议；没有额外音频下载。

## 离线与文件

`./.venv/Scripts/python.exe -m pytest`：保留96项，新增19项路线/探测case，合计115通过，1条原有Starlette/httpx弃用警告。覆盖合法切换、购买/权限拒绝不切换、超时/取消单次终止、mobi文本成功/缺URL/错rid/重复字段/非法协议、私有数据、200完整响应预算、206完整大小语义及错误页。最初新测试有中文bytes字面量语法错误，已修正后全通过。

修改：`server/app/providers/kuwo.py`、`server/app/config/__init__.py`、`server/scripts/verify_kuwo.py`、`server/tests/test_api_config.py`；新增`server/tests/test_kuwo_routes.py`。同步根/后端README、阶段 01架构状态、阶段 02历史提示；本目录仅三份文档。Core模型、pyproject、依赖锁均无变更。

临时算法调查工具已卸载，未加入运行依赖。没有复制研究来源代码或修改旧实现；本阶段仅覆盖媒体解析与有限字节验证。

## 验收边界

本阶段取得可按稳定ID重新解析的真实媒体样本，但URL有效期未知，不得把本次地址当长期fixture。浏览器播放及完整下载未验收。
