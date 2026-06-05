import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import {
  Archive,
  BookOpenText,
  CaretDown,
  CheckCircle,
  Clock,
  DiceFive,
  DownloadSimple,
  FolderOpen,
  HourglassMedium,
  ListMagnifyingGlass,
  MagnifyingGlass,
  MapPin,
  NotePencil,
  Pulse,
  SealWarning,
  Sparkle,
  SpinnerGap,
  UserFocus,
  UsersThree,
  WarningCircle,
  X
} from "@phosphor-icons/react";
import { api } from "./api";
import type {
  BootstrapPayload,
  CampaignSummary,
  ClockSummary,
  LogEntry,
  NpcSummary,
  PlayerState,
  QuestSummary,
  VisibleState,
  VisibleText
} from "./types";

const CAMPAIGN_KEY = "paotuan.react.currentCampaign";
const forbiddenDebugKeys = ["state_patch", "tool_results", "active_lore", "artifact_path"];

type LoadPhase = "loading" | "ready" | "empty" | "error";

interface Toast {
  id: number;
  kind: "info" | "error" | "success";
  message: string;
}

function valueText(value: unknown, fallback = "未记录"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (Array.isArray(value)) return value.map((item) => valueText(item, "")).filter(Boolean).join("、");
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    return String(record.text || record.fact || record.title || record.name || JSON.stringify(value));
  }
  return String(value);
}

function asList(value: unknown): unknown[] {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

function clampRatio(value: unknown, maxValue: unknown) {
  const current = Number(value || 0);
  const max = Number(maxValue || 0);
  if (!Number.isFinite(max) || max <= 0) return 0;
  return Math.max(0, Math.min(100, (current / max) * 100));
}

function statusLabel(status: unknown) {
  const normalized = String(status || "active").toLowerCase();
  const labels: Record<string, string> = {
    active: "进行中",
    complete: "已完成",
    completed: "已完成",
    resolved: "已解决",
    failed: "失败",
    blocked: "受阻",
    dormant: "暂缓"
  };
  return labels[normalized] || valueText(status, "进行中");
}

function statusTone(status: unknown) {
  const normalized = String(status || "active").toLowerCase();
  if (["complete", "completed", "resolved", "success"].includes(normalized)) return "ok";
  if (["failed", "blocked", "danger"].includes(normalized)) return "danger";
  return "active";
}

function initials(name: unknown) {
  return valueText(name, "未知").slice(0, 2).toUpperCase();
}

function formatVisibleSections(visible?: VisibleText, rendered?: string) {
  if (!visible) return rendered ? [{ title: "回合正文", body: [rendered] }] : [];
  const sections = [
    ["场景", visible.scene],
    ["行动结果", visible.action_result],
    ["回应", visible.reaction],
    ["NPC 动作", visible.npc_actions],
    ["世界推进", [visible.world_motion, visible.tension].filter(Boolean)],
    ["可行动线索", visible.actionable_clues],
    ["检定", visible.check]
  ];
  const formatted = sections
    .map(([title, body]) => ({ title: String(title), body: asList(body).map((item) => valueText(item, "")) }))
    .filter((section) => section.body.some(Boolean));
  const summary = visible.state_summary;
  if (summary) {
    const body = [summary.time, summary.memory, summary.quests, ...(summary.unresolved || [])].filter(Boolean);
    if (body.length) formatted.push({ title: "状态变化", body: body.map(String) });
  }
  if (!formatted.length && rendered) formatted.push({ title: "回合正文", body: [rendered] });
  return formatted;
}

function useToast() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  function push(message: string, kind: Toast["kind"] = "info") {
    const id = Date.now() + Math.random();
    setToasts((items) => [...items, { id, message, kind }]);
    window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 4200);
  }
  function remove(id: number) {
    setToasts((items) => items.filter((item) => item.id !== id));
  }
  return { toasts, push, remove };
}

