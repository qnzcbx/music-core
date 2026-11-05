# 39-B.2 验收

日期2026-11-05；独立Windows Python3.10.10环境，新项目server/.venv。开始时git status干净，保留用户已有提交；没有git init/commit/push。

## 离线

原56项保留，仅更新providers状态、OpenAPI路径和新增POST后GET405断言。新增test_kuwo.py共40个参数化case；初次96 passed，1条原有Starlette/httpx TestClient弃用警告。

覆盖单引号/JSON映射、空结果/字段缺损/多歌手/非法ID/上限/分页、结构变化/平台码/HTTP错误/timeout/cancel/响应预算、按IDresolve/错来源/未知格式与大小/拒绝/缺URL/协议/私有投影，及API来源选择/连接池关闭/安全错误。不把成功resolve fixture写成真实成功；样本均人工合成，无真实凭据或媒体URL。

## 真实网络

在server执行`./.venv/Scripts/python.exe scripts/verify_kuwo.py`，脚本用新解释器实际启动`python -m uvicorn app.main:app --host 127.0.0.1 --port 51822`（本次临时空闲端口）。health、providers、openapi、docs均200；POST搜索由真实本机TCP进入新应用，再访问酷我，非MockTransport。

| 关键词 | HTTP | 返回候选数 | 选择的platformId | Core Resolve |
|---|---|---|---|---|
| 银临 | 200 | 10 | 9942644 | access_denied |
| 许嵩 | 200 | 10 | 236362975 | access_denied |

两次取链均为站内playUrl HTTP200、success=false，脱敏业务消息The request is illegal!。成功0、拒绝2，没有媒体资源，格式/大小/有效期均无证据。不能判断具体是反滥用、认证缺失还是歌曲权限；未将其解释成媒体不存在或单元测试代码错误。没有访问其他Provider、没有获取整首或前缀音频。

调查阶段另对银临搜索3条以判断响应格式、固定ID5237999站内取链作有限探测；该取链同样被拒绝。未通过其他接口绕过拒绝。在线脚本不打印或保存完整URL，只输出稳定ID、结果数量、安全错误与公共表示。脚本结束已回收验收服务，不干扰旧8000/5173服务。

## 安装与文件范围

尝试`pip install --no-deps --no-build-isolation -e .`因环境缺bdist_wheel失败；随后标准`pip install -e ".[dev]"`成功构建并安装。最终再次pytest为96 passed、1条同样弃用警告，pip check无冲突，git diff --check无空白错误；同时补验Python3.10总期限超时分类和歌手HTML实体解码。

修改：根/后端README、server/pyproject.toml、app/main.py、config/__init__.py、core/errors.py、基础API测试、39-B.1架构文档的当前状态说明。新增：providers/__init__.py与kuwo.py、tests/test_kuwo.py、scripts/verify_kuwo.py及本期三份文档。核心models.py不变、依赖锁中的httpx0.28.1已存在，无需换版本。

未创建前端、未复制vendor/reference、未迁旧观察缓存/基准、未修改旧项目。Git差异保持未提交可审阅；venv与缓存被忽略。

## 未解决项

官方取链成功、媒体可访问/可播放/可完整下载均未验证；无法交付成功媒体闭环。本期已交付独立搜索、取链实现与明确线上阻塞点。39-B.3先确认合法官方访问条件与样本，再接正式Store/Range/Lease；不把一个离线成功响应当作线上授权证据。
