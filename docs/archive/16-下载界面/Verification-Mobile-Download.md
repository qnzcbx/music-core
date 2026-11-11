# 16 移动下载页面 — 验收记录

## 移动下载页横向溢出与触屏反馈修复

根据用户“下载页怪异问题.png”在常用 Vue / Core 只读复现：390px 视口中 .app-content 的 clientWidth 为 390、scrollWidth 为 396；每个保存歌曲行宽 358、滚动宽 380。根因是隐藏的 accessible-actions 按钮继承了普通按钮 padding、border 和 min-height，声明 1px 后实际仍占 22×40px，定位在行右边界外。修复按钮本身的最小尺寸、内边距、边框和定位，隐藏盒保持在行内；不通过给页面强制 overflow-x:hidden 掩盖问题。键盘 focus-visible 时恢复真实按钮尺寸及菜单功能。

触屏补充独立的瞬时按压反馈（仅组件交互状态，不属于播放状态）：pointerdown 高亮，pointerup / cancel / leave / contextmenu 清理；当前歌曲和打开菜单仍有行背景。保留手机纯文本歌曲列表、长按菜单和现有本地播放链路。桌面 Hover / 键盘焦点继续有效。

真实 Chromium touch context / CDP 触点验证：320、375、390、600、768、1440px 的 Light / Dark 中，内容区和每个歌曲行的 scrollWidth 均不超过 clientWidth；390px 实际为 390 / 390。超长文件名省略不撑宽；触摸保持时行具有按压 class 且计算背景等于选中背景；松开后真实本地歌曲播放、再次轻触暂停；键盘 Tab 后文件操作按钮恢复可见、Enter 打开菜单，聚焦时仍无横向溢出。页面异常为空，没有删除用户歌曲或写入下载文件。

前端 41 项测试、vue-tsc / build 通过；保留既有主包大小告警。[390px Light](screenshots/mobile-download-files-390-light.png)、[390px Dark](screenshots/mobile-download-files-390-dark.png)、[触屏按下反馈](screenshots/mobile-download-touch-pressed.png)。只修改 DownloadItem.vue 及本记录，未自动提交 Git。
