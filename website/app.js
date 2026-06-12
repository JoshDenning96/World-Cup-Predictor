const DATA_URL = "data/master_simulation.json";
const GROUP_SCHEDULE_URL = "data/group_schedule.json";
const API_RUN_URL = "/api/run_simulation";
const API_SAVE_ACTUAL_URL = "/api/save_actual";
const API_ACTUAL_RESULTS_URL = "/api/actual_results";
const API_HISTORY_URL = "/api/simulation_history";
let state = {};
let simulationMode = 'full'; // 'full' | 'actuals'
let actualResultsCache = {}; // keyed by String(match_number)
let groupScheduleCache = []; // loaded once on startup
let _actualsActiveTab = 'Group A';

// FIFA/schedule names → simulation dataset names.
// The group schedule uses official FIFA names; the simulation uses its own variants.
const SCHEDULE_TO_SIM_NAME = {
  'Czechia': 'Czech Republic',
  'Korea Republic': 'South Korea',
  'Türkiye': 'Turkey',
  'IR Iran': 'Iran',
  'USA': 'United States',
  'Cabo Verde': 'Cape Verde',
  "Côte d'Ivoire": "Cote d'Ivoire",
  'Congo DR': 'DR Congo',
  'Austria': 'Austria',  // present in actuals (Group J) but not in sim — keep as-is
};
function toSimName(name) { return SCHEDULE_TO_SIM_NAME[name] || name; }

// Order of 1st-place group slots in the r32_third_place_assignments.json value arrays.
// Columns per the FIFA 2026 third-place table header: 1A, 1B, 1D, 1E, 1G, 1I, 1K, 1L
const _R32_WINNER_GROUP_ORDER = ['A', 'B', 'D', 'E', 'G', 'I', 'K', 'L'];

// Derive the visual R32 bracket order (left half then right half) by traversing the
// knockout_schedule tree from the Final down to each R32 leaf.
function buildBracketOrder(schedule) {
  const byMatch = {};
  schedule.forEach((m) => { byMatch[m.match_number] = m; });

  const parseFeeder = (s) => { const m = /^W(\d+)$/.exec(String(s)); return m ? Number(m[1]) : null; };

  function leavesOf(matchNum) {
    const match = byMatch[matchNum];
    if (!match || match.round === 'Round of 32') return [matchNum];
    const h = parseFeeder(match.home), a = parseFeeder(match.away);
    return [...(h ? leavesOf(h) : []), ...(a ? leavesOf(a) : [])];
  }

  const finalMatch = schedule.find((m) => m.round === 'Finals');
  if (!finalMatch) return null;
  const lsf = parseFeeder(finalMatch.home), rsf = parseFeeder(finalMatch.away);
  if (!lsf || !rsf) return null;
  return [...leavesOf(lsf), ...leavesOf(rsf)];
}

function replaceElement(el) {
  if (!el || !el.parentNode) return el;
  const clone = el.cloneNode(false);
  el.parentNode.replaceChild(clone, el);
  return clone;
}

function setSimulationStatus(text) {
  const status = document.getElementById("simulation-status");
  if (status) status.textContent = text;
  const actualsStatus = document.getElementById("actuals-sim-status");
  if (actualsStatus) actualsStatus.textContent = text;
}

const ACTUALS_STORAGE_KEY = 'wc2026_actual_results';

function persistActualsToStorage() {
  try {
    localStorage.setItem(ACTUALS_STORAGE_KEY, JSON.stringify(Object.values(actualResultsCache)));
  } catch (_) {}
}

async function loadActualResults() {
  // Primary: localStorage (survives page refresh, works without server restart)
  try {
    const raw = localStorage.getItem(ACTUALS_STORAGE_KEY);
    if (raw) {
      const items = JSON.parse(raw);
      actualResultsCache = {};
      items.forEach((item) => { actualResultsCache[String(item.match_number)] = item; });
    }
  } catch (_) {}

  // Secondary: server file (picks up results saved in a previous session)
  try {
    const resp = await fetch(API_ACTUAL_RESULTS_URL);
    if (resp.ok) {
      const items = await resp.json();
      if (items.length > 0) {
        items.forEach((item) => { actualResultsCache[String(item.match_number)] = item; });
        persistActualsToStorage();
      }
    }
  } catch (_) {}

  refreshActualsPanelInputs();
}

function saveActualResult(matchNumber, homeGoals, awayGoals) {
  actualResultsCache[String(matchNumber)] = { match_number: matchNumber, home_goals: homeGoals, away_goals: awayGoals };
  persistActualsToStorage();
  refreshActualMatchStatus(matchNumber);
  refreshGroupTableIfVisible();
  // Best-effort server persist; failures are fine since localStorage is authoritative
  fetch(API_SAVE_ACTUAL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ match_number: matchNumber, home_goals: homeGoals, away_goals: awayGoals }),
  }).catch(() => {});
}

function deleteActualResult(matchNumber) {
  delete actualResultsCache[String(matchNumber)];
  persistActualsToStorage();
  refreshActualMatchStatus(matchNumber);
  refreshGroupTableIfVisible();
}

function refreshGroupTableIfVisible() {
  if (!state.group_tables) return;
  const select = document.getElementById('group-select');
  if (select && select.value) renderGroupTable(state, select.value);
}

function refreshActualMatchStatus(matchNumber) {
  const row = document.querySelector(`[data-match-number="${matchNumber}"]`);
  if (!row) return;
  const indicator = row.querySelector('.actual-indicator');
  if (!indicator) return;
  const saved = actualResultsCache[String(matchNumber)];
  indicator.textContent = saved ? '✓' : '';
  indicator.style.color = saved ? '#4ade80' : 'transparent';
  row.style.background = saved ? 'rgba(74,222,128,0.06)' : '';
}

function refreshActualsPanelInputs() {
  const panel = document.getElementById('actuals-panel');
  if (!panel) return;
  Object.keys(actualResultsCache).forEach((mn) => {
    const saved = actualResultsCache[mn];
    const row = panel.querySelector(`[data-match-number="${mn}"]`);
    if (!row) return;
    const homeInput = row.querySelector('.actual-home-goals');
    const awayInput = row.querySelector('.actual-away-goals');
    if (homeInput && homeInput.value === '') homeInput.value = String(saved.home_goals);
    if (awayInput && awayInput.value === '') awayInput.value = String(saved.away_goals);
    refreshActualMatchStatus(Number(mn));
  });
}

// --- Team name resolution for knockout slots ---

function computeActualGroupStandings() {
  const pts = {}, gf = {}, ga = {};
  groupScheduleCache.forEach((m) => {
    const ar = actualResultsCache[String(m.match_number)];
    if (!ar) return;
    const g = m.group;
    const home = toSimName(m.home_team), away = toSimName(m.away_team);
    [home, away].forEach((t) => {
      if (!pts[g]) { pts[g] = {}; gf[g] = {}; ga[g] = {}; }
      pts[g][t] = pts[g][t] || 0;
      gf[g][t] = gf[g][t] || 0;
      ga[g][t] = ga[g][t] || 0;
    });
    const hg = ar.home_goals, ag = ar.away_goals;
    gf[g][home] += hg; ga[g][home] += ag;
    gf[g][away] += ag; ga[g][away] += hg;
    if (hg > ag) pts[g][home] += 3;
    else if (ag > hg) pts[g][away] += 3;
    else { pts[g][home] += 1; pts[g][away] += 1; }
  });
  const result = {};
  Object.keys(pts).forEach((g) => {
    result[g] = Object.keys(pts[g]).sort((a, b) => {
      const pd = pts[g][b] - pts[g][a];
      if (pd !== 0) return pd;
      const gdd = (gf[g][b] - ga[g][b]) - (gf[g][a] - ga[g][a]);
      if (gdd !== 0) return gdd;
      return gf[g][b] - gf[g][a];
    });
  });
  return result;
}

function simulationGroupRank(letter, pos) {
  if (!state.group_tables || !state.group_tables.length) return null;
  const rows = state.group_tables
    .filter((r) => r.group === letter || r.group === `Group ${letter}`)
    .sort((a, b) => (a.expected_rank || 99) - (b.expected_rank || 99));
  return rows[pos] ? rows[pos].team : null;
}

function computeThirdPlaceQualifiers() {
  // Build per-group stats from entered actuals (all teams initialised, even without results)
  const groupStats = {};
  groupScheduleCache.forEach((m) => {
    const g = m.group.replace(/^Group\s+/i, '').trim();
    const home = toSimName(m.home_team), away = toSimName(m.away_team);
    if (!groupStats[g]) groupStats[g] = {};
    [home, away].forEach((t) => {
      if (!groupStats[g][t]) groupStats[g][t] = { pts: 0, gf: 0, ga: 0 };
    });
    const ar = actualResultsCache[String(m.match_number)];
    if (!ar) return;
    const hg = Number(ar.home_goals), ag = Number(ar.away_goals);
    groupStats[g][home].gf += hg; groupStats[g][home].ga += ag;
    groupStats[g][away].gf += ag; groupStats[g][away].ga += hg;
    if (hg > ag) groupStats[g][home].pts += 3;
    else if (ag > hg) groupStats[g][away].pts += 3;
    else { groupStats[g][home].pts += 1; groupStats[g][away].pts += 1; }
  });

  // Get 3rd-place team per group — only for groups that have at least one actual result.
  // Groups with zero actuals would produce alphabetically-sorted placeholder teams which
  // would duplicate with simulation-predicted group winners/runners-up in the bracket.
  const groupsWithActuals = new Set(
    groupScheduleCache
      .filter((m) => actualResultsCache[String(m.match_number)])
      .map((m) => m.group.replace(/^Group\s+/i, '').trim())
  );

  const thirdPlaceTeams = [];
  Object.keys(groupStats).forEach((g) => {
    if (!groupsWithActuals.has(g)) return;
    const ranked = Object.keys(groupStats[g]).sort((a, b) => {
      const sa = groupStats[g][a], sb = groupStats[g][b];
      if (sb.pts !== sa.pts) return sb.pts - sa.pts;
      const gda = sa.gf - sa.ga, gdb = sb.gf - sb.ga;
      if (gdb !== gda) return gdb - gda;
      if (sb.gf !== sa.gf) return sb.gf - sa.gf;
      return a.localeCompare(b);
    });
    if (ranked.length >= 3) {
      const team = ranked[2];
      const s = groupStats[g][team];
      thirdPlaceTeams.push({ team, group: g, pts: s.pts, gd: s.gf - s.ga, gf: s.gf });
    }
  });

  // Rank all third-place teams by FIFA criteria: pts → GD → GF → alphabetical
  thirdPlaceTeams.sort((a, b) => {
    if (b.pts !== a.pts) return b.pts - a.pts;
    if (b.gd !== a.gd) return b.gd - a.gd;
    if (b.gf !== a.gf) return b.gf - a.gf;
    return a.team.localeCompare(b.team);
  });

  // Collect the 8 third-place slots from the knockout schedule
  const thirdPlaceSlots = [];
  (state.knockout_schedule || []).forEach((m) => {
    ['home', 'away'].forEach((side) => {
      const mx = /^3([A-L]+)$/.exec(m[side] || '');
      if (mx) thirdPlaceSlots.push({ slot: m[side], groups: new Set(mx[1].split('')) });
    });
  });
  if (thirdPlaceSlots.length === 0) return {};

  const qualifiers = thirdPlaceTeams.slice(0, thirdPlaceSlots.length);
  if (qualifiers.length === 0) return {};

  // Bipartite matching: assign each qualifier to exactly one slot whose groups contain their group
  const nSlots = thirdPlaceSlots.length, nQuals = qualifiers.length;
  const adj = thirdPlaceSlots.map((s) =>
    qualifiers.reduce((acc, q, j) => { if (s.groups.has(q.group)) acc.push(j); return acc; }, [])
  );
  const matchSlot = new Array(nSlots).fill(-1);
  const matchQual = new Array(nQuals).fill(-1);

  function augment(si, vis) {
    for (const qi of adj[si]) {
      if (!vis[qi]) {
        vis[qi] = true;
        if (matchQual[qi] === -1 || augment(matchQual[qi], vis)) {
          matchSlot[si] = qi; matchQual[qi] = si; return true;
        }
      }
    }
    return false;
  }
  for (let i = 0; i < nSlots; i++) augment(i, new Array(nQuals).fill(false));

  const result = {};
  thirdPlaceSlots.forEach((s, i) => {
    const qi = matchSlot[i];
    if (qi >= 0) result[s.slot] = qualifiers[qi].team;
  });
  return result;
}

