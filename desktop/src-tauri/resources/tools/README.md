# 可选桌面转换工具

Windows 安装包从此目录映射 `ffmpeg.exe`、`ffprobe.exe` 到安装目录的 `tools/`。
执行 `desktop/scripts/prepare-transcode.ps1 -FfmpegDirectory <FFmpeg 根目录>`，复制工具及上游 LICENSE、README，并检查 libmp3lame。
二进制不进入 Git。无工具时仍可构建并保存原格式，接口不开放压缩选项；运行时不搜索开发机 PATH。
本轮打包使用 Gyan FFmpeg 8.1.2 full GPL v3；对应源码位置见随包 FFmpeg-README.txt。