function SkeletonPanel({ lines = 4 }: { lines?: number }) {
  return (
    <div className="panel skeleton-panel" aria-hidden="true">
      {Array.from({ length: lines }).map((_, index) => (
        <span key={index} className="skeleton-line" style={{ width: `${92 - index * 11}%` }} />
      ))}
    </div>
  );
}

function EmptyState({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function Meter({ label, value, max, tone = "jade" }: { label: string; value?: unknown; max?: unknown; tone?: "jade" | "gold" | "danger" }) {
  const pct = clampRatio(value, max);
  return (
    <div className="meter-block">
      <div className="meter-label">
        <span>{label}</span>
        <strong>{valueText(value, "0")}/{valueText(max, "?")}</strong>
      </div>
      <div className="meter-track">
        <motion.span
          className={`meter-fill ${tone}`}
          initial={{ width: "0%" }}
          animate={{ width: `${pct}%` }}
          transition={{ type: "spring", stiffness: 95, damping: 18 }}
        />
      </div>
    </div>
  );
}

function CampaignRail({
  campaigns,
  currentCampaign,
  phase,
  state,
  onSelect,
  onCreate,
  onDelete,
  busy
}: {
  campaigns: CampaignSummary[];
  currentCampaign: string;
  phase: LoadPhase;
  state: VisibleState | null;
  onSelect: (id: string) => void;
  onCreate: (theme: string) => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const [theme, setTheme] = useState("");
  const player = state?.player || {};
  const stats = Object.entries(player.stats || {}).slice(0, 8);
  const selected = campaigns.find((campaign) => campaign.id === currentCampaign);

  return (
    <aside className="left-rail" aria-label="战役与玩家状态">
      <header className="brand-block">
        <div className="brand-sigil">档</div>
        <div>
          <p>Paotuan Archive</p>
          <h1>跑团档案室</h1>
        </div>
      </header>

      <section className="panel campaign-switcher">
        <div className="panel-heading">
          <span><FolderOpen size={18} /> 战役切换</span>
          <button className="icon-btn" type="button" aria-label="展开战役列表">
            <CaretDown size={17} />
          </button>
        </div>
        {phase === "loading" ? (
          <SkeletonPanel lines={3} />
        ) : campaigns.length ? (
          <>
            <label className="field-label" htmlFor="campaignSelect">当前战役</label>
            <select
              id="campaignSelect"
              value={currentCampaign}
              onChange={(event) => onSelect(event.target.value)}
              disabled={busy}
            >
              {campaigns.map((campaign) => (
                <option key={campaign.id} value={campaign.id}>
                  {campaign.title} / {campaign.current_time || "时间未记录"}
                </option>
              ))}
            </select>
            <p className="quiet-text">{selected?.scene || "场景摘要未记录"}</p>
            <button
              className="danger-link"
              type="button"
              onClick={onDelete}
              disabled={busy || !selected?.deletable}
            >
              删除生成战役
            </button>
          </>
        ) : (
          <EmptyState icon={<Archive size={22} />} title="还没有战役" body="输入世界设定后生成第一个可游玩的档案。" />
        )}
      </section>

      <section className="panel new-world">
        <div className="panel-heading"><span><Sparkle size={18} /> 新世界</span></div>
        <label className="field-label" htmlFor="themeInput">世界设定</label>
        <textarea
          id="themeInput"
          value={theme}
          onChange={(event) => setTheme(event.target.value)}
          placeholder="例如：边境小城、失踪商队、玩家是刚入行的巡夜人"
          disabled={busy}
          rows={4}
        />
        <button
          className="primary-btn"
          type="button"
          disabled={busy || !theme.trim()}
          onClick={() => {
            onCreate(theme);
            setTheme("");
          }}
        >
          {busy ? <SpinnerGap className="spin" size={18} /> : <Sparkle size={18} />}
          生成并进入
        </button>
      </section>

      <section className="panel player-card">
        <div className="panel-heading"><span><UserFocus size={18} /> 玩家状态</span></div>
        {!state?.player ? (
          <EmptyState icon={<UserFocus size={22} />} title="角色未载入" body="选择战役后会显示角色生命、资源、状态和背包。" />
        ) : (
          <>
            <div className="player-id">
              <div className="portrait">{initials(player.name)}</div>
              <div>
                <h2>{valueText(player.name, "玩家角色")}</h2>
                <p>{player.realm || player.location_id || "身份未记录"}</p>
              </div>
            </div>
            <Meter label="生命" value={player.health} max={player.max_health} tone="jade" />
            {state.mechanics?.cultivation && <Meter label="灵力" value={player.qi} max={player.max_qi} tone="gold" />}
            <div className="stat-grid">
              {stats.length ? stats.map(([key, value]) => (
                <div key={key}>
                  <span>{key}</span>
                  <strong>{valueText(value)}</strong>
                </div>
              )) : <div><span>属性</span><strong>未记录</strong></div>}
            </div>
            <ChipList items={[...(player.traits || []), ...(player.conditions || [])]} empty="暂无词条或状态" />
          </>
        )}
      </section>
    </aside>
  );
}

function ChipList({ items, empty }: { items: unknown[]; empty: string }) {
  if (!items.length) return <p className="quiet-text">{empty}</p>;
  return (
    <div className="chip-list">
      {items.slice(0, 12).map((item, index) => <span className="chip" key={`${valueText(item)}-${index}`}>{valueText(item)}</span>)}
    </div>
  );
}

function SceneHeader({ state, apiMode }: { state: VisibleState | null; apiMode?: string }) {
  const campaign = state?.campaign;
  const scene = state?.scene;
  return (
    <header className="scene-header">
      <div>
        <div className="meta-row">
          <span>{campaign?.title || "未选择战役"}</span>
          <span>第 {campaign?.turn || 1} 回合</span>
          <span>{campaign?.time || "时间未记录"}</span>
        </div>
        <h2>{scene?.location?.name || scene?.id || "当前场景"}</h2>
        <p>{scene?.summary || "选择战役或生成新世界后，场景会在这里展开。"}</p>
      </div>
      <div className={`api-pill ${apiMode === "api_unconfigured" ? "warn" : "ok"}`}>
        <Pulse size={16} />
        {apiMode === "api_unconfigured" ? "API 未配置" : "世界运行中"}
      </div>
    </header>
  );
}

function NarrativeTimeline({ logs, pending, phase }: { logs: LogEntry[]; pending?: string; phase: LoadPhase }) {
  const reduced = useReducedMotion();
  const endRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "end" });
  }, [logs.length, pending, reduced]);

  if (phase === "loading") {
    return (
      <section className="timeline" aria-label="叙事时间线">
        <SkeletonPanel lines={7} />
        <SkeletonPanel lines={5} />
      </section>
    );
  }

  if (!logs.length && !pending) {
    return (
      <section className="timeline" aria-label="叙事时间线">
        <EmptyState icon={<BookOpenText size={24} />} title="等待开局" body="选择战役或生成新世界后，在下方输入玩家行动。" />
      </section>
    );
  }

  return (
    <section className="timeline" aria-label="叙事时间线">
      <AnimatePresence initial={false}>
        {logs.map((entry, index) => (
          <TimelineEntry key={`${entry.turn_id || entry.file || index}-${index}`} entry={entry} />
        ))}
        {pending && (
          <motion.article
            className="timeline-entry pending-entry"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            <time>处理中</time>
            <div className="entry-card">
              <div className="entry-title">
                <h3>AI 回合生成中</h3>
                <span><SpinnerGap className="spin" size={15} /> 系统</span>
              </div>
              <p>{pending}</p>
            </div>
          </motion.article>
        )}
      </AnimatePresence>
      <div ref={endRef} />
    </section>
  );
}