function resolveKnockoutSlot(slot, groupStandings, knockoutResolved, thirdPlaceAssignment) {
  if (!slot) return slot;

  // 1A / 2B — group winner or runner-up
  const m12 = /^([12])([A-L])$/.exec(slot);
  if (m12) {
    const pos = parseInt(m12[1]) - 1;
    const letter = m12[2];
    const posLabel = pos === 0 ? 'Winner' : 'Runner-up';
    const gKey = Object.keys(groupStandings).find((k) => k === `Group ${letter}` || k.endsWith(` ${letter}`));
    if (gKey && groupStandings[gKey]?.[pos]) return groupStandings[gKey][pos];
    const simTeam = simulationGroupRank(letter, pos);
    if (simTeam) return simTeam;
    return `Group ${letter} ${posLabel}`;
  }

  // 3ABCDF — best third-place qualifier from those groups
  const m3 = /^3([A-L]+)$/.exec(slot);
  if (m3) {
    if (thirdPlaceAssignment?.[slot]) return thirdPlaceAssignment[slot];
    return `Best 3rd (${m3[1].split('').join('/')})`;
  }

  // W74 — winner of match 74
  const mw = /^W(\d+)$/.exec(slot);
  if (mw) {
    const mn = mw[1];
    const res = knockoutResolved[mn];
    if (res) {
      if (res.winner) return res.winner;
      const h = res.home_team, a = res.away_team;
      const looksResolved = (t) => t && !/^[123W]/.test(t) && !/^(Group|Best|Winner|Runner)/.test(t);
      if (looksResolved(h) && looksResolved(a)) return `${h} / ${a}`;
      if (looksResolved(h)) return h;
    }
    return `W Match ${mn}`;
  }

  // RU74 — runner-up (loser) of match 74 (used for third-place play-off)
  const mru = /^RU(\d+)$/.exec(slot);
  if (mru) {
    const mn = mru[1];
    const res = knockoutResolved[mn];
    if (res?.winner) {
      const loser = res.winner === res.home_team ? res.away_team : res.home_team;
      if (loser) return loser;
    }
    return `RU Match ${mn}`;
  }

  return slot;
}

function buildKnockoutResolution() {
  const groupStandings = computeActualGroupStandings();
  const thirdPlaceAssignment = computeThirdPlaceQualifiers();
  const byMn = {};
  (state.knockout_schedule || []).forEach((m) => { byMn[String(m.match_number)] = m; });
  const resolved = {};

  function resolveMatch(mn) {
    if (resolved[mn]) return;
    const m = byMn[mn];
    if (!m) return;
    const home = resolveKnockoutSlot(m.home, groupStandings, resolved, thirdPlaceAssignment);
    const away = resolveKnockoutSlot(m.away, groupStandings, resolved, thirdPlaceAssignment);
    const ar = actualResultsCache[mn];
    let winner = null;
    if (ar) {
      if (ar.winner === 'home') winner = home;
      else if (ar.winner === 'away') winner = away;
      else if (Number(ar.home_goals) > Number(ar.away_goals)) winner = home;
      else if (Number(ar.away_goals) > Number(ar.home_goals)) winner = away;
    }
    resolved[mn] = { home_team: home, away_team: away, winner };
  }

  (state.knockout_schedule || [])
    .slice().sort((a, b) => a.match_number - b.match_number)
    .forEach((m) => resolveMatch(String(m.match_number)));

  return resolved;
}

// --- Panel row builders ---

function matchRow(mn, homeLabel, awayLabel, dateStr, isKnockout) {
  const saved = actualResultsCache[String(mn)];
  const inputStyle = 'width:36px;text-align:center;padding:2px 4px;border-radius:4px;border:1px solid rgba(255,255,255,0.15);background:rgba(15,23,42,0.8);color:#f8fafc;font-size:12px;';

  if (isKnockout) {
    const winnerVal = saved ? (saved.winner || (saved.home_goals > saved.away_goals ? 'home' : saved.away_goals > saved.home_goals ? 'away' : '')) : '';
    const homeActive = winnerVal === 'home';
    const awayActive = winnerVal === 'away';
    const btnBase = 'padding:4px 10px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid;transition:background 0.15s;';
    const homeBtn = `<button type="button" class="ko-winner-btn" data-side="home" style="${btnBase}${homeActive ? 'background:rgba(74,222,128,0.2);border-color:rgba(74,222,128,0.5);color:#4ade80;' : 'background:rgba(255,255,255,0.04);border-color:rgba(255,255,255,0.1);color:#94a3b8;'}">${homeLabel}</button>`;
    const awayBtn = `<button type="button" class="ko-winner-btn" data-side="away" style="${btnBase}${awayActive ? 'background:rgba(74,222,128,0.2);border-color:rgba(74,222,128,0.5);color:#4ade80;' : 'background:rgba(255,255,255,0.04);border-color:rgba(255,255,255,0.1);color:#94a3b8;'}">${awayLabel}</button>`;
    const tick = winnerVal ? '✓' : '';
    return `<tr data-match-number="${mn}" data-knockout="1" style="${winnerVal ? 'background:rgba(74,222,128,0.04);' : ''}">
      <td style="padding:6px 6px;color:#64748b;font-size:11px;white-space:nowrap;">${dateStr}</td>
      <td colspan="3" style="padding:6px 8px;">
        <div style="display:flex;align-items:center;gap:10px;">
          ${homeBtn}
          <span style="color:#475569;font-size:11px;">vs</span>
          ${awayBtn}
        </div>
      </td>
      <td style="padding:6px 6px;text-align:center;font-size:13px;color:#4ade80;">${tick}</td>
    </tr>`;
  }

  const hVal = saved != null ? saved.home_goals : '';
  const aVal = saved != null ? saved.away_goals : '';
  const bg = saved ? 'rgba(74,222,128,0.06)' : '';
  const tick = saved ? '✓' : '';
  return `<tr data-match-number="${mn}" data-knockout="0" style="background:${bg};">
    <td style="padding:4px 6px;color:#64748b;font-size:11px;white-space:nowrap;">${dateStr}</td>
    <td style="padding:4px 6px;text-align:right;font-weight:600;font-size:12px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${homeLabel}">${homeLabel}</td>
    <td style="padding:4px 8px;white-space:nowrap;text-align:center;">
      <input class="actual-home-goals" type="number" min="0" max="20" value="${hVal}" placeholder="–" style="${inputStyle}" />
      <span style="margin:0 4px;color:#64748b;">:</span>
      <input class="actual-away-goals" type="number" min="0" max="20" value="${aVal}" placeholder="–" style="${inputStyle}" />
    </td>
    <td style="padding:4px 6px;font-weight:600;font-size:12px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${awayLabel}">${awayLabel}</td>
    <td style="padding:4px 6px;text-align:center;font-size:13px;color:#4ade80;" class="actual-indicator">${tick}</td>
  </tr>`;
}

const KO_ROUND_ORDER = ['Round of 32', 'Round of 16', 'Quarter Finals', 'Semi Finals', 'Finals'];
const KO_ROUND_LABEL = { 'Round of 32': 'R32', 'Round of 16': 'R16', 'Quarter Finals': 'QF', 'Semi Finals': 'SF', 'Finals': 'Final' };

function _actualsTabCounts() {
  const counts = {};
  (groupScheduleCache || []).forEach((m) => {
    const g = m.group || 'Unknown';
    if (!counts[g]) counts[g] = { total: 0, entered: 0 };
    counts[g].total++;
    if (actualResultsCache[String(m.match_number)]) counts[g].entered++;
  });
  const ko = state.knockout_schedule || [];
  ko.forEach((m) => {
    const r = m.round;
    if (!counts[r]) counts[r] = { total: 0, entered: 0 };
    counts[r].total++;
    if (actualResultsCache[String(m.match_number)]) counts[r].entered++;
  });
  return counts;
}

