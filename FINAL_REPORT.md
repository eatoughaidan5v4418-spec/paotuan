# Paotuan AI RPG - 发布验证报告

> 验证日期: 2026-06-02
> 性质: 本轮可信验证快照
> 正式支持范围: `campaign/`, `xianxia_campaign/`

## 一、结论

本轮 API-only 改造已完成主要公开入口清理，并通过 Web API 定向测试、架构硬化测试与两个正式支持战役的结构校验。核心 YAML/CLI 路径已有 stdlib fallback，完整 pytest 仍需具备 `pytest` 的运行环境复验。`generated_campaigns/` 中的历史 worldgen 样例不属于正式支持范围，其中仍有旧协议目录无法通过当前校验。

## 二、验证证据

```powershell
python validate_project.py
# [OK] All checks passed

python validate_project.py --root xianxia_campaign
# [OK] All checks passed

python -m unittest tests.test_web_api
# 25 passed

python -m unittest tests.test_architecture_hardening
# ran=32, OK
```

测试分布：

| 测试文件 | 数量 |
|----------|------|
| `tests/test_architecture_hardening.py` | 32 |
| `tests/test_visibility.py` | 12 |
| `tests/test_web_api.py` | 25 |
| **总计** | **69** |

## 三、本轮已验证修复

| 问题 | 当前保障 |
|------|----------|
| `apply_patch` 的 `load_graph` 局部变量遮蔽 | 定向回归与结构校验覆盖 |
| consolidation 调用 API 签名漂移 | 定向回归与结构校验覆盖 |
| 悬空 interpretation provenance 被接受 | 拒绝写入，并覆盖上层 `applied` 语义 |
| NPC memory graph schema 缺少 `visibility_evidence` | 默认 demo 与仙侠战役结构校验通过 |
| `run_turn` smoke 测试污染真实战役 | 测试改为隔离执行 |
| `/api/state` 泄露 private/secret world clocks | Web API 定向回归覆盖 |
| `normalize_patch` 修改主战役状态 | 回归测试确保归一化阶段不写 `campaign_state.json` |
| AI runner 时钟提交缺审计字段 | 回归测试确保提交 `current_turn` 与 `recent_updates` |

## 四、正式支持范围

纳入发布校验：

- `campaign/`：默认 demo 战役。
- `xianxia_campaign/`：仙侠战役。

不纳入发布支持承诺：

- `generated_campaigns/`：历史 worldgen 样例与回归素材。

2026-06-02 审计时，以下旧样例仍使用历史协议并无法通过当前校验：

- `generated_campaigns/9_9`
- `generated_campaigns/ai_campaign_3107d9be`
- `generated_campaigns/ai_campaign_427eb656`

每个目录均报告 6 个校验问题。Data Agent 正在修补 worldgen prompt 源头；完成前不能宣称所有生成战役兼容当前 schema。

## 五、文档状态

- `BUG_AUDIT_V2.md`：历史审计，已标记 superseded。
- `BUG_AUDIT_V3.md`：原文件编码损坏，已重建为历史归档。
- `VULNERABILITY_AUDIT.md`：历史漏洞轨迹，已标记 superseded 并附 2026-06-02 复核。
- `TEST_COVERAGE.md`：当前可信测试快照。
- `WEB_UI.md`：已同步 API-only 启动说明；前端 Mock 开关已移除。

## 六、剩余风险

1. worldgen prompt 源头仍在修补，新增生成战役必须单独执行 `python validate_project.py --root <战役目录>`。
2. 历史生成样例不应被误计入正式支持矩阵。
3. 当前 bundled Python 环境缺少 `pytest`；核心 YAML/CLI 路径已有 stdlib fallback，完整 pytest 需要在具备 `pytest` 后复验。
4. 当前证据覆盖定向自动化测试和结构校验，不替代真实 LLM 服务验收与 UI 人工验收。
