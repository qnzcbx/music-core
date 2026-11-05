# 咪咕身份与Provider

## 本地源码依据与执行顺序

冻结只读依据：`C:/Code_Home/2_projects/media-lab/references/musicdl-master/musicdl/modules/sources/migu.py`，MiguMusicClient（27行）、搜索构造（46行）、响应解码（60行）、原生解析（68行）、搜索编排（101行）。该文件自带响应解码，没有专用miguutils或第三方Resolver函数链。只调查咪咕相关调用，没有复制Client、导入musicdl或升级冻结库。

冻结搜索先请求search_all.do，对每个结果调用原生解析，再用AudioLinkTester探测，只保留有效媒体。原生解析必须有contentId和copyrightId，合并rateFormats/newRateFormats/audioFormats，按目录声明大小从高到低尝试；跳过Z3D；取链失败或探测不通过再尝试后续格式。无第三方替代路径。

冻结实现还会在响应没有url时合成listenSong.do地址并附带固定userId，并把URL路径MP3_128_16_Stero改为MP3_320_16_Stero。新工程不迁入这两个分支：使用平台实际返回地址与实际返回档位，避免把猜测地址或路径变化当成授权及品质证据。

旧实验只读依据：`server/app/migu_adapter.py`及`provider_adapter.py`。旧metadata适配已分离搜索，但将双ID与格式目录留在候选原始数据中。configure_official对原函数的内存AST副本移除合成地址及路径改写；resolve_official只接受LQ/PQ/HQ/SQ，核对返回song的双ID，拒绝HLS，补充错误分类。它不是第三方解析，仍依赖搜索上下文，没有实现单个contentId重建。

## 咪咕身份字段与用途对照表

| 字段 | 实际出现位置及示例 | 确认用途 | 新Core处理 |
|---|---|---|---|
| contentId | 搜索、resourceinfo、取链song均有；600929000006452915 | 平台资源ID；冻结SongInfo.identifier；取链contentId/lowerQualityContentId；能单独重新查询详情 | TrackIdentity.platformId，规范正数字字符串，最长32位 |
| copyrightId | 搜索、详情、取链song；69089800516，也有6005861N5Z8 | 原生listen取链的独立版权资源参数；原歌词接口也使用 | 每次由详情重建，严格核验，不进入稳定身份 |
| songId | resourceinfo返回1140705008；本次搜索未给songId | 平台另一个歌曲目录标识；当前搜索/取链主链不消费 | 不采用，不猜测与contentId的等价关系 |
| 搜索id | 搜索有该字段 | 本次未验证其跨接口恢复语义 | 不作身份，不拿结果下标替代 |
| resourceType | 搜索、详情与格式目录；LQ可为3，PQ可为2 | 资源类型参数，不是歌曲ID；取链必须使用所选目录项值 | 仅Provider本次局部上下文 |
| formatType / audioFormatType | 目录formatType及取链data.audioFormatType | 请求档位与实际返回档位；两者不能混同 | 请求按目录PQ→LQ→HQ选首个支持项；公开qualityId只采用响应给出的普通档位 |
| albumId、封面、lrcUrl等 | 专辑和独立资源引用 | 元数据或歌词资源，不是录音身份 | 仅必要搜索展示字段；本期不做歌词 |

真实详情关系：

| contentId | copyrightId | songId | 歌曲 |
|---|---|---|---|
| 600929000006452915 | 69089800516 | 1140705008 | 一场雨的瞬间（电影《伞少女》插曲） |
| 600919000009441501 | 60078707370 | 1140266537 | 徒然梦 |
| 600929000002040501 | 6005861N5Z8 | 1140225474 | 心有所向（《经典咏流传·正青春》主题曲） |
| 600929000002040505 | 6005861N5Z9 | 1138367354 | 超市 |

contentId的选择同时有冻结源码和真实详情/取链回显依据。copyrightId实际含字母，而既有咪咕TrackIdentity为数字ID，不能直接互换。没有因标题相同或copyrightId相同而合并不同contentId；离线测试专门覆盖该不变量。

本期四首不同录音不构成全曲库字段基数证明。同曲不同版本是否总有不同contentId、一首作品是否总只有一个copyrightId，尚未穷尽实测；不把作品、录音、版权目录视为同一层身份。平台当前详情返回的精确对应关系是取链依据，不承诺ID永久不变。

## Provider / Resolver依赖关系

