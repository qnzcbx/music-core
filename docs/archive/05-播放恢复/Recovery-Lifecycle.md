# 05 播放恢复 — 恢复生命周期与所有权

## 当前关系

开发页创建一个RecoveryPlayer，持有唯一HTMLAudioElement、稳定identity、当前本地session、bookmark、desiredPlaying、automaticUsed和generation。后端仍只处理解析/存储/租约/字节传输，不保存currentTime、playing、volume。生产KuwoProvider、路线优先级、媒体模型、MediaStore TTL300秒、Lease180秒及清理间隔30秒均未改；页面仍每60秒续租。

先前页面没有保存稳定身份和书签；audio.error不能直接告诉它HTTP403/410，renew则能观察本地会话不存在/过期。Stream在上游404/410报告失效、403报告权限，响应头后的断流只能终止连接。新协调器利用这些已有语义，不添加状态查询、请求历史或恢复专用接口。

状态流程：idle→opening→positioning→ready；失败到error，自动播放受阻到blocked，暂时续租断网到network。恢复时opening表示“重新获取媒体”，positioning表示“恢复播放位置”。状态只影响单首开发播放，不是全局音乐会话架构。

## 书签和用户意图

timeupdate/seeked在有当前会话、readyState>=1、没有error、没有未完成seek且不处于重绑时更新bookmark。错误/emptied不能把旧书签变成0；用户请求但尚未完成的远端seek也不是有效书签。因此远端seek失败后可能恢复到此前有效播放点，而不是把未成功的目标时间当成功位置。

desiredPlaying独立于audio.paused：正常playing/pause事件与显式页面按钮维护，错误导致的自动暂停不能直接当用户暂停。内部load/pause由binding标识隔离；恢复中页面暂停按钮仍立即改意图。用户停止清空当前identity与session、暂停并移除src；不会保留“稍后自动播放”的意图。

重新打开前保存时间、音量、静音、速率；如果旧流仍可播放，在绑定新媒体前再取一次有效时间及属性。使用稳定identity调用既有POST playback/open，核对返回identity及同源本地streamUrl。等待metadata，再把书签夹到0到duration-0.1之间；设置currentTime后等待seeking结束并核对误差<=0.5秒，最长12秒。未成功就明确失败并暂停，不假装已恢复。

保留音量/静音/速率，按恢复完成时用户最新播放意图决定play或pause。NotAllowedError只显示手动继续，已恢复会话和位置继续有效，不消耗新的Resolve。恢复期间用户暂停引起play的AbortError不被误当媒体坏掉。

## 自动恢复入口与次数

1. renew对当前会话返回404/410，视为已知本地会话失效，可自动恢复一次。
2. audio.error code1（用户中止）不恢复；code3（解码失败）只给手动入口。
3. 对其他MediaError用当前streamUrl做一次HEAD，复用现有媒体API诊断。401/403/415/400/422不自动重新解析；code4且HEAD成功也视为格式/源支持问题，不默认换URL。
4. 若HEAD表明失效、网络失败或不能确定，可以由一次受限open验证。不创建HEAD轮询，不把所有error无限转成Resolve。

waiting/stalled没有自动恢复处理。重复错误/重试共享当前operation；一次逻辑选择只允许一次自动恢复，恢复后再次失败不递归。明确手动点击可再做一次open，但不会额外赠送自动重试；重新选择歌曲才重置自动预算。

## 并发与Lease释放

generation在停止/切歌时递增。每次异步操作绑定其世代与operation对象；在HTTP返回、metadata/seek完成和play结果之后确认仍有效。stop会abort本地metadata等待，旧结果不能覆盖后续选择。

**打开会话的fetch故意不因停止而abort。** 后端可能已创建Lease，若仅丢弃fetch就无法知道应该关闭哪个新能力。协调器接收晚到响应后检查世代，废弃会话立刻close；已采用但停止/切歌时失效的中间会话也清理。仅AbortController取消媒体等待，不把UI取消当作服务器解析工作一定取消。

恢复成功：新会话就绪并定位后关闭旧Lease，保留新Lease。失败：关闭本次fresh及旧Lease，清空src/session但保留稳定identity与书签供手动再试。close幂等；重复close不释放新会话。权限/格式判断不自动创建新资源，用户仍可主动停止原会话。

正常读取中断的stream引用与Lease仍独立，由原代理finally释放；没有在恢复协调器里管理HTTP字节引用。网络断开致close无法送达、标签页崩溃或整个页面在open返回前销毁时，仍需后端TTL兜底；客户端无法承诺这种情况下即时回收。没有localStorage或媒体字节缓存。

## 测试与生产隔离

自有WAV由标准库生成，仅测试脚本注入MockTransport/Provider替身与目标校验替身；生产目标域名白名单、DNS校验、Kuwo优先级和应用配置不变。不提供故障注入API或请求观察接口。测试脚本只记录事件类别、比较结果和数量，不保存URL、Cookie或真实能力值。