function TimelineEntry({ entry }: { entry: LogEntry }) {
  const sections = formatVisibleSections(entry.visible_text, entry.rendered);
  return (
    <motion.article
      className="timeline-entry"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 120, damping: 22 }}
    >
      <time>{entry.turn_id || "记录"}</time>
      <div className="entry-card">
        {entry.player_action && (
          <div className="player-action">
            <span><NotePencil size={15} /> 玩家行动</span>
            <p>{entry.player_action}</p>
          </div>
        )}
        {sections.map((section) => (
          <div className="entry-section" key={section.title}>
            <div className="entry-title">
              <h3>{section.title}</h3>
              <span>{entry.applied ? <CheckCircle size={15} /> : <HourglassMedium size={15} />} {entry.applied ? "已写回" : "记录"}</span>
            </div>
            {section.body.map((line, index) => <p key={`${section.title}-${index}`}>{line}</p>)}
          </div>
        ))}
      </div>
    </motion.article>
  );
}

function ActionBar({ busy, disabled, onSubmit, onRoll }: { busy: boolean; disabled: boolean; onSubmit: (text: string) => void; onRoll: () => void }) {
  const [action, setAction] = useState("");
  return (
    <form
      className="action-bar"
      onSubmit={(event) => {
        event.preventDefault();
        const text = action.trim();
        if (!text) return;
        onSubmit(text);
        setAction("");
      }}
    >
      <label htmlFor="actionInput">玩家行动</label>
      <textarea
        id="actionInput"
        value={action}
        onChange={(event) => setAction(event.target.value)}
        placeholder="描述你要做什么。系统会推断行动类型和耗时。"
        disabled={busy || disabled}
        rows={2}
      />
      <button className="secondary-btn" type="button" onClick={onRoll} disabled={busy || disabled}>
        <DiceFive size={19} /> 掷骰
      </button>
      <button className="primary-btn" type="submit" disabled={busy || disabled || !action.trim()}>
        {busy ? <SpinnerGap className="spin" size={18} /> : <NotePencil size={18} />}
        送出行动
      </button>
    </form>
  );
}