function renderActualsTabs() {
  const bar = document.getElementById('actuals-tabs-bar');
  if (!bar) return;
  const counts = _actualsTabCounts();
  const groups = Object.keys(counts).filter(k => !KO_ROUND_ORDER.includes(k)).sort();
  const koRounds = KO_ROUND_ORDER.filter(r => counts[r]);
  const tabs = [...groups, ...koRounds];
  if (!tabs.includes(_actualsActiveTab)) _actualsActiveTab = tabs[0] || 'Group A';

  bar.innerHTML = tabs.map((tab) => {
    const c = counts[tab] || { total: 0, entered: 0 };
    const isActive = tab === _actualsActiveTab;
    const allDone = c.total > 0 && c.entered === c.total;
    const label = KO_ROUND_LABEL[tab] ?? tab.replace('Group ', '');
    const badge = c.total > 0
      ? `<span style="display:inline-block;margin-left:4px;font-size:9px;padding:0 4px;border-radius:8px;background:${allDone ? 'rgba(74,222,128,0.25)' : 'rgba(255,255,255,0.08)'};color:${allDone ? '#4ade80' : '#94a3b8'};">${c.entered}/${c.total}</span>`
      : '';
    const activeStyle = isActive
      ? 'background:rgba(124,58,237,0.35);border-color:rgba(167,139,250,0.6);color:#e0d9ff;'
      : 'background:rgba(255,255,255,0.04);border-color:rgba(255,255,255,0.1);color:#94a3b8;';
    return `<button type="button" data-tab="${tab}" style="padding:5px 10px;border-radius:7px;border:1px solid;font-size:12px;font-weight:600;cursor:pointer;white-space:nowrap;${activeStyle}">${label}${badge}</button>`;
  }).join('');

  bar.querySelectorAll('button[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => {
      _actualsActiveTab = btn.dataset.tab;
      rebuildActualsPanel();
    });
  });
}

function buildActualsPanel(groupSchedule, activeTab) {
  if (!groupSchedule || groupSchedule.length === 0) {
    return '<p style="color:#94a3b8;font-size:13px;">Group schedule not available. Run a simulation to load it.</p>';
  }

  if (KO_ROUND_ORDER.includes(activeTab)) {
    const knockoutSchedule = state.knockout_schedule || [];
    if (!knockoutSchedule.length) return '<p style="color:#94a3b8;font-size:13px;">Knockout schedule not yet available.</p>';
    const resolved = buildKnockoutResolution();
    const matches = knockoutSchedule.filter(m => m.round === activeTab);
    if (!matches.length) return '<p style="color:#94a3b8;font-size:13px;">No matches found for this round.</p>';
    const rows = matches.map((m) => {
      const res = resolved[String(m.match_number)] || {};
      const dateStr = m.date ? m.date.split(' ')[0] : '';
      return matchRow(m.match_number, res.home_team || m.home, res.away_team || m.away, dateStr, true);
    }).join('');
    return `<table style="width:100%;border-collapse:collapse;"><tbody>${rows}</tbody></table>`;
  }

  // Group tab
  const matches = groupSchedule.filter((m) => (m.group || 'Unknown') === activeTab);
  if (!matches.length) return '<p style="color:#94a3b8;font-size:13px;">No matches found for this group.</p>';
  const rows = matches.map((m) => {
    const dateStr = m.date ? m.date.split(' ')[0] : '';
    return matchRow(m.match_number, m.home_team, m.away_team, dateStr, false);
  }).join('');
  return `<table style="width:100%;border-collapse:collapse;"><tbody>${rows}</tbody></table>`;
}

function injectSimulationModeControls() {
  const controls = document.querySelector('.simulation-controls');
  if (!controls || document.getElementById('simulation-mode-select')) return;

  const modeLabel = document.createElement('label');
  modeLabel.setAttribute('for', 'simulation-mode-select');
  modeLabel.textContent = 'Mode';
  modeLabel.style.cssText = 'font-size:0.95rem;color:#e2e8f0;';

  const modeSelect = document.createElement('select');
  modeSelect.id = 'simulation-mode-select';
  modeSelect.innerHTML = `
    <option value="full">Full simulation</option>
    <option value="actuals">Actuals + simulation</option>
  `;
  modeSelect.value = simulationMode;
  modeSelect.style.cssText = 'min-width:180px;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.18);background:rgba(15,23,42,0.85);color:#f8fafc;';

  const labelInput = document.createElement('input');
  labelInput.type = 'text';
  labelInput.id = 'simulation-label';
  labelInput.placeholder = 'Run label (e.g. Group MD1)';
  labelInput.maxLength = 80;
  labelInput.style.cssText = 'min-width:180px;padding:8px 10px;border-radius:8px;border:1px solid rgba(255,255,255,0.18);background:rgba(15,23,42,0.85);color:#f8fafc;font-size:0.95rem;';

  const runBtn = document.getElementById('simulation-run-button');
  controls.insertBefore(modeLabel, runBtn);
  controls.insertBefore(modeSelect, runBtn);
  controls.insertBefore(labelInput, runBtn);

  // Panel
  const actualsPanel = document.createElement('div');
  actualsPanel.id = 'actuals-panel';
  actualsPanel.style.cssText = 'display:none;margin-top:16px;padding:16px 20px;border-radius:14px;background:rgba(15,23,42,0.7);border:1px solid rgba(255,255,255,0.08);max-height:480px;overflow-y:auto;';

  // Header row with title + reset button
  const headerRow = document.createElement('div');
  headerRow.style.cssText = 'display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;';
  const panelTitle = document.createElement('div');
  panelTitle.style.cssText = 'font-weight:700;font-size:14px;color:#c7d2fe;';
  panelTitle.textContent = 'Enter actual match results';
  const resetBtn = document.createElement('button');
  resetBtn.type = 'button';
  resetBtn.textContent = 'Reset all results';
  resetBtn.style.cssText = 'padding:4px 10px;font-size:12px;border-radius:6px;border:1px solid rgba(252,165,165,0.4);background:rgba(252,165,165,0.08);color:#fca5a5;cursor:pointer;';
  resetBtn.addEventListener('click', async () => {
    if (!confirm('Clear all entered match results?')) return;
    actualResultsCache = {};
    persistActualsToStorage();
    rebuildActualsPanel();
    try {
      await fetch('/api/clear_actuals', { method: 'POST' });
    } catch (_) {}
  });
  headerRow.appendChild(panelTitle);
  headerRow.appendChild(resetBtn);
  actualsPanel.appendChild(headerRow);

  const panelHelp = document.createElement('p');
  panelHelp.style.cssText = 'font-size:12px;color:#64748b;margin:0 0 10px;';
  panelHelp.textContent = 'Scores saved on blur or Enter. For knockout draws, use the Winner selector to pick who advanced.';
  actualsPanel.appendChild(panelHelp);

  const tabsBar = document.createElement('div');
  tabsBar.id = 'actuals-tabs-bar';
  tabsBar.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;';
  actualsPanel.appendChild(tabsBar);

  const panelBody = document.createElement('div');
  panelBody.id = 'actuals-panel-body';
  actualsPanel.appendChild(panelBody);

  // Footer: run button + status + progress bar
  const panelFooter = document.createElement('div');
  panelFooter.style.cssText = 'margin-top:14px;display:flex;flex-direction:column;gap:6px;';

  const footerTop = document.createElement('div');
  footerTop.style.cssText = 'display:flex;align-items:center;gap:12px;';

  const actualsRunBtn = document.createElement('button');
  actualsRunBtn.id = 'actuals-run-button';
  actualsRunBtn.type = 'button';
  actualsRunBtn.textContent = 'Run simulation';
  actualsRunBtn.style.cssText = 'padding:8px 18px;border-radius:8px;background:rgba(99,102,241,0.85);color:#fff;font-weight:700;font-size:13px;border:1px solid rgba(99,102,241,0.5);cursor:pointer;';

  const actualsStatusEl = document.createElement('span');
  actualsStatusEl.id = 'actuals-sim-status';
  actualsStatusEl.style.cssText = 'font-size:12px;color:#94a3b8;';

  footerTop.appendChild(actualsRunBtn);
  footerTop.appendChild(actualsStatusEl);

  const actualsProgressContainer = document.createElement('div');
  actualsProgressContainer.id = 'actuals-progress-container';
  actualsProgressContainer.className = 'simulation-progress-container';

  const actualsProgressFill = document.createElement('div');
  actualsProgressFill.id = 'actuals-progress-fill';
  actualsProgressFill.className = 'simulation-progress-fill';
  actualsProgressContainer.appendChild(actualsProgressFill);

  panelFooter.appendChild(footerTop);
  panelFooter.appendChild(actualsProgressContainer);
  actualsPanel.appendChild(panelFooter);

  controls.parentNode.insertBefore(actualsPanel, controls.nextSibling);

  modeSelect.addEventListener('change', () => {
    simulationMode = modeSelect.value;
    actualsPanel.style.display = simulationMode === 'actuals' ? 'block' : 'none';
    if (simulationMode === 'actuals') {
      rebuildActualsPanel();
    }
  });
}

function rebuildActualsPanel() {
  const panelBody = document.getElementById('actuals-panel-body');
  if (!panelBody) return;
  renderActualsTabs();
  panelBody.innerHTML = buildActualsPanel(groupScheduleCache, _actualsActiveTab);
  attachActualInputListeners();
}

function attachActualInputListeners() {
  const panel = document.getElementById('actuals-panel');
  if (!panel) return;

  panel.querySelectorAll('tr[data-match-number]').forEach((row) => {
    const mn = Number(row.dataset.matchNumber);
    const isKnockout = row.dataset.knockout === '1';

    if (isKnockout) {
      row.querySelectorAll('.ko-winner-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const side = btn.dataset.side;
          const prev = actualResultsCache[String(mn)];
          if (prev && prev.winner === side) {
            // clicking the active winner clears it
            deleteActualResult(mn);
          } else {
            actualResultsCache[String(mn)] = { match_number: mn, home_goals: 0, away_goals: 0, winner: side };
            persistActualsToStorage();
            fetch(API_SAVE_ACTUAL_URL, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ match_number: mn, home_goals: 0, away_goals: 0, winner: side }),
            }).catch(() => {});
          }
          rebuildActualsPanel();
        });
      });
      return;
    }

    const homeInput = row.querySelector('.actual-home-goals');
    const awayInput = row.querySelector('.actual-away-goals');
    if (!homeInput || !awayInput) return;

    const trySave = () => {
      const hv = homeInput.value.trim();
      const av = awayInput.value.trim();
      if (hv === '' && av === '') { deleteActualResult(mn); return; }
      const hg = parseInt(hv, 10);
      const ag = parseInt(av, 10);
      if (!Number.isNaN(hg) && !Number.isNaN(ag) && hg >= 0 && ag >= 0) {
        actualResultsCache[String(mn)] = { match_number: mn, home_goals: hg, away_goals: ag };
        persistActualsToStorage();
        refreshActualMatchStatus(mn);
        fetch(API_SAVE_ACTUAL_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ match_number: mn, home_goals: hg, away_goals: ag }),
        }).catch(() => {});
      }
    };

    homeInput.addEventListener('blur', trySave);
    awayInput.addEventListener('blur', trySave);
    homeInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') awayInput.focus(); });
    awayInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { trySave(); awayInput.blur(); } });
  });
}

function formatPercent(value) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatNumber(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  return Number(value).toFixed(digits);
}

