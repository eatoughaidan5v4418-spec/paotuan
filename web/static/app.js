const state = {
  campaigns: [],
  currentCampaign: "",
  mock: false,
  serverMock: false,
  busy: false,
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
  toast.textContent = message;
  toast.className = `toast ${isError ? "error" : ""}`;
  setTimeout(() => toast.classList.add("hidden"), 3600);
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

function listItems(items) {
  if (!items || !items.length) return `<p class="muted">暂无</p>`;
  return `<ul>${items.map((item) => `<li>${escapeHtml(typeof item === "string" ? item : JSON.stringify(item))}</li>`).join("")}</ul>`;
}

function card(title, body, extra = "") {
  return `<article class="info-card"><h4>${escapeHtml(title)}</h4><p>${escapeHtml(body)}</p>${extra}</article>`;
}

function scrollNarrativeToEnd() {
  requestAnimationFrame(() => {
    const narrative = $("narrative");
    if (narrative) {
      narrative.scrollTo({ top: narrative.scrollHeight, behavior: "smooth" });
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
  $("sendTurnButton").textContent = message || (state.mock ? "执行 Mock 回合" : "执行回合");
  if (message) {
    $("apiStatus").textContent = message;
  } else {
    renderModeHint();
  }
}

function renderModeHint(config = null) {
  if (state.mock) {
    $("apiStatus").textContent = "Mock 演示模式";
    $("sendTurnButton").textContent = "执行 Mock 回合";
    $("newCampaignButton").textContent = "Mock 生成并进入";
    return;
  }
  const apiInfo = config?.api;
  if (apiInfo) {
    $("apiStatus").textContent = `${apiInfo.model || "未知模型"} / ${apiInfo.has_key ? "API 已配置" : "未配置 API Key"}`;
  } else if ($("apiStatus").textContent.includes("Mock")) {
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
    narrative.insertAdjacentHTML("beforeend", `<article class="gm-card"><p>${escapeHtml(rendered || visible || "")}</p></article>`);
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
  let html = `<article class="gm-card"><h3>GM 回合</h3>`;
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
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card"><h3>你</h3><p>${escapeHtml(entry.player_action)}</p></article>`);
  }
  if (entry.visible_text) {
    renderVisible(entry.visible_text, entry.rendered);
  } else if (entry.rendered) {
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card"><h3>GM 回合</h3><p>${escapeHtml(entry.rendered)}</p></article>`);
  }
}

async function loadLogs() {
  const data = await api("/api/logs");
  const logs = (data.logs || []).slice().reverse();
  $("narrative").innerHTML = "";
  if (!logs.length) {
    $("narrative").innerHTML = `<article class="gm-card"><h3>等待开团</h3><p>选择战役或生成新世界后，在下方输入玩家行动。</p></article>`;
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
    .filter(([key]) => key !== "id" && key !== "type")
    .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join("、") : value}`);
  const specialEffects = player.special_effects || [];

  $("characterSheet").innerHTML = `
    ${card(player.name || "玩家角色", `${text(player.realm)} / 灵根 ${text(player.spiritual_root)}`)}
    <div class="info-card">
      <h4>系统</h4>
      <p>等级 ${text(player.system_rank)} / 特效值 ${text(player.effect_points)}</p>
      <div class="pill-list">${specialEffects.map((v) => `<span class="pill">${escapeHtml(v)}</span>`).join("") || `<span class="pill">暂无特效</span>`}</div>
    </div>
    <div class="info-card">
      <h4>资源</h4>
      <p>生命 ${hp}/${maxHp}</p>
      <div class="meter"><span style="width:${Math.max(0, Math.min(100, hp / maxHp * 100))}%"></span></div>
      <p>灵力 ${qi}/${maxQi}</p>
      <div class="meter"><span style="width:${Math.max(0, Math.min(100, qi / maxQi * 100))}%"></span></div>
      ${resourceRows.length ? `<div class="gm-section">${listItems(resourceRows)}</div>` : ""}
    </div>
    <div class="info-card"><h4>属性</h4><div class="pill-list">${Object.entries(player.stats || {}).map(([k, v]) => `<span class="pill">${escapeHtml(k)} ${escapeHtml(v)}</span>`).join("") || `<span class="pill">暂无</span>`}</div></div>
    <div class="info-card"><h4>词条 / 状态</h4><div class="pill-list">${[...(player.traits || []), ...(player.conditions || [])].map((v) => `<span class="pill">${escapeHtml(v)}</span>`).join("") || `<span class="pill">暂无</span>`}</div></div>
    <div class="info-card"><h4>物品</h4>${listItems(player.inventory || [])}</div>
    <div class="info-card"><h4>进度</h4>${listItems(playerProgress.map((track) => `${track.title || track.id}: ${track.value || track.progress || 0}/${track.max_value || track.target || "?"}`))}</div>
  `;

  const location = data.scene?.location || {};
  $("scenePanel").innerHTML = `
    ${card(location.name || location.id || "未知地点", location.summary || data.scene?.summary || "暂无地点摘要")}
    <div class="info-card"><h4>在场实体</h4><div class="pill-list">${(data.scene?.present_entities || []).map((id) => `<span class="pill">${escapeHtml(id)}</span>`).join("") || `<span class="pill">暂无</span>`}</div></div>
    <div class="info-card"><h4>世界时钟</h4>${listItems((data.clocks || []).map((clock) => `${clock.title || clock.id}: ${clock.value || 0}/${clock.max_value || "?"}`))}</div>
  `;

  $("npcPanel").innerHTML = (data.npcs || []).map((npc) =>
    card(npc.name || npc.id, `${text(npc.role, "身份未明")} / 记忆 ${npc.memory_count || 0} / 理解 ${npc.understanding_count || 0}`)
  ).join("") || `<p class="muted">当前场景没有可见 NPC</p>`;

  const quests = data.quests || [];
  $("questPanel").innerHTML = quests.map((quest) => {
    const extra = quest.clues ? `<div class="gm-section"><div class="muted">线索</div>${listItems(quest.clues.map((clue) => `${clue.found ? "已发现" : "未发现"} / ${clue.text}`))}</div>` : "";
    return card(quest.title || quest.id, `${text(quest.status)} / ${text(quest.pressure || quest.failure_consequence)}`, extra);
  }).join("") || `<p class="muted">暂无任务</p>`;

  const knowledge = data.knowledge || {};
  const clueTexts = [
    ...(knowledge.clues_discovered || []).map((item) => item.text || item.id || item),
    ...(knowledge.facts_understood || []).map((item) => item.fact || item),
    ...(knowledge.locations_explored || []).map((item) => `${item.name || item.id}: ${item.notes || ""}`),
  ];
  $("knowledgePanel").innerHTML = listItems(clueTexts);
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
  const max = Number(maxValue || current || 1);
  const pct = Math.max(0, Math.min(100, (current / max) * 100));
  return `<div class="meter-row"><div class="meter-label"><span>${escapeHtml(label)}</span><strong>${escapeHtml(current)}/${escapeHtml(max)}</strong></div><div class="meter"><span class="${fillClass}" style="width:${pct}%"></span></div></div>`;
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
  const specialEffects = player.special_effects || [];
  const playerResources = (data.resources || []).find((item) => item.id === player.id) || {};
  const resourceRows = Object.entries(playerResources).filter(([key]) => key !== "id" && key !== "type");
  const playerProgress = (data.progress_tracks || []).filter((track) => {
    const scope = String(track.owner_id || track.entity_id || track.subject_id || track.id || "");
    return !scope || scope.includes(player.id || "pc_main") || scope.includes("player") || scope.includes("pc_") || scope.includes("system");
  }).slice(0, 4);
  const progressRows = playerProgress.map((track) => [
    track.title || track.id,
    `${track.value ?? track.progress ?? 0}/${track.max_value ?? track.target ?? "?"}`,
  ]);
  const statEntries = Object.entries(player.stats || {});

  $("characterSheet").innerHTML = `
    <article class="info-card character-hero">
      <div class="character-name">
        <strong>${escapeHtml(player.name || "玩家角色")}</strong>
        <span class="pill gold">${escapeHtml(player.realm || "境界未记录")}</span>
      </div>
      <p class="character-desc">${escapeHtml(player.description || `灵根 ${text(player.spiritual_root)}`)}</p>
    </article>
    <article class="info-card">
      <h4>系统</h4>
      <div class="sheet-grid">
        <div class="metric"><div class="metric-label">等级</div><div class="metric-value">${escapeHtml(text(player.system_rank))}</div></div>
        <div class="metric"><div class="metric-label">特效值</div><div class="metric-value">${escapeHtml(text(player.effect_points))}</div></div>
      </div>
      <div class="gm-section"><div class="pill-list">${specialEffects.map((v) => `<span class="pill gold">${escapeHtml(v)}</span>`).join("") || `<span class="pill">暂无特效</span>`}</div></div>
    </article>
    <article class="info-card">
      <h4>资源</h4>
      ${renderMeter("生命", player.health, player.max_health)}
      ${renderMeter("灵力", player.qi, player.max_qi, "gold-fill")}
      ${resourceRows.length ? renderResourceRows(resourceRows) : ""}
    </article>
    <article class="info-card">
      <h4>属性</h4>
      <div class="pill-list">${statEntries.map(([k, v]) => `<span class="pill">${escapeHtml(k)} ${escapeHtml(v)}</span>`).join("") || `<span class="pill">暂无</span>`}</div>
    </article>
    <article class="info-card">
      <h4>词条 / 状态</h4>
      <div class="pill-list">${[...(player.traits || []), ...(player.conditions || [])].map((v) => `<span class="pill">${escapeHtml(v)}</span>`).join("") || `<span class="pill">暂无</span>`}</div>
    </article>
    <article class="info-card"><h4>物品</h4>${listItems(player.inventory || [])}</article>
    <article class="info-card"><h4>进度</h4>${progressRows.length ? renderResourceRows(progressRows) : `<p class="empty-note">暂无记录</p>`}</article>
  `;

  const location = data.scene?.location || {};
  $("scenePanel").innerHTML = `
    ${card(location.name || location.id || "未知地点", location.summary || data.scene?.summary || "暂无地点摘要")}
    <div class="info-card"><h4>在场实体</h4><div class="pill-list">${(data.scene?.present_entities || []).map((id) => `<span class="pill">${escapeHtml(id)}</span>`).join("") || `<span class="pill">暂无</span>`}</div></div>
    <div class="info-card"><h4>世界时钟</h4>${listItems((data.clocks || []).map((clock) => `${clock.title || clock.id}: ${clock.value ?? 0}/${clock.max_value ?? "?"}`))}</div>
  `;

  $("npcPanel").innerHTML = (data.npcs || []).map((npc) =>
    card(npc.name || npc.id, `${text(npc.role, "身份未明")} / 记忆 ${npc.memory_count || 0} / 理解 ${npc.understanding_count || 0}`)
  ).join("") || `<p class="muted">当前场景没有可见 NPC</p>`;

  const quests = data.quests || [];
  const openThreads = (data.open_threads || []).map((thread) => ({
    id: thread.id,
    title: thread.description || thread.id,
    status: thread.status || "active",
    pressure: thread.next_pressure,
  }));
  $("questPanel").innerHTML = [...quests, ...openThreads].map((quest) => {
    const extra = quest.clues ? `<div class="gm-section"><div class="muted">线索</div>${listItems(quest.clues.map((clue) => `${clue.found ? "已发现" : "未发现"} / ${clue.text}`))}</div>` : "";
    return card(quest.title || quest.id, `${text(quest.status)} / ${text(quest.pressure || quest.failure_consequence)}`, extra);
  }).join("") || `<p class="muted">暂无任务</p>`;

  const knowledge = data.knowledge || {};
  const clueTexts = [
    ...(knowledge.clues_discovered || []).map((item) => item.text || item.id || item),
    ...(knowledge.facts_understood || []).map((item) => item.fact || item),
    ...(knowledge.locations_explored || []).map((item) => `${item.name || item.id}: ${item.notes || ""}`),
  ];
  $("knowledgePanel").innerHTML = listItems(clueTexts);
}

async function loadConfig() {
  const config = await api("/api/config");
  state.serverMock = Boolean(config.mock);
  state.mock = Boolean(config.mock);
  rememberCampaign(localStorage.getItem(CAMPAIGN_KEY) || config.current_campaign || "");
  $("mockToggle").checked = state.mock;
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
  setBusy(state.mock ? "Mock 回合生成中..." : "AI 回合生成中...");
  $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card"><h3>你</h3><p>${escapeHtml(action)}</p></article>`);
  $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card" id="pendingTurn"><h3>处理中</h3><p>${state.mock ? "正在生成本地演示回合。" : "正在调用 AI，并等待状态校验写回。"}</p></article>`);
  scrollNarrativeToEnd();
  try {
    const result = await api("/api/turn", {
      method: "POST",
      body: JSON.stringify({ campaign: state.currentCampaign, action, mock: state.mock }),
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
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card"><h3>执行失败</h3><p>${escapeHtml(error.message)}</p></article>`);
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
  setBusy(state.mock ? "Mock 生成中..." : "AI 生成中...");
  try {
    const result = await api("/api/campaigns/new", {
      method: "POST",
      body: JSON.stringify({ theme, mock: state.mock }),
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
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card"><h3>生成失败</h3><p>${escapeHtml(error.message)}</p></article>`);
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
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card"><h3>项目校验</h3><pre>${escapeHtml(result.stdout || result.stderr)}</pre></article>`);
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
    $("narrative").innerHTML = `<article class="gm-card"><h3>已删除战役</h3><p>${escapeHtml(campaign.title)}</p></article>`;
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
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card"><h3>Obsidian Vault</h3><p>${escapeHtml(result.vault)}</p><p>已生成 ${escapeHtml(result.notes)} 个 Markdown 笔记，可直接用 Obsidian 打开该文件夹。</p></article>`);
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
    $("narrative").insertAdjacentHTML("beforeend", `<article class="gm-card"><h3>掷骰</h3><p>${escapeHtml(result.expression)} = ${escapeHtml(result.rolls.join(" + "))}${result.modifier ? escapeHtml(result.modifier > 0 ? ` + ${result.modifier}` : ` - ${Math.abs(result.modifier)}`) : ""} -> ${escapeHtml(result.total)}</p></article>`);
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
  $("mockToggle").addEventListener("change", (event) => {
    state.mock = event.target.checked;
    renderModeHint();
    showToast(state.mock ? "已切换到 Mock 演示模式。" : "已切换到真实 API 模式。");
  });
}

async function boot() {
  bindEvents();
  await loadConfig();
  await loadCampaigns();
  await loadState(state.currentCampaign);
}

boot().catch((error) => showToast(error.message, true));
