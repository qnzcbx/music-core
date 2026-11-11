# 12 歌词增强 — 阶段 12 验收记录

2026-11-06，在项目隔离环境完成验证。

## QQ配置解耦

原main.py把dev_player传给QQProvider.development_preview，既控制页面又控制available_routes及URL-only身份使用。现在仅由MUSIC_CORE_QQ_RESOLVER_ORDER中是否明确配置vkeys/Tang决定启用原有预览能力，dev_player仅控制开发页面。没有修改Adapter、ResolvedMedia、Store、Lease或恢复协调器。未配置时仍official；qqovo仍不启用，不补造登录材料。

正常服务可设置MUSIC_CORE_QQ_RESOLVER_ORDER=vkeys,tang,official而不设置MUSIC_CORE_DEV_PLAYER。配置不证明内容访问授权；原request_bound、错MID拒绝、明确401/403停止、25秒预算和取消行为保留。沿用development_preview诊断scope，虽名称历史上包含development，但现指受限预览证据，不再表示页面已开放。

真实create_app(dev_player=False)正常API对QQ 004Yi5BD3ksoAN open返回200，/dev/player为404；最终resolver=vkeys、identity=request_bound、media=prefix_verified、scope=development_preview，关闭Lease成功。未伪造confirmed。离线正常API测试分别在页面开/关时执行vkeys、Tang，成功后不调用official；默认official及明确拒绝停止测试保留。

## 酷我301修复

同一9942644的H5接口对照：原请求或只加httpsStatus仍HTTP200/status301、data=null；加入reqId空串、plat=web、from空串后HTTP200/status200、data对象。按该组参数修复原方法，不引入第三方接口或媒体resolve。这里证明必要参数组差异有效，没有逐一声称哪个单字段是唯一根因。

真实统一歌词调用取得52行同步歌词，首时间100ms。标准化仍走原公共解析器。新增请求参数断言，旧301映射upstream_failure保留。

## 咪咕299999修复

真实resourceinfo按contentId600929000006452915返回copyrightId69089800516，双ID对应正确。旧pc/listen原生接口HTTP200，code299999、info明确为“channel不能为空”；对照同平台另一原生Host也相同，因此不是凭业务码猜版权/下架。

进一步核对详情字段，发现resourceinfo已经返回lrcUrl。真实目标d.musicapp.migu.cn，HTTP200，2148字节。现在直接使用同一稳定身份详情中的歌词地址，删除多余pc/listen请求；不需猜channel、不需搜索Session、不改变咪咕媒体链路。具体CDN、公共DNS、端口及不跟随重定向规则保留。取得66行同步歌词。

## 真实浏览器同步

扩展原verify_lyrics_browser.py的--provider/--track参数；使用真实平台Provider、正常API及原唯一audio。以下索引均零起始：

| 来源 / ID | 行数 | Seek120秒索引 | 连续Seek40/180/60秒后索引 |
|---|---:|---:|---:|
| QQ / 001e7VNQ43nv4W | 49 | 25 | 12 |
| 酷我 / 9942644 | 52 | 21 | 7 |
| 咪咕 / 600929000006452915 | 66 | 50 | 30 |

三者播放推进、暂停索引保持、中段及连续Seek、同audio重开且歌词保留均通过。人工响应另外验证翻译展示和旧请求晚到隔离，不将其当成真实译文。最初QQ运行摘要误写固定netease/284617标签，但该次输入、API及49行结果确为QQ；随后摘要改为实际参数。没有保存真实完整歌词或媒体地址。

## 回归与文件

pytest504项通过，原502项保留，新增两个页面关闭时的QQ路线组合；原不开放页面就禁用外部路线的测试按新职责改为未配置时默认official。17项Node恢复测试由已有pytest包装执行，不重复累加。四来源原verify_playback_browser.py --recover本轮均退出0，包含播放/暂停/Seek、新Lease同audio恢复、关闭410及Store/streams归零。原8受控恢复与下载并行验收亦独立运行；故障fixture缺少歌词方法引起隔离的安全500日志，未影响播放器测试，断流RuntimeError为预期。Windows偶见既有Proactor10054。

业务修改main.py、lyrics.py，验收脚本verify_lyrics_browser.py及tests/test_qq_application_routes.py、tests/test_lyrics.py。本目录一份记录。没有增加框架、依赖、来源或Resolver；没有修改DownloadManager。未重下四来源整文件，下载部分以原专项回归及受控取消/断流并行脚本验收，不冒称本期再次全量下载。

局限：当前只是有限样本与当前接口窗口，不证明长期稳定或声学精确对齐；配置仍需实际使用条件，不能以取链成功推定版权授权。本阶段未实现QRC/KRC逐字歌词；验收范围仅限歌词呈现与同步。
