# Windows 桌面转码工具准备

FLAC 转 MP3 是拾音 Windows x64 桌面版的可选功能。不准备转码工具时，按[桌面版指南](./desktop.md)直接从源码运行或打包即可，仍可播放本地歌曲和保存原格式。

## 构建使用的工具包

当前准备脚本锁定一份已验证的 Xiragi 纯音频构建。工具压缩包、EXE 和安装包不随源码提交。如果没有下表所对应的 ZIP，可以向项目维护者获取；没有该文件时可以照常构建不带转码工具的版本。

- 已验证的 ZIP 文件名为 `ffmpeg-master-latest-win64-lgpl-audio.zip`。脚本以 SHA-256 校验内容，不以文件名判断版本。
- [Xiragi 构建脚本](https://github.com/Xiragi/FFmpeg-Audio-Builds/tree/8af875620b8aa273a471dc59a7981d6affd0a92f)固定在提交 `8af875620b8aa273a471dc59a7981d6affd0a92f`。
- FFmpeg 版本为 `N-128274-g83572f1315-20261101`，对应 [FFmpeg 源码提交](https://github.com/FFmpeg/FFmpeg/commit/83572f1315)。实际构建参数可用 `ffmpeg.exe -buildconf` 查看。

| 文件 | 当前脚本期望的 SHA-256 |
| --- | --- |
| ZIP 工具包 | `fc99b877603e7f4cec61a825d738eeb2cf4bbffa378cc663517600ddbd7c1c61` |
| `ffmpeg.exe` | `838e351efcf53daf22a054fa5c75305d0337a3f602ecff0c9afc5e5314271115` |
| `ffprobe.exe` | `16a4f492cdc7c6138de06c286fdfe12458181a7f04b49658d72559d24e807152` |

### 上游公开附件不是当前脚本的输入

[Xiragi 的日期版发布页](https://github.com/Xiragi/FFmpeg-Audio-Builds/releases/tag/autobuild-2026-11-01-14-17)列出了 [带版本号的 Windows x64 静态附件](https://github.com/Xiragi/FFmpeg-Audio-Builds/releases/download/autobuild-2026-11-01-14-17/ffmpeg-N-128274-g83572f1315-win64-lgpl-audio.zip)，记录的 ZIP SHA-256 为 `eefb57ee5a08d8c1744883467a6c26b2e810a6f81b786ded4a61c957f9551e6d`。它与上表锁定的 ZIP 不同，不能直接替换。重命名不会改变哈希。如果日后改用这个公开附件，应先重新核对归档、两份二进制和许可证，再验证转码及成品校验流程。

## 准备工具并打包

在仓库根目录打开 **PowerShell**，把下面的路径替换为你手上的已验证 ZIP。脚本先校验 ZIP，再在临时目录解压，核对两个 EXE 并检查 `libmp3lame`。全部通过后才写到 `desktop/src-tauri/resources/tools/`，同时准备 `FFmpeg-LICENSE` 和 `FFmpeg-README.txt`。

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $archive = 'C:\path\to\ffmpeg-master-latest-win64-lgpl-audio.zip'

    & ./desktop/scripts/prepare-transcode.ps1 -FfmpegArchive $archive
    if (-not $?) { throw '转码工具准备失败，已停止打包。' }

    pnpm --dir desktop exec tauri build --bundles nsis
    if ($LASTEXITCODE -ne 0) { throw 'Windows 安装包构建失败。' }
}
```

校验失败时不要另行运行打包命令。资源目录可能仍留有上次的工具。如果只想在隔离目录试运行准备脚本，可以使用 `-Destination`，但归档的校验规则不变。

Tauri 将准备好的资源映射到安装目录的 `tools/`。应用运行时从自身资源目录查找 `ffmpeg.exe` 和 `ffprobe.exe`，不依赖系统 `PATH`。

## 验证范围

当前锁定的工具包已通过样本 FLAC 转 MP3、成品完整解码和样本数检查。准备脚本也验证过会拒绝哈希不符的 ZIP。上述结果不等同于用新生成的安装包完成安装和转码验收。
