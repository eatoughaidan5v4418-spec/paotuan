export type ApiMode = "api" | "api_unconfigured" | string;

export interface ApiStatus {
  model?: string;
  base_url?: string;
  has_key?: boolean;
  auto_apply?: boolean;
  mode?: ApiMode;
}

export interface CampaignSummary {
  id: string;
  path?: string;
  title: string;
  campaign_id?: string;
  current_turn?: number;
  current_time?: string;
  scene?: string;
  deletable?: boolean;
}

export interface CampaignState {
  id?: string;
  title?: string;
  root?: string;
  turn?: number;
  time?: string;
}

export interface SceneState {
  id?: string;
  summary?: string;
  active_threads?: unknown[];
  present_entities?: string[];
  location?: {
    id?: string;
    name?: string;
    type?: string;
    summary?: string;
    file?: string;
  };
}

export interface PlayerState {
  id?: string;
  name?: string;
  health?: number;
  max_health?: number;
  qi?: number;
  max_qi?: number;
  realm?: string;
  realm_level?: number | string;
  spiritual_root?: string;
  location_id?: string;
  description?: string;
  system_rank?: string;
  effect_points?: number;
  special_effects?: string[];
  stats?: Record<string, string | number>;
  inventory?: unknown[];
  conditions?: string[];
  traits?: string[];
}

export interface SheetItem {
  field: string;
  label: string;
  value: unknown;
  type?: string;
}

export interface CharacterSheet {
  sections?: Array<{
    id: string;
    title: string;
    items: SheetItem[];
  }>;
}

export interface NpcSummary {
  id: string;
  name?: string;
  role?: string;
  location_id?: string;
  memory_count?: number;
  understanding_count?: number;
}

export interface QuestSummary {
  id?: string;
  title?: string;
  status?: string;
  description?: string;
}

export interface ClockSummary {
  id?: string;
  title?: string;
  value?: number | string;
  max_value?: number | string;
  status?: string;
  stakes?: string;
  visibility?: string;
}

export interface VisibleState {
  campaign?: CampaignState;
  scene?: SceneState;
  mechanics?: Record<string, boolean>;
  character_sheet?: CharacterSheet;
  player?: PlayerState;
  npcs?: NpcSummary[];
  quests?: QuestSummary[];
  open_threads?: Array<Record<string, unknown>>;
  quest_graph?: { quests?: QuestSummary[] };
  knowledge?: Record<string, unknown>;
  clocks?: ClockSummary[];
  resources?: Array<Record<string, unknown>>;
  progress_tracks?: Array<Record<string, unknown>>;
  api?: ApiStatus;
}

export interface LogEntry {
  type?: string;
  file?: string;
  turn_id?: string;
  player_action?: string;
  visible_text?: VisibleText;
  rendered?: string;
  applied?: boolean;
}

export interface VisibleText {
  scene?: unknown;
  action_result?: unknown;
  reaction?: unknown;
  npc_actions?: unknown;
  world_motion?: unknown;
  tension?: unknown;
  actionable_clues?: unknown;
  check?: unknown;
  state_summary?: {
    time?: string;
    memory?: string;
    quests?: string;
    unresolved?: string[];
  };
}

export interface BootstrapPayload {
  config?: {
    project_root?: string;
    current_campaign?: string;
    api?: ApiStatus;
  };
  campaigns?: CampaignSummary[];
  state?: VisibleState | null;
  logs?: LogEntry[];
}

export interface TurnResult {
  visible_text?: VisibleText;
  rendered?: string;
  inferred_action?: Record<string, unknown>;
  apply_report?: {
    applied?: boolean;
    errors?: string[];
  };
  artifact_path?: string;
  tool_results?: unknown[];
  active_lore?: unknown[];
  state?: VisibleState;
}
