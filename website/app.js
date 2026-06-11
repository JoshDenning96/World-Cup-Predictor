const DATA_URL = "data/master_simulation.json";
const API_RUN_URL = "/api/run_simulation";
let state = {};

// Order of 1st-place group slots in the r32_third_place_assignments.json value arrays.
// Columns per the FIFA 2026 third-place table header: 1A, 1B, 1D, 1E, 1G, 1I, 1K, 1L
const _R32_WINNER_GROUP_ORDER = ['A', 'B', 'D', 'E', 'G', 'I', 'K', 'L'];

// Official 2026 FIFA WC bracket order for the 16 R32 match numbers.
// Consecutive pairs feed the same R16 match:
//   (73,76)→R16#89, (74,75)→R16#90, (77,80)→R16#91, (78,79)→R16#92  [left half]
//   (83,86)→R16#93, (84,87)→R16#94, (81,82)→R16#95, (85,88)→R16#96  [right half]
const _R32_BRACKET_ORDER = [73, 76, 74, 75, 77, 80, 78, 79, 83, 86, 84, 87, 81, 82, 85, 88];

function replaceElement(el) {
  if (!el || !el.parentNode) return el;
  const clone = el.cloneNode(false);
  el.parentNode.replaceChild(clone, el);
  return clone;
}

