# 39-B.3A：酷我媒体解析修复

日期：2026-11-05。已实现酷我自身mobi `convert_url2`普通参数路线。真实搜索→稳定ID→私有ResolvedMedia→有限字节探测闭环通过，4个录音全部取得地址且HTTP206前缀检查通过。

站内playUrl在访问首页、接受服务器正常Cookie后仍返回HTTP200、success=false、The request is illegal!，不能据此认定需要登录、会员限制或酷我整体不可访问。仅此已实测的接口级拒绝允许尝试同平台mobi；明确401/403、购买提示、超时、取消等不回退。没有引入独立第三方解析服务。

mobi直接接受明文查询参数，无需复制musicdl自定义加密工具。没有新增运行依赖；Core数据模型不变，URL与headers继续服务端私有。状态改为`implemented_sample_media_verified`，仅表示有限样本验证，不是通用可播放保证。

原96项测试保留，新增19项，合计115通过。每样本读取4096字节，总共16384字节，无整曲下载、无签名地址落盘。浏览器解码/播放、完整文件下载仍未验证。未增加公共Resolve、Store/Lease、Range代理或前端。

详见[路线对照](Kuwo-Resolve-Routes.md)、[验收记录](Verification.md)。旧项目与参考库只读，Git未提交或推送。

下一阶段39-B.3B可用这些稳定ID重新获取临时媒体，推进最小Store、Range代理、Lease与取消释放测试；真实平台可能变化，通用媒体传输测试同时准备自有合成音频fixture。不要持久化此次媒体URL，也不要将fixture播放称为酷我播放成功。本次未自动开展39-B.3B。
