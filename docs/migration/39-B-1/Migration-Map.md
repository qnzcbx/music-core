# 迁移映射与第三方边界

已阅读旧项目`notes/65-project-consolidation-audit/`四报告，并核对当前源码。旧根目录为`C:/Code_Home/2_projects/media-lab/musicdl-lab`，参考目录为其上层`references/musicdl-master`。没有复制任何musicdl源码、旧业务模块或历史请求记录。

| 旧源码证据 | 本期用途 | 新实现 |
|---|---|---|
| server/app/source_profile.py:25、config/music-sources.json | 四来源偏好和配置校验 | 重新实现SourcePolicy、整份错误配置安全降级并可见degraded |
| server/app/providers.py:33,62 | 旧8来源/动态导入注册 | 只保留4个稳定ID及展示名；无动态class导入，能力全false |
| server/app/provider_adapter.py:37,99,151 | 元数据与解析分离/白名单 | SongCandidate与async Provider协议；未迁真实映射/HTTP |
| server/app/playback_identity.py:17,57 | ID格式/命名空间 | TrackIdentity；不迁两页补查或single-flight |
| server/app/migu_adapter.py:10 | contentId/copyrightId不同语义 | 稳定ID约束与文档，私有copyrightId留后续Adapter |
| server/app/result_store.py:41,51、player_leases.py:23 | TTL与三类保护引用 | 生命周期说明、Lease数据模型；未迁store实现 |
| server/app/resolved_media.py:59,88 | 公开描述与私有上下文分离 | 新私有ResolvedMedia和PublicMedia显式投影，不保留legacyResolvedId |
| web/src/types/music.ts:72,95、player/player-persistence.ts | Candidate/Identity/QueueEntry分离 | 仅契约参考；没有复制TS或迁前端 |

旧readme、Registry能力描述不能直接作为新能力状态。39-A指出的咪咕后台集合已开放/文案滞后仅作后续迁移提醒，本期没有预解析能力。

完整musicdl当前是旧venv中的2.14.0 editable vendor；39-A同路径112个Python文件与冻结reference一致。四来源功能候选依赖为sources的kuwo/qq/netease/migu/base及utils的data/misc/cookies/hosts/importutils/logger/songinfoutils/lyric/cmd/ip和qqutils/kuwoutils/neteaseutils。现包初始化仍牵动其他平台，保守AST闭包93/95不是最小可安装证明；本期不再普查全平台、不裁剪、不安装该库。

39-B.2如需musicdl，应新增受管理且固定版本的可替换Adapter依赖；不通过sys.path/PYTHONPATH拼旧目录，不跨目录import旧app。QQ FunctionType/身份/三路线、咪咕AST补丁需协议fixture保护，不能仅搬四个客户端文件。

明确不迁入：server/experiments、benchmark_*、validate_*实验服务、请求观察、Range Timeline、旧debug/cache诊断API、notes源码快照、非四来源平台、旧兼容Song大对象。未来必须迁的真实搜索/解析、Stream、队列、恢复、下载和转换，本期均未提前实现。旧项目未修改。

## 依赖与许可

本期直接运行依赖FastAPI（MIT）、Pydantic（MIT）、Uvicorn（BSD-3-Clause）；开发测试pytest（MIT）、httpx（BSD-3-Clause）。准确版本见Verification与环境锁定文件；传递依赖版本也记录在lock，未来发布时仍需收集实际发行包通知/许可，不把版本清单当完整SBOM。

旧musicdl2.14.0的LICENSE为PolyForm Noncommercial1.0.0。仅许可目的内使用、修改、分发并遵守通知条件；没有本次证据支持任意商业分发或改标MIT。旧Mutagen为GPL-2.0-or-later、完整库的pywidevine为GPL-3.0-only；新环境没有这些依赖。未来FFmpeg许可取决于实际构建。本期不新增第三方客户端依赖，不以换TS/Java或进程隔离推定许可豁免。最终产品授权与分发方案尚待明确。
