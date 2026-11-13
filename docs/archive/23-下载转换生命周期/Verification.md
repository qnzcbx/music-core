# 下载转换生命周期修复

2026-11-13。沿当前归档编号建立23。

## 调用链与失败定位

DownloadQualityDialog → useDownloads/API → downloads router/DownloadManager → 四来源统一 resolve(identity, ResolveOptions(purpose=download, providerQualityId)) → 目标验证和流式写盘 → 源检查 → transcode → 输出验证 → 硬链接原子发布 → 文件索引/轮询/通知。QQ 的既有解析顺序和候选选择保持原样。

现存告五人《温蒂公主的侍卫》FLAC为56,510,370字节（界面53.9MiB），SHA256为 ec74e029c2440422d843ecf19e85f0853395f45ca3faaf2f5556a743860c2ee5。FFprobe识别为FLAC、48000Hz、双声道、257.852417秒，但不能据此证明解码完整。

用该文件只读复现旧转换调用：能力检测成功、FFprobe成功，**FFmpeg编码调用实际启动后因解码输入失败退出**。Windows returncode=3199971767（有符号-1094995529），stderr包含 `invalid sync code`、`invalid frame header`、`decode_frame() failed`、`Decoding error: Invalid data found when processing input`。独立的完整解码也返回相同错误。因此该本地样本的问题属于输入媒体损坏，不是已经证明MP3输出校验失败，也不是libmp3lame缺失。原有文件保持原样，不覆盖、删除或尝试修补。

历史任务日志没有保留stderr：原 owned_process 直接丢弃stderr，所有非零退出都抛 upstream_invalid_response；源检查仅有长度、前缀和容器，convert_flac内部的FFprobe也只读结构元数据。任务phase在整个convert_flac调用期间均为transcoding，只有成功返回才转verifying，故无法准确归因。上述证据是现存样本的可重复本地复现，不能冒称已找回截图对应任务的历史日志、旧签名URL或服务端实时任务。

## 修改

- 为转换输入增加 source_verifying：FFprobe选择音轨，随后FFmpeg严格完整解码，检查退出码、解码末尾进度和时长。损坏/截断源在编码前失败，errorCode=source_verification_failed。
- convert_flac保留既有编码参数、目标码率、采样率规则、输出尺寸/码率/时长校验及完整解码要求；新增阶段回调区分transcoding和output_verifying。原正则同时兼容Windows CRLF，不降低校验门槛。FFprobe只选择音频，避免附带封面被误算为第二音轨。
- ConversionError携带阶段与原始异常；编码或输出校验错误映射conversion_failed，文件写入错误仍为file_io_error。缺工具/编码器提示转换失败，不误认源损坏。公共任务新增sourcePreserved布尔值，保留原MP3请求、失败阶段和实际FLAC元数据；不假装MP3完成。
- stderr持续排空，只保留末尾8KiB，不无限积累。非零退出日志记录退出码和固定诊断短语；下载日志记录taskId、phase和错误类别，不记录命令参数、完整路径、签名URL、Cookie或Token。取消/超时继续kill、排空管道并wait。
- 转换失败时先清理不完整MP3，再次完整验证源FLAC。验证通过才使用原硬链接发布机制保底，任务仍failed。发布失败/磁盘错误/非法目录不强行保底。用户取消不进入保底。
- 本进程有相同稳定身份及未变化文件指纹的已保存FLAC时，复制到当前任务私有part后完整验证、直接转换，不调用Provider。原文件不移动、不修改。转码失败引用原文件，串行转换下并行任务保底还比较完整字节，避免重复发布同一份源。不同录音不按歌名或文件名匹配。
- 前端复用原Composable和轮询；失败保底也刷新本地列表。任务及通知显示“转换失败，已保留 FLAC”；本地列表展示真实FLAC，可用原入口播放。移动端原先隐藏文件状态，现补充保底提示。旧任务仅显示“已发起重试，请查看新任务”，不声称重试成功。没有修改播放器底栏。

## 验证结果

后端全量：614 passed / 1原有Windows符号链接权限skip；前端46/46通过，类型检查及Vite生产构建通过。无新增依赖。

扩展原 test_transcode_downloads.py：合法源MP3 192/320、原格式、不覆盖、工具/编码器不可用、模拟启动文件缺失、非零退出诊断脱敏、真实编码后输出验证失败、损坏/截断源阻止编码、取消/超时/磁盘故障、清理、相同源保底复用、再次转换成功及并行保底不重复。原下载、品质、文件索引、本地播放、Provider、Lease及播放器测试保留通过。

真实只读文件复验：QQ样本完整解码失败；已有网易云《天龙八部之宿敌》50,893,686字节、SHA256 5deba3a3bdb56473db9d8fcbcd80c38fb9a12ec9af5babd754aae693934bfe33，完整解码成功，转192与320分别为6,321,467和10,535,750字节，输出通过FFprobe及完整解码。产物仅在.runtime/verify-transcode，不写用户音乐目录。原格式FLAC成功和任务保底使用自有合法短音频受控测试证明；不把损坏QQ样本当成可保底成功。

复用现有 verify_download_saving_ui.py，通过其--url接入现有Vue，未创建固定端口/动态exec的新框架。HTTP夹具覆盖下载、转换、源/输出阶段、取消、失败通知、FLAC保底、本地列表与重试；实际自生成FLAC通过原客户端本地入口由Chromium Audio解码播放，查看了任务失败保底和本地播放截图。HTTP响应为受控夹具，不冒充新的QQ在线下载。截图位于忽略的.runtime/verify-download-saving-ui/screenshots。

原 verify_download_browser.py另证实取消/失败不影响在线Audio：同一实例持续从1.023629秒推进到2.073398秒，paused=false、error=null；Playback Open、Lease不变，连接关闭，无残留成品或MediaStore记录。

## 限制与运行

没有重新下载QQ在线媒体、改变路线或凭标题重建歌曲身份；外部源是否已更换资源未在本次证明。真实样本诊断见real-local.json。

现存文件索引只有fileId/文件信息，没有跨重启的稳定歌曲身份。故本地复用限定当前进程仍有对应任务记录、且指纹有效的文件；历史匿名文件不猜身份，也不引入数据库。源验证需要可用FFmpeg/FFprobe；缺工具无法证明新源完整性时，不将其标为已验证保底。服务总任务预算到期会按原取消/清理路径终止，不能超出预算无限执行保底。

普通原格式下载保留既有传输/前缀检查机制；完整解码作为本期转换准入和保底依据，不把所有历史原格式FLAC重新认证为有效。后端代码需重启目标服务才生效，本次没有自动停止用户正在使用的Core或中断播放。未触碰用户现有音乐文件。
