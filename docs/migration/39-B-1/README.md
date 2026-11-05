# 39-B.1：独立后端基础完成

日期：2026-11-05。本期在用户已初始化main分支的仓库中新增后端，未重建.git、未覆盖已有业务文件、未提交或推送。

实际交付：独立venv和pyproject；异步MusicProvider协议；稳定身份、元数据、私有媒体/公开视图、下载选项、队列条目及租约数据契约；四来源配置校验/降级；安全错误映射；56项离线测试；真实Uvicorn进程HTTP验收。

当前仅提供GET `/api/health`、`/api/providers` 和FastAPI内置文档/OpenAPI。默认顺序kuwo/qq/netease/migu，默认选择kuwo；`implementationStatus=not_integrated`，所有能力false。健康检查表示本服务和配置状态，不探测平台在线状态。

Python是第一阶段复用平台经验的低成本选择，当前并未导入musicdl。未来用同样JSON/HTTP语义替换内部实现，不将Python对象成为协议。

未迁移：SSE、真实搜索/解析、Range代理、完整store/Lease、single-flight、预解析、歌词、下载/转换、前端和旧实验。模型存在不意味着这些服务已经实现。

启动和测试见[后端说明](../../../server/README.md)（正确入口也可从项目根进入server）；架构见[所有权与契约](Music-Core-Architecture.md)，来源见[迁移映射](Migration-Map.md)，实测见[验收记录](Verification.md)。

建议首次提交由用户验收后执行：

```bash
cd /c/Code_Home/2_projects/musicdl-lab
git status --short
git add .gitignore README.md server docs
git diff --cached --stat
git commit -m "建立独立后端与 Music Core 基础契约"
```

本期未自动执行这些命令。
