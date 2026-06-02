const state = {
  campaigns: [],
  currentCampaign: "",
  busy: false,
  toastTimer: null,
};

const $ = (id) => document.getElementById(id);
const CAMPAIGN_KEY = "paotuan.currentCampaign";

function rememberCampaign(id) {
  state.currentCampaign = id || "";
  if (state.currentCampaign) {
    localStorage.setItem(CAMPAIGN_KEY, state.currentCampaign);
  } else {
    localStorage.removeItem(CAMPAIGN_KEY);
  }
}

function showToast(message, isError = false) {
  const toast = $("toast");
  clearTimeout(state.toastTimer);
  toast.textContent = message;
  toast.className = `toast ${isError ? "error" : ""}`;
  toast.setAttribute("role", isError ? "alert" : "status");
  state.toastTimer = setTimeout(() => toast.classList.add("hidden"), 3600);
}

function text(value, fallback = "未记录") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function escapeHtml(value) {
  return text(value, "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[ch]);
}

function displayValue(value) {
  if (Array.isArray(value)) return value.map((item) => displayValue(item)).join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return text(value);
}

function listItems(items) {
  if (!items || !items.length) return `<p class="muted">暂无</p>`;
  return `<ul>${items.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : JSON.stringify(item))}</li>`).join("")}</ul>`;
}

function card(title, body, extra = "") {
  return `<article class="info-card"><h4>${escapeHtml(title)}</h4><p>${escapeHtml(body)}</p>${extra}</article>`;
}

function emptyNote(message) {
  return `<p class="empty-note">${escapeHtml(message)}</p>`;
}

function statusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (["complete", "completed", "success", "resolved"].includes(normalized)) return "ok";
  if (["failed", "danger", "blocked"].includes(normalized)) return "danger";
  return "active";
}

function statusLabel(status) {
  const labels = {
    active: "进行中",
    complete: "已完成",
    completed: "已完成",
    failed: "已失败",
    resolved: "已解决",
    dormant: "暂缓",
  };
  return labels[String(status || "").toLowerCase()] || text(status, "状态未记录");
}

function statusBadge(status) {
  return `<span class="status-badge ${statusClass(status)}">${escapeHtml(statusLabel(status))}</span>`;
}

function scrollNarrativeToEnd() {
  requestAnimationFrame(() => {
    const narrative = $("narrative");
    if (narrative) {
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      narrative.scrollTo({ top: narrative.scrollHeight, behavior: reduceMotion ? "auto" : "smooth" });
    }
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `请求失败: ${response.status}`);
  }
  return data;
}

function setBusy(message = "") {
  state.busy = Boolean(message);
  $("sendTurnButton").disabled = state.busy;
  $("newCampaignButton").disabled = state.busy;
  $("sendTurnButton").textContent = message || "执行回合";
  if (message) {
    $("apiStatus").textContent = message;
  } else {
    renderModeHint();
  }
}

function renderModeHint(config = null) {
  const apiInfo = config?.api;
  if (apiInfo) {
    $("apiStatus").textContent = `${apiInfo.model || "未知模型"} / ${apiInfo.has_key ? "API 已配置" : "未配置 API Key"}`;
  } else {
    $("apiStatus").textContent = "API 模式";
  }
  $("sendTurnButton").textContent = "执行回合";
  $("newCampaignButton").textContent = "生成并进入";
}

function selectedCampaign() {
  return state.campaigns.find((campaign) => campaign.id === state.currentCampaign);
}

function updateDeleteButton() {
  const button = $("deleteCampaign");
  if (!button) return;
  button.disabled = !selectedCampaign()?.deletable;
}

function renderVisible(visible, rendered) {
  const narrative = $("narrative");
  if (!visible || typeof visible === "string") {
    narrative.insertAdjacentHTML("beforeend", `<article class="gm-card gm-card-turn"><p>${escapeHtml(rendered || visible || "")}</p></article>`);
    scrollNarrativeToEnd();
    return;
  }

  const sections = [
    ["场景", visible.scene],
    ["行动结果", visible.action_result],
    ["反应", visible.reaction],
    ["NPC 动作", visible.npc_actions],
    ["局势推进", [visible.world_motion, visible.tension].filter(Boolean)],
    ["可行动线索", visible.actionable_clues],
    ["需要检定", visible.check || "无"],
  ];

  const summary = visible.state_summary || {};
  let html = `<article class="gm-card gm-card-turn"><h3>GM 回合</h3>`;
  for (const [title, value] of sections) {
    if (!value || (Array.isArray(value) && value.length === 0)) continue;
    html += `<div class="gm-section"><h3>${escapeHtml(title)}</h3>`;
    html += Array.isArray(value) ? listItems(value) : `<p>${escapeHtml(value)}</p>`;
    html += `</div>`;
  }
  if (Object.keys(summary).length) {
    html += `<div class="gm-section"><h3>状态变化</h3>`;
    html += listItems([summary.time, summary.memory, summary.quests].filter(Boolean));
    if (summary.unresolved && summary.unresolved.length) {
      html += `<div class="muted">未解决悬念</div>${listItems(summary.unresolved)}`;
    }
    html += `</div>`;
  }
  html += `</article>`;
  narrative.insertAdjacentHTML("beforeend", html);
  scrollNarrativeToEnd();
}

function renderLogEntry(entry) {
  if (entry.player_action) {
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card player-card"><h3>你</h3><p>${escapeHtml(entry.player_action)}</p></article>`);
  }
  if (entry.visible_text) {
    renderVisible(entry.visible_text, entry.rendered);
  } else if (entry.rendered) {
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card gm-card-turn"><h3>GM 回合</h3><p>${escapeHtml(entry.rendered)}</p></article>`);
  }
}

