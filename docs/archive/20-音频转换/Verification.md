# 20 音频转换 — 阶段 20：FLAC保存方式与空间优化

## 完成结果

同一首网易云《天龙八部之宿敌》（167691），从正常Vue下载入口检测自动取得FLAC后，已完成保留原格式、MP3 320、MP3 192三种保存，并验证真实成品、本地播放和取消清理。

| 音源品质 / 保存方式 | 实际源编码 | 最终文件 | 字节数 | 时长 | 是否转码 |
| --- | --- | --- | ---: | --- | --- |
| 自动 / 保留原格式 | FLAC | FLAC | 50893686 | 263.340408秒 | 否 |
| 自动 / 节省空间 | FLAC | MP3 320000 bps | 10535750 | 263.340408秒 | 是 |
| 自动 / 更小的文件 | FLAC | MP3 192000 bps | 6321467 | 263.340408秒 | 是 |
| 高品质 / 原格式 | MP3 320000 bps | MP3 | 10535750 | 263.340408秒 | 否 |
| 无损 / 明确选择MP3 320，已有可信目标MP3 | MP3 320000 bps | MP3 | 10535750 | 263.340408秒 | 否，优先直下 |

五项均44100Hz、双声道。约节省79.3% / 87.6%空间是本样本结果，不宣称有损MP3比源FLAC品质更高。最后一项为MP3保存模式下优先选择可信MP3直下；该结果不适用于“保留原格式 / 保留无损”。请求品质为lossless，但sourceMedia实际为MP3，transcoded=false、actualMedia.lossless=false，不作为无损保存。

真实在线请求、任务阶段、源/最终媒体及ffprobe结果见 [real-saving.json](real-saving.json)。验收成品写入项目根目录下的 `downloads/`，未覆盖已有文件。只有原样保存的FLAC正式发布，其余转换的中间FLAC没有进入成品索引。

## 旧实现审计与最小改动

旧实现的转换流程仅作只读对照。其encoder_capability用shutil.which和-encoders验证libmp3lame；owned_process负责取消终止；转换使用-nostdin、-xerror、-n、协议白名单、-map 0:a:0、libmp3lame、目标码率及采样率；随后ffprobe和完整解码进度核对时长，再发布文件。复用了这些安全处理思路，没有实现独立转换调度、批量转换入口或超出本阶段范围的功能。不支持FLAC重新压缩等额外功能。

当前DownloadManager原状态是queued / resolving / downloading / completed / failed / cancelled，原下载临时名带进程PID和taskId，文件发布为同文件系统硬链接、不存在才创建。现只在同一个transfer内加入可选转换及最终验证；并发2、排队、进度、取消、重试、长度校验、安全文件名、同名序号、不覆盖、文件索引仍走原实现，没有第二个下载器。

DownloadRequest / Task兼容新增：outputMode=original / mp3_320 / mp3_192（缺省original）、expectedSourceCodec、phase、sourceMedia、transcoded、finalSizeBytes。quality仍为原音源品质；sourceMedia描述实际源文件，actualMedia描述已经验证的最终文件。转换尚未完成时不提前填充最终媒体或fileId。重试保留quality、outputMode及已确认源意图，并重新解析媒体。

## 保存意图与直接资源优先

当前选中音源已确认FLAC时，原品质弹窗内增加“保存方式”：保留原格式、节省空间MP3 320、更小文件MP3 192，明确说明MP3有损。MP3 / AAC / 未确认格式不提供转换承诺。换品质时重置保存方式；时长可读时才用时长×码率÷8估算，并标“预计”，不能估算则显示大小待保存后确认。

前端只发送固定保存枚举与codec约束，不发送服务器路径或FFmpeg参数。保留原格式且确认源FLAC时，如果最终重新解析变为其他编码就失败，不静默换成有损文件。明确请求MP3时，仅接受已确认的FLAC转换或精确目标MP3直接保存；AAC、有损MP3不同码率、ALAC/WAV等均不进入本期转换。

优先直下只查看阶段 19短缓存中同一TrackIdentity、未过期、编码为MP3且目标码率匹配的公开摘要。仅对此目标按既有品质参数重新解析一次（最多8秒），不复用缓存URL，不按歌名猜替代资源。总解析仍由25秒预算包住；未找到匹配时重新取得用户所选源媒体。明确权限拒绝不会转成普通不匹配继续绕过。没有已确认目标MP3时直接下载FLAC转换，不要求用户逐档试音质，也不遍历所有来源。

## FFmpeg调用、校验与资源

实现位置：`server/app/transcode.py`。工具由受控服务环境MUSIC_CORE_FFMPEG或shutil.which查找后解析为绝对路径，ffprobe优先同目录。使用asyncio.create_subprocess_exec参数数组，无Shell、无用户自定义参数。转换前确认libmp3lame；没有工具或编码器时检测响应给简短原因、转换选项禁用，原格式下载不调用这些工具，FastAPI启动不依赖安装成功。

转换核心：-nostdin -xerror -n、仅file/pipe协议、只读当前任务完整FLAC、仅选第一音轨、无视频、libmp3lame、320000或192000目标码率、单线程，不添加滤镜/响度/音效/声道增强。44100Hz双声道实测保持不变；MP3不支持的采样率仅做编码器必要处理，不宣称上采样提升品质。非单/双声道输入暂不支持。

