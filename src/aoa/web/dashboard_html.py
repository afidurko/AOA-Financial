"""Interactive team-embedded dashboard HTML."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AOA Financial</title>
  <style>
    :root {
      --bg:#0f1419; --surface:#1a2332; --border:#2d3a4f;
      --text:#e7ecf3; --muted:#8b9cb3; --accent:#3b82f6;
      --green:#22c55e; --red:#ef4444; --amber:#f59e0b;
    }
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:ui-sans-serif,system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.5}
    header{padding:1rem 1.5rem;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;flex-wrap:wrap;gap:1rem}
    main{padding:1.5rem;max-width:1280px;margin:0 auto}
    .badge{display:inline-block;padding:.15rem .55rem;border-radius:999px;font-size:.75rem;font-weight:600;text-transform:uppercase}
    .badge-paper{background:#1e3a5f;color:#93c5fd}.badge-live{background:#450a0a;color:#fca5a5}.badge-dry{background:#422006;color:#fcd34d}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem;margin-bottom:1rem}
    .card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1rem 1.25rem}
    .card h2{font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:.75rem}
    .stat{font-size:1.4rem;font-weight:700}.stat-sm{font-size:.85rem;color:var(--muted);margin-top:.25rem}
    .actions{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem}
    button{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:.5rem .9rem;font-size:.85rem;font-weight:600;cursor:pointer}
    button.secondary{background:var(--surface);border:1px solid var(--border);color:var(--text)}
    button.danger{background:var(--red)} button.ok{background:var(--green)}
    table{width:100%;border-collapse:collapse;font-size:.85rem}
    th,td{text-align:left;padding:.45rem .6rem;border-bottom:1px solid var(--border)}
    th{color:var(--muted);font-size:.7rem;text-transform:uppercase}
    .team-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:.75rem}
    .member{border:1px solid var(--border);border-radius:8px;padding:.75rem;cursor:pointer}
    .member.ok{border-color:var(--green)} .member.warn{border-color:var(--amber)}
    .member h3{font-size:.9rem;margin-bottom:.35rem}.member p{font-size:.8rem;color:var(--muted)}
    .detail{display:none;margin-top:.5rem;font-size:.8rem;color:var(--text)}
    .member.open .detail{display:block}
    .approved{color:var(--green)}.blocked{color:var(--red)}
    .tabs{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}
    .tab{padding:.35rem .75rem;border-radius:6px;border:1px solid var(--border);cursor:pointer;font-size:.8rem}
    .tab.active{background:var(--accent);border-color:var(--accent)}
    .panel{display:none}.panel.active{display:block}
    #toast{position:fixed;bottom:1.5rem;right:1.5rem;background:var(--surface);border:1px solid var(--border);padding:.75rem 1rem;border-radius:8px;display:none;max-width:360px;font-size:.85rem}
  </style>
</head>
<body>
  <header>
    <div><h1>AOA Financial</h1> <span id="mode-badge" class="badge badge-paper">…</span></div>
    <div id="market-status" class="stat-sm">Market: —</div>
  </header>
  <main>
    <div class="actions">
      <button onclick="runCycle()">Run cycle</button>
      <button class="secondary" onclick="startLoop()">Start loop</button>
      <button class="secondary danger" onclick="stopLoop()">Stop loop</button>
      <button class="secondary" onclick="discoverResearch()">Scholar scan</button>
      <button class="secondary" onclick="proposePromotions()">Build sub-teams</button>
      <button class="secondary" onclick="refresh()">Refresh</button>
    </div>
    <div class="grid">
      <div class="card"><h2>Equity</h2><div class="stat" id="equity">—</div></div>
      <div class="card"><h2>Cash</h2><div class="stat" id="cash">—</div></div>
      <div class="card"><h2>Loop</h2><div class="stat" id="loop-status">—</div><div class="stat-sm" id="loop-detail"></div></div>
      <div class="card"><h2>ROI summary</h2><div class="stat-sm" id="roi-summary">—</div></div>
    </div>
    <div class="tabs">
      <div class="tab" data-tab="assistant">Assistant</div>
      <div class="tab active" data-tab="team">Team</div>
      <div class="tab" data-tab="analysts">Analysts</div>
      <div class="tab" data-tab="trades">Trades</div>
      <div class="tab" data-tab="approvals">Approvals</div>
      <div class="tab" data-tab="research">Research</div>
      <div class="tab" data-tab="promotions">Promotions</div>
      <div class="tab" data-tab="catalysts">Catalysts</div>
      <div class="tab" data-tab="risk">Risk plans</div>
      <div class="tab" data-tab="journal">Journal</div>
    </div>
    <div id="panel-assistant" class="panel card">
      <h2>Alex — your priorities</h2>
      <div class="stat-sm" id="assistant-focus">Focus: —</div>
      <div class="stat-sm" id="assistant-summary" style="margin:.5rem 0"></div>
      <div id="assistant-must"></div>
      <div id="assistant-should"></div>
      <div id="assistant-later"></div>
      <button class="secondary" style="margin-top:.75rem" onclick="loadAssistant()">Refresh priorities</button>
    </div>
    <div id="panel-team" class="panel active card">
      <h2>Team roster — click to expand</h2>
      <div class="team-grid" id="team-roster"></div>
    </div>
    <div id="panel-analysts" class="panel card">
      <h2>Analyst reports</h2>
      <table><thead><tr><th>Symbol</th><th>Analyst</th><th>Direction</th><th>Conviction</th><th>Summary</th></tr></thead>
      <tbody id="analysts-body"><tr><td colspan="5">No reports yet</td></tr></tbody></table>
    </div>
    <div id="panel-trades" class="panel card">
      <h2>Positions & proposals</h2>
      <table><thead><tr><th>Symbol</th><th>Qty</th><th>MV</th><th>uPL</th></tr></thead>
      <tbody id="positions-body"></tbody></table>
      <h2 style="margin-top:1rem">Proposals</h2>
      <table><thead><tr><th>Status</th><th>Side</th><th>Symbol</th><th>Strategy</th><th>Notional</th></tr></thead>
      <tbody id="proposals-body"></tbody></table>
    </div>
    <div id="panel-approvals" class="panel card">
      <h2>Approval inbox</h2>
      <div id="approvals-list"></div>
    </div>
    <div id="panel-research" class="panel card">
      <h2>Scholar research proposals</h2>
      <div id="research-list"></div>
    </div>
    <div id="panel-promotions" class="panel card">
      <h2>Team promotions — review &amp; edit before approving</h2>
      <p class="stat-sm" style="margin-bottom:.75rem">Each lead proposes a small sub-team. Edit roles or mission, then approve or reject.</p>
      <div id="promotions-list"></div>
    </div>
    <div id="panel-catalysts" class="panel card">
      <h2>Hailey — news &amp; catalysts</h2>
      <div id="catalysts-list"></div>
    </div>
    <div id="panel-risk" class="panel card">
      <h2>Andrea — pre-execution risk &amp; trade plans</h2>
      <div id="risk-plans-list"></div>
    </div>
    <div id="panel-journal" class="panel card">
      <h2>Journal tail</h2>
      <div id="journal"></div>
    </div>
  </main>
  <div id="toast"></div>
  <script>
    const fmt = n => n==null?'—':'$'+Number(n).toLocaleString(undefined,{maximumFractionDigits:0});
    const toast = m => { const el=document.getElementById('toast'); el.textContent=m; el.style.display='block'; setTimeout(()=>el.style.display='none',4000); };
    document.querySelectorAll('.tab').forEach(t => t.onclick = () => {
      document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
      t.classList.add('active');
      document.getElementById('panel-'+t.dataset.tab).classList.add('active');
    });
    function toggleMember(el){ el.classList.toggle('open'); }
    async function refresh(){
      const [status,last,journal,roi,approvals,research,promotions] = await Promise.all([
        fetch('/api/status').then(r=>r.json()),
        fetch('/api/last-cycle').then(r=>r.json()),
        fetch('/api/journal?n=20').then(r=>r.json()),
        fetch('/api/analytics/roi').then(r=>r.json()).catch(()=>({})),
        fetch('/api/approvals').then(r=>r.json()).catch(()=>({items:[]})),
        fetch('/api/research/proposals').then(r=>r.json()).catch(()=>({items:[]})),
        fetch('/api/team/expansions').then(r=>r.json()).catch(()=>({items:[]})),
      ]);
      const badge=document.getElementById('mode-badge');
      badge.textContent=status.mode;
      badge.className='badge '+(status.mode==='live'?'badge-live':status.mode==='dry-run'?'badge-dry':'badge-paper');
      document.getElementById('market-status').textContent='Market: '+(status.market_open?'OPEN':'CLOSED')+' · '+status.broker;
      document.getElementById('equity').textContent=fmt(status.account.equity);
      document.getElementById('cash').textContent=fmt(status.account.settled_cash);
      document.getElementById('loop-status').textContent=status.loop.running?'Running':'Stopped';
      document.getElementById('loop-detail').textContent=status.loop.last_cycle_at||status.loop.last_error||'';
      document.getElementById('roi-summary').textContent=roi.cycles_recorded!=null
        ? `${roi.cycles_recorded} cycles · halt ${(roi.halt_rate*100).toFixed(0)}% · ${roi.approved_proposals} approved`
        : '—';
      const r=last.result||{};
      renderTeam(r);
      renderAnalysts(r);
      renderAssistantFrom(r.assistant);
      document.getElementById('positions-body').innerHTML=status.positions.length
        ? status.positions.map(p=>`<tr><td>${p.symbol}</td><td>${p.qty}</td><td>${fmt(p.market_value)}</td><td>${fmt(p.unrealized_pl)}</td></tr>`).join('')
        : '<tr><td colspan="4">No positions</td></tr>';
      const proposals=r.proposals||[];
      document.getElementById('proposals-body').innerHTML=proposals.length
        ? proposals.map(p=>`<tr><td class="${p.approved?'approved':'blocked'}">${p.approved?'OK':'block'}</td><td>${p.side}</td><td>${p.symbol}</td><td>${p.strategy||''}</td><td>${fmt(p.est_notional)}</td></tr>`).join('')
        : '<tr><td colspan="5">No proposals</td></tr>';
      document.getElementById('journal').innerHTML=(journal.entries||[]).slice().reverse().map(e=>
        `<div style="font-family:monospace;font-size:.8rem;padding:.3rem 0;border-bottom:1px solid var(--border)"><span style="color:var(--muted)">${e.ts||''}</span> ${e.event||''}</div>`
      ).join('')||'Empty';
      renderApprovals(approvals.items||[]);
      renderResearch(research.items||[]);
      renderPromotions(promotions.items||[]);
      renderCatalysts(r.catalysts||[]);
      renderRiskPlans(r.risk_plans||[]);
    }
    function renderTeam(r){
      const roster=[
        {name:'Bob',role:'Health',data:r.health,summary:r.health?.summary},
        {name:'Tom',role:'Trends',data:r.trends,count:(r.trends||[]).length},
        {name:'Julie',role:'Algorithms',data:r.algorithms,count:(r.algorithms||[]).length},
        {name:'Morgan',role:'Volume & Options',data:r.market_contexts,count:(r.market_contexts||[]).length},
        {name:'Hailey',role:'Catalysts',data:r.catalysts,count:(r.catalysts||[]).length},
        {name:'Alan',role:'Decision',data:r.decision,summary:r.decision?.summary},
        {name:'Andrea',role:'Risk',data:r.risk_plans,count:(r.risk_plans||[]).length},
        {name:'Aaron',role:'CEO',data:r.ceo,summary:r.ceo?.summary},
        {name:'Alex',role:'Assistant',data:r.assistant,summary:r.assistant?.focus},
      ];
      document.getElementById('team-roster').innerHTML=roster.map(m=>{
        const ok=m.data&&(m.count===undefined||m.count>0||m.data.can_proceed!==false);
        const detail=m.summary||(m.count!=null?`${m.count} reports`:JSON.stringify(m.data||{}).slice(0,120));
        return `<div class="member ${ok?'ok':'warn'}" onclick="toggleMember(this)"><h3>${m.name}</h3><p>${m.role}</p><div class="detail">${detail||'—'}</div></div>`;
      }).join('');
    }
    function renderAnalysts(r){
      const rows=[...(r.analyst_reports||[])];
      (r.trends||[]).forEach(t=>rows.push({symbol:t.symbol,analyst:'Tom',direction:t.direction,conviction:t.strength,summary:t.rationale}));
      (r.algorithms||[]).forEach(a=>rows.push({symbol:a.symbol,analyst:'Julie',direction:a.validated?'validated':'review',conviction:a.adjusted_strength,summary:a.method_notes}));
      (r.market_contexts||[]).forEach(m=>rows.push({symbol:m.symbol,analyst:'Morgan',direction:m.volume_regime,conviction:m.volume_ratio,summary:(m.options_volume_note?m.options_volume_note+' · ':'')+(m.summary||'')}));
      (r.catalysts||[]).forEach(c=>rows.push({symbol:c.symbol,analyst:'Hailey',direction:c.headline_sentiment,conviction:c.impact_score,summary:c.catalyst_summary}));
      document.getElementById('analysts-body').innerHTML=rows.length
        ? rows.map(x=>`<tr><td>${x.symbol||''}</td><td>${x.analyst||''}</td><td>${x.direction||''}</td><td>${x.conviction??'—'}</td><td>${(x.summary||'').slice(0,80)}</td></tr>`).join('')
        : '<tr><td colspan="5">No reports yet</td></tr>';
    }
    function renderApprovals(items){
      document.getElementById('approvals-list').innerHTML=items.length?items.map(a=>`
        <div style="border:1px solid var(--border);border-radius:8px;padding:.75rem;margin-bottom:.5rem">
          <strong>${a.title}</strong> <span style="color:var(--muted)">(${a.status})</span>
          <p style="font-size:.85rem;margin:.35rem 0">${a.summary||''}</p>
          ${a.status==='pending'?`<button class="ok" onclick="resolveApproval('${a.id}','approved')">Approve</button> <button class="danger" onclick="resolveApproval('${a.id}','rejected')">Reject</button>`:''}
        </div>`).join(''):'<p class="stat-sm">No pending approvals</p>';
    }
    function renderResearch(items){
      document.getElementById('research-list').innerHTML=items.length?items.map(p=>`
        <div style="border:1px solid var(--border);border-radius:8px;padding:.75rem;margin-bottom:.5rem">
          <strong>${p.title}</strong> · ${p.technique||''} · score ${p.backtest_score??'—'}
          <p style="font-size:.85rem;margin:.35rem 0">${(p.abstract||'').slice(0,160)}</p>
          ${p.source_url?`<a href="${p.source_url}" target="_blank" style="color:var(--accent);font-size:.8rem">Paper</a> `:''}
          ${p.status==='pending'?`<button class="ok" onclick="resolveResearch('${p.id}','approved')">Approve</button> <button class="danger" onclick="resolveResearch('${p.id}','rejected')">Reject</button>`:''}
        </div>`).join(''):'<p class="stat-sm">Run Scholar scan to discover algorithm edges</p>';
    }
    function renderPromotions(items){
      document.getElementById('promotions-list').innerHTML=items.length?items.map(p=>{
        const payload=p.payload||{};
        const members=(payload.members||[]).map(m=>
          `<li><strong>${m.name}</strong> — ${m.role}<br><span style="color:var(--muted);font-size:.8rem">${(m.responsibilities||[]).join(' · ')}</span></li>`
        ).join('');
        const goals=(payload.first_quarter_goals||[]).map(g=>`<li>${g}</li>`).join('');
        const edit=p.status==='pending'?`
          <details style="margin-top:.5rem"><summary style="cursor:pointer;font-size:.85rem">Edit proposal</summary>
            <label style="display:block;margin-top:.5rem;font-size:.75rem;color:var(--muted)">Promotion title</label>
            <input id="promo-title-${p.id}" value="${(p.promotion_title||'').replace(/"/g,'&quot;')}" style="width:100%;padding:.35rem;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px"/>
            <label style="display:block;margin-top:.5rem;font-size:.75rem;color:var(--muted)">Team name</label>
            <input id="promo-team-${p.id}" value="${(p.team_name||'').replace(/"/g,'&quot;')}" style="width:100%;padding:.35rem;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px"/>
            <label style="display:block;margin-top:.5rem;font-size:.75rem;color:var(--muted)">Mission</label>
            <textarea id="promo-mission-${p.id}" rows="2" style="width:100%;padding:.35rem;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px">${p.mission||''}</textarea>
            <label style="display:block;margin-top:.5rem;font-size:.75rem;color:var(--muted)">Rationale</label>
            <textarea id="promo-rationale-${p.id}" rows="2" style="width:100%;padding:.35rem;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px">${payload.expansion_rationale||''}</textarea>
            <button class="secondary" style="margin-top:.5rem" onclick="savePromotion('${p.id}')">Save edits</button>
          </details>
          <div style="margin-top:.5rem">
            <button class="ok" onclick="resolvePromotion('${p.id}','approved')">Approve team</button>
            <button class="danger" onclick="resolvePromotion('${p.id}','rejected')">Reject</button>
          </div>`:'';
        return `<div style="border:1px solid var(--border);border-radius:8px;padding:.75rem;margin-bottom:.75rem">
          <strong>${p.lead_name}</strong> → ${p.promotion_title} <span style="color:var(--muted)">(${p.status})</span>
          <p style="font-size:.85rem;margin:.35rem 0"><em>${p.team_name}</em> — ${p.mission||''}</p>
          ${payload.expansion_rationale?`<p style="font-size:.8rem;color:var(--muted)">${payload.expansion_rationale}</p>`:''}
          <ul style="font-size:.85rem;margin:.35rem 0 .35rem 1.1rem">${members}</ul>
          ${goals?`<p style="font-size:.75rem;color:var(--muted);margin-top:.35rem">Q1 goals</p><ul style="font-size:.8rem;margin-left:1.1rem">${goals}</ul>`:''}
          ${edit}
        </div>`;
      }).join(''):'<p class="stat-sm">Click “Build sub-teams” so each lead can propose their team for your approval.</p>';
    }
    function renderCatalysts(items){
      document.getElementById('catalysts-list').innerHTML=items.length?items.map(c=>`
        <div style="border:1px solid var(--border);border-radius:8px;padding:.75rem;margin-bottom:.5rem">
          <strong>${c.symbol}</strong> · event risk <span style="color:${c.event_risk==='high'?'var(--red)':c.event_risk==='medium'?'var(--amber)':'var(--green)'}">${c.event_risk}</span>
          · sentiment ${c.headline_sentiment} · impact ${c.impact_score}
          <p style="font-size:.85rem;margin:.35rem 0">${c.catalyst_summary||''}</p>
          ${(c.key_events||[]).length?`<ul style="font-size:.8rem;margin-left:1.1rem">${c.key_events.map(e=>`<li>${e}</li>`).join('')}</ul>`:''}
          ${c.macro_note?`<p style="font-size:.8rem;color:var(--muted)">${c.macro_note}</p>`:''}
        </div>`).join(''):'<p class="stat-sm">No catalyst reports yet — run a cycle.</p>';
    }
    function levelPct(stats, price){
      if(!stats||!price||!stats.bar_high||stats.bar_high<=stats.bar_low) return 50;
      return ((price-stats.bar_low)/(stats.bar_high-stats.bar_low)*100).toFixed(1);
    }
    function renderRiskPlans(items){
      document.getElementById('risk-plans-list').innerHTML=items.length?items.map(r=>{
        const p=r.plan||{}; const s=r.stats||{};
        const ok=r.approved_for_execution;
        return `<div style="border:1px solid var(--border);border-radius:8px;padding:.75rem;margin-bottom:.75rem">
          <strong>${r.symbol}</strong>
          <span style="color:${ok?'var(--green)':'var(--amber)'};margin-left:.5rem">${ok?'Approved':'Review'}</span>
          <p style="font-size:.85rem;margin:.35rem 0">${r.summary||''}</p>
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:.5rem;font-size:.8rem;margin:.5rem 0">
            <div>Qty <strong>${p.quantity??'—'}</strong></div>
            <div>Cost <strong>${fmt(p.est_cost)}</strong></div>
            <div>Max risk <strong>${fmt(p.max_risk_dollars)}</strong></div>
            <div>R:R <strong>${p.reward_risk_ratio??'—'}</strong></div>
            <div>Pos % <strong>${s.position_pct??'—'}%</strong></div>
            <div>Risk % eq <strong>${s.risk_pct_equity??'—'}%</strong></div>
          </div>
          <div style="position:relative;height:28px;background:#0f1419;border:1px solid var(--border);border-radius:6px;margin:.5rem 0">
            ${p.stop_loss?`<div title="Stop ${p.stop_loss}" style="position:absolute;left:${levelPct(s,p.stop_loss)}%;top:0;bottom:0;width:3px;background:var(--red)"></div>`:''}
            ${p.entry_price?`<div title="Entry ${p.entry_price}" style="position:absolute;left:${levelPct(s,p.entry_price)}%;top:0;bottom:0;width:3px;background:var(--accent)"></div>`:''}
            ${p.take_profit?`<div title="Target ${p.take_profit}" style="position:absolute;left:${levelPct(s,p.take_profit)}%;top:0;bottom:0;width:3px;background:var(--green)"></div>`:''}
          </div>
          <div style="font-size:.75rem;color:var(--muted)">Entry ${p.entry_price??'—'} · Stop ${p.stop_loss??'—'} · Target ${p.take_profit??'—'}</div>
          ${r.hedging?`<p style="font-size:.8rem;margin-top:.35rem"><strong>Hedging:</strong> ${r.hedging}</p>`:''}
          ${p.options_analysis?`<p style="font-size:.8rem"><strong>Options:</strong> ${p.options_analysis}</p>`:''}
          ${p.pre_execution_note?`<p style="font-size:.8rem;color:var(--muted)">${p.pre_execution_note}</p>`:''}
        </div>`;
      }).join(''):'<p class="stat-sm">Andrea publishes plans after portfolio proposals, before execution.</p>';
    }
    function renderAssistantFrom(a){
      if(!a){ document.getElementById('assistant-focus').textContent='Focus: —'; return; }
      document.getElementById('assistant-focus').textContent='Focus: '+(a.focus||'—');
      document.getElementById('assistant-summary').textContent=a.summary||'';
      const block=(id,title,items)=>{ document.getElementById(id).innerHTML=items?.length
        ? `<h3 style="font-size:.8rem;color:var(--muted);margin:.75rem 0 .35rem">${title}</h3>`+
          items.map(i=>`<div style="border-left:3px solid var(--border);padding:.35rem .65rem;margin-bottom:.35rem"><strong>${i.title}</strong><br><span style="font-size:.85rem;color:var(--muted)">${i.detail||''}</span></div>`).join('')
        : ''; };
      block('assistant-must','Must do',a.must_do);
      block('assistant-should','Should do',a.should_do);
      block('assistant-later','Can wait',a.can_wait);
    }
    async function loadAssistant(){
      const d=await fetch('/api/assistant/brief').then(r=>r.json());
      renderAssistantFrom(d.brief);
    }
    async function runCycle(){ toast('Running…'); const r=await fetch('/api/run',{method:'POST'}); if(!r.ok){toast('Failed');return;} toast('Done'); refresh(); }
    async function startLoop(){ await fetch('/api/loop/start',{method:'POST'}); toast('Loop started'); refresh(); }
    async function stopLoop(){ await fetch('/api/loop/stop',{method:'POST'}); toast('Loop stopped'); refresh(); }
    async function discoverResearch(){ toast('Searching literature…'); const r=await fetch('/api/research/discover',{method:'POST'}); const d=await r.json(); toast(`Found ${(d.created||[]).length} proposals`); refresh(); }
    async function proposePromotions(){ toast('Leads are building their teams…'); const r=await fetch('/api/team/expansions/propose',{method:'POST'}); if(!r.ok){toast('Failed — enable analytics');return;} const d=await r.json(); toast(`${(d.proposals||[]).length} proposals ready for review`); refresh(); }
    async function savePromotion(id){
      const body={
        promotion_title: document.getElementById('promo-title-'+id)?.value,
        team_name: document.getElementById('promo-team-'+id)?.value,
        mission: document.getElementById('promo-mission-'+id)?.value,
        expansion_rationale: document.getElementById('promo-rationale-'+id)?.value,
      };
      await fetch(`/api/team/expansions/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      toast('Saved'); refresh();
    }
    async function resolveApproval(id,status){ await fetch(`/api/approvals/${id}/resolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})}); refresh(); }
    async function resolveResearch(id,status){ await fetch(`/api/research/${id}/resolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})}); refresh(); }
    async function resolvePromotion(id,status){ await fetch(`/api/team/expansions/${id}/resolve`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})}); toast(status==='approved'?'Team approved':'Proposal rejected'); refresh(); }
    refresh(); setInterval(refresh,15000);
  </script>
</body>
</html>"""
