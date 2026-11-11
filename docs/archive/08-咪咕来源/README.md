# 08 咪咕来源

2026-11-06，完成独立MiguProvider。原生搜索、按稳定身份重建元数据、按需取链均接入已有API。两个关键词各10条，四个录音全部通过原生取链及4096字节MP3前缀验证；其中一首通过Chromium播放、暂停、继续、中段和近末尾Seek、同一audio重开及资源回收。样本结论不代表全曲库覆盖率。

稳定身份使用数字字符串contentId。新增原生resourceinfo.do精确资源查询，在每次resolve时重新取得copyrightId和格式目录；不依赖搜索缓存，公共TrackIdentity和其他Core模型不变。真实copyrightId包含字母，不能与contentId互换。更换Provider实例后直接按相同身份重开已通过；两个独立验证进程也均未先搜索便成功播放。

搜索采用c.musicapp.migu.cn/v1.0/content/search_all.do，元数据重建采用同域/v1.0/content/resourceinfo.do，取链采用同域/strategy/listen-url/h5/v2.4。研究来源没有咪咕第三方解析函数链；本项目也没有第三方解析依赖、内置账号、合成媒体地址或音质路径改写。响应的公开字节混淆协议留在Provider内，不涉及音频DRM解密，无新增依赖。

四来源均通过相同MusicProvider、MediaStore、PlaybackLease和Range代理。默认顺序仍为kuwo、qq、netease、migu，默认只选酷我；能力状态表示有限真实样本已验证，歌词和下载仍关闭。没有修改Store/Lease职责或RecoveryPlayer，没有创建Vue、队列、聚合搜索、下载或缓存系统。

验收：334项pytest通过（保留原260项，新增74项），原17项Node状态机测试通过，8项受控恢复场景通过，酷我/QQ/网易云真实播放、Seek、稳定身份重开均通过。

详见[咪咕身份与Provider](Migu-Provider.md)及[验证记录](Verification.md)。仍未验证登录、高品质、更多CDN、同曲不同版本的全局ID关系及完整下载；真实搜索没有时长字段，保留未知。
