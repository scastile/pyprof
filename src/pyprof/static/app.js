/* pyprof dashboard — d3.js flame graph + call tree + diff view */

let profileData = null;
let diffData = null;
let currentSort = 'time';
let sortDir = -1;
let currentFilter = '';

/* ── Init ────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadData();
});

async function loadData() {
  try {
    const resp = await fetch('/api/data');
    if (!resp.ok) throw new Error('No profile data');
    profileData = await resp.json();
    document.getElementById('command').textContent = profileData.command;
    document.getElementById('total-time').textContent =
      `total: ${profileData.total_time.toFixed(4)}s`;

    // Check for diff
    const diffResp = await fetch('/api/diff');
    if (diffResp.ok) {
      diffData = await diffResp.json();
      document.querySelector('.diff-btn').classList.remove('hidden');
    }

    renderFlameGraph();
    renderTable();
    if (diffData) renderDiff();
  } catch (e) {
    console.error('Failed to load data:', e);
    document.getElementById('flame-info').innerHTML =
      `<p style="color:var(--danger)">Error loading profile data: ${e.message}</p>`;
  }
}

/* ── Tab switching ──────────────────────────────────── */
function showTab(tab, btn) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  if (btn) btn.classList.add('active');

  document.getElementById('flame-view').classList.toggle('hidden', tab !== 'flame');
  document.getElementById('table-view').classList.toggle('hidden', tab !== 'table');
  document.getElementById('diff-view').classList.toggle('hidden', tab !== 'diff');
}

/* ── Helpers ────────────────────────────────────────── */
function fmtTime(t) {
  if (t >= 1) return t.toFixed(3) + 's';
  if (t >= 0.001) return (t * 1000).toFixed(1) + 'ms';
  return (t * 1e6).toFixed(0) + '\u00b5s';
}

const PALETTE = [
  '#58a6ff', '#3fb950', '#a371f7', '#f78166',
  '#d29922', '#56d4dd', '#db61a2', '#8b949e',
  '#79c0ff', '#56d364', '#d2a8ff', '#ff7b72',
  '#e3b341', '#7ee787', '#f0883e', '#6e7681',
];

