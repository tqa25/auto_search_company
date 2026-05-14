// ===================== CONFIG =====================
const STEP_COLORS = ["#818cf8","#60a5fa","#22d3ee","#c084fc","#34d399"];
const STEP_TAGS = [
  ["Excel","SQLite","Resumable"],
  ["AI Model","Grounding","JSON"],
  ["Serper API","Maps","High Trust"],
  ["SearchModule","4-Strategy","Dedup"],
  ["Firecrawl","AI Extract","Conflict Resolution"]
];
const SUB_STEPS_MAP = {
  3: [{id:"4.1",title:"Contact Query"},{id:"4.2",title:"Infer VN"},{id:"4.3",title:"Tax Code"},{id:"4.4",title:"Bare Query"}],
  4: [{id:"5.1",title:"Firecrawl"},{id:"5.2",title:"AI Extract"}]
};
const NODE_POSITIONS = [
  {x:50,y:30},{x:250,y:160},{x:490,y:30},{x:700,y:160},{x:930,y:30}
];
const CONN_PAIRS = [{from:0,to:1},{from:1,to:2},{from:2,to:3},{from:3,to:4}];

let currentLang = 'vi';
let subStepsVisible = false;

// ===================== LANGUAGE =====================
function setLang(lang) {
  currentLang = lang;
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.toggle('active', b.dataset.lang === lang));
  document.documentElement.lang = lang;
  rebuildUI();
}

function T() { return I18N[currentLang]; }

// ===================== REBUILD =====================
function rebuildUI() {
  const t = T();
  document.getElementById('headerBadge').textContent = t.badge;
  document.getElementById('headerTitle').textContent = t.title;
  document.getElementById('headerSubtitle').innerHTML = t.subtitle;
  t.stats.forEach((s,i) => { const el = document.querySelectorAll('.stat-label')[i]; if(el) el.textContent = s; });
  document.querySelector('[data-action="substeps"]').innerHTML = t.btnSub;
  document.querySelector('[data-action="highlight"]').innerHTML = t.btnHighlight;
  document.getElementById('footerTitle').textContent = t.footerTitle;
  document.getElementById('footerHint').textContent = t.footerHint;
  document.querySelectorAll('.legend-text').forEach((el,i) => el.textContent = t.legendItems[i]);
  
  // Rebuild nodes
  const canvas = document.getElementById('diagramCanvas');
  canvas.querySelectorAll('.node,.sub-node,.line-label').forEach(n => n.remove());
  renderNodes();
  renderSubSteps();
  updateLineLabels();
}

// ===================== NODES =====================
function renderNodes() {
  const canvas = document.getElementById('diagramCanvas');
  const t = T();
  t.steps.forEach((step, i) => {
    const pos = NODE_POSITIONS[i];
    const node = document.createElement('div');
    node.className = 'node';
    node.style.cssText = `left:${pos.x}px;top:${pos.y}px;--node-color:${STEP_COLORS[i]};animation-delay:${i*0.12}s`;
    node.dataset.step = i;
    node.innerHTML = `
      <div class="node-glow"></div>
      <div class="node-step">${i+1}</div>
      <div class="node-title">${step.title}</div>
      <div class="node-subtitle">${step.subtitle}</div>
      <div class="node-status"><span class="status-dot"></span>${step.status}</div>
      <div class="node-tooltip">
        <h4>⚡ ${step.titleEn}</h4>
        <p>${step.tooltip}</p>
        <div class="tooltip-tags">${STEP_TAGS[i].map(tg=>`<span class="tag">${tg}</span>`).join('')}</div>
      </div>`;
    node.addEventListener('click', () => openModal(i));
    node.addEventListener('mouseenter', () => highlightConnections(i, true));
    node.addEventListener('mouseleave', () => highlightConnections(i, false));
    canvas.appendChild(node);
  });
}

// ===================== CONNECTIONS =====================
function getNodeCenter(idx) {
  const p = NODE_POSITIONS[idx];
  return {x:p.x+110, y:p.y+70};
}

function renderConnections() {
  const svg = document.getElementById('connectionsSvg');
  const defs = document.createElementNS("http://www.w3.org/2000/svg","defs");
  const grad = document.createElementNS("http://www.w3.org/2000/svg","linearGradient");
  grad.id = "lineGradient";
  grad.innerHTML = `<stop offset="0%" stop-color="#818cf8"/><stop offset="100%" stop-color="#22d3ee"/>`;
  defs.appendChild(grad);
  const filter = document.createElementNS("http://www.w3.org/2000/svg","filter");
  filter.id = "glowFilter";
  filter.innerHTML = `<feGaussianBlur stdDeviation="3" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>`;
  defs.appendChild(filter);
  svg.appendChild(defs);

  CONN_PAIRS.forEach((c,i) => {
    const f = getNodeCenter(c.from), t = getNodeCenter(c.to);
    const mx = (f.x+t.x)/2, my = Math.min(f.y,t.y) - 30 + (i%2===0 ? -20 : 40);
    const path = `M${f.x},${f.y} Q${mx},${my} ${t.x},${t.y}`;

    const base = document.createElementNS("http://www.w3.org/2000/svg","path");
    base.setAttribute("d",path); base.setAttribute("class","connection-line"); base.dataset.conn=i;
    svg.appendChild(base);

    const glow = document.createElementNS("http://www.w3.org/2000/svg","path");
    glow.setAttribute("d",path); glow.setAttribute("class","connection-line-glow");
    glow.setAttribute("filter","url(#glowFilter)"); glow.dataset.conn=i;
    svg.appendChild(glow);

    const circle = document.createElementNS("http://www.w3.org/2000/svg","circle");
    circle.setAttribute("r","3"); circle.setAttribute("class","connection-particle"); circle.dataset.conn=i;
    circle.style.opacity="0";
    const anim = document.createElementNS("http://www.w3.org/2000/svg","animateMotion");
    anim.setAttribute("dur",`${2+i*0.5}s`); anim.setAttribute("repeatCount","indefinite"); anim.setAttribute("path",path);
    circle.appendChild(anim);
    svg.appendChild(circle);
  });
}

