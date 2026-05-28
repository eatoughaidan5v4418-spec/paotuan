# State Extractor

Read the GM output and produce a state_patch.

## player_state_changes

Use `entity_id`, `field`, `operation`, and `value`/`delta`.

- `health`, `max_health`, `qi`, `max_qi` support numeric delta
- `realm` and `realm_level` use set operation
- `system_rank` use set operation  
- `effect_points` support delta
- `special_effects` use add/remove
- `stats.xxx` use set (e.g. stats.strength)
- `conditions` use add/remove

Operations: set, add, remove, delta

**player_state_changes fields:**

| Field | Operation | Example |
|-------|-----------|---------|
| health | delta | `{"entity_id": "pc_xxx", "field": "health", "operation": "delta", "delta": -3}` |
| max_health | set | `{"entity_id": "pc_xxx", "field": "max_health", "operation": "set", "value": 30}` |
| realm | set | `{"entity_id": "pc_xxx", "field": "realm", "operation": "set", "value": "Foundation Establishment"}` |
| realm_level | set | `{"entity_id": "pc_xxx", "field": "realm_level", "operation": "set", "value": 1}` |
| qi | delta | `{"entity_id": "pc_xxx", "field": "qi", "operation": "delta", "delta": -5}` |

**inventory_changes change values:**

- `gain` - add item to inventory
- `lose` - remove item from inventory
- `consume` - consume consumable item
- `damage` - damage equipment
- `repair` - repair equipment
- `move` - move item between inventories

## location_changes

Fields: entity_id, from, to, reason

## relationship_changes

Fields: a, b, metric, delta, reason
