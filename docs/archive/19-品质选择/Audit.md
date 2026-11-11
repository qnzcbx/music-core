# 19 品质选择 — 修改前品质能力审计

修改前四 Provider 都拒绝非空 providerQualityId；搜索只输出歌曲候选，没有已验证品质目录。下载目前仅 purpose=download，其余与播放解析一致。完整性校验已有长度、文件头、原子发布及取消清理；音频编码和码率缺少真实解析。

| 来源 | 源码已能传入的档位参数 | 修改前真实自动媒体（有界字节） | 限制 |
| --- | --- | --- | --- |
| 酷我 | mobi 固定 format=mp3，无显式档位 | 9942644 MP3，4346545 字节 | 网页接口受拒才进入 mobi；旧实现 有 bitrate / format 请求，不代表当前档位可取 |
| QQ | vkeys quality=14；Tang 在多个媒体字段中首选；巡回寺及 official 无显式品质参数 | 004Yi5BD3ksoAN MP4，5979794 字节，编码未知 | 外部路线保持 configured_preview，请求绑定不冒充独立录音确认；明确拒绝不能降级绕过 |
| 网易云 | native br=128000；GD br=999；jfjt level=standard | 167691 MP3，4214326 字节 | native 权限拒绝停止；第三方品质字段只是请求，须验证实际字节 |
| 咪咕 | 资源目录含 rateFormats，当前按 PQ/LQ/HQ 取首个；toneFlag 已存在 | 600902000009209221 MP3，4089941 字节 | 双ID匹配、needEncrypt/freeListenType 拒绝保留；没有证据可用 SQ 不擅自开放 |

完整结果 audit-before.json。上述是实际取得地址和有界媒体前缀成功，尚不是本期完整下载证据，现有探测不提供真实码率。旧实现 只读研究了品质弹窗与下载职责、有限探测与大小证据、Provider 参数，未复制其技术说明界面或调度体系。
