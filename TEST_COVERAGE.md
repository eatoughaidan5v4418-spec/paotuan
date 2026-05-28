# Paotuan 项目测试覆盖报告

> 生成时间: 2026-05-28
> 审计轮次: 13 轮
> 漏洞修复: 38 个
> Git: 20 commits

---

## 一、自动化测试 (59 tests)

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| test_architecture_hardening.py | 26 | apply_patch, run_turn, zone_validator, CLI |
| test_visibility.py | 11 | 可见性隔离, 记忆图谱 |
| test_web_api.py | 22 | Web API, mock turn, worldgen, obsidian |

---

## 二、CLI 工具 (20个全部通过)

apply_patch, chaos_manager, conditions_manager, lore_manager, memory_manager,
obsidian_vault, player_knowledge, player_state, progress_tracker, quest_viewer,
resource_manager, run_turn, session_summarizer, time_utils, web_api, web_game,
world_graph_query, world_tick_manager, zone_validator

---

## 三、API 端到端 (11个全部通过)

GET: /api/config, /api/campaigns, /api/state, /api/logs
POST: /api/campaigns/new, /api/campaigns/select, /api/campaigns/delete,
      /api/turn, /api/roll, /api/validate, /api/obsidian/export

---

## 四、边缘 case

| 测试 | 结果 |
|------|------|
| 无效骰子 | 400 |
| 空行动 | 400 |
| visibility_path=none 跳过 | 通过 |
| 新NPC自动创建 | 通过 |
| 重复条件不写 | 通过 |
| slug 路径穿越 | 通过 |

---

## 五、数据完整性

| 检查项 | 状态 |
|--------|--------|
| NPC YAML (8) | 全部合法 |
| NPC memory graphs (8) | 全部合规 |
| 悬挂引用 | 0 |
| JSON Schemas (9) | 全部合法 |
| Prompts (13) | 全部存在 |
| Generated campaigns (4) | 结构完整 |

---

## 六、安全

| 检查 | 结果 |
|------|------|
| 硬编码API密钥 | 无 |
| .env gitignore | OK |
| XSS | escapeHtml() |
| 路径穿越 | V27已修复 |

---

## 七、漏洞统计

| 严重度 | 数量 |
|--------|------|
| HIGH | 4 |
| MEDIUM | 16 |
| LOW | 18 |
| **总计** | **38** |

---

## 八、已知限制

1. PowerShell 管道传递中文可能损坏，应用 Python 文件 + unicode 转义
2. 代码重复 (V37): run_turn.py 和 apply_patch.py 重复时间函数
3. 缺少 LLM 集成测试