async function loadLogs() {
  const data = await api("/api/logs");
  const logs = (data.logs || []).slice().reverse();
  $("narrative").innerHTML = "";
  if (!logs.length) {
    $("narrative").innerHTML = `<article class="gm-card waiting-card"><h3>等待开团</h3><p>选择战役或生成新世界后，在下方输入玩家行动。</p></article>`;
    return;
  }
  logs.forEach(renderLogEntry);
  scrollNarrativeToEnd();
}

function renderState(data) {
  if (!data || !data.campaign) return;
  rememberCampaign(data.campaign.root || state.currentCampaign);
  $("campaignTitle").textContent = `${text(data.campaign.title)} / 第 ${text(data.campaign.turn, 1)} 回合`;
  $("sceneTitle").textContent = text(data.scene?.location?.name || data.scene?.id, "当前场景");
  $("campaignMeta").textContent = `${text(data.campaign.time)} / ${text(data.scene?.summary, "暂无场景摘要")}`;
  renderModeHint({ api: data.api });
  updateDeleteButton();

  const player = data.player || {};
  const mechanics = data.mechanics || {};
  const hp = Number(player.health || 0);
  const maxHp = Number(player.max_health || hp || 1);
  const qi = Number(player.qi || 0);
  const maxQi = Number(player.max_qi || qi || 1);
  const playerProgress = (data.progress_tracks || []).filter((track) => {
    const scope = String(track.owner_id || track.entity_id || track.subject_id || track.id || "");
    return !scope || scope.includes(player.id || "pc_main") || scope.includes("player") || scope.includes("pc_") || scope.includes("system");
  }).slice(0, 4);
  const playerResources = (data.resources || []).find((item) => item.id === player.id) || {};
  const resourceRows = Object.entries(playerResources)
    .filter(([key]) => key !== "id" && key !== "type");
  const specialEffects = player.special_effects || [];
  const builtInSheetFields = new Set([
    "health",
    "max_health",
    "qi",
    "max_qi",
    "realm",
    "realm_level",
    "spiritual_root",
    "system_rank",
    "effect_points",
    "special_effects",
  ]);
  const sheetSections = data.character_sheet?.sections || [];
  const dynamicSheetCards = sheetSections.map((section) => {
    const customItems = (section.items || []).filter((item) => !builtInSheetFields.has(String(item.field || "")));
    if (!customItems.length) return "";
    return `
      <div class="info-card">
        <h4>${escapeHtml(section.title || section.id || "Character")}</h4>
        <div class="pill-list">${customItems.map((item) => `<span class="pill">${escapeHtml(item.label || item.field)} ${escapeHtml(displayValue(item.value))}</span>`).join("")}</div>
      </div>
    `;
  }).join("");
  const systemCard = (mechanics.system || mechanics.effect_points) ? `
    <div class="info-card compact-card">
      <h4>\u4e16\u754c\u673a\u5236</h4>
      <p>${mechanics.system ? `\u9636\u5c42 ${escapeHtml(text(player.system_rank))}` : ""}${mechanics.system && mechanics.effect_points ? " / " : ""}${mechanics.effect_points ? `\u8d44\u6e90 ${escapeHtml(text(player.effect_points))}` : ""}</p>
      ${mechanics.system ? `<div class="pill-list">${specialEffects.map((v) => `<span class="pill">${escapeHtml(v)}</span>`).join("") || `<span class="pill">\u6682\u65e0\u6548\u679c</span>`}</div>` : ""}
    </div>
  ` : "";
  const cultivationLine = mechanics.cultivation ? `<div class="character-desc">\u7075\u6839 ${escapeHtml(text(player.spiritual_root))}</div>` : "";
  const qiMeter = mechanics.cultivation ? renderMeter("\u7075\u529b", qi, maxQi, "gold-fill") : "";
  const characterMeta = mechanics.cultivation ? `<span>${escapeHtml(text(player.realm))}</span>` : "";

  $("characterSheet").innerHTML = `
    <article class="info-card character-hero">
      <div class="character-name"><strong>${escapeHtml(player.name || "\u73a9\u5bb6\u89d2\u8272")}</strong>${characterMeta}</div>
      ${cultivationLine}
    </article>
    ${systemCard}
    <div class="info-card compact-card">
      <h4>\u8d44\u6e90</h4>
      ${renderMeter("\u751f\u547d", hp, maxHp)}
      ${qiMeter}
      ${resourceRows.length ? renderResourceRows(resourceRows) : ""}
    </div>
    <div class="info-card"><h4>\u5c5e\u6027</h4><div class="pill-list">${Object.entries(player.stats || {}).map(([k, v]) => `<span class="pill">${escapeHtml(k)} ${escapeHtml(v)}</span>`).join("") || `<span class="pill">\u6682\u65e0</span>`}</div></div>
    <div class="info-card"><h4>\u8bcd\u6761 / \u72b6\u6001</h4><div class="pill-list">${[...(player.traits || []), ...(player.conditions || [])].map((v) => `<span class="pill">${escapeHtml(v)}</span>`).join("") || `<span class="pill">\u6682\u65e0</span>`}</div></div>
    <div class="info-card"><h4>\u7269\u54c1</h4>${listItems(player.inventory || [])}</div>
    <div class="info-card"><h4>\u8fdb\u5ea6</h4>${listItems(playerProgress.map((track) => `${track.title || track.id}: ${track.value || track.progress || 0}/${track.max_value || track.target || "?"}`))}</div>
  `;
  if (dynamicSheetCards) {
    $("characterSheet").querySelector(".character-hero")?.insertAdjacentHTML("afterend", dynamicSheetCards);
  }

  const location = data.scene?.location || {};
  $("scenePanel").innerHTML = `
    ${card(location.name || location.id || "未知地点", location.summary || data.scene?.summary || "暂无地点摘要")}
    <div class="info-card"><h4>在场实体</h4><div class="pill-list">${(data.scene?.present_entities || []).map((id) => `<span class="pill">${escapeHtml(id)}</span>`).join("") || `<span class="pill">暂无</span>`}</div></div>
  `;

  const clocks = data.clocks || [];
  $("clockPanel").innerHTML = clocks.map((clock) => `
    <article class="info-card clock-card">
      <div class="card-heading">
        <h4>${escapeHtml(clock.title || clock.id)}</h4>
        ${statusBadge(clock.status)}
      </div>
      ${renderMeter("推进", clock.value ?? 0, clock.max_value ?? "?")}
      ${clock.stakes ? `<p class="card-note">${escapeHtml(clock.stakes)}</p>` : ""}
    </article>
  `).join("") || emptyNote("暂无公开时钟");

  $("npcPanel").innerHTML = (data.npcs || []).map((npc) =>
    `<article class="info-card npc-card">
      <div class="card-heading"><h4>${escapeHtml(npc.name || npc.id)}</h4><span class="status-badge active">在场</span></div>
      <p>${escapeHtml(text(npc.role, "身份未明"))}</p>
      <p class="card-note">记忆 ${escapeHtml(npc.memory_count || 0)} / 理解 ${escapeHtml(npc.understanding_count || 0)}</p>
    </article>`
  ).join("") || emptyNote("当前场景没有可见 NPC");

  const quests = data.quests || [];
  const questCards = quests.map((quest) => {
    const foundClues = (quest.clues || []).filter((clue) => clue.found);
    const extra = foundClues.length
      ? `<div class="card-subsection"><div class="muted">已发现线索</div>${listItems(foundClues.map((clue) => clue.text))}</div>`
      : "";
    return `<article class="info-card quest-card">
      <div class="card-heading"><h4>${escapeHtml(quest.title || quest.id)}</h4>${statusBadge(quest.status)}</div>
      <p>${escapeHtml(text(quest.pressure || quest.failure_consequence, "暂无压力记录"))}</p>
      ${extra}
    </article>`;
  });
  const openThreads = (data.open_threads || []).slice(-5).reverse().map((thread) => `
    <article class="info-card thread-card">
      <div class="card-heading"><h4>悬念</h4>${statusBadge(thread.status)}</div>
      <p>${escapeHtml(thread.description || thread.thread || thread.summary || thread.id)}</p>
      ${thread.next_pressure ? `<p class="card-note">下一步压力：${escapeHtml(thread.next_pressure)}</p>` : ""}
    </article>
  `);
  $("questPanel").innerHTML = [...questCards, ...openThreads].join("") || emptyNote("暂无任务或悬念");

  const knowledge = data.knowledge || {};
  const clueTexts = [
    ...(knowledge.clues_discovered || []).map((item) => item.text || item.id || item),
    ...(knowledge.facts_understood || []).map((item) => item.fact || item),
    ...(knowledge.locations_explored || []).map((item) => `${item.name || item.id}: ${item.notes || ""}`),
  ];
  $("knowledgePanel").innerHTML = clueTexts.length ? listItems(clueTexts) : emptyNote("尚未记录可见线索");
}

