---
kind: frontend_style
name: 前端样式系统：本项目无前端 UI 代码，属于后端/CLI 库
category: frontend_style
scope:
    - '**'
---

经全面检索，本仓库未发现任何前端样式相关代码与配置。具体证据如下：

- 未找到任何 CSS/SCSS/Less/Stylus/Tailwind 配置文件（`*.css`, `*.scss`, `tailwind.config.*` 等）。
- 未找到 HTML/Jinja2 模板文件或静态资源目录（如 `templates/`, `static/`, `public/`）。
- 示例中的 `examples/web_app.py` 仅基于 FastAPI + Uvicorn 暴露 JSON REST API，并启用 `/docs`、`/redoc` 文档页面，不包含自定义 UI 或样式。
- 根目录的 `assets/imgs/` 仅包含项目架构图 PNG/WebP 图片，非样式资源。
- 所有关于 “style” 的匹配均指向视频生成提示词中的视觉风格字段（如 `"style": "cinematic realism"`），而非前端样式。

结论：PenShot 是一个纯 Python 后端/CLI 库，负责剧本到分镜的智能体工作流编排，不提供任何前端界面或样式系统。因此 `frontend_style` 类别不适用于此仓库。