function RightDossier({
  state,
  onExport,
  onValidate,
  busy
}: {
  state: VisibleState | null;
  onExport: () => void;
  onValidate: () => void;
  busy: boolean;
}) {
  const knowledge = state?.knowledge || {};
  const clueTexts = [
    ...asList(knowledge.clues_discovered).map((item) => valueText(item, "")),
    ...asList(knowledge.facts_understood).map((item) => valueText(item, "")),
    ...asList(knowledge.locations_explored).map((item) => valueText(item, ""))
  ].filter(Boolean);
  const unresolved = [
    ...(state?.quests || []).map((quest) => quest.title || quest.id),
    ...(state?.open_threads || []).map((thread) => thread.description || thread.thread || thread.summary || thread.id)
  ].filter(Boolean);

  return (
    <aside className="right-rail" aria-label="档案抽屉">
      <section className="panel scene-dossier">
        <div className="panel-heading"><span><MapPin size={18} /> 当前场景</span></div>
        <h3>{state?.scene?.location?.name || "地点未记录"}</h3>
        <p>{state?.scene?.location?.summary || state?.scene?.summary || "暂无地点摘要。"}</p>
        <ChipList items={state?.scene?.present_entities || []} empty="暂无可见实体" />
      </section>

      <section className="panel">
        <div className="panel-heading"><span><Clock size={18} /> 世界时钟</span></div>
        <ClockList clocks={state?.clocks || []} campaignTime={state?.campaign?.time} />
      </section>

      <section className="panel">
        <div className="panel-heading"><span><UsersThree size={18} /> NPC 档案</span></div>
        <NpcList npcs={state?.npcs || []} />
      </section>

      <section className="panel">
        <div className="panel-heading"><span><ListMagnifyingGlass size={18} /> 线索证据</span></div>
        <EvidenceList items={clueTexts} empty="尚未记录玩家可见线索。" />
      </section>

      <section className="panel">
        <div className="panel-heading"><span><SealWarning size={18} /> 任务悬念</span></div>
        <QuestList quests={state?.quests || []} extra={unresolved} />
      </section>

      <details className="system-drawer">
        <summary><Archive size={18} /> 系统面板</summary>
        <div className="drawer-actions">
          <button className="secondary-btn" type="button" onClick={onExport} disabled={busy}>
            <DownloadSimple size={18} /> 导出 Obsidian
          </button>
          <button className="secondary-btn" type="button" onClick={onValidate} disabled={busy}>
            <CheckCircle size={18} /> 校验项目
          </button>
          <p>前端只消费玩家可见 DTO。调试字段不会进入主屏。</p>
        </div>
      </details>
    </aside>
  );
}

