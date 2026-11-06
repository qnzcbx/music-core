# 40-B 验收记录

2026-11-06。只写入新工程C:/Code_Home/2_projects/musicdl-lab；开始Git干净。只读核对冻结库四来源歌词方法、旧Lab app/lyrics.py及新项目既有迁移记录。未复制真实完整歌词、平台凭据或签名地址。无新依赖、无commit/push，未开始40-C。

## 真实接口

| 来源 / 稳定身份 | 真实结果 | 标准化 |
|---|---|---|
| kuwo / 9942644 | H5接口HTTP200，status301、msg音乐查询失败、data=null | upstream_failure，不能冒称无歌词 |
| qq / 001e7VNQ43nv4W | 原生歌词请求成功，base64字段解码 | synced，49行，首时间250ms，无翻译 |
| netease / 284617 | 原生歌词请求成功 | synced，27行，首时间0ms，无翻译 |
| migu / 600929000006452915 | 先独立resourceinfo重建版权ID；pc/listen接口HTTP200，code299999，未返回歌词地址 | upstream_failure，不尝试新服务扫描 |

四来源均有实际请求，只有QQ、网易云本轮取得同步歌词。酷我和咪咕未完成真实歌词同步；已有普通媒体能播放不代表歌词接口可用。两者响应映射已用人工Fixture验证，但不能用Mock成功替代在线结果。没有为了验收捏造时间戳。当前样本不提供真实翻译、纯文本或纯音乐证据，这些分支由人工短歌词测试覆盖。

## 浏览器

运行server/scripts/verify_lyrics_browser.py，普通create_app(dev_player=True)、独立Uvicorn、本机Chromium153.0.8010.12，无替换网易云业务Provider。284617实际媒体播放超过1秒且歌词区域显示同步歌词。暂停后Seek120秒，零起始索引14；等待500ms保持同一索引；连续Seek40/180/60秒后索引5。API文档时间戳用于独立计算预期，不打印真实歌词文本。

手动媒体重开后phase=ready，同一个audio，歌词仍存在；没有为媒体恢复重新创建歌词状态。额外使用人工响应：A请求延迟、B先到并显示人工翻译，随后A返回旧文本，B内容保持。证明请求代次隔离，不把人工译文当真实平台歌词。没有逐字时间、音频识别或声学对齐证明；此验收证明播放器时间轴与歌词时间戳一致，不声称所有平台歌词均与录音声学精确对齐。

脚本初次API及另一次全新应用真实请求分别取得网易云27行，证明无历史MediaStore/搜索Session可取；缓存仅在进程内。离线API验收在未播放状态取得歌词，Store和Lease为空。缓存测试覆盖同身份5个并发请求仅调用一次Provider、TTL过期重查及容量淘汰。

## 回归

最终pytest为502 passed（原484项保留，新增歌词18项），一个既有Starlette/httpx弃用警告。已有pytest包装内17项Node恢复测试通过，不另加到pytest数量。人工短歌词覆盖小数精度、offset、多标签、乱序/重复/空行、纯文本/空/纯音乐、翻译匹配及未对齐、四来源字段映射、私有认证隔离、HTTP403/404/429/503、超时、结构变化、超大响应及取消。普通测试不访问公网，包括咪咕歌词CDN的DNS使用替身。

四来源均运行原verify_playback_browser.py --recover成功：kuwo9942644、qq001e7VNQ43nv4W、netease30352891、migu600929000006452915；初次resolve1次，手动重开总2次、新Lease/同audio、暂停/音量/速率保持，关闭410、records/streams=0。原8项受控恢复浏览器场景亦通过，最终records/streams/leases=0、singleAudio=true。故障fixture未提供新增get_lyrics方法，故歌词API出现隔离的AttributeError安全500，播放故障验收仍通过；不是生产Provider缺少该方法。故意断流的RuntimeError日志仍属预期。Windows浏览器收尾偶见既有Proactor10054，所有断言及线程收尾通过。

40-A下载专项继续通过，下载取消/失败与audio并行脚本另执行。未重新下载四来源完整文件，40-A真实文件结果仍是上一期证据，不冒称本期重新全量下载。

## 交付与限制

新增app/lyrics.py、tests/test_lyrics.py、scripts/verify_lyrics_browser.py、本目录两份文档。修改四Provider加入get_lyrics、公共MusicProvider协议、main.py统一路由与独立缓存、来源lyrics能力声明、player.html最小观察区域及OpenAPI契约测试。没有修改MediaStore、PlaybackLease、DownloadManager或恢复控制器。pip依赖未变。

仍未解决：酷我301、咪咕299999的当前接口失败；QQ真实同步Seek未单独验证；没有完整QRC/KRC、逐字高亮和自动翻译。其他咪咕CDN在没有当前成功证据前不放开。当前平台映射集中在小型歌词模块，后续协议变复杂时可移回各Provider，不增加全局框架。结束Git为本期上述修改和新增文件，未自动提交。