function renderResourceRows(rows) {
  if (!rows.length) return `<p class="empty-note">暂无记录</p>`;
  return `<ul class="resource-list">${rows.map(([key, value]) => `<li><span>${escapeHtml(key)}</span><span>${escapeHtml(Array.isArray(value) ? value.join("、") : value)}</span></li>`).join("")}</ul>`;
}

function renderMeter(label, value, maxValue, fillClass = "") {
  if (value === null || value === undefined || maxValue === null || maxValue === undefined) {
    return `<div class="meter-row"><div class="meter-label"><span>${escapeHtml(label)}</span><strong>未记录</strong></div><div class="meter"><span class="${fillClass}" style="width:0%"></span></div></div>`;
  }
  const current = Number(value || 0);
  const parsedMax = Number(maxValue);
  const hasNumericMax = Number.isFinite(parsedMax) && parsedMax > 0;
  const pct = hasNumericMax ? Math.max(0, Math.min(100, (current / parsedMax) * 100)) : 0;
  return `<div class="meter-row"><div class="meter-label"><span>${escapeHtml(label)}</span><strong>${escapeHtml(current)}/${escapeHtml(maxValue)}</strong></div><div class="meter"><span class="${fillClass}" style="width:${pct}%"></span></div></div>`;
}

async function loadConfig() {
  const config = await api("/api/config");
  rememberCampaign(localStorage.getItem(CAMPAIGN_KEY) || config.current_campaign || "");
  renderModeHint(config);
}