function setSimulationStatus(text) {
  const status = document.getElementById("simulation-status");
  if (status) {
    status.textContent = text;
  }
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
    // show CONMEBOL offset when provided by the server response
    data.conmebol_offset !== undefined && data.conmebol_offset !== null
      ? createSummaryCard(
          "CONMEBOL offset",
          `${data.conmebol_offset >= 0 ? '+' : ''}${Number(data.conmebol_offset).toFixed(1)} Elo points`,
          "Negative weakens CONMEBOL teams",
        )
      : null,
    createSummaryCard("Best champion", winner ? winner.team : "N/A", formatPercent(winner?.prob_Winner ?? 0)),
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
            callback: (value) => `${value * 100}%`,
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
  const rows = data.group_tables
    .filter((row) => row.group === group)
    .sort((a, b) => a.expected_rank - b.expected_rank);
  const body = rows
    .map(
      (row) => `
      <tr>
        <td>${row.team}</td>
        <td>${formatNumber(row.expected_rank, 2)}</td>
        <td>${formatNumber(row.avg_points, 2)}</td>
        <td>${formatNumber(row.avg_goal_difference, 2)}</td>
        <td>${formatPercent(row.prob_1)}</td>
        <td>${formatPercent(row.prob_2)}</td>
        <td>${formatPercent(row.prob_3)}</td>
        <td>${formatPercent(row.prob_4)}</td>
      </tr>
    `,
    )
    .join("");
  document.querySelector("#group-table tbody").innerHTML = body;
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

function populateViewSelect(selectId, defaultValue = 'Top 12') {
  let select = document.getElementById(selectId);
  if (!select) return;
  select = replaceElement(select);
  select.innerHTML = `
    <option value="Top 12">Top 12</option>
    <option value="All">All teams</option>
  `;
  select.value = defaultValue;
  select.addEventListener('change', () => {
    const currentTeam = document.getElementById('knockout-team-select')?.value || null;
    renderKnockoutProjection(state, currentTeam, select.value);
  });
}

async function runSimulation(simulations) {
  const countInput = document.getElementById("simulation-count");
  const offsetInput = document.getElementById("conmebol-offset");
  const simulationCount = countInput ? Number.parseInt(countInput.value, 10) : simulations;
  const rawOffset = offsetInput ? Number.parseFloat(offsetInput.value) : NaN;
  const conmebolOffset = Number.isNaN(rawOffset) ? 0 : rawOffset;

  // validate conmebol offset before sending
  if (!validateConmebolOffset()) {
    setSimulationStatus("Invalid CONMEBOL offset — must be between -200 and 200.");
    if (button) button.disabled = false;
    return;
  }

  setSimulationStatus(`Running ${simulationCount} simulations...`);
  const button = document.getElementById("simulation-run-button");
  if (button) button.disabled = true;

  try {
    const response = await fetch(API_RUN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simulations: simulationCount, conmebol_offset: conmebolOffset }),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Simulation request failed: ${response.status} ${response.statusText} ${text}`);
    }
    const data = await response.json();
    // persist chosen offset for next load
    try {
      if (data && data.conmebol_offset !== undefined && data.conmebol_offset !== null) {
        localStorage.setItem('last_conmebol_offset', String(data.conmebol_offset));
      } else {
        localStorage.setItem('last_conmebol_offset', String(conmebolOffset));
      }
      if (data && data.saved_filename) {
        localStorage.setItem('last_saved_simulation', String(data.saved_filename));
      }
    } catch (err) {
      // ignore localStorage errors
    }
    renderDashboard(data);
    const saved = data.saved_filename ? ` Saved to ${data.saved_filename}` : "";
    setSimulationStatus(`Loaded ${simulations} simulations.${saved}`);
  } catch (error) {
    console.error(error);
    const message = error.message || String(error);
    if (/501/.test(message) || /Unsupported method/.test(message)) {
      setSimulationStatus("Server does not support POST. Run this app with `python3 server.py` instead of a static http.server.");
    } else {
      setSimulationStatus(`Error: ${message}`);
    }
  } finally {
    if (button) button.disabled = false;
  }
}

function validateConmebolOffset() {
  const offsetEl = document.getElementById('conmebol-offset');
  const errEl = document.getElementById('conmebol-offset-error');
  if (!offsetEl) return true;
  const val = Number.parseFloat(offsetEl.value);
  if (Number.isNaN(val)) {
    if (errEl) { errEl.style.display = 'block'; errEl.textContent = 'Invalid number'; }
    return false;
  }
  const min = Number.parseFloat(offsetEl.getAttribute('min')) || -Infinity;
  const max = Number.parseFloat(offsetEl.getAttribute('max')) || Infinity;
  if (val < min || val > max) {
    if (errEl) { errEl.style.display = 'block'; errEl.textContent = `Value out of range (${min} to ${max})`; }
    return false;
  }
  if (errEl) { errEl.style.display = 'none'; }
  return true;
}

function renderDashboard(data) {
  state = data;
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
  populateViewSelect('knockout-view-select', 'Top 12');
  populateTeamSelect(
    "knockout-team-select",
    state.tournament_simulation.map((row) => row.team),
    (team) => {
      const view = document.getElementById('knockout-view-select')?.value || 'Top 12';
      renderKnockoutProjection(state, team, view);
    },
    knockoutDefault,
  );

  renderWinnerChart(state, winnerDefault);
  renderAdvanceChart(state, advanceDefault);
  renderKnockoutProjection(state, knockoutDefault, document.getElementById('knockout-view-select')?.value || 'Top 12');
  populateGroupSelect(state);
  renderBracket(state, 32).catch(err => console.error('Failed to render bracket:', err));
}

function renderKnockoutProjection(data, selectedTeam, viewMode = 'Top 12') {
  const stages = [
    { key: "prob_Round_of_32", label: "Round of 32" },
    { key: "prob_Round_of_16", label: "Round of 16" },
    { key: "prob_Quarter_Finals", label: "Quarter Finals" },
    { key: "prob_Semi_Finals", label: "Semi Finals" },
    { key: "prob_Finals", label: "Finals" },
    { key: "prob_Winner", label: "Winner" },
  ];

  const sortedRows = [...data.tournament_simulation].sort((a, b) => b.prob_Winner - a.prob_Winner);
  const rows = viewMode === 'All' ? sortedRows : sortedRows.slice(0, 12);

  const filteredRows = selectedTeam
    ? (() => {
        const inPage = rows.find((row) => row.team === selectedTeam);
        if (inPage) return [inPage];
        const fallback = sortedRows.find((row) => row.team === selectedTeam);
        return fallback ? [fallback] : [];
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
    'Mexico': 'MX', 'Czech Republic': 'CZ', 'Switzerland': 'CH', 'Canada': 'CA',
    'Brazil': 'BR', 'Scotland': 'GB', 'Turkey': 'TR', 'United States': 'US',
    'Germany': 'DE', 'Ecuador': 'EC', 'Netherlands': 'NL', 'Japan': 'JP',
    'Belgium': 'BE', 'Iran': 'IR', 'Spain': 'ES', 'Uruguay': 'UY',
    'France': 'FR', 'Norway': 'NO', 'Argentina': 'AR', 'Algeria': 'DZ',
    'Colombia': 'CO', 'Portugal': 'PT', 'England': 'GB', 'Croatia': 'HR',
    'Cape Verde': 'CV', 'Bosnia and Herzegovina': 'BA', 'Ghana': 'GH', 'Haiti': 'HT',
    'Iraq': 'IQ', 'Austria': 'AT', "Cote d'Ivoire": 'CI', 'Uzbekistan': 'UZ',
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
    const groupName = normalizeGroupName(match[2]);
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

  function updateThirdPlaceKeyLabel() {
    const el = document.getElementById('third-place-key');
    if (!el) return;
    const chosen = window._chosen_third_place_key || 'N/A';
    const desired = window._desired_third_place_key ? ` (desired ${window._desired_third_place_key})` : '';
    el.textContent = `3rd-place assignment key: ${chosen}${desired}`;
  }

  updateThirdPlaceKeyLabel();

  function resolveThirdPlace(slot, oppositeSlot, usedThird) {
    const slotText = String(slot).trim();
    const m3 = /^3([A-L]+)$/.exec(slotText);
    if (!m3) {
      return { team: slotText };
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
    if (placement) return { team: placement.team, ...(probMap[placement.team] || {}) };
    if (/^3[A-L]+$/.test(String(slot).trim())) {
      return resolveThirdPlace(slot, oppositeSlot, usedThird);
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
  const matchById = Object.fromEntries(r32Matches.map((m) => [m.id, m]));
  const ordered = _R32_BRACKET_ORDER.map((id) => matchById[id]).filter(Boolean);
  // Fall back to original order if the schedule doesn't contain all expected match numbers.
  if (ordered.length === 16) r32Matches = ordered;

  const leftR32 = [];
  const rightR32 = [];
  r32Matches.slice(0, 8).forEach((match) => leftR32.push([match.home, match.away]));
  r32Matches.slice(8, 16).forEach((match) => rightR32.push([match.home, match.away]));

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
    box.setAttribute('width', stage === 'Winner' ? centerBoxW : boxW);
    box.setAttribute('height', boxH);
    box.setAttribute('class', 'match-box');
    box.setAttribute('fill', 'rgba(31,47,91,0.75)');
    box.setAttribute('stroke', 'rgba(255,255,255,0.14)');
    box.setAttribute('stroke-width', '1');
    g.appendChild(box);

    if (teamObj) {
      const iso = teamIsoMap[teamObj.team] || '';
      const flag = iso ? isoToEmoji(iso) + ' ' : '';
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', x + 8);
      text.setAttribute('y', y + 18);
      text.setAttribute('font-size', '11');
      text.setAttribute('fill', '#e2e8f0');
      text.setAttribute('class', 'team-cell');
      text.textContent = flag + (teamObj.team || '').substring(0, 18);
      g.appendChild(text);

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
      const yTop = 80 + idx * 80;
      const yBottom = yTop + boxH + 10;
      const yMid = yTop + boxH + 5;

      svg.appendChild(drawBox(x, yTop, match[0], 'R32'));
      svg.appendChild(drawBox(x, yBottom, match[1], 'R32'));

      groups.push({
        winner: chooseMatchWinner(match[0], match[1], advanceKey),
        yMid,
      });
    });
    return groups;
  }

  function projectRound(prevGroups, prevX, nextX, advanceKey, isRight) {
    const nextGroups = [];
    for (let i = 0; i < prevGroups.length; i += 2) {
      const left = prevGroups[i];
      const right = prevGroups[i + 1];
      if (!right) {
        nextGroups.push(left);
        continue;
      }
      const yMid = (left.yMid + right.yMid) / 2;
      const winner = chooseMatchWinner(left.winner, right.winner, advanceKey);
      const xStart = isRight ? prevX : prevX + boxW;
      const xEnd = isRight ? nextX + boxW : nextX;
      drawConnector(xStart, left.yMid, xEnd, yMid);
      drawConnector(xStart, right.yMid, xEnd, yMid);
      svg.appendChild(drawBox(nextX, yMid - boxH / 2, winner, 'R16'));
      nextGroups.push({ winner, yMid });
    }
    return nextGroups;
  }

  const leftGroupsR32 = createProgression(leftR32, leftXs[0], getProbabilityKey('Round of 16'));
  const rightGroupsR32 = createProgression(rightR32, rightXs[0], getProbabilityKey('Round of 16'));

  const leftGroupsR16 = projectRound(leftGroupsR32, leftXs[0], leftXs[1], getProbabilityKey('Quarter Finals'), false);
  const leftGroupsQF = projectRound(leftGroupsR16, leftXs[1], leftXs[2], getProbabilityKey('Semi Finals'), false);
  const leftGroupsSF = projectRound(leftGroupsQF, leftXs[2], leftXs[3], getProbabilityKey('Finals'), false);

  const rightGroupsR16 = projectRound(rightGroupsR32, rightXs[0], rightXs[1], getProbabilityKey('Quarter Finals'), true);
  const rightGroupsQF = projectRound(rightGroupsR16, rightXs[1], rightXs[2], getProbabilityKey('Semi Finals'), true);
  const rightGroupsSF = projectRound(rightGroupsQF, rightXs[2], rightXs[3], getProbabilityKey('Finals'), true);

  if (leftGroupsSF.length > 0 && rightGroupsSF.length > 0) {
    const finalY = (leftGroupsSF[0].yMid + rightGroupsSF[0].yMid) / 2;
    const winner = chooseMatchWinner(leftGroupsSF[0].winner, rightGroupsSF[0].winner, getProbabilityKey('Winner'));

    drawConnector(leftXs[3] + boxW, leftGroupsSF[0].yMid, centerX, finalY);
    drawConnector(rightXs[3], rightGroupsSF[0].yMid, centerX + centerBoxW, finalY);
    svg.appendChild(drawBox(centerX, finalY - boxH / 2, winner, 'Winner'));

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', centerX + centerBoxW / 2);
    label.setAttribute('y', finalY - boxH / 2 - 14);
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

async function initializeDashboard() {
  try {
    const loadedState = await loadData();
    renderDashboard(loadedState);
    // Auto-populate CONMEBOL offset from loaded data or localStorage
    try {
      const offsetEl = document.getElementById('conmebol-offset');
      if (offsetEl) {
        if (loadedState && loadedState.conmebol_offset !== undefined && loadedState.conmebol_offset !== null) {
          offsetEl.value = String(loadedState.conmebol_offset);
        } else if (localStorage.getItem('last_conmebol_offset') !== null) {
          offsetEl.value = localStorage.getItem('last_conmebol_offset');
        }
        // validate on init
        validateConmebolOffset();
      }
    } catch (err) {
      // ignore
    }

    const simulationButton = document.getElementById("simulation-run-button");
    if (simulationButton) {
      simulationButton.addEventListener("click", () => {
        const countInput = document.getElementById("simulation-count");
        const simulations = Number(countInput?.value) || 200;
        runSimulation(simulations);
      });
    }
    // live-validate input
    const offsetInput = document.getElementById('conmebol-offset');
    if (offsetInput) {
      offsetInput.addEventListener('input', () => validateConmebolOffset());
    }
  } catch (error) {
    const errorDetails = error?.stack || error?.message || String(error);
    document.body.innerHTML = `<div class="page-shell"><div class="hero-card"><h1>Unable to load dashboard data</h1><p>${error?.message || 'Unknown error'}</p><pre style="white-space: pre-wrap; color: #f9fafb; margin-top: 12px;">${errorDetails}</pre></div></div>`;
    console.error(error);
  }
}

initializeDashboard();
