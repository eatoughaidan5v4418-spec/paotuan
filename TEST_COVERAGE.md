# Paotuan 项目测试覆盖报告

> 验证日期: 2026-06-02
> 性质: 本轮可信验证快照
> 正式支持范围: `campaign/`, `xianxia_campaign/`

## 一、验证命令

```powershell
python validate_project.py
# [OK] All checks passed

python validate_project.py --root xianxia_campaign
# [OK] All checks passed

python -m unittest tests.test_web_api
# 25 passed

python -m unittest tests.test_architecture_hardening
# ran=30, failures=4；当前 bundled Python 缺少 PyYAML，涉及 YAML/CLI 子进程的 4 项失败；其余 26 项通过
```

## 二、自动化测试

| 测试文件 | 数量 | 覆盖范围 |
|----------|------|----------|
| `tests/test_architecture_hardening.py` | 30 | apply_patch、run_turn、zone_validator、CLI smoke、校验器、文档一致性、API runner 世界时钟提交 |
| `tests/test_visibility.py` | 12 | 可见性隔离、记忆图谱、visibility evidence、interpretation provenance |
| `tests/test_web_api.py` | 25 | Web API、API turn、worldgen、可见状态过滤、私有 clock 隔离 |
| **总计** | **67** | **当前环境已定向验证；完整 pytest 需 pytest + PyYAML 环境** |

## 三、关键回归保障

| 风险 | 当前保障 |
|------|----------|
| NPC 记忆越权写入 | 缺少或不匹配 `visibility_evidence` 时拒绝写入 |
| NPC 认知链悬空 | interpretation 的来源记忆不存在时拒绝写入 |
| consolidation 调用漂移 | 覆盖 rerank 与回合提交路径 |
| run_turn smoke 污染真实战役 | 临时副本隔离测试 |
| `/api/state` 泄露隐藏时钟 | 私有与 secret world clocks 过滤测试 |
| Web API 状态回写 | `tests/test_web_api.py` 25 项通过 |
| `normalize_patch` 写主战役状态 | 定向回归通过 |
| API runner 时钟提交缺审计字段 | 定向回归通过 |

## 四、正式支持范围

发布校验承诺覆盖：

- `campaign/`：默认 demo 战役。
- `xianxia_campaign/`：仙侠战役。

`generated_campaigns/` 下的目录是历史 worldgen 样例与回归素材，不应描述为全部兼容当前协议。2026-06-02 审计时，以下旧样例仍无法通过当前校验：

- `generated_campaigns/9_9`
- `generated_campaigns/ai_campaign_3107d9be`
- `generated_campaigns/ai_campaign_427eb656`

这些目录每个均报告 6 个校验问题。Data Agent 正在修补 worldgen prompt 源头；新增生成战役仍需逐个运行 `python validate_project.py --root <战役目录>`。

## 五、限制

1. 当前 bundled Python 环境缺少 `pytest` 和 `PyYAML`；完整 pytest 需要在具备这些依赖的环境中复验。
2. 本报告证明已运行的自动化回归与两个正式支持战役的结构校验状态，不等价于真实 LLM 服务的完整线上验收。
3. `generated_campaigns/` 包含旧协议样例，不属于发布支持矩阵。
4. Web 前端已移除公开 Mock 入口，但仍需浏览器人工验收或 Playwright 视觉验收。
