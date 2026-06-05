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
- `npm install -D @playwright/test`：通过，用于本地截图和交互审计。
- `python tools/web_game.py --no-open --port 8765`：已有本地服务响应，确认返回新版 `web/static-react/index.html`。
- Playwright 桌面/移动截图审计：通过，输出到 `output/ui-check/react/`；覆盖 `1440x900`、`1024x768`、`390x844`、`360x740`。
- Playwright DOM 审计：通过，四个视口均未检测到乱码 token、无横向溢出、行动输入可见且可聚焦、控制台无错误。
- Playwright 交互审计：通过，空行动提交按钮 disabled，输入后 enabled，系统抽屉可打开，行动输入 focus outline 为 `2px solid`。

### 未解决风险
- 当前工作区已有未提交改动，包括旧 `web/static/*`、`tests/test_web_api.py` 和部分后端安全过滤草稿；本阶段未回滚这些改动。
- `/api/config`、`/api/campaigns`、`/api/obsidian/export` 仍可能暴露本地路径，玩家端不展示，但后端合同还需要继续收紧。
- Playwright 截图文件位于被忽略的 `output/` 下，作为本地验证证据，不纳入提交。

## 阶段 2：滚动锁定修复

### 本阶段目标
- 修复桌面端长日志时页面被固定在中段、无法上下滑动、行动栏不可达的问题。

### 修改文件
- `web/frontend/src/styles.css`
- `web/frontend/src/App.tsx`
- `web/static-react/index.html`
- `web/static-react/assets/index-D3CIFOL9.css`
- `web/static-react/assets/index-lCuny7QR.js`

### 设计决策
- 根因是 `.archive-app` 使用 `max-height: 100dvh` 和 `overflow: hidden`，真实内容高度超过 19000px 时被外壳裁切。
- 桌面端改为页面级滚动：`.archive-app` 不再裁切，左右档案栏使用 `position: sticky` 和各自内部滚动。
- 行动输入栏改为桌面和移动统一 `position: sticky; bottom: 0`，保证长日志中随时可达。
- 历史日志首次载入不再自动 `scrollIntoView` 到底部；只在 pending 回合生成时滚动到底。

### 子代理分工与结论
- 主代理按 systematic-debugging 复现并采集 DOM 证据：修复前 `.archive-app` `clientHeight=1110`、`scrollHeight=19102`、`overflowY=hidden`，行动栏 top 超过 15000px。
- 本阶段未再次派发子代理，问题范围集中在布局 CSS 和一次自动滚动副作用。

### 验证命令和结果
- `npm run typecheck`：通过。
- `npm run build`：通过，新产物哈希为 `index-D3CIFOL9.css` 和 `index-lCuny7QR.js`。
- Playwright 2048x1110 复现脚本：通过，初始 `scrollY=0`，文档可滚动，行动栏位于视口底部，左右栏 sticky。
- Playwright 桌面 1440x900 与移动 390x844 滚动审计：通过，主叙事区域滚轮后 `scrollY=600`，无横向溢出、无乱码 token、行动栏可见、控制台无错误。

### 未解决风险
- 旧 `web/static/*` 仍有未提交改动，本阶段没有触碰或提交。
- `output/ui-check/react/` 内有本地截图证据，按仓库忽略规则未提交。