async function loadCampaigns() {
  const data = await api("/api/campaigns");
  state.campaigns = data.campaigns || [];
  $("campaignSelect").innerHTML = state.campaigns.length
    ? state.campaigns.map((campaign) =>
      `<option value="${escapeHtml(campaign.id)}">${escapeHtml(campaign.title)} / ${escapeHtml(campaign.current_time || "")}</option>`
    ).join("")
    : `<option value="">未找到战役</option>`;
  if (!state.campaigns.some((campaign) => campaign.id === state.currentCampaign)) {
    rememberCampaign(state.campaigns[0]?.id || "");
  }
  $("campaignSelect").value = state.currentCampaign;
  updateDeleteButton();
}

async function loadState(campaign = state.currentCampaign) {
  if (!campaign) {
    $("campaignTitle").textContent = "未选择战役";
    $("sceneTitle").textContent = "当前场景";
    $("campaignMeta").textContent = "";
    return;
  }
  const data = await api(`/api/state?campaign=${encodeURIComponent(campaign)}`);
  renderState(data);
  $("campaignSelect").value = data.campaign.root;
  await loadLogs();
}

async function submitTurn() {
  if (state.busy) return;
  const action = $("actionInput").value.trim();
  if (!action) {
    showToast("先输入玩家行动。", true);
    return;
  }
  const startedAt = Date.now();
  setBusy("AI 回合生成中...");
  $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card player-card"><h3>你</h3><p>${escapeHtml(action)}</p></article>`);
  $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card pending-card" id="pendingTurn"><h3>处理中</h3><p>正在调用 AI，并等待状态校验写回。</p></article>`);
  scrollNarrativeToEnd();
  try {
    const result = await api("/api/turn", {
      method: "POST",
      body: JSON.stringify({ campaign: state.currentCampaign, action }),
    });
    $("pendingTurn")?.remove();
    renderVisible(result.visible_text, result.rendered);
    renderState(result.state);
    if (result.apply_report?.errors?.length) {
      showToast(`patch 未写入: ${result.apply_report.errors.join("; ")}`, true);
    } else if (result.apply_report?.applied) {
      showToast("状态已校验并写入。");
    } else {
      showToast(`回合已生成，用时 ${Math.round((Date.now() - startedAt) / 1000)} 秒。`);
    }
  } catch (error) {
    $("pendingTurn")?.remove();
    showToast(error.message, true);
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card error-card"><h3>执行失败</h3><p>${escapeHtml(error.message)}</p></article>`);
    scrollNarrativeToEnd();
  } finally {
    setBusy("");
  }
}

