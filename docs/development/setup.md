# 开发环境与验证

后端安装、运行和测试命令见 [server/README.md](../../server/README.md)。要求 Python 3.10+；按本项目锁文件安装依赖，不使用未锁定的额外包。Vue 前端依赖与脚本以 `web/package.json` 为准。

## 验证类型

- 日常回归：后端在 `server/` 执行 `python -m pytest`；前端使用 `web/package.json` 中定义的脚本。
- 在线专项：`server/scripts/verify_*.py` 会访问真实来源，结果受平台与样本状态影响；使用前阅读脚本参数及其对应归档报告。
- 浏览器专项：部分脚本要求可用 Chromium/Playwright。示例命令使用 `$env:CHROMIUM_PATH` 指定本机浏览器可执行文件；未配置时可按脚本参数使用 Playwright 默认浏览器。

专项验收的有限样本结论不外推为全曲库覆盖率。归档中的 JSON、截图和报告是当时证据，不作为运行时配置。
