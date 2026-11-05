# 39-B.4B 网易云独立接入

2026-11-06，在新工程完成独立 `NeteaseProvider`。搜索、按稳定歌曲ID取链及统一播放链路已接通；一个真实匿名样本通过有限字节探测和 Chromium 播放、暂停、继续、两处 Seek、稳定身份重开。四个录音样本中其余三个返回平台 `code=-110`，未推断其权限原因或全曲库覆盖率。

搜索使用网易云自身 `POST https://music.163.com/api/cloudsearch/pc`；取链使用自身 `POST https://music.163.com/api/song/enhance/player/url`，普通128kbps请求。成功样本为MP3。原生EAPI高品质接口和冻结库30个第三方解析方法仅调查，未迁入、未发请求。当前实现没有第三方取链依赖，没有新增软件依赖，也没有请求加密需求。

公共模型、MusicProvider协议、MediaStore、PlaybackLease、Range代理实现及RecoveryPlayer均沿用。代理仅新增网易云已观察到的两个媒体主机。默认来源顺序仍为 `kuwo,qq,netease,migu`，默认仅酷我；前三者标记有限样本验证，咪咕未接入，歌词和下载能力仍关闭。

稳定身份为 `{"providerId":"netease","platformId":"30352891"}`。不保存歌曲媒体地址、账号Cookie或加密上下文到歌曲身份；临时URL及UA/Referer只在私有ResolvedMedia中。仅支持普通渐进媒体，不提供品质选择、登录、高品质解锁、试听拼接或DRM处理。

详见 [Provider与Resolver调查](Netease-Provider.md) 和 [验证记录](Verification.md)。后续39-B.4C建议按任务接入咪咕，沿用同一协议及验收标准；网易云如需扩展CDN主机或登录上下文，先补真实证据和隔离测试。`-110`具体成因、其他录音和格式覆盖率、完整下载仍未验证，不增加无依据的第三方回退。
