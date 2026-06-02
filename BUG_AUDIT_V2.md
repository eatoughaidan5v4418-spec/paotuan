# Paotuan AI RPG - BUG_AUDIT_V2 实机测试报告

> 历史状态: **Superseded**
> 本文保留 2026-05-28 的发现过程，不代表当前发布状态。
> 当前可信验证请查看 `FINAL_REPORT.md` 与 `TEST_COVERAGE.md`。
> 文中“59/59通过”“待修复”等结论均应按当时快照理解。
>
> 日期: 2026-05-28
> 测试方法: API实机测试(DeepSeek) + 静态分析 + CLI直接调用
> 参考: CALYPSO (arXiv 2308.07540), Generative Agents, LangGraph Memory

## 测试流程

1. 运行全部59个现有测试 -> 全部通过
2. 检查主战役玩家角色 -> player_characters为空(致命缺陷)
3. API实机测试"查看状态" -> AI正确叙述但不写入player_state_changes
4. API实机测试"修炼冲关" -> AI描述了灵力变化但不写入状态
5. apply_patch.py直接测试 -> 管道正常，realm_level可变更
6. 发现.env加载、realm同步等多个附加问题

---

## 核心发现

### V10 [HIGH] AI叙述变化但不写入player_state_changes
- **测试**: API模式下"修炼引气诀"，AI叙述"灵力从3/6提升到5/6"、"消耗两块灵石"
- **结果**: player_state_changes=0条，玩家灵力/物品完全不变
- **影响**: 这是玩家等级永远无法提升的根因
- **修复**: 扩展了CALYPSO风格的叙述->状态提取器，从visible_text中自动解析数值变化
- **参考**: CALYPSO论文的"extractor module"模式、D&D milestone leveling
- **状态**: 已修复（prompts/ai-game-runner.md + tools/play_game.py）

### V11 [MEDIUM] .env加载在子目录战役中失效
- **测试**: --root xianxia_campaign 时API key读取失败
- **根因**: load_dotenv(root)只检查campaign目录，.env在项目根目录
- **修复**: load_dotenv同时检查project root (TOOLS_DIR.parent)
- **状态**: 已修复

### V12 [MEDIUM] realm/realm_level不同步
- **测试**: apply_patch realm_level=3但realm="炼气二层"
- **根因**: realm_level变更时realm文本字段不自动更新
- **修复**: apply_player_state_change中增加realm自动映射表
- **状态**: 已修复

### V13 [HIGH] play_game.py的apply_state_patch返回applied=False
- **测试**: API回合后apply_report.applied=False但errors=[]
- **表现**: validate_patch_structure通过但状态未写入
- **根因**: 待确认，可能与"inventory"字段验证有关
- **影响**: API回合的状态变更无法持久化
- **状态**: 待修复

### V14 [MEDIUM] 主战役无玩家角色
- **表现**: campaign/campaign_state.json中player_characters=[]
- **影响**: 从项目根目录启动游戏无法玩
- **状态**: 待修复

### V15 [MEDIUM] Consolidation从不执行
- **表现**: apply_patch.rb每隔5回合报告"consolidation due"
- **根因**: prompts/memory-consolidator.md存在但无代码路径调用
- **影响**: NPC长期记忆不会沉淀为稳定理解
- **状态**: 待修复

### V16 [LOW] inventory字段不在PLAYER_STATE_FIELDS
- **表现**: AI写入field="inventory"时验证失败
- **根因**: LIST_PLAYER_FIELDS不包含"inventory"
- **状态**: 待修复

## 成熟方案对比

| 方案 | 来源 | 适用场景 |
|------|------|----------|
| 叙述->状态提取器 | CALYPSO arXiv 2308.07540 | AI同步描述与状态 |
| 结构化输出+示例 | OpenAI/Anthropic best practice | 提示词优化 |
| Memory consolidation trigger | Generative Agents paper | 定期记忆沉淀 |
| Milestone leveling | D&D 5e DMG | 事件触发升级 |

## 修复优先级

1. V13: 修复apply_state_patch的applied=False（阻塞所有API状态写入）
2. V14: 为主战役创建默认玩家角色
3. V15: 实现consolidation自动化触发
4. V16: 扩展PLAYER_STATE_FIELDS包含inventory

## 已验证可用的功能

- apply_patch.py直接调用: realm_level/stats/qi等完全可用
- AI叙述质量: 非常优秀，正确描述修炼逻辑和状态
- NPC记忆系统: 可见性判定和独立记忆正常工作
- 世界时钟推进: 回合时间消耗正常
- 测试套件: 59/59通过