下载并发2保留；额外一个Semaphore限制转换及验证同时1项。转换整体默认300秒，受原任务1800秒总预算进一步限制。输入和输出各受原1GiB上限约束；输出有FFmpeg -fs及轮询检查，超限不发布。子进程stdout有128KiB限额，stderr不向内存无限积累；不把完整音频读入Python。

转换输出只写同一受控下载目录下、当前PID/taskId的-output.part，-n不覆盖已有文件。FFprobe核对输出MP3、码率、采样率、声道、完整时长和大小，随后使用FFmpeg -xerror完整解码并核对实际out_time_us，不只相信Xing头中的时长。最终MP3验证成功后沿用硬链接原子发布，源part和输出part最后分别清理；删除其中一份失败不会跳过另一份。不删除或转换用户历史文件。

所有外部进程都直接持有、无Shell派生树；进程创建时就用shield避免“刚创建就取消”丢失句柄，超时、取消、输出超限时kill、读管道至EOF并wait。Windows无可见辅助窗口；验证了取消/超时后进程已退出，没有Proactor未关闭管道警告。启动清理只识别本实现且所属PID已退出的两类part，不扫描用户其他目录。

## 同一任务状态与通知

公共status保持原语义，下载/转换/验证均为活跃的downloading；可选phase区分downloading / transcoding / verifying / completed。转换和验证显示不确定进度，不把FLAC接收100%当成最终完成；取消按钮继续可用，轮询继续进行。

最终completed才写filename / fileId / actualMedia / finalSizeBytes；任务页显示最终大小而不是源FLAC接收量。绿色完成勾和成功通知仍以完成状态+成品文件存在为条件，只出现一次。转码失败进入原failed错误流程，不自动无限重试。phase不会变成客户端不识别的新终态。

## 实际验收与测试

真实在线主验收脚本 `server/scripts/verify_download_saving_browser.py`：隔离Core8014 / Vue5191，正常搜索167691、原弹窗选择保存方式、确认创建原DownloadManager任务；没有替换搜索、Provider或媒体。观测到转换任务resolving→downloading→transcoding→completed，taskId始终同一；前三种保存成功，普通高品质MP3直接保存、已知目标MP3优先直下成功。

下载全过程已有在线播放持续推进，唯一Audio引用不变，Playback Open没有增加。首次验收的本地文件阶段遇到测试定位器把歌名当文件名的问题；已改按data-filename精确定位，并用 `verify_download_saving_followup.py` 独立复验既有成品，无需重新下载。

后续实际本地列表播放四份MP3（两份转换、两份直下）均完成暂停、继续与中点Seek。followup又从正常Vue创建新的在线FLAC→192任务，在真实transcoding阶段点取消：任务cancelled、无fileId，目录成品前后完全一致，两份part均清理，三个已记录FFmpeg/ffprobe进程均退出，原Audio继续播放。[实际后续记录](followup.json)。

[移动端保存方式](screenshots/conversion-save-options-390-light.png)、[桌面保存方式](screenshots/conversion-save-options-1440-light.png)、[中等暗色](screenshots/conversion-save-options-768-dark.png)、[320转换阶段](screenshots/conversion-transcoding-mp3_320.png)、[192成品](screenshots/conversion-completed-auto-mp3_192.png)、[真实取消](screenshots/conversion-cancelled-conversion.png)。1440 / 768 / 390px、Light / Dark均无横向溢出，原生模态层位于播放器上方；短屏可内部滚动到确认按钮。

`verify_download_saving_ui.py` 使用明确标记的HTTP夹具验证：无编码器仍可选原格式、FLAC专属选项、切品质重置、预计大小、六种响应式主题组合、转换中无百分比、取消、失败、验证中、最终大小、一次成功通知。这些是UI受控结果，不冒充真实在线转换。

后端18项转换专项覆盖真实短FLAC两码率/原样/不覆盖、缺工具、坏工具、无编码器、损坏FLAC、禁止有损二次编码、保留源意图、已知MP3直下、下载过期后重新解析重试、转换超时/取消/磁盘错误/无效输出清理、双任务串行转换、服务关闭、子进程超时/取消/输出上限及创建期间取消。原下载中断、取消、目录失败、并发2、长度/格式/原子发布由已有下载测试继续覆盖，没有重复搭建第二套测试下载器。

前端45项通过，类型检查和生产构建通过；约517KB主包的既有500KB告警保留。后端全量607项收集，606通过 / 1原有Windows符号链接权限跳过；最后的最终元数据时机修正又以全部转换+下载69项回归通过。四来源、默认解析顺序、歌词、Lease、播放恢复和本地文件原有测试保持通过。

## 依赖、运行与剩余限制

没有新增Python/npm依赖或大型媒体框架。转换可选使用本机FFmpeg及同工具包FFprobe；后者用于最终文件结构检查，完整解码仍由FFmpeg完成。仅扩展下载请求/任务/检测响应和前端类型，没有改Provider、播放ResolveOptions或PlaybackLease协议。

常用后端没有强制停止，以免打断当前播放。加载本期后端代码后需重启目标Core并刷新前端，才能获得conversion能力和新保存参数；隔离验收服务均已收尾。实验目录无残留part。

仅支持任务下载得到的已确认FLAC→MP3 320/192；不开放任意本地文件转换、AAC二次有损转换、批量历史转码、标签/封面嵌入、响度标准化、FLAC重新压缩、假无损检测。非标准采样率/多声道的额外兼容可后续扩展，本期不能宣称全部FLAC均支持。上游资源可能变化，重新解析不符保存意图会明确失败；可访问不等于独立版权或永久下载许可，原访问限制始终保留。
