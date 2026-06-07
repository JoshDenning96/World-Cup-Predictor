const DATA_URL = "data/master_simulation.json";
let state = {};

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
  const cards = [
    createSummaryCard("Simulation runs", data.tournament_simulation.length ? `${data.tournament_simulation.length} teams` : "N/A"),
    createSummaryCard("Best champion", winner ? winner.team : "N/A", formatPercent(winner?.prob_Winner ?? 0)),
    createSummaryCard("Top advance chance", data.group_probabilities.length ? data.group_probabilities[0].team : "N/A", formatPercent(data.group_probabilities[0]?.advance_probability ?? 0)),
    createSummaryCard("Exported groups", `${new Set(data.group_tables.map((row) => row.group)).size} groups`),
  ];
  document.getElementById("summary-cards").innerHTML = cards.join("");
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

function renderWinnerChart(data) {
  const top = getTopTeamsByWinProbability(data, 10);
  const labels = top.map((row) => row.team);
  const values = top.map((row) => row.prob_Winner);
  const colors = top.map((_, index) => `rgba(124, 58, 237, ${0.8 - index * 0.05})`);
  renderChart("winnerChart", labels, values, "Win probability", colors);
}

function renderAdvanceChart(data) {
  const top = getTopAdvanceTeams(data, 10);
  const labels = top.map((row) => row.team);
  const values = top.map((row) => row.advance_probability);
  const colors = top.map((_, index) => `rgba(59, 130, 246, ${0.8 - index * 0.04})`);
  renderChart("advanceChart", labels, values, "Advance probability", colors);
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

function renderKnockoutProjection(data) {
  const stages = [
    { key: "prob_Round_of_32", label: "Round of 32" },
    { key: "prob_Round_of_16", label: "Round of 16" },
    { key: "prob_Quarter_Finals", label: "Quarter Finals" },
    { key: "prob_Semi_Finals", label: "Semi Finals" },
    { key: "prob_Finals", label: "Finals" },
    { key: "prob_Winner", label: "Winner" },
  ];

  const rows = [...data.tournament_simulation]
    .sort((a, b) => b.prob_Winner - a.prob_Winner)
    .slice(0, 12);

  const html = rows
    .map((row) => {
      const cells = stages
        .map((stage) => {
          const value = row[stage.key] ?? 0;
          const width = Math.max(6, Math.min(100, value * 100));
          const filled = value > 0;
          return `
            <div class="knockout-cell">
              <div class="knockout-bar ${filled ? "" : "empty"}" style="width: ${width}%"></div>
              <div class="knockout-label ${filled ? "" : "muted"}">${formatPercent(value)}</div>
            </div>
          `;
        })
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
}

function populateGroupSelect(data) {
  const groups = [...new Set(data.group_tables.map((row) => row.group))].sort();
  const select = document.getElementById("group-select");
  select.innerHTML = groups.map((group) => `<option value="${group}">${group}</option>`).join("");
  select.addEventListener("change", (event) => renderGroupTable(data, event.target.value));
  if (groups.length) {
    renderGroupTable(data, groups[0]);
  }
}

async function loadData() {
  const response = await fetch(DATA_URL);
  if (!response.ok) {
    throw new Error(`Unable to load data from ${DATA_URL}`);
  }
  return await response.json();
}

function renderBracket(data, count = 32) {
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

  // Ensure tooltip element exists
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

  const top2 = [];
  const thirdCandidates = [];
  groups.forEach((g) => {
    const rows = groupMap[g] || [];
    if (rows[0]) top2.push(rows[0].team);
    if (rows[1]) top2.push(rows[1].team);
    if (rows.length >= 3) {
      const third = rows.reduce((best, r) => (r.prob_3 > (best.prob_3 || 0) ? r : best), rows[2]);
      thirdCandidates.push({ team: third.team, prob_3: third.prob_3 });
    }
  });
  const needed = Math.max(0, 32 - top2.length);
  const bestThirds = thirdCandidates.sort((a, b) => b.prob_3 - a.prob_3).slice(0, needed).map((t) => t.team);
  let teams = [...top2, ...bestThirds].map((teamName) => ({ team: teamName, ...(probMap[teamName] || {}) }));
  if (count && teams.length > count) teams = teams.slice(0, count);

  // Build R32 match pairs
  const r32Matches = [];
  for (let i = 0; i < teams.length; i += 2) {
    r32Matches.push([teams[i], teams[i + 1]]);
  }

  const viewW = 1400;
  const viewH = Math.max(800, r32Matches.length * 32 + 100);
  svg.setAttribute('viewBox', `0 0 ${viewW} ${viewH}`);
  svg.innerHTML = '';

  const boxW = 120;
  const boxH = 28;
  const stageXs = [80, 280, 470, 660, 850, 1050];
  const stages = ['R32', 'R16', 'QF', 'SF', 'Final', 'Winner'];

  function drawBox(x, y, teamObj, stage) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const box = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    box.setAttribute('x', x);
    box.setAttribute('y', y);
    box.setAttribute('width', boxW);
    box.setAttribute('height', boxH);
    box.setAttribute('class', 'match-box');
    box.setAttribute('fill', 'rgba(31,47,91,0.6)');
    box.setAttribute('stroke', 'rgba(255,255,255,0.12)');
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
      text.textContent = flag + (teamObj.team || '').substring(0, 16);
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
    path.setAttribute('stroke', 'rgba(255,255,255,0.1)');
    path.setAttribute('stroke-width', '1');
    svg.appendChild(path);
  }

  // Render R32 matches
  const r32Boxes = [];
  r32Matches.forEach((match, idx) => {
    const y = 50 + idx * 70;
    const top = drawBox(stageXs[0], y, match[0], 'R32');
    const bottom = drawBox(stageXs[0], y + boxH + 8, match[1], 'R32');
    svg.appendChild(top);
    svg.appendChild(bottom);
    r32Boxes.push({ match, y: y + boxH / 2, y2: y + boxH + 8 + boxH / 2 });
  });

  // Render R16, QF, SF, Final progression
  let prevStage = r32Boxes;
  for (let stage = 1; stage < 5; stage++) {
    const nextStage = [];
    for (let i = 0; i < prevStage.length; i += 2) {
      const box1 = prevStage[i];
      const box2 = prevStage[i + 1];
      const midY = (box1.y + box2.y2) / 2;

      const t1 = box1.match ? box1.match[0] : box1;
      const t2 = box2.match ? box2.match[0] : box2;
      const winner = (t1.prob_Winner || 0) > (t2.prob_Winner || 0) ? t1 : t2;

      const newBox = drawBox(stageXs[stage], midY - boxH / 2, winner, stages[stage]);
      svg.appendChild(newBox);

      drawConnector(stageXs[stage - 1] + boxW, box1.y, stageXs[stage], midY - boxH / 2 + boxH / 2);
      drawConnector(stageXs[stage - 1] + boxW, box2.y2, stageXs[stage], midY - boxH / 2 + boxH / 2);

      nextStage.push({ match: [winner], y: midY - boxH / 2 + boxH / 2 });
    }
    prevStage = nextStage;
  }

  // Render Winner
  if (prevStage.length > 0) {
    const winner = prevStage[0];
    const winnerBox = drawBox(stageXs[5], viewH / 2 - boxH / 2, winner.match[0], 'Winner');
    svg.appendChild(winnerBox);
    drawConnector(stageXs[4] + boxW, winner.y, stageXs[5], viewH / 2);
  }

  // Draw stage labels
  stages.forEach((s, i) => {
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', stageXs[i] + boxW / 2);
    label.setAttribute('y', 25);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', '11');
    label.setAttribute('fill', 'rgba(255,255,255,0.4)');
    label.textContent = s;
    svg.appendChild(label);
  });
}

async function initializeDashboard() {
  try {
    state = await loadData();
    renderSummary(state);
    renderWinnerChart(state);
    renderAdvanceChart(state);
    renderKnockoutProjection(state);
    populateGroupSelect(state);
    // Always render full 32-team bracket
    renderBracket(state, 32);
  } catch (error) {
    document.body.innerHTML = `<div class="page-shell"><div class="hero-card"><h1>Unable to load dashboard data</h1><p>${error.message}</p></div></div>`;
    console.error(error);
  }
}

initializeDashboard();
