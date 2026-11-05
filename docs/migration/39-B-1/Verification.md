# 验收记录

日期：2026-11-05；Windows，独立Python3.10.10，解释器`C:/Code_Home/2_projects/musicdl-lab/server/.venv/Scripts/python.exe`。未使用旧项目venv、运行服务或runtime。

## 实际执行

从新项目根执行`py -3.10 -m venv server/.venv`，随后新解释器执行`-m pip install -e "./server[dev]"`成功。在server工作目录执行`./.venv/Scripts/python.exe -m pytest`。运行依赖FastAPI0.162.0、Pydantic2.14.3、Uvicorn0.54.0；测试pytest9.2.0、httpx0.28.1。完整环境版本见server/requirements-dev.lock.txt。

56项离线测试通过；覆盖4来源ID格式/命名空间/边界、Candidate缺失/未知/多歌手、公开媒体投影及repr不泄密、有效期和非法URL、未知品质/大小、租约token隐藏、async协议调用、配置排序/降级、HTTP状态及异常清洗。fixture是人工合成安全DTO，不包含真实平台请求或签名。

实际以新解释器启动：`python -m uvicorn app.main:app --host 127.0.0.1 --port 64224`，进程内探测选空闲端口；urllib通过真实本机TCP访问，非TestClient替代：

| 请求 | 结果 |
|---|---|
| /api/health | 200，status=ok，version=0.1.0，configurationFallback=false |
| /api/providers | 200，kuwo/qq/netease/migu，默认kuwo，全部not_integrated、能力false |
| /openapi.json | 200，当前paths仅health/providers，无上游URL/headers schema |
| /docs | 200，文档HTML可获取 |

测试进程已结束，不占用用户端口；旧8000/5173服务未触碰。`pip check`无依赖冲突。开发文档使用8001避免默认旧端口冲突；reload选项未验证。

## Git与范围

开始时仅.git，main分支工作区干净；结束时新增.gitignore、README、server、docs，尚未提交、未建远程、未push。venv、缓存、egg-info及日志被忽略；没有前端、musicdl/vendor、媒体文件、真实凭据或旧业务import。没有修改旧实验项目代码。可用`git status --short --untracked-files=all`审阅全部新增文件。

## 限制

Starlette TestClient对当前httpx适配产生一条弃用警告，56项测试仍通过；不是业务失败，未为消除警告引入额外httpx2运行依赖。当前lock记录实测Windows/Python3.10环境，其他系统需独立安装验证。

健康检查仅证明本服务可响应和配置有效，不证明任何平台可用。PublicMedia等模型尚无实际业务路由；完整媒体生命周期、Lease发放、候选私有上下文仓库、下载任务均留后续。当前不声称真实搜索、播放、下载或四平台映射已经验证。不自动开始39-B.2。