function createSummaryCard(title, value, subtitle) {
  return `
    <div class="summary-card">
      <h3>${title}</h3>
      <p>${value}</p>
      ${subtitle ? `<span>${subtitle}</span>` : ""}
    </div>
  `;
}

function getTopTeamsByWinProbability(data, count = 10) {
  return [...data.tournament_simulation]
    .sort((a, b) => b.prob_Winner - a.prob_Winner)
    .slice(0, count);
}

function getTopAdvanceTeams(data, count = 10) {
  return [...data.group_probabilities]
    .sort((a, b) => b.advance_probability - a.advance_probability)
    .slice(0, count);
}

function renderSummary(data) {
  const winner = getTopTeamsByWinProbability(data, 1)[0];
  const simulationCount = data.simulations ?? (data.tournament_simulation?.length ? data.tournament_simulation.length : null);
  const cards = [
    createSummaryCard("Simulation runs", simulationCount ? `${simulationCount} runs` : "N/A"),
    createSummaryCard("Sim favourite", winner ? winner.team : "N/A", formatPercent(winner?.prob_Winner ?? 0)),
    createSummaryCard("Top advance chance", data.group_probabilities.length ? data.group_probabilities[0].team : "N/A", formatPercent(data.group_probabilities[0]?.advance_probability ?? 0)),
    createSummaryCard("Exported groups", `${new Set(data.group_tables.map((row) => row.group)).size} groups`),
  ];
  // filter out any null entries
  document.getElementById("summary-cards").innerHTML = cards.filter(Boolean).join("");
}

function renderChart(canvasId, labels, values, label, backgroundColor) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  return new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label,
          data: values,
          borderRadius: 10,
          backgroundColor,
          hoverBackgroundColor: backgroundColor.map((color) => color.replace("0.8", "1")),
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          ticks: { color: "#dbeafe" },
          grid: { color: "rgba(255,255,255,0.05)" },
        },
        y: {
          ticks: {
            callback: (value) => `${(value * 100).toFixed(0)}%`,
            color: "#dbeafe",
          },
          grid: { color: "rgba(255,255,255,0.05)" },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (context) => `${formatPercent(context.raw)}`,
          },
        },
      },
    },
  });
}

function renderWinnerChart(data, selectedTeam) {
  if (typeof Chart === 'undefined') {
    throw new Error('Chart.js did not load. Check your internet connection or CDN access.');
  }

  const top = getTopTeamsByWinProbability(data, 10);
  const labels = top.map((row) => row.team);
  const values = top.map((row) => row.prob_Winner);
  const colors = top.map((_, index) => `rgba(124, 58, 237, ${0.8 - index * 0.05})`);

  if (window.winnerChartInstance) {
    window.winnerChartInstance.destroy();
  }
  window.winnerChartInstance = renderChart("winnerChart", labels, values, "Win probability", colors);

  const teamRow = data.tournament_simulation.find((row) => row.team === selectedTeam) || top[0];
  const detailContainer = document.getElementById("winner-team-detail");
  if (detailContainer) {
    detailContainer.innerHTML = `
      <div class="detail-title">Selected team</div>
      <div class="detail-grid">
        <div><strong>${teamRow.team}</strong></div>
        <div>${formatPercent(teamRow.prob_Winner)}</div>
      </div>
    `;
  }
}

function renderAdvanceChart(data, selectedTeam) {
  if (typeof Chart === 'undefined') {
    throw new Error('Chart.js did not load. Check your internet connection or CDN access.');
  }

  const top = getTopAdvanceTeams(data, 10);
  const labels = top.map((row) => row.team);
  const values = top.map((row) => row.advance_probability);
  const colors = top.map((_, index) => `rgba(59, 130, 246, ${0.8 - index * 0.04})`);

  if (window.advanceChartInstance) {
    window.advanceChartInstance.destroy();
  }
  window.advanceChartInstance = renderChart("advanceChart", labels, values, "Advance probability", colors);

  const teamRow = data.group_probabilities.find((row) => row.team === selectedTeam) || data.group_probabilities[0];
  const detailContainer = document.getElementById("advance-team-detail");
  if (detailContainer) {
    detailContainer.innerHTML = `
      <div class="detail-title">Selected team</div>
      <div class="detail-grid">
        <div><strong>${teamRow.team}</strong></div>
        <div>${formatPercent(teamRow.advance_probability)}</div>
      </div>
    `;
  }
}

function renderGroupTable(data, group) {
  // Compute actual standings for this group from entered results.
  // Keys are normalised to simulation team names so lookups match group_tables rows.
  const groupMatches = groupScheduleCache.filter((m) => m.group === group);
  const actualStats = {};
  groupMatches.forEach((m) => {
    [m.home_team, m.away_team].forEach((schedName) => {
      const t = toSimName(schedName);
      if (!actualStats[t]) actualStats[t] = { pts: 0, gf: 0, ga: 0, played: 0 };
    });
    const ar = actualResultsCache[String(m.match_number)];
    if (!ar) return;
    const home = toSimName(m.home_team), away = toSimName(m.away_team);
    const hg = Number(ar.home_goals), ag = Number(ar.away_goals);
    actualStats[home].gf += hg; actualStats[home].ga += ag; actualStats[home].played++;
    actualStats[away].gf += ag; actualStats[away].ga += hg; actualStats[away].played++;
    if (hg > ag) actualStats[home].pts += 3;
    else if (ag > hg) actualStats[away].pts += 3;
    else { actualStats[home].pts += 1; actualStats[away].pts += 1; }
  });

  const gamesInGroup = groupMatches.length;
  const gamesPlayed = groupMatches.filter((m) => actualResultsCache[String(m.match_number)]).length;
  // Only overlay actual data when the user has chosen actuals mode
  const hasActuals = simulationMode === 'actuals' && gamesPlayed > 0;

  const simRows = data.group_tables
    .filter((row) => row.group === group)
    .sort((a, b) => a.expected_rank - b.expected_rank);

  // If actuals exist, sort teams by actual standing (pts → GD → GF → alpha)
  let orderedTeams = simRows.map((r) => r.team);
  if (hasActuals) {
    orderedTeams = [...orderedTeams].sort((a, b) => {
      const sa = actualStats[a] || { pts: 0, gf: 0, ga: 0 };
      const sb = actualStats[b] || { pts: 0, gf: 0, ga: 0 };
      if (sb.pts !== sa.pts) return sb.pts - sa.pts;
      const gda = sa.gf - sa.ga, gdb = sb.gf - sb.ga;
      if (gdb !== gda) return gdb - gda;
      if (sb.gf !== sa.gf) return sb.gf - sa.gf;
      return a.localeCompare(b);
    });
  }

  // Update header: swap simulation columns for actual when all games played
  const head = document.getElementById('group-table-head');
  if (head) {
    if (gamesPlayed === gamesInGroup) {
      head.innerHTML = `<th>Team</th><th>Pos</th><th>Pts</th><th>GD</th><th>1st%</th><th>2nd%</th><th>3rd%</th><th>4th%</th>`;
    } else if (hasActuals) {
      head.innerHTML = `<th>Team</th><th>Pos</th><th>Pts (${gamesPlayed}/${gamesInGroup})</th><th>GD</th><th>1st%</th><th>2nd%</th><th>3rd%</th><th>4th%</th>`;
    } else {
      head.innerHTML = `<th>Team</th><th>Rank</th><th>Avg. points</th><th>Goal diff</th><th>1st</th><th>2nd</th><th>3rd</th><th>4th</th>`;
    }
  }

  const simByTeam = Object.fromEntries(simRows.map((r) => [r.team, r]));
  const body = orderedTeams.map((team, idx) => {
    const row = simByTeam[team] || {};
    const actual = actualStats[team] || { pts: 0, gf: 0, ga: 0 };
    const rankCell = hasActuals
      ? `<td style="font-weight:700;color:${idx < 2 ? '#4ade80' : idx === 2 ? '#facc15' : '#94a3b8'}">${idx + 1}</td>`
      : `<td>${formatNumber(row.expected_rank, 2)}</td>`;
    const ptsCell = hasActuals
      ? `<td style="font-weight:600">${actual.pts}</td>`
      : `<td>${formatNumber(row.avg_points, 2)}</td>`;
    const gdCell = hasActuals
      ? `<td>${actual.gf - actual.ga >= 0 ? '+' : ''}${actual.gf - actual.ga}</td>`
      : `<td>${formatNumber(row.avg_goal_difference, 2)}</td>`;
    return `<tr>
      <td>${team}</td>
      ${rankCell}
      ${ptsCell}
      ${gdCell}
      <td>${formatPercent(row.prob_1 || 0)}</td>
      <td>${formatPercent(row.prob_2 || 0)}</td>
      <td>${formatPercent(row.prob_3 || 0)}</td>
      <td>${formatPercent(row.prob_4 || 0)}</td>
    </tr>`;
  }).join('');
  document.querySelector('#group-table tbody').innerHTML = body;
}

function sortTeamsAlphabetically(teams) {
  return [...teams].sort((a, b) => a.localeCompare(b));
}

function populateTeamSelect(selectId, teams, onChange, defaultTeam) {
  let select = document.getElementById(selectId);
  if (!select) return;
  select = replaceElement(select);
  const options = sortTeamsAlphabetically(teams);
  select.innerHTML = options.map((team) => `<option value="${team}">${team}</option>`).join("");
  if (defaultTeam && options.includes(defaultTeam)) {
    select.value = defaultTeam;
  }
  select.addEventListener("change", (event) => onChange(event.target.value));
}


function setProgress(fraction) {
  for (const [fillId, containerId] of [
    ['simulation-progress-fill', 'simulation-progress-container'],
    ['actuals-progress-fill', 'actuals-progress-container'],
  ]) {
    const fill = document.getElementById(fillId);
    const container = document.getElementById(containerId);
    if (!fill || !container) continue;
    container.classList.add('visible');
    fill.style.width = `${Math.round(fraction * 100)}%`;
  }
}

function clearProgress() {
  for (const [fillId, containerId] of [
    ['simulation-progress-fill', 'simulation-progress-container'],
    ['actuals-progress-fill', 'actuals-progress-container'],
  ]) {
    const fill = document.getElementById(fillId);
    const container = document.getElementById(containerId);
    if (!fill || !container) continue;
    fill.style.width = '100%';
    setTimeout(() => {
      container.classList.remove('visible');
      fill.style.width = '0%';
    }, 400);
  }
}

