# 拾音 Windows 桌面版

拾音桌面版适用于 Windows x64。它与网页版共用前端，但正式桌面程序内置构建好的界面，运行时不需要启动 Python、Node.js 或 Vite。

如果已经拿到安装包，直接运行 `*-setup.exe` 即可。以下步骤用于从源码开发或打包。

## 桌面版能做什么

- 搜索并播放酷我、QQ 音乐、网易云和咪咕的歌曲，查看可用的歌词与封面。在线播放、音质和下载是否可用，以曲目来源和当次网络条件为准。
- 在「本地和下载」里查看下载历史、导入本地 MP3 / FLAC，并离线播放已保存或导入的文件。默认下载位置为 Windows「音乐」文件夹下的「拾音」，可在设置里更改。
- 下载时可保留原格式。如果桌面构建包含转码工具，下载 FLAC 时还可选择生成 320 或 192 kbps 的 MP3。

## 从源码运行

开发机需要 Node.js、pnpm、Rust stable MSVC 工具链、Microsoft C++ Build Tools 的「使用 C++ 的桌面开发」工作负载（含 Windows SDK），以及 Microsoft Edge WebView2 Runtime。Node.js 与 pnpm 的具体版本以仓库配置为准。工具安装步骤可参考 [Tauri 的 Windows 前置条件](https://v2.tauri.app/start/prerequisites/)。

在 Windows 上，从仓库根目录使用 Git Bash 或 PowerShell 执行：

```bash
pnpm --dir web install --frozen-lockfile
pnpm --dir desktop install --frozen-lockfile
pnpm --dir desktop dev
```

## 构建 Windows 安装包

完成依赖安装后，停止开发进程或另开一个终端，再从仓库根目录执行：

```bash
pnpm --dir desktop exec tauri build --bundles nsis
```

安装包输出到 `desktop/src-tauri/target/release/bundle/nsis/`。如果只需要编译 Release 程序，可使用 `pnpm --dir desktop exec tauri build --no-bundle`。Release EXE 位于 `desktop/src-tauri/target/release/`。

### 可选的 FLAC 转 MP3

从干净的源码工作区构建时，不需要额外准备 FFmpeg。生成的桌面版仍可运行、播放本地歌曲和保存原格式，只是不提供 FLAC 转 MP3。

若要打出带转码功能的安装包，请先按 [Windows 转码工具准备](./windows-transcode.md) 校验和准备工具，再执行打包。运行时只使用随应用分发的转换工具，不搜索系统 `PATH`。