| 路线 | 实际归属、输入 | 原库作用与条件 | 本期处理 |
|---|---|---|---|
| search_all.do | 原生c.musicapp.migu.cn；text/pageNo/pageSize/isCopyright/sort/searchSwitch | 元数据搜索，随后原库逐首取链 | 使用，只做元数据，不按可播性过滤 |
| resourceinfo.do | 原生同域；resourceId=contentId、resourceType=2 | 冻结咪咕Client未使用该接口 | 本期新增并真实验证，按精确稳定ID重建copyrightId与格式目录 |
| listen-url/h5/v2.4 | 原生同域；双ID、resourceType、netType、toneFlag、scene、lowerQualityContentId | 默认原生格式循环；响应可能混淆 | 使用目录中普通档位，仅一次取链；无URL或拒绝时不扩散回退 |
| 合成listenSong.do | 原生app.pd.nf.migu.cn；双ID、toneFlag等及固定userId | 原URL缺失时合成候选地址 | 不采用，不迁入账号参数，不猜地址 |
| PC listen/v1.0及lrcUrl | 原生app.c.nf.migu.cn接口及平台返回歌词引用 | 原媒体成功后补歌词 | 不采用，本期无歌词能力 |
| 第三方Resolver | 冻结咪咕类没有此链 | 不存在QQ/网易云式函数列表 | 没有新增第三方取链或在线扫描 |
| 旧实验兼容 | 原生方法内存AST适配 | 移除合成/改路径、限制格式、细化错误 | 仅学习边界，新Provider独立异步实现，无AST执行 |

接口归属根据实际请求目标及冻结调用点确认，不因函数名含official就假设成功；媒体主机与API域也分开管理。

## 搜索与元数据映射

`POST /api/search` → provider_for → MiguProvider.search → GET `/v1.0/content/search_all.do` → SongCandidate。

请求text为去空白关键词，pageNo从1开始，pageSize=limit（1–10），isCopyright=1、sort=1；searchSwitch保留冻结构造器实际URL编码的字典文本，开放song/tagSong/bestShow。cursor与limit绑定，最多10页。totalCount真实为数字字符串，按严格数字解析；以contentId页内去重，不按名称去重。

name/songName→title，singers/singerList的name→多歌手，album或albums[].name→album，imgItems最后一个img或img3/2/1→cover，平台相对图片以d.musicapp.migu.cn补全。duration若为有限非负数字则按秒映射；真实搜索没有该字段，20条都保持durationSeconds=null，不在搜索时额外逐首请求详情。详情length为时分秒文本、取链song.duration为秒；首样本分别00:03:26与206，浏览器实际206.4秒，未把毫秒当秒。

## 按身份重建与取链

`POST /api/playback/open` → resolve(identity) → GET resourceinfo.do → 核验唯一resource.contentId → 获得copyrightId/目录 → GET listen-url/h5/v2.4 → 核验data.song两个ID → ResolvedMedia → 既有Store/Lease/Range。

目录选择PQ优先，缺少时选LQ，再HQ；仅使用平台实际给出的resourceType，不猜测格式目录。参数为contentId、copyrightId、resourceType、netType=01、toneFlag、scene空串、lowerQualityContentId=contentId。不会在某个档位权限拒绝后试图解锁其他资源。明确加密标记needEncrypt非零、不支持的返回档位、freeListenType非零或HLS/DASH地址均拒绝，不做试听拼接或DRM处理。

必须取得单条精确详情，且取链回显同一双ID；错配、缺失ID或不同录音直接拒绝。不通过歌名搜索替代，不保存双ID缓存或原始搜索JSON。每次resolve局部上下文在返回后丢弃。真实browser流程未调用search；关闭旧Lease、更换Provider对象再open成功。两个独立脚本进程启动各自新服务后均能只凭contentId打开，说明当前无进程内搜索状态依赖。

取链接口和元数据无明确可采信的媒体过期时间，validUntil=None；不从URL或响应version字段推断TTL。size/codec/container/contentType在Provider阶段保持未知，不拿目录里可能存在单位差异的size推算字节。qualityId只采用实际data.audioFormatType，当前实测PQ；真实MP3格式和文件大小由独立有界字节探测确认。

## 请求上下文、协议解码及安全

普通上下文：UA、Origin/Referer=h5.nf.migu.cn、ua=Android_migu、version=6.8.8、channel/subchannel=014021I；listen额外birth=h5page、signature=1、Content-Type。它们是公开客户端协议参数，不是登录身份。本期匿名成功，不支持或保存Migu Cookie/token，也不复用QQ或网易云私有上下文。

响应若signature=1或以AB CD 01开头，读取第四字节seed，按平台公开循环字节偏移规则恢复JSON。该规则仅是API响应封装，不处理媒体字节，不是DRM密码学；留在MiguProvider，使用标准库即可。固定明文/二进制测试向量、非法头、截断、非法JSON及HTTP响应集成均有离线测试，不引入通用加密库。

显式httpx.Request避免共享客户端Cookie/默认认证头合并；共享连接池，底层连接5秒/读12秒、每个API请求总时限20秒、响应最多2MiB、禁止自动跟随API重定向，无无限重试。超时、取消、解码失败均关闭响应。

HTTP401/403或明确业务401/403→access_denied；404/详情空列表→track_not_found；200但成功结构中url为空→media_unavailable；非成功业务码→upstream_failure；结构/ID错误→upstream_invalid_response。错误DTO不含平台原始消息、URL或请求参数。

媒体只允许本期实际freetyst.nf.migu.cn的精确主机名，不接受其任意子域、其他migu.cn主机或任意URL。仍逐跳检查重定向、公共DNS地址和端口；跨域移除私有上下文，浏览器Cookie/Authorization不透传。既有DNS预检查未绑定实际连接IP的局限照实保留，不为本期改造整个网络层。
