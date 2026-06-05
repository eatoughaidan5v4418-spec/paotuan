# 2026-06-05 Frontend Agent

## 阶段 1：架构与脚手架

### 本阶段目标
- 新建 `web/frontend`，使用 Vite + React + TypeScript 承载新版玩家沉浸端。
- 保留旧 `web/static` 作为临时回退。
- 安装并使用 `react`、`react-dom`、`vite`、`typescript`、`motion`、`@phosphor-icons/react`。
- 接入玩家可见 API，不在主屏消费 GM hidden/debug 字段。

### 修改文件
- `web/frontend/package.json`
- `web/frontend/package-lock.json`
- `web/frontend/tsconfig.json`
- `web/frontend/vite.config.ts`
- `web/frontend/index.html`
- `web/frontend/src/main.tsx`
- `web/frontend/src/types.ts`
- `web/frontend/src/api.ts`
- `web/frontend/src/App.tsx`
- `web/frontend/src/styles.css`
- `tools/web_game.py`
- `tools/web_api.py`

### 设计决策
- 新版构建输出到 `web/static-react`，`tools/web_game.py` 在存在构建产物时优先服务新版，否则继续服务旧 `web/static`。
- 启动优先调用 `/api/app/bootstrap`，若旧后端没有该接口，前端会回退到 `/api/campaigns`、`/api/state`、`/api/logs`。
- 前端 DTO 只渲染 `visible_text`、`rendered`、`turn_meta`、`apply_report` 的公开摘要和 `state`，不依赖 `state_patch`、`tool_results`、`active_lore`、`artifact_path`。
- 主屏采用“叙事时间线 + 行动输入 + 当前场景”中心结构；GM/导出/校验放进系统面板。

### 子代理分工与结论
- Frontend Architecture Agent：确认 `/api/app/bootstrap` 需要聚合启动数据；指出 `/api/turn` 原返回隐藏调试字段，建议玩家端 DTO 强约束。
- Visual Design Agent：确认当前旧静态最大问题是中文乱码和 GM 控制台感；建议档案室 token、中文叙事字体、纸张/案卷动效。
- Interaction QA Agent：给出 Playwright 桌面/移动截图矩阵、键盘焦点、loading/empty/error/disabled 检查点。

### 验证命令和结果
- `npm install`：通过，安装 75 个包。
- `npm run typecheck`：首次发现 `valueText` 返回类型和任务 fallback 类型问题，修复后通过。
- `npm run build`：通过，产物位于 `web/static-react`。

### 未解决风险
- 当前工作区已有未提交改动，包括旧 `web/static/*`、`tests/test_web_api.py` 和部分后端安全过滤草稿；本阶段未回滚这些改动。
- `/api/config`、`/api/campaigns`、`/api/obsidian/export` 仍可能暴露本地路径，玩家端不展示，但后端合同还需要继续收紧。
- 需要用 Playwright 实测中文渲染、移动布局、按钮状态和截图。
