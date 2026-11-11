# 09 QQ解析器收敛

2026-11-06。完成实际函数对照和小范围代码整理，没有停在审计。业务代码三个文件净减9行：删除重复资格/输入校验，合并qqovo会话函数及重复Cookie容器；身份等级改由实际response_mid推导，避免两份状态矛盾。

保留有独立职责的三项保护：调用前服务资格、返回后的录音身份判断、HTTP媒体目标与字节检查。没有增加新Gate、评分器或全局注册表，也未把URL-only当作异常协议。允许执行的模拟路线可通过实际分发函数，确认结果只探测一次；未确认结果不冒充已确认媒体。

当前调用链为QQProvider.resolve统一输入/预算→按顺序筛选允许路线一次→协议适配→响应ID判断→媒体安全检查→原ResolvedMedia。默认仍official；三条外部Adapter都保留，但当前服务使用条件未确认，未调用歌曲API，不声称在线协议成功、线路失效或覆盖率改善。

393项pytest、17项Node、8项受控恢复场景通过；四来源真实播放、两处Seek、重开与引用释放通过。无新增依赖，无其他Provider、公共模型、Store/Lease/RecoveryPlayer修改。

具体差异和必要性见[Behavior-Diff](Behavior-Diff.md)，当前真实记录见[Verification](Verification-Resolver-Convergence.md)。后续仍需明确外部接口测试使用条件，并对URL-only资源用有权访问参考录音或人工比对补足证据；本期不把这项未完成工作包装为播放能力提升。