function ClockList({ clocks, campaignTime }: { clocks: ClockSummary[]; campaignTime?: string }) {
  if (!clocks.length) return <EmptyState icon={<Clock size={22} />} title="暂无公开时钟" body={campaignTime || "离屏推进会在公开后显示在这里。"} />;
  return (
    <div className="clock-list">
      {clocks.map((clock, index) => (
        <article className="clock-card" key={clock.id || index}>
          <div>
            <strong>{clock.title || clock.id || "世界时钟"}</strong>
            <span className={`status ${statusTone(clock.status)}`}>{statusLabel(clock.status)}</span>
          </div>
          <p>{clock.stakes || "风险说明未记录"}</p>
          <Meter label="推进" value={clock.value} max={clock.max_value} tone={statusTone(clock.status) === "danger" ? "danger" : "gold"} />
        </article>
      ))}
    </div>
  );
}

function NpcList({ npcs }: { npcs: NpcSummary[] }) {
  if (!npcs.length) return <EmptyState icon={<UsersThree size={22} />} title="当前无可见 NPC" body="NPC 只会显示玩家可见范围内的档案。" />;
  return (
    <div className="npc-list">
      {npcs.map((npc) => (
        <article className="npc-card" key={npc.id}>
          <div className="mini-portrait">{initials(npc.name || npc.id)}</div>
          <div>
            <h3>{npc.name || npc.id}</h3>
            <p>{npc.role || "身份未记录"}</p>
            <span>记忆 {npc.memory_count || 0} / 理解 {npc.understanding_count || 0}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function EvidenceList({ items, empty }: { items: unknown[]; empty: string }) {
  if (!items.length) return <EmptyState icon={<MagnifyingGlass size={22} />} title="证据栏为空" body={empty} />;
  return (
    <div className="evidence-list">
      {items.slice(0, 8).map((item, index) => (
        <article className="evidence-card" key={`${valueText(item)}-${index}`}>
          <span>{index < 2 ? "重要" : "记录"}</span>
          <p>{valueText(item)}</p>
        </article>
      ))}
    </div>
  );
}

function QuestList({ quests, extra }: { quests: QuestSummary[]; extra: unknown[] }) {
    const items: QuestSummary[] = quests.length
      ? quests
      : extra.map((item, index) => ({ id: `thread-${index}`, title: valueText(item), status: "active", description: "" }));
  if (!items.length) return <EmptyState icon={<SealWarning size={22} />} title="暂无任务悬念" body="新的目标、未解问题和公开线程会在这里沉淀。" />;
  return (
    <div className="quest-list">
      {items.slice(0, 8).map((quest, index) => (
        <article className="quest-card" key={quest.id || index}>
          <div>
            <strong>{quest.title || quest.id || "未命名任务"}</strong>
            <span className={`status ${statusTone(quest.status)}`}>{statusLabel(quest.status)}</span>
          </div>
          {quest.description && <p>{quest.description}</p>}
        </article>
      ))}
    </div>
  );
}

function ToastStack({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: number) => void }) {
  return (
    <div className="toast-stack" aria-live="polite" aria-atomic="false">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            className={`toast ${toast.kind}`}
            key={toast.id}
            initial={{ opacity: 0, y: 14, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8 }}
          >
            {toast.kind === "error" ? <WarningCircle size={18} /> : <CheckCircle size={18} />}
            <span>{toast.message}</span>
            <button type="button" aria-label="关闭提示" onClick={() => onRemove(toast.id)}><X size={15} /></button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

export function App() {
  const [phase, setPhase] = useState<LoadPhase>("loading");
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [currentCampaign, setCurrentCampaign] = useState(localStorage.getItem(CAMPAIGN_KEY) || "");
  const [visibleState, setVisibleState] = useState<VisibleState | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState("");
  const { toasts, push, remove } = useToast();

  const apiMode = visibleState?.api?.mode;
  const hasForbiddenDebug = useMemo(() => {
    const snapshot = JSON.stringify({ visibleState, logs });
    return forbiddenDebugKeys.some((key) => snapshot.includes(`"${key}"`));
  }, [visibleState, logs]);

  function rememberCampaign(id: string) {
    setCurrentCampaign(id);
    if (id) localStorage.setItem(CAMPAIGN_KEY, id);
  }

  async function loadAll(campaignOverride?: string) {
    setPhase("loading");
    try {
      let boot: BootstrapPayload;
      try {
        boot = await api.bootstrap();
      } catch {
        const [campaignResult, logResult] = await Promise.all([api.campaigns(), api.logs()]);
        const preferred = campaignOverride || currentCampaign || campaignResult.campaigns[0]?.id || "";
        const state = preferred ? await api.state(preferred) : null;
        boot = {
          campaigns: campaignResult.campaigns,
          logs: logResult.logs,
          state,
          config: { current_campaign: preferred, api: state?.api }
        };
      }
      const nextCampaigns = boot.campaigns || [];
      const preferred = campaignOverride || currentCampaign || boot.config?.current_campaign || nextCampaigns[0]?.id || "";
      setCampaigns(nextCampaigns);
      if (preferred) rememberCampaign(preferred);
      setVisibleState(boot.state || null);
      setLogs((boot.logs || []).slice().reverse());
      setPhase(nextCampaigns.length || boot.state ? "ready" : "empty");
    } catch (error) {
      setPhase("error");
      push(error instanceof Error ? error.message : "载入失败", "error");
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  useEffect(() => {
    if (hasForbiddenDebug) {
      push("检测到疑似调试字段进入玩家端 DTO，请检查后端过滤。", "error");
    }
  }, [hasForbiddenDebug]);

  async function selectCampaign(id: string) {
    if (!id) return;
    setBusy(true);
    try {
      rememberCampaign(id);
      const state = await api.selectCampaign(id);
      const logResult = await api.logs();
      setVisibleState(state);
      setLogs((logResult.logs || []).slice().reverse());
      setPhase("ready");
    } catch (error) {
      push(error instanceof Error ? error.message : "切换战役失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function createCampaign(theme: string) {
    setBusy(true);
    setPending("正在生成世界设定、开局场景和玩家可见状态。");
    try {
      const result = await api.createCampaign(theme);
      rememberCampaign(result.campaign.id);
      const campaignsResult = await api.campaigns();
      setCampaigns(campaignsResult.campaigns || []);
      setVisibleState(result.state);
      setLogs([{
        type: "opening",
        turn_id: "opening",
        rendered: result.campaign.opening_prompt || "新世界已经生成。",
        visible_text: { scene: result.campaign.opening_prompt || "新世界已经生成。" },
        applied: true
      }]);
      setPhase("ready");
      push("新世界已生成。", "success");
    } catch (error) {
      push(error instanceof Error ? error.message : "生成失败", "error");
    } finally {
      setPending("");
      setBusy(false);
    }
  }

  async function deleteCampaign() {
    const selected = campaigns.find((campaign) => campaign.id === currentCampaign);
    if (!selected?.deletable) {
      push("只能删除生成战役，内置战役会被保护。", "error");
      return;
    }
    if (!window.confirm(`删除生成战役“${selected.title}”？`)) return;
    setBusy(true);
    try {
      const result = await api.deleteCampaign(selected.id);
      setCampaigns(result.campaigns || []);
      rememberCampaign(result.next_campaign || "");
      setVisibleState(result.state);
      setLogs([]);
      push("生成战役已删除。", "success");
    } catch (error) {
      push(error instanceof Error ? error.message : "删除失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function submitTurn(action: string) {
    setBusy(true);
    setPending("正在调用 AI，并等待状态校验与写回。");
    setLogs((items) => [...items, { type: "player", turn_id: "pending-action", player_action: action, applied: false }]);
    try {
      const result = await api.turn(currentCampaign, action);
      const nextLogs = await api.logs();
      if (result.state) setVisibleState(result.state);
      setLogs((nextLogs.logs || []).slice().reverse());
      if (result.apply_report?.errors?.length) {
        push(`状态写回存在问题：${result.apply_report.errors.join("；")}`, "error");
      } else {
        push("回合已生成。", "success");
      }
    } catch (error) {
      setLogs((items) => [...items, {
        type: "error",
        turn_id: "error",
        rendered: error instanceof Error ? error.message : "执行失败",
        visible_text: { action_result: error instanceof Error ? error.message : "执行失败" },
        applied: false
      }]);
      push(error instanceof Error ? error.message : "执行失败", "error");
    } finally {
      setPending("");
      setBusy(false);
    }
  }

  async function rollDice() {
    const expression = window.prompt("骰子表达式", "1d20") || "1d20";
    try {
      const result = await api.roll(expression);
      setLogs((items) => [...items, {
        type: "roll",
        turn_id: `roll-${Date.now()}`,
        rendered: `${result.expression} = ${result.rolls.join(" + ")}${result.modifier ? ` ${result.modifier > 0 ? "+" : "-"} ${Math.abs(result.modifier)}` : ""} -> ${result.total}`,
        visible_text: { check: `${result.expression} = ${result.total}` },
        applied: true
      }]);
    } catch (error) {
      push(error instanceof Error ? error.message : "掷骰失败", "error");
    }
  }

  async function exportObsidian() {
    setBusy(true);
    try {
      const result = await api.exportObsidian(currentCampaign);
      push(`已导出 Obsidian：${result.notes || 0} 条笔记。`, "success");
    } catch (error) {
      push(error instanceof Error ? error.message : "导出失败", "error");
    } finally {
      setBusy(false);
    }
  }

  async function validateProject() {
    setBusy(true);
    try {
      const result = await api.validate(currentCampaign);
      push(result.ok ? "项目校验通过。" : "项目校验发现问题，详情已返回。", result.ok ? "success" : "error");
      setLogs((items) => [...items, {
        type: "validate",
        turn_id: `validate-${Date.now()}`,
        rendered: result.stdout || result.stderr || "无输出",
        visible_text: { action_result: result.stdout || result.stderr || "无输出" },
        applied: result.ok
      }]);
    } catch (error) {
      push(error instanceof Error ? error.message : "校验失败", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="archive-app">
      <a className="skip-link" href="#actionInput">跳到行动输入</a>
      <CampaignRail
        campaigns={campaigns}
        currentCampaign={currentCampaign}
        phase={phase}
        state={visibleState}
        onSelect={selectCampaign}
        onCreate={createCampaign}
        onDelete={deleteCampaign}
        busy={busy}
      />
      <main className="play-surface">
        <SceneHeader state={visibleState} apiMode={apiMode} />
        {phase === "error" && (
          <div className="error-banner">
            <WarningCircle size={20} />
            <span>前端无法载入当前档案。请检查本地服务和 API Key 配置。</span>
          </div>
        )}
        <NarrativeTimeline logs={logs} pending={pending} phase={phase} />
        <ActionBar busy={busy} disabled={!currentCampaign || phase === "error"} onSubmit={submitTurn} onRoll={rollDice} />
      </main>
      <RightDossier state={visibleState} onExport={exportObsidian} onValidate={validateProject} busy={busy} />
      <ToastStack toasts={toasts} onRemove={remove} />
    </div>
  );
}