async function createCampaign() {
  if (state.busy) return;
  const theme = $("themeInput").value.trim();
  if (!theme) {
    showToast("请输入世界观设定。", true);
    return;
  }
  setBusy("AI 生成中...");
  try {
    const result = await api("/api/campaigns/new", {
      method: "POST",
      body: JSON.stringify({ theme }),
    });
    rememberCampaign(result.campaign.id);
    await loadCampaigns();
    renderState(result.state);
    $("narrative").innerHTML = "";
    renderVisible({
      scene: result.campaign.opening_prompt || "新世界已经生成。",
      actionable_clues: ["观察周围", "确认自身状态", "寻找第一个可交谈对象"],
      check: "无",
    });
    $("themeInput").value = "";
    showToast("新世界已生成。");
  } catch (error) {
    showToast(error.message, true);
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card error-card"><h3>生成失败</h3><p>${escapeHtml(error.message)}</p></article>`);
  } finally {
    setBusy("");
  }
}

async function validateProject() {
  try {
    const result = await api("/api/validate", {
      method: "POST",
      body: JSON.stringify({ campaign: state.currentCampaign }),
    });
    showToast(result.ok ? "校验通过。" : "校验发现问题，详情已写入剧情区。", !result.ok);
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card tool-card"><h3>项目校验</h3><pre>${escapeHtml(result.stdout || result.stderr)}</pre></article>`);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function deleteCurrentCampaign() {
  const campaign = selectedCampaign();
  if (!campaign?.deletable) {
    showToast("只能删除生成的战役，内置示例战役会被保护。", true);
    return;
  }
  if (!window.confirm(`删除生成战役「${campaign.title}」?\n\n目录: ${campaign.path}`)) return;
  try {
    const result = await api("/api/campaigns/delete", {
      method: "POST",
      body: JSON.stringify({ campaign: campaign.id }),
    });
    state.campaigns = result.campaigns || [];
    rememberCampaign(result.next_campaign || "");
    await loadCampaigns();
    renderState(result.state);
    $("campaignSelect").value = state.currentCampaign;
    $("narrative").innerHTML = `<article class="gm-card tool-card"><h3>已删除战役</h3><p>${escapeHtml(campaign.title)}</p></article>`;
    showToast("生成战役已删除。");
  } catch (error) {
    showToast(error.message, true);
  }
}

async function exportObsidian() {
  try {
    const result = await api("/api/obsidian/export", {
      method: "POST",
      body: JSON.stringify({ campaign: state.currentCampaign }),
    });
    showToast(`已导出 Obsidian vault: ${result.notes} 个笔记`);
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card tool-card"><h3>Obsidian Vault</h3><p>${escapeHtml(result.vault)}</p><p>已生成 ${escapeHtml(result.notes)} 个 Markdown 笔记，可直接用 Obsidian 打开该文件夹。</p></article>`);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function rollDice() {
  try {
    const expression = window.prompt("骰子表达式", "1d20") || "1d20";
    const result = await api("/api/roll", {
      method: "POST",
      body: JSON.stringify({ expression }),
    });
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card dice-card"><h3>掷骰</h3><p>${escapeHtml(result.expression)} = ${escapeHtml(result.rolls.join(" + "))}${result.modifier ? escapeHtml(result.modifier > 0 ? ` + ${result.modifier}` : ` - ${Math.abs(result.modifier)}`) : ""} -> ${escapeHtml(result.total)}</p></article>`);
    scrollNarrativeToEnd();
  } catch (error) {
    showToast(error.message, true);
  }
}

function bindEvents() {
  $("refreshCampaigns").addEventListener("click", async () => {
    await loadCampaigns();
    await loadState(state.currentCampaign);
  });
  $("deleteCampaign").addEventListener("click", deleteCurrentCampaign);
  $("campaignSelect").addEventListener("change", async (event) => {
    rememberCampaign(event.target.value);
    await api("/api/campaigns/select", {
      method: "POST",
      body: JSON.stringify({ campaign: state.currentCampaign }),
    });
    await loadState(state.currentCampaign);
  });
  $("sendTurnButton").addEventListener("click", submitTurn);
  $("rollButton").addEventListener("click", rollDice);
  $("newCampaignButton").addEventListener("click", createCampaign);
  $("validateButton").addEventListener("click", validateProject);
  $("obsidianButton").addEventListener("click", exportObsidian);
}

async function boot() {
  bindEvents();
  await loadConfig();
  await loadCampaigns();
  await loadState(state.currentCampaign);
}

boot().catch((error) => showToast(error.message, true));