async function runSimulation(simulations) {
  const countInput = document.getElementById("simulation-count");
  const simulationCount = countInput ? Number.parseInt(countInput.value, 10) : simulations;
  const conmebolOffset = -45;

  const modeLabel = simulationMode === 'actuals' ? ' (actuals + simulation)' : '';
  setSimulationStatus(`Running ${simulationCount} simulations${modeLabel}…`);
  setProgress(0);
  const button = document.getElementById("simulation-run-button");
  const actualsButton = document.getElementById("actuals-run-button");
  if (button) button.disabled = true;
  if (actualsButton) actualsButton.disabled = true;

  try {
    // Start simulation — server returns a job_id immediately
    const startResp = await fetch(API_RUN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        simulations: simulationCount,
        conmebol_offset: conmebolOffset,
        use_actuals: simulationMode === 'actuals',
        actual_results: simulationMode === 'actuals' ? Object.values(actualResultsCache) : [],
        label: document.getElementById('simulation-label')?.value.trim() || '',
      }),
    });
    if (!startResp.ok) {
      const text = await startResp.text();
      throw new Error(`Simulation request failed: ${startResp.status} ${startResp.statusText} ${text}`);
    }
    const { job_id } = await startResp.json();

    // Poll for progress
    while (true) {
      await new Promise((r) => setTimeout(r, 300));
      const statusResp = await fetch(`/api/simulation_status?job_id=${job_id}`);
      if (!statusResp.ok) throw new Error(`Status poll failed: ${statusResp.status}`);
      const status = await statusResp.json();
      setProgress(status.progress);
      if (status.done) {
        if (status.error) throw new Error(status.error);
        const data = status.result;
        try {
          if (data.saved_filename) localStorage.setItem('last_saved_simulation', String(data.saved_filename));
        } catch (_) {}
        renderDashboard(data);
        const saved = data.saved_filename ? ` Saved to ${data.saved_filename}` : "";
        setSimulationStatus(`Loaded ${simulationCount} simulations.${saved}`);
        loadSimulationHistory();
        break;
      }
    }
  } catch (error) {
    console.error(error);
    const message = error.message || String(error);
    if (/501/.test(message) || /Unsupported method/.test(message)) {
      setSimulationStatus("Server does not support POST. Run this app with `python3 server.py` instead of a static http.server.");
    } else {
      setSimulationStatus(`Error: ${message}`);
    }
  } finally {
    clearProgress();
    if (button) button.disabled = false;
    if (actualsButton) actualsButton.disabled = false;
  }
}


function renderDashboard(data) {
  state = data;
  // Refresh actuals panel body if group_schedule from simulation has more info
  if (data.group_schedule && data.group_schedule.length > groupScheduleCache.length) {
    groupScheduleCache = data.group_schedule;
    const panelBody = document.getElementById('actuals-panel-body');
    if (panelBody) {
      panelBody.innerHTML = buildActualsPanel(groupScheduleCache);
      attachActualInputListeners();
      refreshActualsPanelInputs();
    }
  }
  renderSummary(state);

  const winnerDefault = getTopTeamsByWinProbability(state, 1)[0]?.team;
  const advanceDefault = state.group_probabilities[0]?.team;
  const knockoutDefault = winnerDefault || advanceDefault;

  populateTeamSelect(
    "winner-team-select",
    state.tournament_simulation.map((row) => row.team),
    (team) => renderWinnerChart(state, team),
    winnerDefault,
  );
  populateTeamSelect(
    "advance-team-select",
    state.group_probabilities.map((row) => row.team),
    (team) => renderAdvanceChart(state, team),
    advanceDefault,
  );
  populateTeamSelect(
    "knockout-team-select",
    state.tournament_simulation.map((row) => row.team),
    (team) => renderKnockoutProjection(state, team),
    knockoutDefault,
  );

  renderWinnerChart(state, winnerDefault);
  renderAdvanceChart(state, advanceDefault);
  renderKnockoutProjection(state, knockoutDefault);
  populateGroupSelect(state);
  renderBracket(state, 32).catch(err => console.error('Failed to render bracket:', err));
}

function renderKnockoutProjection(data, selectedTeam) {
  const stages = [
    { key: "prob_Round_of_32", label: "Round of 32" },
    { key: "prob_Round_of_16", label: "Round of 16" },
    { key: "prob_Quarter_Finals", label: "Quarter Finals" },
    { key: "prob_Semi_Finals", label: "Semi Finals" },
    { key: "prob_Finals", label: "Finals" },
    { key: "prob_Winner", label: "Winner" },
  ];

  const rows = [...data.tournament_simulation].sort((a, b) => b.prob_Winner - a.prob_Winner);

  const filteredRows = selectedTeam
    ? (() => {
        const match = rows.find((row) => row.team === selectedTeam);
        return match ? [match] : [];
      })()
    : rows;

  const html = filteredRows
    .map((row) => {
      const cells = stages
        .map((stage) => `
            <div class="knockout-cell">
              <div class="knockout-bar ${row[stage.key] > 0 ? "" : "empty"}" style="width: ${Math.max(6, Math.min(100, (row[stage.key] || 0) * 100))}%"></div>
              <div class="knockout-label ${row[stage.key] > 0 ? "" : "muted"}">${formatPercent(row[stage.key] || 0)}</div>
            </div>
          `)
        .join("");

      return `
        <div class="knockout-row">
          <div class="knockout-team">${row.team}</div>
          ${cells}
        </div>
      `;
    })
    .join("");

  document.getElementById("knockout-rows").innerHTML = html;

  const detailContainer = document.getElementById("knockout-team-detail");
  if (detailContainer) {
    if (selectedTeam) {
      const selectedRow = data.tournament_simulation.find((row) => row.team === selectedTeam);
      // show only the selected team name here to avoid duplicating percent bars
      detailContainer.innerHTML = selectedRow
        ? `
          <div class="detail-title">Selected team</div>
          <div class="detail-grid">
            <div><strong>${selectedRow.team}</strong></div>
          </div>
        `
        : `<div class="detail-title">Selected team</div><div class="detail-grid">Team not found</div>`;
    } else {
      detailContainer.innerHTML = `<div class="detail-title">Selected team</div><div class="detail-grid"><div>None selected</div></div>`;
    }
  }
}

function populateGroupSelect(data) {
  let select = document.getElementById("group-select");
  if (!select) return;
  select = replaceElement(select);
  const groups = [...new Set(data.group_tables.map((row) => row.group))].sort();
  select.innerHTML = groups.map((group) => `<option value="${group}">${group}</option>`).join("");
  select.addEventListener("change", (event) => renderGroupTable(data, event.target.value));
  if (groups.length) {
    renderGroupTable(data, groups[0]);
  }
}

async function loadData() {
  const response = await fetch(DATA_URL);
  if (!response.ok) {
    throw new Error(`Unable to load data from ${DATA_URL}: ${response.status} ${response.statusText}`);
  }
  try {
    return await response.json();
  } catch (error) {
    throw new Error(`Unable to parse JSON from ${DATA_URL}: ${error.message}`);
  }
}

