# 旧Lab与新Core的具体行为差异

旧文件位置均在只读`C:/Code_Home/2_projects/media-lab/musicdl-lab/server/app/`；新文件在`C:/Code_Home/2_projects/musicdl-lab/server/app/`。以下行号为本期读取/修改后的源码位置，历史删除点同时给函数名。

| 行为 | 旧Lab的实际条件与位置 | 新Core的实际条件与位置 | 原因、必要性与本期处理 |
|---|---|---|---|
| 入口 | provider_adapter.py:151 resolve_candidate，168先调用第三方 | qq.py:134 resolve，统一校验身份与选项 | 新统一协议所需；保留，删除_resolve_official重复的同一校验和不用的options参数 |
| 路线顺序 | qq_fallback.py:21 resolve_priority固定vkeys→qqovo→Tang，provider_adapter再官方 | qq.py构造route_order、main.py环境变量，resolve:141按顺序 | 一个顺序入口有实际用途，保留；没有增第二套顺序配置 |
| 执行资格 | qq_fallback.py:10 access_for有效MID按应用请求范围允许；更正说明不以pay_play=1推断用户无权 | qq.py:45 enabled_external_routes构造资格，132默认只有official，141循环筛选 | 服务使用条件与顺序不同，当前任务要求保留；删除_resolve_route原本重复的available_routes判断与重复未知路由分支 |
| vkeys请求 | 原方法mid/quality，原品质列表逆序切片迭代 | qq_resolvers/vkeys.py:6，mid/quality默认14且单次请求 | 首次对应原方法14，但不复刻全部高档循环；档位请求不等于格式证明。原始功能仍保留，不改协议参数 |
| qqovo请求 | 动态deviceId、bootstrap取得key、当前会话Cookie，按query排序签名 | qqovo.py:14 sign，21 resolve，同一签名字段/顺序和请求参数 | 已有确定性向量，保留；移除只调用一次的_resolve_session层和重复check_mid。没有改签名/key来源 |
| Cookie所有权 | 原独立Session的Cookie自动管理 | 4D2独立AsyncClient又额外维护httpx.Cookies，common.request_json再次extract | 两容器表达同一会话，冗余；改为直接用独立session.cookies。common函数删除jar参数/第二次extract；退出仍关闭，不向共享QQ池写Cookie |
| URL-only协议 | qq_routes.py:126 check_payload，qq_fallback.py:33 require_response_mid=False接受request_bound | common.result:25接受URL-only，不要求mid；qq.py:158未回显结果不发布而按既有错误继续 | 协议有效与身份充分是两问题，保留分离。增加实际分发测试，证明不是尚未请求就被重复Gate拦住 |
| 身份状态 | 旧midState请求绑定/回显证据；identifier是请求MID赋值 | 原RouteResult同时保存evidence字符串与response_mid；Provider同时查evidence再查MID | 字符串可由MID是否存在推导，重复；删除存储字段，evidence:21只读推导；Provider直接判断未回显/错MID，避免多层Evidence/Publish Gate |
| 旧正式接受条件 | qq_fallback.py:47实测duration与搜索interval差不超过max(5秒,2%)，加identifier/协议检查 | qq.py:158/159要求响应MID，之后媒体探测 | 这是功能差异的关键。旧规则能排除明显错曲，不能证明同长不同版本；本任务要求证据充分，不能直接删掉身份边界。没有把时长近似当成confirmed |
| Tang选择 | qq_routes.check_payload核对song_mid，防accom/替代录音；原函数字段顺序本含accom | tang.resolve核对MID/非空元数据，完全不选accom，可额外核对预期标题/歌手 | 是已发生的版本风险，保留；不要求URL-only路线提供Tang字段 |
| 媒体探测 | 原函数AudioLinkTester后，resolve_priority再probe_media检查时长等，不完全同类 | 外部通过身份后media.verify_media一次有限读取；后续Stream是用户传输 | 没有发现新Core同一阶段重复探测。继续一次；新增测试确认成功仅一次Adapter/一次probe，不能删用户Stream验证 |
| 回退 | 旧resolve_priority继续三路失败，交provider_adapter官方；含宽泛异常处理 | qq.resolve只对超时/临时失败/无媒体按策略继续；权限/错身份停止 | 25秒统一预算、取消及明确权限停止有独立收益，保留，不用模糊异常吞掉失败 |

## 最终路径与职责数量

官方路径：QQProvider.resolve（含execute预算闭包）→_resolve_route→_resolve_official→rpc→QQ request_json→HTTP。以上为同一Provider中的普通函数，不是五层全局Service。分发函数处理四条不同协议，不是只有一条空转发，保留其测试边界。

外部路径：resolve→_resolve_route→对应Adapter.resolve→外部common.request_json→HTTP；qqovo由原两层Adapter函数降为一个。返回后在Provider检查实际response_mid，之后media.verify_media和原ResolvedMedia转换。一次请求最多涉及qq.py、对应适配器、common __init__.py、media.py四个业务文件；官方只需qq.py。Store/Lease/Stream仍由已有公共代码负责，没有为Resolver复制生命周期。

旧路径还包括provider_adapter、qq_adapter转发、qq_fallback、qq_routes的IsolatedQQRoutes/RouteTransport及运行时FunctionType依赖克隆、冻结Client/AudioLinkTester/probe_media。新工程没有这些克隆框架。不能为了再减文件把三条独立签名/请求协议合成巨型函数。

五个身份等级只是任务的语义候选，4D2实际只生成confirmed/request_bound两种。本期不保留不存在的空枚举，错配继续以错误拒绝。title/artist保留真实响应元数据供独立核验，不参与新增评分；不凭已知MID伪造标题或回显。

## 当前不能复现旧媒体的准确原因

当前应用资格未授予外部路线，因此默认根本不发三路歌曲请求；这是第一处差异。即便给服务端实例授予资格，URL-only结果会正常解析但未达到当前正式录音发布条件，仍不能取代目标版本；这是第二处差异。两者职责不同，不能合并成一个“线路不可用”状态。已消除的是同一职责在不同函数的重复判断，未以降低授权或身份要求制造历史成功复现。