function updateLineLabels() {
  document.querySelectorAll('.line-label').forEach(l => l.remove());
  const canvas = document.getElementById('diagramCanvas');
  const t = T();
  CONN_PAIRS.forEach((c,i) => {
    const f = getNodeCenter(c.from), to = getNodeCenter(c.to);
    const mx = (f.x+to.x)/2, my = Math.min(f.y,to.y) - 30 + (i%2===0 ? -20 : 40);
    const label = document.createElement('div');
    label.className = 'line-label'; label.dataset.conn = i;
    label.textContent = t.connections[i].label;
    label.style.left = `${mx-60}px`; label.style.top = `${my+(i%2===0?-18:12)}px`;
    canvas.appendChild(label);
  });
}

function highlightConnections(stepIdx, active) {
  CONN_PAIRS.forEach((c,i) => {
    if (c.from===stepIdx || c.to===stepIdx) {
      document.querySelectorAll(`.connection-line-glow[data-conn="${i}"]`).forEach(l=>l.style.opacity=active?"1":"0");
      document.querySelectorAll(`.connection-particle[data-conn="${i}"]`).forEach(p=>p.style.opacity=active?"1":"0");
      document.querySelectorAll(`.line-label[data-conn="${i}"]`).forEach(l=>l.classList.toggle('visible',active));
    }
  });
}

// ===================== MODAL =====================
function openModal(idx) {
  const t = T();
  const step = t.steps[idx];
  const d = step.detail;
  const sec = t.modalSections;
  const overlay = document.getElementById('modalOverlay');
  const modal = overlay.querySelector('.modal');
  modal.querySelector('.step-badge').style.background = STEP_COLORS[idx];
  modal.querySelector('.step-badge').textContent = idx+1;
  modal.querySelector('.modal-title-text').textContent = `${step.title} — ${step.titleEn}`;

  let html = `
    <div class="modal-section"><h3>${sec.mission}</h3><div class="detail-card"><p>${d.mission}</p></div></div>
    <div class="modal-section"><h3>${sec.input}</h3><div class="detail-card"><p>${d.input}</p></div></div>
    <div class="modal-section"><h3>${sec.process}</h3>
      <ul class="flow-list">${d.process.map((p,j)=>`
        <li class="flow-item"><div class="flow-marker"><div class="flow-dot" style="background:${STEP_COLORS[idx]}"></div>
        ${j<d.process.length-1?`<div class="flow-line-v" style="background:linear-gradient(to bottom,${STEP_COLORS[idx]},transparent)"></div>`:''}</div>
        <div class="flow-content"><h4>${p.title}</h4><p>${p.desc}</p></div></li>`).join('')}</ul></div>`;

  if(d.earlyStop) html += `<div class="modal-section"><h3>${sec.earlyStop}</h3><div class="early-stop-badge">🛑 ${d.earlyStop}</div></div>`;
  html += `<div class="modal-section"><h3>${sec.output}</h3><div class="detail-card"><p>${d.output.replace(/\n/g,'<br>')}</p></div></div>`;
  html += `<div class="modal-section"><h3>${sec.example}</h3><div class="detail-card" style="border-color:rgba(251,191,36,0.2)"><p class="highlight">${d.example}</p></div></div>`;

  modal.querySelector('.modal-body').innerHTML = html;
  overlay.classList.add('active');
  document.body.style.overflow='hidden';
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('active');
  document.body.style.overflow='';
}

// ===================== SUB-STEPS =====================
function toggleSubSteps() {
  subStepsVisible = !subStepsVisible;
  document.querySelectorAll('.sub-node').forEach(n=>n.classList.toggle('visible',subStepsVisible));
  document.querySelector('[data-action="substeps"]').classList.toggle('active',subStepsVisible);
}

function renderSubSteps() {
  const canvas = document.getElementById('diagramCanvas');
  Object.entries(SUB_STEPS_MAP).forEach(([stepIdx, subs]) => {
    const pos = NODE_POSITIONS[parseInt(stepIdx)];
    const color = STEP_COLORS[parseInt(stepIdx)];
    subs.forEach((sub,i) => {
      const el = document.createElement('div');
      el.className = 'sub-node' + (subStepsVisible?' visible':'');
      el.style.cssText = `left:${pos.x-30+i*55}px;top:${pos.y+155+Math.abs(i-1)*10}px;--node-color:${color}`;
      el.innerHTML = `<div class="sub-node-label">${sub.id}</div><div class="sub-node-title">${sub.title}</div>`;
      el.addEventListener('click',e=>{e.stopPropagation();openModal(parseInt(stepIdx));});
      canvas.appendChild(el);
    });
  });
}

function highlightAll() {
  document.querySelectorAll('.node').forEach(n=>{
    n.dispatchEvent(new Event('mouseenter'));
    setTimeout(()=>n.dispatchEvent(new Event('mouseleave')),2500);
  });
}

// ===================== INIT =====================
document.addEventListener('DOMContentLoaded', () => {
  renderNodes();
  renderConnections();
  renderSubSteps();
  updateLineLabels();
  document.getElementById('modalOverlay').addEventListener('click',e=>{if(e.target===e.currentTarget)closeModal();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
});