async function renderBracket(data, count = 32) {
  // Wait for assignment table to load
  let assignmentTableCache = null;
  async function loadR32ThirdPlaceAssignments() {
    if (assignmentTableCache) return assignmentTableCache;
    try {
      const response = await fetch('data/r32_third_place_assignments.json');
      assignmentTableCache = await response.json();
    } catch (e) {
      console.error('Failed to load R32 third-place assignments:', e);
      assignmentTableCache = {};
    }
    return assignmentTableCache;
  }
  const assignmentTablePromise = loadR32ThirdPlaceAssignments().then(table => {
    assignmentTableCache = table;
    return table;
  });
  await assignmentTablePromise;

  const svg = document.getElementById('bracket-svg');
  if (!svg) return;

  // Map team display names to ISO country codes for emoji flags
  const teamIsoMap = {
    // Group A
    'Mexico': 'MX', 'Czech Republic': 'CZ', 'South Korea': 'KR', 'South Africa': 'ZA',
    // Group B
    'Switzerland': 'CH', 'Canada': 'CA', 'Bosnia and Herzegovina': 'BA', 'Qatar': 'QA',
    // Group C
    'Brazil': 'BR', 'Morocco': 'MA', 'Scotland': 'GB', 'Haiti': 'HT',
    // Group D
    'Turkey': 'TR', 'United States': 'US', 'Australia': 'AU', 'Paraguay': 'PY',
    // Group E
    'Germany': 'DE', 'Ecuador': 'EC', "Cote d'Ivoire": 'CI', 'Curaçao': 'CW',
    // Group F
    'Netherlands': 'NL', 'Japan': 'JP', 'Sweden': 'SE', 'Tunisia': 'TN',
    // Group G
    'Belgium': 'BE', 'Iran': 'IR', 'Egypt': 'EG', 'New Zealand': 'NZ',
    // Group H
    'Spain': 'ES', 'Uruguay': 'UY', 'Saudi Arabia': 'SA', 'Cape Verde': 'CV',
    // Group I
    'France': 'FR', 'Norway': 'NO', 'Senegal': 'SN', 'Iraq': 'IQ',
    // Group J
    'Argentina': 'AR', 'Austria': 'AT', 'Algeria': 'DZ', 'Jordan': 'JO',
    // Group K
    'Portugal': 'PT', 'Colombia': 'CO', 'DR Congo': 'CD', 'Uzbekistan': 'UZ',
    // Group L
    'England': 'GB', 'Croatia': 'HR', 'Ghana': 'GH', 'Panama': 'PA',
  };

  function isoToEmoji(cc) {
    if (!cc || cc.length !== 2) return '';
    const A = 0x1F1E6;
    const a = 'A'.charCodeAt(0);
    const chars = cc.toUpperCase().split('');
    return chars.map(c => String.fromCodePoint(A + c.charCodeAt(0) - a)).join('');
  }

  let tooltip = document.getElementById('bracket-tooltip');
  if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.id = 'bracket-tooltip';
    tooltip.className = 'bracket-tooltip';
    document.body.appendChild(tooltip);
  }

  const probMap = {};
  (data.tournament_simulation || []).forEach((t) => (probMap[t.team] = t));

  const groups = [...new Set((data.group_tables || []).map((r) => r.group))].sort();
  if (groups.length === 0) return;

  const groupMap = {};
  (data.group_tables || []).forEach((r) => {
    if (!groupMap[r.group]) groupMap[r.group] = [];
    groupMap[r.group].push(r);
  });
  Object.keys(groupMap).forEach((g) => groupMap[g].sort((a, b) => (a.expected_rank || 99) - (b.expected_rank || 99)));

  // In actuals mode, seed the bracket with entered results; in full-sim mode use only simulation.
  const useActuals = simulationMode === 'actuals';
  const actualStandings     = useActuals ? computeActualGroupStandings() : {};
  const actualThirdPlaceMap = useActuals ? computeThirdPlaceQualifiers()  : {};
  const actualKo            = useActuals ? buildKnockoutResolution()       : {};

  // Which groups have all matches entered (locks their R32 slots)
  const groupComplete = {};
  if (useActuals && groupScheduleCache) {
    const byG = {};
    groupScheduleCache.forEach((m) => {
      const g = m.group || '';
      if (!byG[g]) byG[g] = { total: 0, done: 0 };
      byG[g].total++;
      if (actualResultsCache[String(m.match_number)]) byG[g].done++;
    });
    Object.entries(byG).forEach(([g, c]) => { groupComplete[g] = c.total > 0 && c.done === c.total; });
  }
  const allGroupsComplete = useActuals && Object.keys(groupComplete).length >= 12 && Object.values(groupComplete).every(Boolean);
  // Map: match_number (string) → match_number of the match whose slot takes that winner (W<n>)
  const winnerGoesTo = {};
  (data.knockout_schedule || []).forEach((ks) => {
    ['home', 'away'].forEach((side) => {
      const mw = /^W(\d+)$/.exec(ks[side] || '');
      if (mw) winnerGoesTo[mw[1]] = ks.match_number;
    });
  });

  function parseThirdPlaceAssignmentText(assignmentTable) {
    // assignmentTable is already parsed JSON, just return it
    return assignmentTable || {};
  }

  function normalizeGroupName(letter) {
    const key = `Group ${letter}`;
    if (groupMap[key]) return key;
    return Object.keys(groupMap).find((group) => String(group).trim().endsWith(letter));
  }

  function resolveGroupPlacement(slot) {
    const match = /^([12])([A-L])$/.exec(String(slot).trim());
    if (!match) return null;
    const pos = Number(match[1]);
    const letter = match[2];
    // Actual group standings take priority
    const actualKey = Object.keys(actualStandings).find((k) => k === `Group ${letter}` || k.endsWith(` ${letter}`));
    if (actualKey && actualStandings[actualKey]?.[pos - 1]) {
      const teamName = actualStandings[actualKey][pos - 1];
      return { team: teamName, ...(probMap[teamName] || {}) };
    }
    const groupName = normalizeGroupName(letter);
    const rows = groupMap[groupName] || [];
    return rows[pos - 1] || null;
  }

  function getThirdPlaceRow(groupName) {
    const rows = groupMap[groupName] || [];
    return rows.length >= 3 ? rows[2] : null;
  }

  function selectBestThirdPlaceAssignmentKey(thirdPlaceRows, assignmentTable) {
    const thirdStats = Object.fromEntries(
      thirdPlaceRows.map(({ letter, third }) => [
        letter,
        {
          avgPoints: third.avg_points || 0,
          avgGoalDifference: third.avg_goal_difference || 0,
          prob3: third.prob_3 || 0,
        },
      ]),
    );

    const validKeys = Object.keys(assignmentTable).filter((key) =>
      key.split("").every((letter) => thirdStats[letter]),
    );
    if (validKeys.length === 0) return null;

    const keyScore = (key) =>
      key.split("").reduce((sum, letter) => {
        const stats = thirdStats[letter];
        return sum + stats.avgPoints * 100 + stats.avgGoalDifference * 10 + stats.prob3 * 1000;
      }, 0);

    return validKeys.reduce((best, key) => {
      const score = keyScore(key);
      if (!best || score > best.score || (score === best.score && key < best.key)) {
        return { key, score };
      }
      return best;
    }, null)?.key;
  }

  function buildRoundOf32ThirdPlaceAssignmentMap() {
    const thirdPlaceRows = Object.keys(groupMap)
      .map((groupName) => {
        const third = getThirdPlaceRow(groupName);
        return third
          ? {
              groupName,
              letter: String(groupName).replace(/^Group\s*/, ""),
              third,
            }
          : null;
      })
      .filter(Boolean);

    if (thirdPlaceRows.length < 8) return null;

    thirdPlaceRows.sort((a, b) => {
      const ap = (b.third.avg_points || 0) - (a.third.avg_points || 0);
      if (ap !== 0) return ap;
      const agd = (b.third.avg_goal_difference || 0) - (a.third.avg_goal_difference || 0);
      if (agd !== 0) return agd;
      const p3 = (b.third.prob_3 || 0) - (a.third.prob_3 || 0);
      if (p3 !== 0) return p3;
      return a.letter.localeCompare(b.letter);
    });

    const assignmentTable = parseThirdPlaceAssignmentText(assignmentTableCache);

    // Primary strategy: use the top-8 third-placed teams by avg_points, then GD, then prob_3.
    // Build the "desiredKey" from those eight letters and use it if present in the static table.
    const desiredKey = thirdPlaceRows
      .slice(0, 8)
      .map((item) => item.letter)
      .sort()
      .join("");

    // expose desired key for debugging
    window._desired_third_place_key = desiredKey;

    if (assignmentTable[desiredKey]) {
      window._chosen_third_place_key = desiredKey;
      return Object.fromEntries(_R32_WINNER_GROUP_ORDER.map((winnerGroup, idx) => [winnerGroup, assignmentTable[desiredKey][idx]]));
    }

    // Fallback: try the scoring-based selector (previous behavior)
    const bestKey = selectBestThirdPlaceAssignmentKey(thirdPlaceRows, assignmentTable);
    if (bestKey) {
      window._chosen_third_place_key = bestKey;
      return Object.fromEntries(_R32_WINNER_GROUP_ORDER.map((winnerGroup, idx) => [winnerGroup, assignmentTable[bestKey][idx]]));
    }

    // Final fallback: choose the available key with smallest symmetric difference to desiredKey
    const availableKeys = Object.keys(assignmentTable);
    let closestKey = null;
    let bestDistance = Infinity;
    const desiredLetters = new Set(desiredKey.split(""));

    availableKeys.forEach((key) => {
      const keyLetters = new Set(key.split(""));
      const symmetricDiff = new Set([
        ...[...desiredLetters].filter((l) => !keyLetters.has(l)),
        ...[...keyLetters].filter((l) => !desiredLetters.has(l)),
      ]);
      const distance = symmetricDiff.size;
      if (distance < bestDistance || (distance === bestDistance && key < closestKey)) {
        bestDistance = distance;
        closestKey = key;
      }
    });

    if (!closestKey) return null;
    window._chosen_third_place_key = closestKey;
    return Object.fromEntries(_R32_WINNER_GROUP_ORDER.map((winnerGroup, idx) => [winnerGroup, assignmentTable[closestKey][idx]]));
  }

  const assignmentMap = buildRoundOf32ThirdPlaceAssignmentMap();




  function resolveThirdPlace(slot, oppositeSlot, usedThird) {
    const slotText = String(slot).trim();
    const m3 = /^3([A-L]+)$/.exec(slotText);
    if (!m3) {
      return { team: slotText };
    }

    // Actual third-place assignment takes priority
    if (actualThirdPlaceMap[slotText]) {
      const team = actualThirdPlaceMap[slotText];
      if (!usedThird.has(team)) {
        usedThird.add(team);
        return { team, ...(probMap[team] || {}) };
      }
    }

    if (assignmentMap && /^1[A-L]$/.test(String(oppositeSlot).trim())) {
      const winnerGroup = String(oppositeSlot).trim()[1];
      const thirdGroupLetter = assignmentMap[winnerGroup];
      const thirdGroupName = normalizeGroupName(thirdGroupLetter);
      const thirdRow = thirdGroupName ? getThirdPlaceRow(thirdGroupName) : null;
      if (thirdRow) {
        usedThird.add(thirdRow.team);
        return { team: thirdRow.team, ...(probMap[thirdRow.team] || {}) };
      }
    }

    const candidates = m3[1]
      .split("")
      .map(normalizeGroupName)
      .filter(Boolean)
      .map(getThirdPlaceRow)
      .filter(Boolean)
      .sort((a, b) => {
        const pd = (b.prob_3 || 0) - (a.prob_3 || 0);
        if (pd !== 0) return pd;
        return a.team.localeCompare(b.team);
      });

    const candidate = candidates.find((row) => !usedThird.has(row.team));
    if (candidate) {
      usedThird.add(candidate.team);
      return { team: candidate.team, ...(probMap[candidate.team] || {}) };
    }

    return { team: slotText };
  }

  function resolveBracketSlot(slot, oppositeSlot, usedThird) {
    if (!slot) return null;
    const placement = resolveGroupPlacement(slot);
    if (placement) {
      const obj = { team: placement.team, ...(probMap[placement.team] || {}) };
      const m = /^[12]([A-L])$/.exec(String(slot));
      if (m && groupComplete[`Group ${m[1]}`]) obj.locked = true;
      return obj;
    }
    if (/^3[A-L]+$/.test(String(slot).trim())) {
      const tp = resolveThirdPlace(slot, oppositeSlot, usedThird);
      if (tp && allGroupsComplete) tp.locked = true;
      return tp;
    }
    return { team: String(slot) };
  }

  const schedule = (data.knockout_schedule || []).filter((row) => row.round === 'Round of 32');
  schedule.sort((a, b) => (Number(a.match_number) || 0) - (Number(b.match_number) || 0));

  const usedThird = new Set();
  let r32Matches = schedule.map((row) => ({
    id: row.match_number,
    home: resolveBracketSlot(row.home, row.away, usedThird),
    away: resolveBracketSlot(row.away, row.home, usedThird),
    label: `${row.home} vs ${row.away}`,
  }));

  if (r32Matches.length !== 16) {
    const top2 = [];
    const thirdCandidates = [];
    groups.forEach((g) => {
      const rows = groupMap[g] || [];
      if (rows[0]) top2.push(rows[0].team);
      if (rows[1]) top2.push(rows[1].team);
      if (rows.length >= 3) {
        thirdCandidates.push(rows[2]);
      }
    });
    const bestThirds = thirdCandidates.sort((a, b) => (b.prob_3 || 0) - (a.prob_3 || 0)).slice(0, Math.max(0, 32 - top2.length));
    const fallbackTeams = [...top2, ...bestThirds.map((row) => row.team)].map((teamName) => ({ team: teamName, ...(probMap[teamName] || {}) }));
    r32Matches = [];
    for (let i = 0; i < fallbackTeams.length; i += 2) {
      r32Matches.push({ home: fallbackTeams[i], away: fallbackTeams[i + 1] });
    }
  }

  function getProbabilityKey(stage) {
    switch (stage) {
      case 'Round of 32':
        return 'prob_Round_of_32';
      case 'Round of 16':
        return 'prob_Round_of_16';
      case 'Quarter Finals':
        return 'prob_Quarter_Finals';
      case 'Semi Finals':
        return 'prob_Semi_Finals';
      case 'Finals':
        return 'prob_Finals';
      case 'Winner':
        return 'prob_Winner';
      default:
        return 'prob_Winner';
    }
  }

  function chooseMatchWinner(left, right, probKey) {
    if (!left) return right;
    if (!right) return left;
    const leftProb = left[probKey] || 0;
    const rightProb = right[probKey] || 0;
    return leftProb >= rightProb ? left : right;
  }

  const viewW = 1700;
  // Re-order r32Matches to follow the official bracket path so R16 pairings are correct.
  const bracketOrder = buildBracketOrder(data.knockout_schedule || []);
  if (bracketOrder) {
    const matchById = Object.fromEntries(r32Matches.map((m) => [m.id, m]));
    const ordered = bracketOrder.map((id) => matchById[id]).filter(Boolean);
    if (ordered.length === 16) r32Matches = ordered;
  }

  const leftR32 = [];
  const rightR32 = [];
  r32Matches.slice(0, 8).forEach((match) => leftR32.push(match));
  r32Matches.slice(8, 16).forEach((match) => rightR32.push(match));

  const viewH = Math.max(900, Math.max(leftR32.length, rightR32.length) * 80 + 120);
  svg.setAttribute('viewBox', `0 0 ${viewW} ${viewH}`);
  svg.innerHTML = '';

  const boxW = 120;
  const boxH = 28;
  const centerBoxW = 160;
  const centerX = (viewW - centerBoxW) / 2;
  const leftXs = [80, 260, 440, 620];
  const rightXs = [1500, 1320, 1140, 960];

  function drawBox(x, y, teamObj, stage) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const box = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    box.setAttribute('x', x);
    box.setAttribute('y', y);
    box.setAttribute('width', (stage === 'Winner' || stage === 'Finals') ? centerBoxW : boxW);
    box.setAttribute('height', boxH);
    box.setAttribute('class', 'match-box');

    // Color boxes by tournament win probability: grey (low) → gold (high)
    const probT = teamObj ? Math.min(1, ((probMap[teamObj.team] || {}).prob_Winner || 0) / 0.12) : 0;
    if (stage === 'Winner') {
      box.setAttribute('fill', 'rgba(91,60,5,0.88)');
      box.setAttribute('stroke', 'rgba(251,191,36,0.95)');
      box.setAttribute('stroke-width', '2.5');
    } else {
      box.setAttribute('fill', 'rgba(31,47,91,0.75)');
      const sG = Math.round(255 - 64 * probT);
      const sB = Math.round(255 - 219 * probT);
      const sA = (0.14 + 0.76 * probT).toFixed(2);
      box.setAttribute('stroke', `rgba(255,${sG},${sB},${sA})`);
      box.setAttribute('stroke-width', (1 + 0.8 * probT).toFixed(1));
    }
    g.appendChild(box);

    if (teamObj) {
      // Left accent bar (slate → gold) based on win probability
      if (stage !== 'Winner') {
        const ar = Math.round(71 + probT * 180);
        const ag = Math.round(85 + probT * 106);
        const ab = Math.round(105 - probT * 69);
        const aa = (0.4 + probT * 0.55).toFixed(2);
        const accent = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        accent.setAttribute('x', x);
        accent.setAttribute('y', y);
        accent.setAttribute('width', 4);
        accent.setAttribute('height', boxH);
        accent.setAttribute('fill', `rgba(${ar},${ag},${ab},${aa})`);
        g.appendChild(accent);
      }

      const iso = teamIsoMap[teamObj.team] || '';
      const flag = iso ? isoToEmoji(iso) + ' ' : '';
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', x + 12);
      text.setAttribute('y', y + 18);
      text.setAttribute('font-size', '11');
      text.setAttribute('fill', '#e2e8f0');
      text.setAttribute('class', 'team-cell');
      text.textContent = flag + (teamObj.team || '').substring(0, 18);
      g.appendChild(text);

      if (teamObj.locked) {
        const bw = (stage === 'Winner' || stage === 'Finals') ? centerBoxW : boxW;
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx', x + bw - 8);
        dot.setAttribute('cy', y + boxH / 2);
        dot.setAttribute('r', 4);
        dot.setAttribute('fill', 'rgba(34,197,94,0.9)');
        dot.setAttribute('title', 'Confirmed result');
        g.appendChild(dot);
      }

      box.addEventListener('mouseenter', (ev) => {
        const prob = probMap[teamObj.team] || {};
        const lines = [
          `<strong>${teamObj.team}</strong>`,
          `R32: ${formatPercent(prob.prob_Round_of_32 || 0)}`,
          `R16: ${formatPercent(prob.prob_Round_of_16 || 0)}`,
          `QF: ${formatPercent(prob.prob_Quarter_Finals || 0)}`,
          `SF: ${formatPercent(prob.prob_Semi_Finals || 0)}`,
          `Final: ${formatPercent(prob.prob_Finals || 0)}`,
          `Win: ${formatPercent(prob.prob_Winner || 0)}`,
        ];
        tooltip.innerHTML = lines.join('<br>');
        tooltip.style.display = 'block';
        tooltip.style.left = (ev.clientX + 12) + 'px';
        tooltip.style.top = (ev.clientY + 12) + 'px';
      });
      box.addEventListener('mousemove', (ev) => {
        tooltip.style.left = (ev.clientX + 12) + 'px';
        tooltip.style.top = (ev.clientY + 12) + 'px';
      });
      box.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
    }
    return g;
  }

  function drawConnector(x1, y1, x2, y2) {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const midX = (x1 + x2) / 2;
    path.setAttribute('d', `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'rgba(255,255,255,0.18)');
    path.setAttribute('stroke-width', '2');
    svg.appendChild(path);
  }

  function createProgression(matches, x, advanceKey) {
    const groups = [];
    matches.forEach((match, idx) => {
      // matches may be objects {home, away, id} or legacy [home, away] arrays
      const home = match.home || match[0];
      const away = match.away || match[1];
      const matchId = match.id;
      const yTop = 80 + idx * 80;
      const yBottom = yTop + boxH + 10;
      const yMid = yTop + boxH + 5;
      svg.appendChild(drawBox(x, yTop, home, 'R32'));
      svg.appendChild(drawBox(x, yBottom, away, 'R32'));
      // Use actual result if available, otherwise project from simulation
      const koData = matchId != null ? actualKo[String(matchId)] : null;
      const winner = koData?.winner
        ? { team: koData.winner, ...(probMap[koData.winner] || {}), locked: true }
        : { ...chooseMatchWinner(home, away, advanceKey), locked: false };
      groups.push({ winner, yMid, matchId });
    });
    return groups;
  }

  // Projects winners from one round to the next, using actual results where available.
  // Each group carries { winner, yMid, matchId } so downstream rounds can resolve actuals.
  function projectRound(prevGroups, prevX, nextX, advanceKey, isRight, stage) {
    const nextGroups = [];
    for (let i = 0; i < prevGroups.length; i += 2) {
      const left = prevGroups[i];
      const right = prevGroups[i + 1];
      if (!right) {
        svg.appendChild(drawBox(nextX, left.yMid - boxH / 2, left.winner, stage));
        nextGroups.push(left);
        continue;
      }
      const midY = (left.yMid + right.yMid) / 2;
      const yTop = midY - boxH - 5;
      const yBottom = midY + 5;
      const yMid = yTop + boxH + 5;
      const xStart = isRight ? prevX : prevX + boxW;
      const xEnd = isRight ? nextX + boxW : nextX;
      drawConnector(xStart, left.yMid, xEnd, yTop + boxH / 2);
      drawConnector(xStart, right.yMid, xEnd, yBottom + boxH / 2);
      svg.appendChild(drawBox(nextX, yTop, left.winner, stage));
      svg.appendChild(drawBox(nextX, yBottom, right.winner, stage));
      // Find the match that takes the winners of left and right as its participants
      const nextMatchId = winnerGoesTo[String(left.matchId)] || winnerGoesTo[String(right.matchId)];
      const koData = nextMatchId ? actualKo[String(nextMatchId)] : null;
      const winner = koData?.winner
        ? { team: koData.winner, ...(probMap[koData.winner] || {}), locked: true }
        : { ...chooseMatchWinner(left.winner, right.winner, advanceKey), locked: false };
      nextGroups.push({ winner, yMid, matchId: nextMatchId });
    }
    return nextGroups;
  }

  const leftGroupsR32 = createProgression(leftR32, leftXs[0], getProbabilityKey('Round of 16'));
  const rightGroupsR32 = createProgression(rightR32, rightXs[0], getProbabilityKey('Round of 16'));

  const leftGroupsR16 = projectRound(leftGroupsR32, leftXs[0], leftXs[1], getProbabilityKey('Quarter Finals'), false, 'Round of 16');
  const leftGroupsQF = projectRound(leftGroupsR16, leftXs[1], leftXs[2], getProbabilityKey('Semi Finals'), false, 'Quarter Finals');
  const leftGroupsSF = projectRound(leftGroupsQF, leftXs[2], leftXs[3], getProbabilityKey('Finals'), false, 'Semi Finals');

  const rightGroupsR16 = projectRound(rightGroupsR32, rightXs[0], rightXs[1], getProbabilityKey('Quarter Finals'), true, 'Round of 16');
  const rightGroupsQF = projectRound(rightGroupsR16, rightXs[1], rightXs[2], getProbabilityKey('Semi Finals'), true, 'Quarter Finals');
  const rightGroupsSF = projectRound(rightGroupsQF, rightXs[2], rightXs[3], getProbabilityKey('Finals'), true, 'Semi Finals');

  if (leftGroupsSF.length > 0 && rightGroupsSF.length > 0) {
    const finalMidY = (leftGroupsSF[0].yMid + rightGroupsSF[0].yMid) / 2;
    const finalYTop = finalMidY - boxH - 5;
    const finalYBottom = finalMidY + 5;
    const finalist1 = leftGroupsSF[0].winner;
    const finalist2 = rightGroupsSF[0].winner;

    // Connectors from each SF to its finalist box
    drawConnector(leftXs[3] + boxW, leftGroupsSF[0].yMid, centerX, finalYTop + boxH / 2);
    drawConnector(rightXs[3], rightGroupsSF[0].yMid, centerX + centerBoxW, finalYBottom + boxH / 2);

    // Final matchup: both finalists stacked at center
    svg.appendChild(drawBox(centerX, finalYTop, finalist1, 'Finals'));
    svg.appendChild(drawBox(centerX, finalYBottom, finalist2, 'Finals'));

    // Projected winner below the Final matchup (use actual if Final has been played)
    const winnerY = finalYBottom + boxH + 60;
    const finalKo = actualKo['104'];
    const winner = finalKo?.winner
      ? { team: finalKo.winner, ...(probMap[finalKo.winner] || {}), locked: true }
      : { ...chooseMatchWinner(finalist1, finalist2, getProbabilityKey('Winner')), locked: false };

    // Vertical connector from Final midpoint down to winner box
    drawConnector(centerX + centerBoxW / 2, finalMidY, centerX + centerBoxW / 2, winnerY + boxH / 2);

    svg.appendChild(drawBox(centerX, winnerY, winner, 'Winner'));

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', centerX + centerBoxW / 2);
    label.setAttribute('y', winnerY - 10);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', '12');
    label.setAttribute('fill', 'rgba(255,255,255,0.65)');
    label.textContent = 'Projected winner';
    svg.appendChild(label);
  }

  const stageLabels = [
    { text: 'Round of 32', x: leftXs[0] + boxW / 2 },
    { text: 'Round of 16', x: leftXs[1] + boxW / 2 },
    { text: 'Quarter Finals', x: leftXs[2] + boxW / 2 },
    { text: 'Semi Finals', x: leftXs[3] + boxW / 2 },
    { text: 'Final', x: centerX + centerBoxW / 2 },
    { text: 'Semi Finals', x: rightXs[3] + boxW / 2 },
    { text: 'Quarter Finals', x: rightXs[2] + boxW / 2 },
    { text: 'Round of 16', x: rightXs[1] + boxW / 2 },
    { text: 'Round of 32', x: rightXs[0] + boxW / 2 },
  ];

  stageLabels.forEach((item) => {
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', item.x);
    label.setAttribute('y', 35);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', '12');
    label.setAttribute('fill', 'rgba(255,255,255,0.45)');
    label.textContent = item.text;
    svg.appendChild(label);
  });
}

// ── Simulation history ──────────────────────────────────────────────────────

let _historyChart = null;

const HISTORY_COLORS = [
  '#818cf8', '#34d399', '#f59e0b', '#f472b6',
  '#60a5fa', '#a78bfa', '#fb923c', '#4ade80',
];

function fmtTimestamp(ms) {
  const d = new Date(ms);
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
    + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function buildHistoryChart(history) {
  const canvas = document.getElementById('historyChart');
  const emptyEl = document.getElementById('history-empty');
  if (!canvas) return;

  const actualsRuns = history.filter(r => r.mode === 'actuals');
  const fullRuns    = history.filter(r => r.mode === 'full');

  if (history.length === 0) {
    canvas.style.display = 'none';
    if (emptyEl) { emptyEl.textContent = 'No simulation history yet. Run a simulation to start building history.'; emptyEl.style.display = 'block'; }
    return;
  }
  canvas.style.display = '';
  if (emptyEl) emptyEl.style.display = 'none';

  // Pick teams to display
  const topN = parseInt(document.getElementById('history-view-select')?.value || '5', 10);
  const highlight = document.getElementById('history-team-select')?.value || '';

  // Rank teams by max win_prob across all runs
  const maxProb = {};
  history.forEach(r => Object.entries(r.win_probs).forEach(([t, p]) => { if (p > (maxProb[t] || 0)) maxProb[t] = p; }));
  const ranked = Object.keys(maxProb).sort((a, b) => maxProb[b] - maxProb[a]);

  // Populate highlight selector once
  const sel = document.getElementById('history-team-select');
  if (sel && sel.options.length === 1) {
    ranked.forEach(t => { const o = document.createElement('option'); o.value = t; o.textContent = t; sel.appendChild(o); });
  }

  const shown = ranked.slice(0, topN);
  if (highlight && !shown.includes(highlight)) shown.push(highlight);

  // Build an ordered index of all runs sorted by timestamp.
  // Each run gets an integer x position; the label is used as the tick text.
  const allRunsSorted = [...history].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const runIndex = new Map(allRunsSorted.map((r, i) => [r.timestamp, i]));
  const xLabels = allRunsSorted.map(r => r.label || fmtTimestamp(new Date(r.timestamp).getTime()));

  const datasets = [];
  shown.forEach((team, i) => {
    const color = HISTORY_COLORS[i % HISTORY_COLORS.length];
    const isHL  = team === highlight;

    // Merge full-sim and actuals into one timeline per team, sorted by run index
    const allPts = [
      ...fullRuns.filter(r => r.win_probs[team] != null)
        .map(r => ({ x: runIndex.get(r.timestamp), y: +(r.win_probs[team] * 100).toFixed(2), sims: r.simulations, mode: 'full', xLabel: r.label || fmtTimestamp(new Date(r.timestamp).getTime()) })),
      ...actualsRuns.filter(r => r.win_probs[team] != null)
        .map(r => ({ x: runIndex.get(r.timestamp), y: +(r.win_probs[team] * 100).toFixed(2), sims: r.simulations, mode: 'actuals', xLabel: r.label || fmtTimestamp(new Date(r.timestamp).getTime()) })),
    ].sort((a, b) => a.x - b.x);

    if (allPts.length) {
      const lineColor  = isHL ? '#ffffff' : color;
      const fadeColor  = isHL ? 'rgba(255,255,255,0.5)' : color + 'aa';
      datasets.push({
        label: team,
        data: allPts,
        showLine: true,
        tension: 0.25,
        borderColor: isHL ? 'rgba(255,255,255,0.9)' : color,
        backgroundColor: isHL ? 'rgba(255,255,255,0.15)' : color + '33',
        borderWidth: isHL ? 3 : 1.5,
        pointRadius: allPts.map(p => p.mode === 'full' ? (isHL ? 5 : 3) : (isHL ? 7 : 4)),
        pointBackgroundColor: allPts.map(p => p.mode === 'full' ? 'transparent' : lineColor),
        pointBorderColor: allPts.map(p => p.mode === 'full' ? fadeColor : lineColor),
        pointBorderWidth: allPts.map(p => p.mode === 'full' ? (isHL ? 2 : 1.5) : (isHL ? 2.5 : 1.5)),
        pointHoverRadius: isHL ? 9 : 7,
        order: isHL ? 0 : 1,
      });
    }
  });

  if (_historyChart) _historyChart.destroy();
  _historyChart = new Chart(canvas, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      scales: {
        x: {
          type: 'linear',
          min: -0.5,
          max: allRunsSorted.length - 0.5,
          ticks: {
            color: '#94a3b8',
            maxRotation: 30,
            autoSkip: true,
            maxTicksLimit: 10,
            stepSize: 1,
            callback: v => xLabels[Math.round(v)] ?? '',
          },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
        y: {
          min: 0,
          ticks: { callback: v => v + '%', color: '#94a3b8' },
          grid: { color: 'rgba(255,255,255,0.05)' },
        },
      },
      plugins: {
        legend: {
          labels: { color: '#dbeafe' },
        },
        tooltip: {
          backgroundColor: 'rgba(15,23,42,0.92)',
          titleColor: '#e2e8f0',
          bodyColor: '#94a3b8',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          callbacks: {
            title: items => items[0].raw.xLabel,
            label: item => {
              const d = item.raw;
              const tag = d.mode === 'full' ? ' (full sim)' : '';
              return ` ${item.dataset.label}${tag}: ${item.parsed.y.toFixed(1)}%  [${d.sims} runs]`;
            },
          },
        },
      },
    },
  });
}

let _historyListenersAttached = false;

async function loadSimulationHistory() {
  try {
    const resp = await fetch(API_HISTORY_URL);
    if (!resp.ok) throw new Error(resp.status);
    const history = await resp.json();
    buildHistoryChart(history);

    if (!_historyListenersAttached) {
      _historyListenersAttached = true;
      ['history-view-select', 'history-team-select'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', () => loadSimulationHistory());
      });
    }
  } catch (err) {
    console.warn('Could not load simulation history:', err);
  }
}

async function initializeDashboard() {
  try {
    const loadedState = await loadData();

    // Restore simulation mode from the last saved run so the bracket is
    // immediately consistent with the data (locks visible on page load).
    if (loadedState.use_actuals) simulationMode = 'actuals';

    renderDashboard(loadedState);

    // Load group schedule for actuals panel
    try {
      const gs = await fetch(GROUP_SCHEDULE_URL);
      if (gs.ok) groupScheduleCache = await gs.json();
    } catch (_) { /* ignore */ }

    // Inject simulation mode toggle and actuals panel
    injectSimulationModeControls();
    // Load persisted actual results from server, then re-render bracket with locks
    await loadActualResults();
    if (simulationMode === 'actuals') {
      renderBracket(loadedState, 32).catch(() => {});
    }

    const simulationButton = document.getElementById("simulation-run-button");
    if (simulationButton) {
      simulationButton.addEventListener("click", () => {
        const countInput = document.getElementById("simulation-count");
        const simulations = Number(countInput?.value) || 200;
        runSimulation(simulations);
      });
    }

    const actualsRunButton = document.getElementById("actuals-run-button");
    if (actualsRunButton) {
      actualsRunButton.addEventListener("click", () => {
        const countInput = document.getElementById("simulation-count");
        const simulations = Number(countInput?.value) || 200;
        runSimulation(simulations);
      });
    }

    // History clear button
    document.getElementById('history-clear-button')?.addEventListener('click', async () => {
      if (!confirm('Move all saved simulation files to the archive folder?')) return;
      try {
        const resp = await fetch('/api/clear_history', { method: 'POST' });
        const text = await resp.text();
        let data;
        try { data = JSON.parse(text); } catch (_) { throw new Error(`Server returned (${resp.status}): ${text.slice(0, 300)}`); }
        if (data.error) throw new Error(data.error);
        _historyListenersAttached = false;
        document.getElementById('history-team-select').innerHTML = '<option value="">None</option>';
        await loadSimulationHistory();
        alert(`Archived ${data.archived} file${data.archived !== 1 ? 's' : ''}.`);
      } catch (err) {
        alert('Archive failed: ' + err.message);
      }
    });

    // Lazy-load history chart when the section scrolls into view
    const historySection = document.getElementById('history-section');
    if (historySection) {
      const obs = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
          loadSimulationHistory();
          obs.disconnect();
        }
      }, { threshold: 0.1 });
      obs.observe(historySection);
    }
  } catch (error) {
    const errorDetails = error?.stack || error?.message || String(error);
    document.body.innerHTML = `<div class="page-shell"><div class="hero-card"><h1>Unable to load dashboard data</h1><p>${error?.message || 'Unknown error'}</p><pre style="white-space: pre-wrap; color: #f9fafb; margin-top: 12px;">${errorDetails}</pre></div></div>`;
    console.error(error);
  }
}

initializeDashboard();
