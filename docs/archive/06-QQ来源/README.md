# 06 QQ来源

日期：2026-11-05。QQProvider已接入现有统一搜索/播放API，无新平台专属接口，无新增运行依赖，未安装或复制研究来源。

QQ自身搜索接口真实验证：“许嵩”“银临”各10条；四个选定录音中1个取得媒体并通过4096字节检查，其余3个没有可用purl。成功样本`001e7VNQ43nv4W`通过Chromium本地代理播放、暂停/继续、中段及近末尾seek；显式关闭旧会话后，通过稳定songmid手动重开恢复位置，仍为同一audio。**不代表全部QQ歌曲稳定可播放，也不把缺purl统一解释为会员限制。**

酷我默认来源、顺序、取链路线及生命周期保持不变，真实播放/seek再次通过，正常Resolve一次；原受控恢复矩阵再次通过，资源清理为零。网易/咪咕仍未接入。QQ与酷我状态均为implemented_sample_media_verified，仅表明有限样本验证；两者lyrics/download能力仍false。

离线pytest193项通过，原159项全部保留，新增34项；内部17项Node状态机测试仍通过。详见[QQ实现](QQ-Provider.md)、[验收](Verification.md)。没有修改旧实现/研究来源，未创建分支、commit或push。

## 使用

按[后端运行说明](../../../server/README.md)启动。POST `/api/search`输入`{"providerId":"qq","query":"银临","limit":10}`；POST `/api/playback/open`输入`{"identity":{"providerId":"qq","platformId":"001e7VNQ43nv4W"}}`。后续stream/renew/close与酷我相同。

开发页只增加来源选择，可选QQ并输入songmid；不是新播放器或Vue工程。服务端可选环境变量`MUSIC_CORE_QQ_COOKIE`用于自有合法QQ登录上下文，未配置时匿名请求；不要写入示例、日志或仓库。本次在线验收未配置凭据，不声称已经验证登录账户能力。

有限在线脚本：server目录执行`./.venv/Scripts/python.exe scripts/verify_qq.py`。浏览器脚本可加`--provider qq --track 001e7VNQ43nv4W --recover`；正常酷我验收不加平台参数。不要将这些在线脚本作为日常离线CI。当前缺purl案例保留安全错误，不引入陌生第三方兜底、多级重试或凭据伪造；无需重写MediaStore/Lease。
