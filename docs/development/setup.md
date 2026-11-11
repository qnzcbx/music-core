# 开发环境与验证

后端安装、运行和测试命令见 [server/README.md](../../server/README.md)。要求 Python 3.10+；按本项目锁文件安装依赖，不使用未锁定的额外包。Vue 前端依赖与脚本以 `web/package.json` 为准。

## 验证类型

- 日常回归：后端在 `server/` 执行 `python -m pytest`；前端使用 `web/package.json` 中定义的脚本。
- 在线来源冒烟：在 `server/` 使用 `python scripts/verify_kuwo.py`、`verify_qq.py`、`verify_netease.py`、`verify_migu.py`；有限真实下载检查使用 `python scripts/verify_download_online.py --url <Core地址>`。结果受来源和样本状态影响。
- 浏览器专项：长期脚本及用途见 [后端验证说明](../../server/README.md)。需要安装 `.[browser]` 并安装 Playwright Chromium；默认使用 Playwright 浏览器，也可设置 `$env:CHROMIUM_PATH` 或传入 `--browser`。自启动服务使用临时端口；连接现有 Vue/Core 的脚本用 `--url` 或 `MUSIC_CORE_WEB_URL` / `MUSIC_CORE_API_URL` 指定地址。
- 验证产物默认写入项目根目录的 `.runtime/verify-*/`，由 Git 忽略。历史报告和必要 JSON 证据位于 `docs/archive/`；浏览器脚本不会覆盖归档结果。

专项验收的有限样本结论不外推为全曲库覆盖率。归档中的 JSON、截图和报告是当时证据，不作为运行时配置。
