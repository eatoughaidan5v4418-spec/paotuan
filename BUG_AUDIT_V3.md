# Paotuan AI RPG - BUG_AUDIT_V3 历史审计归档

> 历史状态: **Superseded**
> 原始文件曾发生不可逆的字面量 `?` 编码损坏。
> 本文件于 2026-06-02 重建，仅保留能够从现有测试、后续审计和当前验证中确认的内容。
> 当前发布结论请查看 `FINAL_REPORT.md`。

## 一、历史范围

V3 审计围绕玩家成长、状态回写、NPC interpretation 写入与 Web API 行为展开。原始逐行叙述已损坏，因此不再将无法还原的数字、措辞或结论作为事实引用。

## 二、可确认的历史问题

| 编号 | 类别 | 历史问题 | 2026-06-02 状态 |
|------|------|----------|------------------|
| V17 | 玩家成长 | 状态回写与成长推进需要结构化处理 | 已有自动化覆盖 |
| V18 | 初始角色 | 初始角色字段与 worldgen 数据质量需要约束 | worldgen 源头仍在修补 |
| V19 | NPC 认知 | interpretation 写入可能引用不存在的来源记忆 | 已修复并有回归测试 |

## 三、V19 后续确认

V19 的核心不是普通的 `applied=false` 展示问题，而是认知链 provenance 完整性：

- interpretation 必须引用存在的来源记忆。
- 悬空 `derived_from_memory_id` 必须拒绝写入。
- 语义应用失败时，上层不能误报 `applied=True`。

当前回归测试覆盖：

- `tests/test_visibility.py::MemoryGraphIntegrityTests::test_dangling_interpretation_provenance_rejected`
- `tests/test_architecture_hardening.py::ApplyPatchHardeningTests::test_apply_state_patch_reports_semantic_apply_errors_as_not_applied`

## 四、2026-06-02 复核

```powershell
python -m pytest -q
# 63 passed, 9 subtests passed

python validate_project.py
# [OK] All checks passed

python validate_project.py --root xianxia_campaign
# [OK] All checks passed

python -m pytest tests/test_web_api.py -q
# 23 passed
```

## 五、保留风险

`generated_campaigns/` 下仍有历史 worldgen 样例使用旧协议。它们不是正式支持战役，不应用来证明当前 worldgen 全链路已经完成迁移。Data Agent 正在修补 worldgen prompt 源头。