function colorFor(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

/* ── Flame Graph (d3.js) ────────────────────────────── */

function renderFlameGraph() {
  const container = document.getElementById('flame-chart');
  container.innerHTML = '';
  if (!profileData || !profileData.flame_tree) return;

  const treeData = profileData.flame_tree;
  const totalTime = profileData.total_time || 1;

  const containerRect = container.getBoundingClientRect();
  const width = Math.max(containerRect.width, 800);
  const frameHeight = 22;
  const maxDepth = maxNodeDepth(treeData);
  const height = (maxDepth + 3) * frameHeight;

  const svg = d3.select(container).append('svg')
    .attr('width', width)
    .attr('height', height);

  // Use d3.hierarchy with the raw data values (not summed)
  const root = d3.hierarchy(treeData, d => d.children || [])
    .sum(d => d.value || 0)
    .sort((a, b) => b.value - a.value);

  // d3.partition does the layout correctly
  const marginTop = frameHeight;  // reserve space for reset zoom bar
  d3.partition()
    .size([width, height - marginTop])
    (root);

  const g = svg.selectAll('g')
    .data(root.descendants())
    .join('g')
    .attr('transform', d => `translate(${d.x0},${marginTop + d.depth * frameHeight})`);

  // Bars
  g.append('rect')
    .attr('class', 'flame-rect')
    .attr('width', d => Math.max(d.x1 - d.x0 - 1, 1))
    .attr('height', frameHeight - 2)
    .attr('fill', d => colorFor(d.data.name))
    .on('click', (e, d) => zoomFlame(d, root, svg, width, frameHeight, totalTime))
    .on('mouseover', (e, d) => showTooltip(e, d, totalTime))
    .on('mouseout', hideTooltip);

  // Labels
  g.append('text')
    .attr('class', 'flame-label')
    .attr('x', 6)
    .attr('y', 14)
    .text(d => {
      const w = Math.max(d.x1 - d.x0 - 1, 1);
      if (w < 40) return '';
      const label = shortenName(d.data.name);
      return label.length > (w / 7) ? label.slice(0, w / 7) + '\u2026' : label;
    });

  // Zoom reset bar
  svg.append('rect')
    .attr('class', 'flame-zoom-bar')
    .attr('x', 0).attr('y', 0)
    .attr('width', width).attr('height', frameHeight - 2)
    .on('click', () => resetZoom(root, svg, width, frameHeight, totalTime));

  svg.append('text')
    .attr('class', 'flame-label')
    .attr('x', 8)
    .attr('y', 14)
    .attr('fill', '#fff')
    .text('Reset zoom');
}

function maxNodeDepth(node) {
  if (!node.children || !node.children.length) return 0;
  return 1 + Math.max(...node.children.map(maxNodeDepth));
}

function shortenName(name) {
  // "func_name (file.py:42)" -> "func_name"
  const paren = name.indexOf(' (');
  return paren > -1 ? name.slice(0, paren) : name;
}

function zoomFlame(node, root, svg, width, frameHeight, totalTime) {
  // Zoom so that this node fills the full width
  const targetWidth = (node.x1 - node.x0);
  if (targetWidth <= 0) return;
  const scale = width / targetWidth;

  svg.selectAll('g').transition().duration(300)
    .attr('transform', d => {
      const nx0 = (d.x0 - node.x0) * scale;
      const nx1 = (d.x1 - node.x0) * scale;
      d._zoomedX0 = nx0;
      d._zoomedX1 = nx1;
      return `translate(${nx0},${d.depth * frameHeight})`;
    });

  svg.selectAll('.flame-rect').transition().duration(300)
    .attr('width', d => Math.max((d._zoomedX1 || d.x1) - (d._zoomedX0 || d.x0) - 1, 1));

  svg.selectAll('.flame-label').transition().duration(300)
    .attr('x', 6)
    .text(d => {
      const w = Math.max((d._zoomedX1 || d.x1) - (d._zoomedX0 || d.x0) - 1, 1);
      if (w < 40) return '';
      const label = shortenName(d.data.name);
      return label.length > (w / 7) ? label.slice(0, w / 7) + '\u2026' : label;
    });
}

function resetZoom(root, svg, width, frameHeight, totalTime) {
  renderFlameGraph();
}

/* ── Tooltip ────────────────────────────────────────── */
function showTooltip(e, d, totalTime) {
  const tt = document.getElementById('tooltip');
  const pct = ((d.data.value / totalTime) * 100).toFixed(1);
  tt.innerHTML = `
    <div class="tt-time">${fmtTime(d.data.value)}</div>
    <div class="tt-pct">${pct}% of total</div>
    <div class="tt-file">${d.data.name}</div>
  `;
  tt.classList.remove('hidden');
  tt.style.left = (e.clientX + 14) + 'px';
  tt.style.top = (e.clientY - 10) + 'px';
}

function hideTooltip() {
  document.getElementById('tooltip').classList.add('hidden');
}

/* ── Call Tree Table ────────────────────────────────── */
function renderTable() {
  if (!profileData) return;

  const sortField = document.getElementById('sort-select').value;
  const limit = parseInt(document.getElementById('limit-select').value, 10);
  const filter = document.getElementById('filter-input').value.toLowerCase();

  let funcs = [...profileData.functions];

  // Filter
  if (filter) {
    funcs = funcs.filter(f =>
      f.func_name.toLowerCase().includes(filter) ||
      f.filename.toLowerCase().includes(filter)
    );
  }

  // Sort
  const keyMap = {
    cumulative: f => f.total_time,
    time: f => f.self_time,
    calls: f => f.call_count,
    name: f => f.func_name,
  };
  const keyFn = keyMap[sortField] || keyMap.time;
  funcs.sort((a, b) => {
    const va = keyFn(a), vb = keyFn(b);
    return typeof va === 'string' ? va.localeCompare(vb) : vb - va;
  });
  funcs = funcs.slice(0, limit);

  const tbody = document.getElementById('func-tbody');
  tbody.innerHTML = funcs.map(f => `
    <tr>
      <td>${fmtTime(f.self_time)}</td>
      <td>${fmtTime(f.total_time)}</td>
      <td>${f.call_count}</td>
      <td>${escHtml(f.func_name)} <span style="color:var(--text-dim)">(${escHtml(f.filename)}:${f.line_no})</span></td>
    </tr>
  `).join('');
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/* ── Diff View ──────────────────────────────────────── */
function renderDiff() {
  if (!diffData) return;

  const changed = (diffData.changed || []).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

  document.getElementById('diff-summary').innerHTML = `
    <div class="diff-stat added">Added: <span class="num">${diffData.added.length}</span></div>
    <div class="diff-stat removed">Removed: <span class="num">${diffData.removed.length}</span></div>
    <div class="diff-stat changed">Changed: <span class="num">${changed.length}</span></div>
  `;

  const tbody = document.getElementById('diff-tbody');
  tbody.innerHTML = changed.map(d => `
    <tr>
      <td class="${d.delta > 0 ? 'deltapos' : 'deltaneg'}">${d.delta > 0 ? '+' : ''}${fmtTime(d.delta)}</td>
      <td class="${d.delta > 0 ? 'deltapos' : 'deltaneg'}">${d.pct_change > 0 ? '+' : ''}${d.pct_change}%</td>
      <td>${fmtTime(d.old_time)}</td>
      <td>${fmtTime(d.new_time)}</td>
      <td>${escHtml(shortenName(d.func))}</td>
    </tr>
  `).join('');
}
