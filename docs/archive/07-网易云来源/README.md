# 07 网易云来源

2026-11-06，完成独立 `NeteaseProvider`。

搜索使用网易云自身 `POST https://music.163.com/api/cloudsearch/pc`；取链使用自身 `POST https://music.163.com/api/song/enhance/player/url`，普通128kbps请求。成功样本为MP3。原生高品质接口和研究来源记录的30条外部解析路线仅作调查；未发起外部取链请求，也未将其接入当前实现。当前实现没有第三方取链依赖，没有新增软件依赖，也没有请求加密需求。

公共模型、MusicProvider协议、MediaStore、PlaybackLease、Range代理实现及RecoveryPlayer均沿用。代理仅新增网易云已观察到的两个媒体主机。默认来源顺序仍为 `kuwo,qq,netease,migu`，默认仅酷我；前三者标记有限样本验证，咪咕未接入，歌词和下载能力仍关闭。

稳定身份为 `{"providerId":"netease","platformId":"30352891"}`。不保存歌曲媒体地址、账号Cookie或加密上下文到歌曲身份；临时URL及UA/Referer只在私有ResolvedMedia中。仅支持普通渐进媒体，不提供品质选择、登录、高品质解锁、试听拼接或DRM处理。

详见[Provider与Resolver调查](Netease-Provider.md)和[验证记录](Verification.md)。`-110`的具体成因、其他录音的结果、格式覆盖率及完整下载均未验证；不据此推断平台权限原因，也不启用未经核验的外部回退。
