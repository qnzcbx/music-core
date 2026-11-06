# 40-B：歌词获取与逐行同步

调用链为 TrackIdentity → GET /api/lyrics → 独立 LyricsCache → Provider.get_lyrics → 原生接口 → 公共 LRC 解析器 → LyricDocument。无需搜索、媒体解析、下载任务或播放Lease。模型及解析、平台响应映射、有界请求和缓存集中在 server/app/lyrics.py；四Provider提供薄方法入口，MusicProvider协议增加get_lyrics。没有新增媒体Resolver。

示例：`GET /api/lyrics?providerId=netease&platformId=284617`。仅接受四来源合法稳定身份，错误继续使用既有统一错误格式。开发页 /dev/player 增加独立歌词按钮和观察区域；启动仍需 MUSIC_CORE_DEV_PLAYER=1。

LyricDocument包含identity、status、lines、plainText、sourceFormat、unalignedTranslation。状态为synced/plain/instrumental/unavailable；网络、权限及结构错误不转为unavailable。LyricLine包含startMs、endMs、text、translation、romanization。romanization当前保持null，不实现逐字系统或自动翻译。

所有时间为毫秒。LRC支持BOM、换行、多时间戳、1至6位小数、乱序、重复、空行、metadata和offset。offset单位毫秒，按原时间加offset并夹到0；小数超过毫秒部分截断。同时间不同文本合并，同时间同文本去重；结束时间仅推导至下一不同开始时间，最后保持null。纯文本不伪造时间。翻译按时间差最多20ms且唯一最近候选对齐，不按列表位置绑定；未对齐内容保留unalignedTranslation。没有独立无演唱标志时，不靠标题猜纯音乐。

| 来源 | 原生接口与格式 | 所需身份 |
|---|---|---|
| 酷我 | m.kuwo.cn/newh5/singles/songinfoandlrc；lrclist秒时间+文本 | musicId |
| QQ | c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg；base64 lyric/trans，解码后LRC或文本 | songmid |
| 网易云 | interface3.music.163.com/api/song/lyric；lrc/tlyric，nolyric明确标志 | id |
| 咪咕 | resourceinfo.do按contentId重建copyrightId；app.c.nf.migu.cn/MIGUM3.0/strategy/pc/listen/v1.0取lrcUrl，再受控读取 | contentId，无需旧搜索JSON |

QQ/网易云映射支持平台提供的翻译；本期真实样本没有翻译。酷我/咪咕未宣称支持翻译。咪咕当前仅允许d.musicapp.migu.cn歌词CDN，检查公共DNS和端口，不跟随重定向；其他目标拒绝。所有请求独立构建Request、auth=None，不合并共享Cookie/认证头；限制1MiB响应、10000行和12秒获取预算，响应finally关闭。不记录私有上下文。

缓存只存标准化DTO，key为(providerId,platformId)，TTL600秒、容量128，正常无歌词结果也按相同TTL缓存；失败不缓存。相同身份并发使用短生命周期锁合并，上限128个正在获取的身份，结束后移除锁。没有数据库，重启后根据稳定身份重查。

浏览器仅使用已有audio.currentTime，通过timeupdate/seeking/seeked/loadedmetadata重新计算当前行，暂停保持；媒体恢复不重新创建歌词状态。请求代次隔离切歌后的晚到响应；歌词失败只更新歌词区域，不调用播放恢复。纯文本和无歌词显示明确状态。未实现Vue组件、动画、自动翻译、QRC/KRC逐字解码、LRC下载或标签嵌入。未来Vue可直接复用API和DTO。
