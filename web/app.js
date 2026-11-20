const $ = (q, root = document) => root.querySelector(q);
const e = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths = {
  dashboard:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  scan:'M4 4h16M7 10h10M10 16h4M12 16v5', bell:'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  book:'M12 5c-4-3-9-2-9-2v16s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2v16', settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2',
  plus:'M12 5v14M5 12h14', refresh:'M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 13-3l2 2M4 17l2 2a8 8 0 0 0 13-3',
  arrow:'M5 12h14M14 7l5 5-5 5', check:'m5 12 4 4L19 6', close:'M6 6l12 12M18 6 6 18', search:'M16 16l5 5M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14',
  activity:'M2 12h5l3-8 4 16 3-8h5', clock:'M12 7v5l3 2M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20',
  info:'M12 11v6M12 7h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20', chart:'M3 3v18h18M6 15l5-6 4 3 5-7',
  trash:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7', play:'m8 4 12 8-12 8z', edit:'m14 4 6 6M4 20l5-1L21 7l-5-5L4 14z',
  mail:'M3 5h18v14H3zM3 5l9 7 9-7', shield:'m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6zM8 12l3 3 5-6', chevron:'m9 5 7 7-7 7'
};
const icon = (name, cls='') => `<svg class="icon ${cls}" aria-hidden="true" viewBox="0 0 24 24"><path d="${paths[name] || paths.activity}"/></svg>`;
const state = {page:'dashboard',status:{},watch:[],rules:[],catalog:[],alerts:[],symbol:'510300.SH',tf:'1d',indicator:'MACD',chartParams:{},filter:'全部',editing:null,scanned:null,navVersion:0,chartVersion:0,ruleSymbol:'',ruleScreen:null,screenFilter:'matched',screenAuto:true,screenBusy:false};
const labels = {dashboard:'自选监控',scan:'规则工作台',signals:'盘中筛选',alerts:'报警中心',library:'指标库',settings:'数据与设置'};
const tfLabels = {'1m':'1分','3m':'3分','5m':'5分','10m':'10分','15m':'15分','30m':'30分','60m':'60分','120m':'120分','1d':'日线','1w':'周线','1M':'月线'};
const templates = [
  ['趋势跟踪','CLOSE(tf="1d") > MA(20, tf="1d") and RSI(14, tf="1d") > 50'],
  ['超卖观察','RSI(14, tf="15m") < 30'],
  ['布林突破','CROSSUP(CLOSE(tf="30m"), BOLL(20, tf="30m", line="upper"))'],
  ['多周期共振','CROSSUP(MACD(tf="5m", line="dif"), MACD(tf="5m", line="dea")) and CLOSE(tf="1d") > MA(20, tf="1d")'],
  ['持续放量','EVERY(VOLUME(tf="15m") > REF(AVG(VOLUME(tf="15m"), 5), 1) * 1.5, 2)']
];
const onPhone = typeof window.GuanlanNative?.request === 'function';
const nativePending = new Map();
let nativeSequence = 0;
window.guanlanResponse = (id, json) => {
  const pending = nativePending.get(id); if (!pending) return;
  clearTimeout(pending.timer); nativePending.delete(id);
  try { pending.resolve(JSON.parse(json)); } catch { pending.reject(new Error('本地响应格式无效')); }
};
function nativeRequest(path, options) {
  return new Promise((resolve, reject) => {
    const id = String(++nativeSequence);
    const timer = setTimeout(() => {nativePending.delete(id); reject(new Error('本地计算或行情请求超时，请稍后重试'));}, 180000);
    nativePending.set(id, {resolve, reject, timer});
    window.GuanlanNative.request(id, options.method || 'GET', `/api${path}`, options.body || '');
  });
}
async function api(path, options={}) {
  if (onPhone) {
    const response = await nativeRequest(path, options);
    if (response.status < 200 || response.status >= 300) throw new Error(typeof response.body.detail === 'string' ? response.body.detail : response.body.detail?.map(x=>x.msg).join('；') || '请求失败');
    return response.body;
  }
  const response = await fetch(`/api${path}`, {...options,headers:{'Content-Type':'application/json',...options.headers}});
  if(response.status===401){location.replace('/connect');throw new Error('连接已过期，请重新配对');}
  const body = await response.json();
  if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : body.detail?.map(x=>x.msg).join('；') || '请求失败');
  return body;
}
const send = (path, data, method='POST') => api(path,{method,body:data === undefined ? undefined : JSON.stringify(data)});
let toastTimer;
function toast(message, error=false) {
  const node=$('#toast'); node.textContent=message; node.className='show'+(error?' error':'');
  clearTimeout(toastTimer); toastTimer=setTimeout(()=>node.className='',5000);
}
const fmt = (n, digits=2) => n == null ? '—' : Number(n).toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits});
const amount = n => n == null ? '—' : n>=1e8?`${fmt(n/1e8)} 亿`:`${fmt(n/1e4)} 万`;
const change = n => n == null ? '—' : `${n>=0?'+':''}${fmt(n)}%`;
const color = n => n == null ? '' : n>=0 ? 'up':'down';
function empty(title, text, symbol='scan') {return `<div class="empty">${icon(symbol)}<strong>${e(title)}</strong>${e(text)}</div>`;}
const sourceName = source => ({demo:'演示',public:'公开行情 · 自动备用',tushare:'Tushare'}[source]||source);
function sourceBadge(source) {return `<span class="tag ${source==='demo'?'amber':'green'}">${e(sourceName(source))}</span>`;}
function shell() {
  $('#app').innerHTML=`<div class="shell"><aside class="sidebar"><div class="brand"><span class="brand-mark">观</span><div class="brand-text"><div class="brand-name">观澜</div><small>MARKET OBSERVER</small></div></div><div class="nav-label">WORKSPACE</div><nav class="nav" aria-label="主导航">${Object.entries(labels).map(([key,label])=>`<button data-nav="${key}" class="${state.page===key?'active':''}" aria-label="${label}">${icon({dashboard:'dashboard',scan:'scan',signals:'activity',alerts:'bell',library:'book',settings:'settings'}[key])}<span>${label}</span></button>`).join('')}</nav><div class="sidebar-bottom"><div class="engine-card"><strong><i class="dot"></i> 本地监控引擎</strong>每 ${state.status.interval||60} 秒计算一次<br>${onPhone?'后台运行请在顶部“运行”开启':'关闭网页后继续运行'}</div><div class="sidebar-foot"><span>个人工作空间</span><span>v0.3.1</span></div></div></aside><div class="workspace"><header class="topbar"><div class="breadcrumb">个人工作空间 ${icon('chevron')} <strong id="crumb">${labels[state.page]}</strong></div><div class="top-actions"><span class="date">${new Date().toLocaleDateString('zh-CN',{year:'numeric',month:'long',day:'numeric',weekday:'short'})}</span><button data-nav="alerts" aria-label="查看报警">${icon('bell')}</button><div class="avatar" title="本地个人模式">V</div></div></header><main id="main" class="main"></main></div></div>`;
}
function header(title,subtitle,actions='') {return `<div class="page-head"><div><h1>${title}</h1><div class="subtitle">${subtitle}</div></div><div class="actions">${actions}</div></div>`;}
function notice() {return state.status.source==='demo'?`<div class="notice">${icon('info')}<span>演示模式 · 所有价格与信号均来自合成数据，仅用于体验功能。</span><button data-nav="settings">配置真实行情 →</button></div>`:`<div class="notice">${icon('info')}<span>${e(sourceName(state.status.source))} · 不复权真实行情，仅已完成 K 线参与计算；行情缺失或延迟时暂停报警。</span></div>`;}
const footer=()=>`<footer class="footer"><span>观澜 · 为每一次判断保留依据</span><span>Asia/Shanghai · ${state.status.source==='demo'?'合成数据 / 工作日日历':e(sourceName(state.status.source))+' / 不复权'} · 本地运行</span></footer>`;
async function loadCore() { [state.status,state.watch,state.rules]=await Promise.all([api('/status'),api('/watchlist'),api('/rules')]); }
async function navigate(page, keep=false) {
  state.page=Object.hasOwn(labels,page)?page:'dashboard';
  location.hash=state.page;
  const version=++state.navVersion;
  document.querySelectorAll('[data-nav]').forEach(n=>n.classList.toggle('active',n.dataset.nav===state.page));
  $('#crumb').textContent=labels[state.page];
  $('#main').innerHTML='<div class="loader"><span class="loading-dot"></span>正在读取工作空间…</div>';
  try {
    await loadCore();
    if(version!==state.navVersion)return;
    if(state.page==='dashboard') renderDashboard();
    if(state.page==='scan') renderScan(keep);
    if(state.page==='signals') {state.ruleScreen=await api('/rule-screen');if(version===state.navVersion)renderRuleScreen();}
    if(state.page==='alerts') {state.alerts=await api('/alerts');if(version===state.navVersion)renderAlerts();}
    if(state.page==='library') {if(!state.catalog.length)state.catalog=await api('/indicators');if(version===state.navVersion)renderLibrary();}
    if(state.page==='settings')renderSettings();
  } catch(error) {$('#main').innerHTML=empty('暂时无法读取数据',error.message,'info');toast(error.message,true);}
}
function sparkline(values, cls) {
  values=values.filter(v=>v!=null&&Number.isFinite(v));
  if(!values.length)return '—';
  const min=Math.min(...values),span=Math.max(...values)-min||1;
  return `<svg class="spark ${cls}" viewBox="0 0 95 26" aria-label="最近28个交易日价格走势"><polyline points="${values.map((v,i)=>`${i/(values.length-1)*95},${23-(v-min)/span*20}`).join(' ')}" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>`;
}
function marketErrors(errors={}) {
  const entries=Object.entries(errors);if(!entries.length)return '';
  const groups=new Map();
  for(const [symbol,message] of entries){if(!groups.has(message))groups.set(message,[]);groups.get(message).push(symbol);}
  return `<details class="inset-error market-errors"><summary>${entries.length} 只标的行情暂不可用，保留缓存并暂停报警 · 查看原因</summary>${[...groups].map(([message,symbols])=>`<p><strong>${e(symbols.join('、'))}</strong><br>${e(message)}</p>`).join('')}</details>`;
}
function monitorShortcut() {
  if(!state.watch.length)return '';
  return `<div class="monitor-shortcut"><label for="monitor-symbol">当前标的</label><select id="monitor-symbol">${state.watch.map(x=>`<option value="${e(x.symbol)}" ${x.symbol===state.symbol?'selected':''}>${e(x.name)} · ${e(x.symbol)}</option>`).join('')}</select><button class="btn small" data-manage-rules="${e(state.symbol)}">${icon('bell')}配置该标的规则</button></div>`;
}
function chartProvider(data) {
  const vendors=[...new Set(Object.values(data.providers||{}))];
  return vendors.length?vendors.map(x=>({sina:'新浪',eastmoney:'东方财富'}[x]||x)).join(' / ')+' · ':'';
}
function renderDashboard() {
  if(!state.watch.find(x=>x.symbol===state.symbol))state.symbol=state.watch[0]?.symbol;
  const s=state.status;
  $('#main').innerHTML=header('自选监控','统一观察股票与 ETF 的价格、指标和条件信号。',`<button class="btn" data-action="refresh">${icon('refresh')}刷新数据</button><button class="btn primary" data-action="add-watch">${icon('plus')}添加自选</button>`)+notice()+
    `<div class="stats">${[
      ['自选标的',s.watch_count,'只','股票与 ETF，同一套监控','chart'],
      ['运行中规则',s.rule_count,'条','满足条件时自动记录信号','activity'],
      ['未读信号',s.unread,'条',s.unread?'前往报警中心查看触发依据':'等待下一个符合条件的信号','bell'],
      ['计算周期',s.interval,'秒',`<strong>${s.indicator_count} 种</strong>可用计算函数`,'clock']
    ].map(([label,n,unit,note,ic])=>`<div class="stat"><div class="stat-top">${label}${icon(ic)}</div><div class="stat-number">${n??'—'}<small>${unit}</small></div><div class="stat-note">${note}</div></div>`).join('')}</div>`+
    marketErrors(s.errors)+monitorShortcut()+
    `<div class="dashboard-grid"><section class="panel" id="chart-panel"><div class="loader">正在准备多周期图表…</div></section><section class="panel"><div class="panel-head"><div><h2>监控规则</h2><div class="subtitle">条件满足，信号自动抵达</div></div><button class="btn ghost small" data-nav="scan" aria-label="管理规则">${icon('arrow')}</button></div><div class="rule-overview">${state.rules.slice(0,3).map(ruleCard).join('')||empty('还没有规则','在筛选工作台创建第一条规则')}</div><div class="rule-panel-foot">${icon('shield')}仅在条件由不满足变为满足时提醒，持续满足不会重复报警。</div></section></div>`+
    `<section class="panel"><div class="table-head"><div class="tabs"><h2>我的自选<span class="badge">${state.watch.length}</span></h2>${['全部','股票','ETF'].map(x=>`<button data-filter="${x}" class="${state.filter===x?'active':''}">${x}</button>`).join('')}</div><span class="subtitle">${state.status.source==='demo'?'演示行情':'分钟行情'}</span></div><div class="table-scroll"><table><thead><tr><th>标的 / 代码</th><th>最新价</th><th>涨跌幅</th><th>日线 RSI · 14</th><th>当日成交额</th><th>近期走势</th><th>报警规则</th><th></th></tr></thead><tbody>${state.watch.filter(x=>state.filter==='全部'||x.kind===state.filter).map(x=>`<tr class="${x.symbol===state.symbol?'selected':''}"><td><button class="stock-name" data-symbol="${e(x.symbol)}">${e(x.name)} <span class="tag">${e(x.kind)}</span></button><span class="stock-code">${e(x.symbol)}</span>${x.time?`<span class="stock-code" title="行情时间">${e(x.time)}</span>`:''}${x.error?`<div class="down" title="${e(x.error)}">行情不可用</div>`:''}${x.stale?'<span class="tag amber">延迟</span>':''}</td><td class="number">${fmt(x.price,x.kind==='ETF'?3:2)}</td><td class="number ${color(x.change)}">${change(x.change)}</td><td><span class="number">${fmt(x.rsi,1)}</span><div class="progress"><span style="width:${Math.min(100,Math.max(0,x.rsi||0))}%"></span></div></td><td class="number">${amount(x.amount)}</td><td>${sparkline(x.sparkline,color(x.sparkline.at(-1)-x.sparkline[0]))}</td><td><button class="btn small" data-manage-rules="${e(x.symbol)}" aria-label="配置 ${e(x.name)} 的报警规则">${icon('bell')}配置规则</button><div class="subtitle">${state.rules.filter(r=>r.enabled&&(!r.symbols.length||r.symbols.includes(x.symbol))).length} 条启用 · ${state.rules.filter(r=>r.symbols.includes(x.symbol)).length} 条指定</div></td><td><button class="btn ghost small" data-remove-watch="${e(x.symbol)}" aria-label="移除 ${e(x.name)}">${icon('close')}</button></td></tr>`).join('')}</tbody></table>${state.watch.length?'':empty('建立你的观察列表','添加股票或 ETF，开始多周期监控','chart')}</div><div class="table-foot"><span>点击标的切换图表 · 红涨绿跌</span><span>最近计算 ${e(s.last_sync||'尚未计算')}</span></div></section>`+footer();
  loadChart();
}
function ruleCard(rule) {return `<div class="mini-rule"><div class="mini-rule-top"><button data-edit-rule="${rule.id}"><h3>${e(rule.name)}</h3></button><button class="toggle ${rule.enabled?'on':''}" data-toggle-rule="${rule.id}" role="switch" aria-checked="${rule.enabled}" aria-label="${rule.enabled?'暂停':'启用'} ${e(rule.name)}"></button></div><code>${e(rule.expression)}</code><div class="mini-rule-bottom"><i class="dot" style="background:${rule.enabled?'#87aa90':'#cad2d6'}"></i>${rule.enabled?'监控中':'已暂停'}<span>· ${e(ruleScope(rule))} · 收盘确认</span></div></div>`;}
async function loadChart() {
  const target=$('#chart-panel');if(!target)return;
  const version=++state.chartVersion;
  if(!state.symbol){target.innerHTML=empty('图表等待就绪','先添加一个自选标的','chart');return;}
  const stock=state.watch.find(x=>x.symbol===state.symbol)||{symbol:state.symbol,name:state.symbol};
  try {
    const data=await api(`/chart?${new URLSearchParams({symbol:state.symbol,tf:state.tf,indicator:state.indicator,params:JSON.stringify(state.chartParams)})}`);
    if(version!==state.chartVersion||!target.isConnected)return;
    state.chart=data;
    const options=['MACD','RSI','KDJ','CCI','ATR','OBV','DMI','BIAS','BBI','VR','PSY','MFI','SUPERTREND'];
    if(!options.includes(state.indicator))options.push(state.indicator);
    target.innerHTML=`<div class="panel-head"><div class="chart-heading"><span class="security-square">${e(stock.kind==='ETF'?'ETF':'A')}</span><div><div class="chart-title"><h2>${e(stock.name)}</h2><span class="tag">${e(stock.kind||'')}</span></div><div class="subtitle ticker">${e(stock.symbol)} · 已收盘 K 线</div></div></div><div class="chart-price">${fmt(stock.price,stock.kind==='ETF'?3:2)}<small class="${color(stock.change)}">${change(stock.change)}</small></div></div><div class="timebar">${['1m','3m','5m','10m','15m','30m','60m','120m','1d','1w','1M'].map(tf=>`<button data-tf="${tf}" class="${tf===state.tf?'active':''}">${tfLabels[tf]}</button>`).join('')}<select id="chart-indicator" aria-label="副图指标">${options.map(x=>`<option ${x===state.indicator?'selected':''}>${x}</option>`).join('')}</select><button data-action="chart-params" aria-label="修改指标参数">${icon('settings')}</button></div><div class="legend"><span><i style="background:#c6ac6e"></i>BOLL · 20 / 2</span><span><i style="background:#9aabd5"></i>上 / 下轨</span><span>${e(state.indicator)}</span></div><div class="chart-wrap">${drawChart(data)}<div class="chart-tip"></div></div><div class="chart-footer"><span>${e(chartProvider(data))}${data.stale?'行情缺失 / 延迟 · 暂停信号判断':'不复权 · '+data.valid_count+' 根有效历史'}</span><span>${e(data.bars.at(-1)?.time||'历史不足')}</span></div>${data.bars.length&&Object.values(data.bars.at(-1).indicator).every(v=>v==null)?'<div class="chart-data-note">当前指标历史不足或存在行情缺口，暂不可判定；待连续数据足够后恢复。</div>':''}${data.amount_missing?'<div class="chart-data-note">此周期成交额缺失，依赖成交额的指标与规则暂不可判定；价格与成交量指标照常计算。</div>':''}`;
    const svg=$('.chart-svg',target);
    svg?.addEventListener('pointermove',evt=>{
      const box=svg.getBoundingClientRect(); const index=Math.max(0,Math.min(data.bars.length-1,Math.round(((evt.clientX-box.left)/box.width*1000-15)/(910/(data.bars.length||1))-.5)));
      const bar=data.bars[index];if(!bar)return;
      const tip=$('.chart-tip',target);tip.style.display='block';
      tip.innerHTML=`${e(bar.time)}<br>开 ${fmt(bar.open,3)}　高 ${fmt(bar.high,3)}<br>收 ${fmt(bar.close,3)}　低 ${fmt(bar.low,3)}<br>${Object.entries(bar.indicator).map(([k,v])=>`${e(k)} ${fmt(v,3)}`).join('　')}`;
    });
    svg?.addEventListener('pointerleave',()=>$('.chart-tip',target).style.display='none');
  }catch(error){if(version===state.chartVersion)target.innerHTML=empty('图表暂不可用',error.message,'info');}
}
function drawChart(data) {
  const bars=data.bars;if(!bars.length)return empty('历史数据不足','该周期暂时没有已完成的 K 线','chart');
  const W=1000,H=460,left=15,right=925,top=15,bottom=290,iw=(right-left)/bars.length;
  const valid=bars.filter(b=>b.high!=null&&b.low!=null);
  if(!valid.length)return empty('当前区间行情缺失','保留时间轴，等待真实行情恢复','chart');
  const hi=Math.max(...valid.map(b=>Math.max(b.high,b.boll.upperband??b.high))),lo=Math.min(...valid.map(b=>Math.min(b.low,b.boll.lowerband??b.low))),pad=(hi-lo)*.08||1;
  const y=v=>top+(hi+pad-v)/(hi-lo+2*pad)*(bottom-top), x=i=>left+(i+.5)*iw;
  let svg=`<svg class="chart-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(data.symbol)} ${e(tfLabels[data.tf])}蜡烛图和${e(data.indicator)}指标">`;
  for(let i=0;i<5;i++){const yy=top+i*(bottom-top)/4;svg+=`<path d="M${left} ${yy}H${right}" stroke="#edf1f4" stroke-dasharray="3 4"/><text x="945" y="${yy+4}" fill="#9da8b2" font-size="11" font-family="monospace">${fmt(hi+pad-i*(hi-lo+2*pad)/4,2)}</text>`;}
  for(const [key,c] of [['upperband','#aeb8d0'],['middleband','#c5ad72'],['lowerband','#aeb8d0']]){
    const path=bars.map((b,i)=>b.boll[key]==null?'':`${i&&bars[i-1].boll[key]!=null?'L':'M'}${x(i)},${y(b.boll[key])}`).join(' ');
    svg+=`<path d="${path}" fill="none" stroke="${c}" stroke-width="1.2"/>`;
  }
  bars.forEach((b,i)=>{if([b.open,b.high,b.low,b.close].some(v=>v==null))return;const c=b.close>=b.open?'#d76c66':'#3c9b83';svg+=`<path d="M${x(i)} ${y(b.high)}V${y(b.low)}" stroke="${c}" stroke-width="1"/><rect x="${x(i)-Math.max(1,iw*.28)}" y="${Math.min(y(b.open),y(b.close))}" width="${Math.max(2,iw*.56)}" height="${Math.max(1,Math.abs(y(b.close)-y(b.open)))}" fill="${c}"/>`;});
  [0,Math.floor(bars.length/3),Math.floor(bars.length*2/3),bars.length-1].forEach(i=>svg+=`<text x="${Math.min(880,Math.max(15,x(i)-20))}" y="314" fill="#9aa6af" font-size="11">${e(data.tf.endsWith('m')?bars[i].time.slice(5,16):bars[i].time.slice(0,10))}</text>`);
  svg+=`<path d="M15 329H985" stroke="#edf1f4"/><text x="16" y="349" fill="#83929c" font-size="11">${e(data.indicator)}${data.indicator==='MACD'?' · DIF / DEA / HIST':''}</text>`;
  const vals=bars.flatMap(b=>Object.values(b.indicator).filter(v=>v!=null&&Number.isFinite(v)));
  const min=Math.min(0,...vals),max=Math.max(0,...vals),span=max-min||1;
  const yy=v=>363+(max-v)/span*77;
  if(min<0&&max>0)svg+=`<path d="M15 ${yy(0)}H925" stroke="#e8edf0"/>`;
  const colors=['#c6a769','#8da7d2','#7eaf98','#c79091'];
  data.outputs.forEach((key,idx)=>{
    if(key==='macdhist')bars.forEach((b,i)=>{const v=b.indicator[key];if(v!=null)svg+=`<rect x="${x(i)-iw*.23}" y="${Math.min(yy(v),yy(0))}" width="${Math.max(1,iw*.46)}" height="${Math.max(.5,Math.abs(yy(v)-yy(0)))}" fill="${v>=0?'#db8b84':'#83b9a6'}"/>`;});
    else svg+=`<path d="${bars.map((b,i)=>b.indicator[key]==null?'':`${i&&bars[i-1].indicator[key]!=null?'L':'M'}${x(i)},${yy(b.indicator[key])}`).join(' ')}" fill="none" stroke="${colors[idx%4]}" stroke-width="1.6"/>`;
  });
  svg+=`<text x="945" y="371" fill="#a1aab1" font-size="10">${fmt(max,2)}</text><text x="945" y="440" fill="#a1aab1" font-size="10">${fmt(min,2)}</text></svg>`;
  return svg;
}
function builderRow() {return `<div class="builder-row"><select data-builder="indicator" aria-label="条件指标">${['RSI(14)','MA(20)','MACD()','BOLL(20)','KDJ()','CCI(14)','BIAS(6)','CLOSE()','VOLUME()'].map(x=>`<option>${x}</option>`).join('')}</select><select data-builder="tf" aria-label="条件周期">${Object.entries(tfLabels).map(([v,l])=>`<option value="${v}" ${v==='15m'?'selected':''}>${l}</option>`).join('')}</select><select data-builder="op" aria-label="比较运算">${['<','>','<=','>=','==','!='].map(x=>`<option value="${e(x)}">${e(x)}</option>`).join('')}</select><input data-builder="value" type="number" step="any" value="30" aria-label="条件阈值"><button data-action="remove-condition" aria-label="删除条件">${icon('close')}</button></div>`;}
function ruleScope(rule) {
  if(!rule.symbols.length)return '全部自选 · 通用规则';
  if(rule.symbols.length===1)return (state.watch.find(x=>x.symbol===rule.symbols[0])?.name||rule.symbols[0])+' · 专属规则';
  return `${rule.symbols.length} 个指定标的 · 共用规则`;
}
function scopeEditor(rule) {
  const chosen=rule?rule.symbols:state.ruleSymbol?[state.ruleSymbol]:[];
  const options=[...state.watch,...chosen.filter(s=>!state.watch.some(x=>x.symbol===s)).map(symbol=>({symbol,name:'已移出自选'}))];
  return `<div class="field"><label for="rule-scope">适用标的</label><select id="rule-scope"><option value="all" ${!chosen.length?'selected':''}>全部自选 · 通用规则</option><option value="selected" ${chosen.length?'selected':''}>指定标的 · 可为每只标的单独配置</option></select><div id="rule-targets" class="target-list" ${!chosen.length?'hidden':''}>${options.map(x=>`<label class="check-label"><input type="checkbox" data-rule-target value="${e(x.symbol)}" ${chosen.includes(x.symbol)?'checked':''}><span>${e(x.name)}<small>${e(x.symbol)}</small></span></label>`).join('')}</div><small>每只标的可有多条独立规则，参数和阈值分别保存。通用规则也会参与判断；多选标的共用这一条规则。</small></div><div class="field"><label class="check-label"><input id="rule-enabled" type="checkbox" ${rule?.enabled===false?'':'checked'}>启用自动监控和盘中筛选</label></div>`;
}
function selectedRuleSymbols() {
  if($('#rule-scope').value==='all')return [];
  const symbols=[...document.querySelectorAll('[data-rule-target]:checked')].map(x=>x.value);
  if(!symbols.length)throw new Error('请至少选择一个标的，或明确选择全部自选');
  return symbols;
}
function renderScan(keep=false) {
  if(!keep)state.editing=null;
  const rule=state.rules.find(r=>r.id===state.editing);
  const selected=state.watch.find(x=>x.symbol===state.ruleSymbol);
  const visibleRules=state.rules.filter(r=>!state.ruleSymbol||!r.symbols.length||r.symbols.includes(state.ruleSymbol));
  $('#main').innerHTML=header(selected?selected.name+' · 报警规则':'规则工作台','为不同标的设置独立指标、周期和阈值；保存后用于后台报警及盘中筛选。',`<button class="btn" data-nav="signals">${icon('scan')}按报警规则筛选</button>`)+notice()+
    `<div class="editor-grid"><section class="panel"><div class="panel-head"><div><h2>${rule?'编辑监控规则':selected?'新建专属报警':'构建筛选条件'}</h2><div class="subtitle">即刻筛选，或保存为持续运行的监控规则</div></div><button class="btn small" data-action="new-rule">新建规则</button></div><div class="pad"><div class="template-row">${templates.map(([name],i)=>`<button class="chip" data-template="${i}">${name}</button>`).join('')}</div><div class="builder-header"><span>可视化条件</span><select id="builder-join" aria-label="条件组合方式"><option value="and">全部满足 · AND</option><option value="or">任一满足 · OR</option></select></div><div id="builder">${builderRow()}</div><div class="builder-buttons"><button class="btn small" data-action="add-condition">${icon('plus')}增加条件</button><button class="btn small" data-action="build-expression">生成表达式</button></div><div class="field editor-divider"><label for="expression">条件表达式 · 可直接编辑复杂运算</label><textarea id="expression" spellcheck="false">${e(rule?.expression||templates[1][1])}</textarea><small>默认周期为日线；多周期均引用最近已完成的 K 线。支持 + − × ÷、and / or / not、交叉及历史引用。</small></div><div class="field"><label for="rule-name">规则名称</label><input id="rule-name" maxlength="80" placeholder="例如：15分钟超卖观察" value="${e(rule?.name||(selected?selected.name+' · 个性报警':''))}"></div>${scopeEditor(rule)}<div class="actions"><button class="btn primary" data-action="run-scan">${icon('play')}执行筛选</button><button class="btn" data-action="save-rule">${icon('plus')}${rule?'保存修改':'保存为监控规则'}</button></div></div></section><aside class="editor-side"><section class="panel"><div class="panel-head"><h2>适用规则<span class="badge">${visibleRules.length}</span></h2></div><div class="pad rule-filter"><label for="rule-filter">按标的查看规则</label><select id="rule-filter"><option value="">全部规则</option>${state.watch.map(x=>`<option value="${e(x.symbol)}" ${state.ruleSymbol===x.symbol?'selected':''}>${e(x.name)} · ${e(x.symbol)}</option>`).join('')}</select></div><div class="rule-overview" style="display:block">${visibleRules.map(r=>`${ruleCard(r)}<div class="actions" style="padding-bottom:13px"><button class="btn small ghost" data-edit-rule="${r.id}">${icon('edit')}编辑</button><button class="btn small ghost danger" data-delete-rule="${r.id}">${icon('trash')}删除</button></div>`).join('')||empty('还没有规则','保存条件后即可自动监控')}</div></section><section class="panel section-gap"><div class="panel-head"><h2>表达式速查</h2></div><div class="pad"><ul class="help-list"><li><code>RSI(14, tf="15m") &lt; 30</code>15 分钟 RSI 进入超卖区</li><li><code>REF(CLOSE(), 1)</code>上一根日 K 线的收盘价</li><li><code>CROSSUP(MA(5), MA(20))</code>5 日均线上穿 20 日均线</li><li><code>EVERY(RSI(14) &gt; 50, 3)</code>最近 3 根日 K 线连续满足</li><li><code>HHV(HIGH(), 20)</code>最近 20 根 K 线的最高价</li><li><code>BOLL(20, line="lower")</code>访问多输出指标的指定分量</li></ul></div></section></aside></div><section id="scan-results" class="panel section-gap">${empty('准备好后，执行一次筛选','每个结果都会保留具体指标值和对应的 K 线时间。')}</section>`+footer();
}
function expressionFromBuilder() {
  const clauses=[...document.querySelectorAll('.builder-row')].map(row=>{
    const indicator=$('[data-builder="indicator"]',row).value,tf=$('[data-builder="tf"]',row).value,op=$('[data-builder="op"]',row).value,val=$('[data-builder="value"]',row).value;
    if(val===''||!Number.isFinite(Number(val)))throw new Error('请为每条条件填写有效阈值');
    return `${indicator.slice(0,-1)}${indicator.endsWith('()')?'':', '}tf="${tf}") ${op} ${Number(val)}`;
  });
  if(!clauses.length)throw new Error('请先添加一条条件');
  $('#expression').value=clauses.join(`\n${$('#builder-join').value} `);toast('表达式已生成，可继续编辑');
}
function evidence(data) {return `<div class="evidence">${Object.entries(data||{}).map(([key,v])=>`<div><code>${e(key)}</code><span>${fmt(v.value,4)} <small style="color:#a0aab0">${e(v.time||'数据不足')}</small></span></div>`).join('')}</div>`;}
function scanResults(data) {
  $('#scan-results').innerHTML=`<div class="panel-head"><div><h2>筛选结果 <span class="badge">${data.matched} 命中 / ${data.scanned} 个标的</span></h2><div class="subtitle">${e(data.asof)} · 同一条件可保存为后台报警规则</div></div></div>${data.results.length?`<div class="table-scroll"><table><thead><tr><th>标的</th><th>判定</th><th>触发依据</th></tr></thead><tbody>${[...data.results].sort((a,b)=>Number(b.matched)-Number(a.matched)).map(x=>`<tr><td><span class="stock-name">${e(x.name)}</span><span class="stock-code">${e(x.symbol)}</span></td><td><span class="result-status ${x.matched?'yes':'no'}">${icon(x.matched?'check':x.ready?'close':'info')}${x.matched?'符合条件':x.ready?'未满足':'暂不可判定'}</span></td><td>${x.error||x.reason?`<span class="note">${e(x.error||x.reason)}</span>`:`<details ${x.matched?'open':''}><summary class="note">查看 ${Object.keys(x.evidence).length} 项指标值</summary>${evidence(x.evidence)}</details>`}</td></tr>`).join('')}</tbody></table></div>`:empty('自选列表为空','请先在自选监控页添加标的。')}`;
}
async function updateRuleScreen(manual=false) {
  if(state.screenBusy)return;
  state.screenBusy=true;
  const version=state.navVersion;
  try {
    const data=await (manual?send('/rule-screen'):api('/rule-screen'));
    if(state.page!=='signals'||version!==state.navVersion)return;
    state.ruleScreen=data;
    renderRuleScreen();
    if(manual)toast(`${data.reference_only?'休市参考：':''}${data.matched} 个标的满足已启用的报警规则`);
  } catch(error) {
    if(state.page==='signals'){
      const target=$('#screen-error');
      if(target){target.hidden=false;target.textContent='筛选更新失败，以下为上次结果：'+error.message;}
      toast(error.message,true);
    }
  } finally {state.screenBusy=false;}
}
function renderRuleScreen() {
  const data=state.ruleScreen;if(!data)return;
  const session=data.session;
  const rows=data.results.filter(x=>state.screenFilter==='all'||(state.screenFilter==='unknown'?x.rules.some(r=>!r.ready):x.status===state.screenFilter));
  const names={matched:'满足报警条件',unmatched:'暂未满足',unknown:'暂不可判定',no_rules:'未配置启用规则'};
  $('#main').innerHTML=header('盘中筛选','按每只标的已启用的报警规则筛选；任一适用规则满足，即列为命中。',`<button class="btn primary" data-action="screen-refresh">${icon('refresh')}${data.reference_only?'复核最近行情':'立即筛选'}</button><button class="btn" data-nav="scan">${icon('settings')}配置规则</button>`)+notice()+
    `<div class="session-strip"><div><span class="tag ${session.active?'green':'amber'}">${e(session.label)}</span><strong>${data.reference_only?'休市参考结果':data.source==='demo'?'演示规则筛选':'盘中规则筛选'}</strong><p>${data.reference_only?'自动筛选等待开盘。以下按最近已完成 K 线复核，不新增报警。':'只用已完成 K 线；行情延迟、缺失或预热不足时不计入命中。'}${session.next_open?` 下次开盘 ${e(session.next_open)}`:''}</p></div><label class="check-label"><input id="screen-auto" type="checkbox" ${state.screenAuto?'checked':''}>盘中每分钟刷新页面</label></div>
    <div class="stats">${[['符合条件',data.matched,'只','相同标的合并展示全部命中规则'],['参与筛选',data.scanned-data.no_rules,'只',`${data.enabled_rules} 条已启用规则`],['数据待确认',data.unknown,'只','有规则缺少有效数据，不当作未满足'],['尚未配置',data.no_rules,'只','添加并启用该标的的报警规则']].map(([title,n,unit,note])=>`<div class="stat"><div class="stat-top">${title}</div><div class="stat-number">${n}<small>${unit}</small></div><div class="stat-note">${note}</div></div>`).join('')}</div>
    <div id="screen-error" class="inset-error" hidden></div><section class="panel"><div class="panel-head"><div><h2>报警条件命中列表</h2><div class="subtitle">计算时间 ${e(data.asof)} · ${e(sourceName(data.source))} · 当前自选池</div></div><select id="screen-filter" aria-label="筛选结果范围">${[['matched','仅看符合条件'],['all','全部标的与状态'],['unknown','数据待确认'],['no_rules','尚未配置规则']].map(([value,label])=>`<option value="${value}" ${state.screenFilter===value?'selected':''}>${label}</option>`).join('')}</select></div>
    ${rows.length?`<div class="signal-list">${rows.map(x=>`<article class="signal-row"><div class="signal-security"><h3>${e(x.name)} <span class="tag">${e(x.kind)}</span></h3><span class="stock-code">${e(x.symbol)}</span><p class="result-status ${x.matched?'yes':'no'}">${icon(x.matched?'check':'info')}${names[x.status]}</p><span class="subtitle">行情 ${e(x.time||'待加载')}</span><button class="btn small" data-manage-rules="${e(x.symbol)}">${icon('bell')}配置该标的规则</button></div><div class="signal-rules">${x.rules.map(r=>`<details class="signal-rule" ${r.matched?'open':''}><summary><strong>${e(r.name)}</strong><span class="tag ${r.matched?'green':!r.ready?'amber':''}">${r.matched?'命中':r.ready?'未满足':'数据待确认'}</span><span class="subtitle">${e(ruleScope(r))}</span></summary><p class="note">判定 K 线：${e(r.bar_time||'暂无')} · 规则版本 ${r.version}</p><pre class="settings-code">${e(r.expression)}</pre>${r.reason?`<p class="note">${e(r.reason)}</p>`:evidence(r.evidence)}<button class="btn small ghost" data-edit-rule="${r.id}">${icon('edit')}编辑规则</button></details>`).join('')||'<p class="note">该标的尚无已启用的适用规则。</p>'}</div></article>`).join('')}</div>`:empty(state.screenFilter==='matched'?'当前没有标的满足报警条件':'当前范围内没有标的','可切换“全部标的与状态”查看未命中、数据待确认或未配置的原因。')}
    <div class="table-foot"><span>持续满足会一直列在这里；后台提醒仅在首次命中或由不满足变为满足时发送。</span><span>页面刷新${state.screenAuto?'已开启':'已暂停'} · ${onPhone?'后台状态请查看顶部“运行”':'后台监控照常运行'}</span></div></section>`+footer();
}
function renderAlerts() {
  $('#main').innerHTML=header('报警中心','保留每一次触发的条件与数值，随时回看信号依据。',`<button class="btn" data-action="mark-read">${icon('check')}全部标为已读</button>`)+notice()+
    `<div class="notice" style="background:#edf4f0;border-color:#dceadf;color:#6f8a79">${icon('mail')}<span>${state.status.email_configured?'邮件通道已配置；发送状态可在各条信号中查看。':(onPhone?'站内信号已启用。手机后台通知请在顶部“运行”开启。':'站内信号已启用。邮件尚未配置；关闭网页后后台仍记录，系统退出或电脑休眠后停止。')}</span><button data-nav="settings">提醒设置 →</button></div><section class="panel"><div class="panel-head"><h2>信号记录<span class="badge">最近 ${state.alerts.length} 条</span></h2><span class="subtitle">首次满足提醒 · 持续满足去重</span></div>${state.alerts.map(x=>`<article class="alert-card"><span class="alert-symbol">${icon('bell')}</span><div class="alert-content"><div class="alert-top"><h3>${!x.read?'<i class="dot"></i> ':''}${e(x.rule_name)} ${sourceBadge(x.source)}</h3><span class="alert-time">K线 ${e(x.bar_time)}</span></div><div class="alert-meta"><span>${e(x.name)} · ${e(x.symbol)}</span><span>站内已记录</span><span>${!state.status.email_configured?'邮件未配置':x.delivery_status==='disabled'?'触发时未启用邮件':x.delivery_status==='sent'?'邮件服务已接收':x.delivery_status==='failed'?'邮件发送失败':'邮件待发送 / 重试中'}</span></div><details><summary>查看触发条件与指标证据</summary><pre class="settings-code">${e(x.expression)}</pre>${evidence(x.evidence)}</details></div></article>`).join('')||empty('还没有触发的信号','在筛选工作台创建并启用规则。满足条件时，触发依据会保存在这里。','bell')}</section>`+footer();
}
function renderLibrary() {
  $('#main').innerHTML=header('指标库',`${state.status.indicator_count} 种可用计算函数，覆盖趋势、动量、量价、波动与 K 线形态。`)+
    `<div class="notice">${icon('info')}<span>计算口径：TA-Lib 标准公式 + A股常用补充。MACD 柱值为 DIF − DEA；KDJ 以 K=D=50 初始化。各软件默认口径可能不同。</span></div><div class="library-filter"><div class="search-box">${icon('search')}<input id="indicator-search" placeholder="搜索 RSI、BOLL、KDJ 或指标名称" aria-label="搜索指标"></div><select id="indicator-group" aria-label="指标分类"><option value="">全部分类</option>${[...new Set(state.catalog.map(x=>x.group))].map(g=>`<option>${e(g)}</option>`).join('')}</select><span class="subtitle" id="library-count"></span></div><div id="indicator-grid" class="indicator-grid"></div>`+footer();
  filterLibrary();
}
function filterLibrary() {
  const query=$('#indicator-search').value.toLowerCase(),group=$('#indicator-group').value;
  const items=state.catalog.filter(x=>(!group||x.group===group)&&(!query||(`${x.name} ${x.label} ${x.name==='BBANDS'?'BOLL 布林带':''}`).toLowerCase().includes(query)));
  $('#library-count').textContent=`${items.length} 项`;
  $('#indicator-grid').innerHTML=items.map(x=>`<article class="indicator-card"><header><h3>${e(x.name)}</h3><span class="tag">${e(x.group)}</span></header><p>${e(x.label)}</p><code>${Object.entries(x.parameters).map(([k,v])=>`${e(k)}=${e(v)}`).join(' · ')||'无需参数'}</code><footer><span>${x.outputs.length} 个输出 · ${e(x.outputs.join(' / '))}</span>${x.available?`<div class="actions"><button class="btn small ghost" data-chart-indicator="${e(x.name)}">看图</button><button class="btn small ghost" data-use-indicator="${e(x.name)}">用于筛选 ${icon('arrow')}</button></div>`:'<span class="tag amber">需额外输入</span>'}</footer>${x.note?`<p>${e(x.note)}</p>`:''}</article>`).join('')||empty('未找到指标','尝试更换搜索关键词。','book');
}
function renderSettings() {
  if (!onPhone) renderDesktopSettings();
  else {
    const s=state.status;
    $('#main').innerHTML=header('数据与设置','手机独立采集、计算和保存；无需电脑服务。')+
      `<div class="settings-grid"><section class="panel"><div class="panel-head"><h2>行情与计算</h2>${sourceBadge(s.source)}</div><div class="pad"><div class="field"><label for="source">当前数据源</label><select id="source">${[['public','真实行情 · 免 Token / 自动备用'],['demo','演示行情 · 合成数据'],['tushare','Tushare · 需分钟行情权限']].map(([v,t])=>`<option value="${v}" ${s.source===v?'selected':''}>${t}</option>`).join('')}</select><small>真实行情需联网。接口异常、数据延迟或预热不足时保留历史，暂停信号判定。</small></div><div class="field"><label for="interval">计算间隔</label><select id="interval">${[60,120,300,600].map(v=>`<option value="${v}" ${s.interval===v?'selected':''}>${v/60} 分钟</option>`).join('')}</select></div><button class="btn primary" data-action="save-settings">保存设置</button><p class="note">支持 1–120 分钟、日、周、月；仅已完成 K 线参与计算。不复权口径，跨除权日的价格指标可能受跳空影响。</p><p class="note">东方财富公开行情 + 新浪交易日历，无需 Token。1 分钟历史首次通常只有最近一个交易日；手机持续运行后积累更多历史。接口稳定性与延迟由数据源决定。</p><p class="note">Tushare：${s.tushare_configured?'已配置密钥':'未配置密钥'}；邮件：${s.email_configured?'已配置':'未配置'}。可在顶部“运行”中配置，密钥在本机加密保存。</p></div></section><section class="panel"><div class="panel-head"><h2>手机通知与后台运行</h2>${icon('bell')}</div><div class="pad"><p class="note">应用前台自动监控。离开应用前，请在“运行”中开启本次后台监控并允许通知；满足报警条件后发送本地系统通知，同时保存触发依据。</p><p class="note">后台会显示常驻通知，每次最长 5 小时 45 分。到时、手机重启或强制停止后，需重新打开并开启。省电策略可能延迟调度，请允许后台运行。</p><button class="btn primary" data-action="phone-settings">管理运行与通知</button><p class="note">休市时可复核最近行情，不产生新报警。演示信号会明确标记。通知失败不影响站内报警保存。</p></div></section></div>`+footer();
  }
  $('#main .footer').insertAdjacentHTML('beforebegin', `<section class="panel section-gap"><div class="panel-head"><h2>自选与规则迁移</h2>${icon('shield')}</div><div class="pad"><p class="note">独立 App 与电脑分别保存工作空间。导出后将内容传到另一端粘贴导入；合并相同规则，保留已有自选和规则。导出不包含密钥、报警记录或行情缓存。</p><div class="actions"><button class="btn" data-action="workspace-export">导出自选与规则</button><button class="btn" data-action="workspace-import">粘贴并导入</button></div></div></section>`);
}
function renderDesktopSettings() {
  const s=state.status;
  $('#main').innerHTML=header('数据与设置','管理行情接入、计算频率和提醒渠道。')+
    `<div class="settings-grid"><div><section class="panel"><div class="panel-head"><h2>行情数据源</h2>${sourceBadge(s.source)}</div><div class="pad"><div class="field"><label for="source">当前数据源</label><select id="source"><option value="demo" ${s.source==='demo'?'selected':''}>演示行情 · 无需密钥</option><option value="public" ${s.source==='public'?'selected':''}>真实行情 · 免 Token / 自动备用</option><option value="tushare" ${s.source==='tushare'?'selected':''}>Tushare · 需要分钟行情权限</option></select><small>免 Token 源支持沪深股票和场内 ETF，无需注册。首次载入需要获取各周期历史；后续按周期增量更新。单个接口故障时自动切换；均不可用时保留历史并暂停信号判断。</small></div><div class="field"><label for="interval">监控间隔</label><select id="interval">${[60,120,300,600].map(v=>`<option value="${v}" ${v===s.interval?'selected':''}>${v/60} 分钟</option>`).join('')}</select><small>服务在后台调度，网页关闭后继续监控。电脑休眠或服务退出后停止。</small></div><button class="btn primary" data-action="save-settings">保存设置</button><div class="editor-divider section-gap"><h3>免 Token 真实行情</h3><p class="note">行情优先读取东方财富，失败时自动使用新浪，交易日历来自新浪。各周期独立获取历史并本地缓存。新浪日线缺少成交额，相关条件显示未知；1 分钟集合竞价缺口保留为空，不补造数据。接口没有稳定性或延迟保证；缺失、预热不足会显示未知。</p><h3>可选：接入 Tushare</h3><p class="note">将项目的 .env.example 复制为 .env，在本地填写密钥后重启。股票与 ETF 的历史分钟、实时分钟可能需要分别开通权限。</p><pre class="settings-code">TUSHARE_TOKEN=你的密钥</pre><p class="note">密钥状态：${s.tushare_configured?'服务端已配置':'未配置'}。密钥不会返回浏览器。</p><p class="note">当前真实行情按不复权口径计算，跨除权日的价格指标可能受跳空影响。本版本已完成休市时段真实数据联调，盘中延迟仍需继续观察。</p></div></div></section><section class="panel section-gap"><div class="panel-head"><h2>计算与数据说明</h2></div><div class="pad"><div class="settings-status"><span>K线确认</span><strong>只使用已完成周期</strong></div><div class="settings-status"><span>周期</span><span>1–120 分钟 / 日 / 周 / 月</span></div><div class="settings-status"><span>复权口径</span><span>不复权</span></div><div class="settings-status"><span>数据缺失 / 指标预热</span><span>返回未知，不触发信号</span></div><div class="settings-status"><span>信号触发</span><span>首次命中 / 条件由假变真</span></div><div class="settings-status"><span>历史信号</span><span>保存在本地 SQLite</span></div></div></section></div><div><section class="panel"><div class="panel-head"><h2>被动提醒</h2>${icon('bell')}</div><div class="pad"><div class="settings-status"><span>站内信号中心</span><span class="tag green">已启用</span></div><div class="settings-status"><span>邮件通知</span><span class="tag ${s.email_configured?'green':'amber'}">${s.email_configured?'已配置':'未配置'}</span></div><p class="note">需要离开网页后收到提醒，可配置邮件渠道。邮件失败时后台自动重试，并保留发送状态。</p><pre class="settings-code">SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=你的邮箱
SMTP_PASSWORD=邮箱授权码
SMTP_FROM=发件邮箱
ALERT_EMAIL=收件邮箱</pre><button class="btn" data-action="browser-notifications" ${!navigator.userAgent.includes('GuanlanAndroid/') && 'Notification' in window?'':'hidden'}>${icon('bell')}启用网页桌面通知</button><p class="note">桌面通知仅在网页打开时轮询触发；Android 0.3 独立版支持本机通知，可在 App 的“运行”中开启后台监控。系统桌面通知权限由浏览器管理。</p></div></section><section class="panel section-gap"><div class="panel-head"><h2>本地工作空间</h2>${icon('shield')}</div><div class="pad"><p class="note">电脑网页在本地服务运行。Android 0.3 独立版将全部计算与数据存储放在手机，两端分别保存工作空间。</p><p class="note">独立版直接打开使用，无需服务地址或配对码。功能代码共用；网页新增功能后需重新构建、安装新版 APK。自选与规则可在下方导出迁移。</p><a class="btn small" href="/docs" target="_blank" rel="noopener">查看 API 文档 ${icon('arrow')}</a></div></section></div></div>`+footer();
}
function dialog(title,body) {const node=$('#dialog');node.innerHTML=`<div class="panel-head"><h2>${title}</h2><button data-action="close-dialog" aria-label="关闭对话框">${icon('close')}</button></div><div class="dialog-body">${body}</div>`;node.showModal();}
async function searchInstruments(query='') {
  const items=await api(`/instruments?q=${encodeURIComponent(query)}`);
  if(!$('#search-results'))return;
  $('#search-results').innerHTML=items.map(x=>`<button class="search-item" data-add-symbol="${e(x.symbol)}"><span>${e(x.name)} ${x.unverified?'<span class="tag amber">名称未核验</span>':''}<small>${e(x.symbol)} · ${e(x.kind)}</small></span>${state.watch.some(w=>w.symbol===x.symbol)?'<span class="tag">已添加</span>':icon('plus')}</button>`).join('')||'<div class="empty">输入六位代码，或搜索内置标的名称。</div>';
}
let searchTimer;
document.addEventListener('input',event=>{
  if(event.target.id==='instrument-search'){clearTimeout(searchTimer);searchTimer=setTimeout(()=>searchInstruments(event.target.value).catch(err=>toast(err.message,true)),200);}
  if(event.target.id==='indicator-search')filterLibrary();
});
document.addEventListener('change',event=>{
  if(event.target.id==='monitor-symbol'){state.symbol=event.target.value;renderDashboard();}
  if(event.target.id==='chart-indicator'){state.indicator=event.target.value;state.chartParams={};loadChart();}
  if(event.target.id==='indicator-group')filterLibrary();
  if(event.target.id==='rule-scope')$('#rule-targets').hidden=event.target.value==='all';
  if(event.target.id==='rule-filter'){state.ruleSymbol=event.target.value;renderScan();}
  if(event.target.id==='screen-filter'){state.screenFilter=event.target.value;renderRuleScreen();}
  if(event.target.id==='screen-auto'){state.screenAuto=event.target.checked;renderRuleScreen();}
});
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  try {
    if(button.dataset.nav){await navigate(button.dataset.nav);return;}
    if(button.dataset.manageRules){state.ruleSymbol=button.dataset.manageRules;await navigate('scan');return;}
    if(button.dataset.symbol){state.symbol=button.dataset.symbol;await loadChart();document.querySelectorAll('tr.selected').forEach(x=>x.classList.remove('selected'));button.closest('tr')?.classList.add('selected');$('#chart-panel')?.scrollIntoView({behavior:'smooth',block:'nearest'});return;}
    if(button.dataset.tf){state.tf=button.dataset.tf;await loadChart();return;}
    if(button.dataset.filter){state.filter=button.dataset.filter;renderDashboard();return;}
    if(button.dataset.template){$('#expression').value=templates[Number(button.dataset.template)][1];$('#rule-name').value=templates[Number(button.dataset.template)][0];return;}
    if(button.dataset.addSymbol){await send('/watchlist',{symbol:button.dataset.addSymbol});$('#dialog').close();await navigate('dashboard');toast('已加入自选监控');return;}
    if(button.dataset.removeWatch){await send(`/watchlist/${button.dataset.removeWatch}`,undefined,'DELETE');await navigate('dashboard');toast('已移出自选');return;}
    if(button.dataset.toggleRule){await send(`/rules/${button.dataset.toggleRule}/toggle`);await navigate(state.page,true);return;}
    if(button.dataset.editRule){state.editing=Number(button.dataset.editRule);const rule=state.rules.find(r=>r.id===state.editing);state.ruleSymbol=rule?.symbols.length===1?rule.symbols[0]:'';await navigate('scan',true);return;}
    if(button.dataset.deleteRule){dialog('删除监控规则','<p class="note">删除后停止这条规则的监控，已有报警记录保留。</p><button class="btn danger" data-confirm-delete="'+Number(button.dataset.deleteRule)+'">确认删除</button>');return;}
    if(button.dataset.confirmDelete){await send(`/rules/${Number(button.dataset.confirmDelete)}`,undefined,'DELETE');$('#dialog').close();await navigate('scan');toast('规则已删除，历史信号已保留');return;}
    if(button.dataset.chartIndicator){state.indicator=button.dataset.chartIndicator;state.chartParams={};if(state.indicator==='VWAP')state.tf='15m';await navigate('dashboard');return;}
    if(button.dataset.useIndicator){const name=button.dataset.useIndicator;await navigate('scan');$('#expression').value=`${name}(${name==='VWAP'?'tf="15m"':''}) > 0`;$('#rule-name').value=name+' 指标观察';toast('已填入指标，请设置阈值或组合条件');return;}
    const action=button.dataset.action;
    if(!action)return;
    if(action==='close-dialog'){$('#dialog').close();return;}
    if(action==='phone-settings'){window.GuanlanNative.settings();return;}
    if(action==='workspace-export'){
      const data=await api('/workspace/export');
      dialog('导出自选与规则',`<p class="note">复制以下内容保存或传到另一端。请妥善保管，其中包含你的自选和规则。</p><textarea id="workspace-json" rows="12" style="width:100%" readonly aria-label="工作空间导出内容">${e(JSON.stringify(data,null,2))}</textarea><button class="btn primary" data-action="workspace-copy">复制内容</button>`);return;
    }
    if(action==='workspace-copy'){
      const node=$('#workspace-json');
      if(onPhone)window.GuanlanNative.copy(node.value);
      else if(navigator.clipboard)await navigator.clipboard.writeText(node.value);
      else {node.select();if(!document.execCommand('copy'))throw new Error('请长按或全选复制内容');}
      toast('已复制');return;
    }
    if(action==='workspace-import'){
      dialog('合并导入自选与规则','<p class="note">粘贴另一端导出的完整内容。已有数据保留；相同内容不会重复导入。</p><textarea id="workspace-json" rows="12" maxlength="131072" style="width:100%" aria-label="工作空间导入内容"></textarea><button class="btn primary" data-action="workspace-confirm">合并导入</button>');return;
    }
    if(action==='workspace-confirm'){
      let data;try{data=JSON.parse($('#workspace-json').value);}catch{throw new Error('内容不是有效的 JSON，请完整粘贴导出内容');}
      button.disabled=true;const result=await send('/workspace/import',data);$('#dialog').close();await navigate('settings');toast(`新增 ${result.watchlist_added} 只自选、${result.rules_added} 条规则`);return;
    }
    if(action==='add-watch'){dialog('添加股票 / ETF','<div class="search-box" style="max-width:none">'+icon('search')+'<input id="instrument-search" placeholder="搜索名称或输入证券代码" autocomplete="off" autofocus aria-label="搜索股票或ETF"></div><div class="search-results" id="search-results"></div>');await searchInstruments();$('#instrument-search').focus();return;}
    if(action==='add-condition'){$('#builder').insertAdjacentHTML('beforeend',builderRow());return;}
    if(action==='remove-condition'){button.closest('.builder-row').remove();return;}
    if(action==='build-expression'){expressionFromBuilder();return;}
    if(action==='new-rule'){await navigate('scan');return;}
    if(action==='chart-params'){
      if(!state.catalog.length)state.catalog=await api('/indicators');
      const spec=state.catalog.find(x=>x.name===state.indicator);
      dialog(`${e(state.indicator)} 参数`,`${Object.entries(spec?.parameters||{}).map(([key,value])=>`<div class="field"><label for="param-${e(key)}">${e(key)}</label><input id="param-${e(key)}" data-chart-param="${e(key)}" type="number" step="any" value="${state.chartParams[key]??value}"></div>`).join('')||'<p class="note">该指标没有可调整的参数。</p>'}<button class="btn primary" data-action="apply-chart-params">应用到图表</button>`);return;
    }
    if(action==='apply-chart-params'){
      const params={};document.querySelectorAll('[data-chart-param]').forEach(n=>{if(n.value===''||!Number.isFinite(Number(n.value)))throw new Error('参数必须为有效数值');params[n.dataset.chartParam]=Number(n.value);});
      // Validate before closing; an invalid parameter must not trap the chart view.
      await api(`/chart?${new URLSearchParams({symbol:state.symbol,tf:state.tf,indicator:state.indicator,params:JSON.stringify(params)})}`);
      state.chartParams=params;$('#dialog').close();await loadChart();return;
    }
    if(action==='browser-notifications'){
      if(!('Notification' in window))throw new Error('当前浏览器不支持桌面通知，请使用邮件渠道');
      const permission=await Notification.requestPermission();toast(permission==='granted'?'网页桌面通知已启用，请保持页面打开':'未获得通知权限，可在浏览器设置中修改');return;
    }
    button.disabled=true;
    if(action==='screen-refresh'){await updateRuleScreen(true);return;}
    if(action==='refresh'){await send('/refresh');await navigate(state.page);toast('监控周期已执行');}
    if(action==='run-scan'){
      const symbols=selectedRuleSymbols();
      const result=await send('/scan',{expression:$('#expression').value,symbols});
      state.scanned=result;scanResults(result);$('#scan-results').scrollIntoView({behavior:'smooth',block:'start'});toast(`已筛选 ${result.scanned} 个标的，${result.matched} 个符合条件`);
    }
    if(action==='save-rule'){
      const name=$('#rule-name').value.trim();if(!name)throw new Error('请先填写规则名称');
      const symbols=selectedRuleSymbols();
      const rule=state.rules.find(x=>x.id===state.editing);
      const result=await send(state.editing?`/rules/${state.editing}`:'/rules',{name,expression:$('#expression').value,symbols,enabled:$('#rule-enabled').checked},state.editing?'PUT':'POST');
      state.editing=state.editing||result.id;await navigate('scan',true);toast('规则已保存，下一轮监控自动生效');
    }
    if(action==='mark-read'){await send('/alerts/read');await navigate('alerts');toast('已全部标为已读');}
    if(action==='save-settings'){await send('/settings',{source:$('#source').value,interval:Number($('#interval').value)},'PUT');await navigate('settings');toast('配置已保存');}
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
});
$('#dialog').addEventListener('click',event=>{if(event.target===$('#dialog'))$('#dialog').close();});
let lastAlert=0;
let polling=false;
async function poll() {
  if(polling)return;polling=true;
  try {
    const alerts=await api('/alerts');
    if('Notification' in window&&Notification.permission==='granted'){
      for(const alert of alerts.filter(x=>x.id>lastAlert).slice(0,3))new Notification(`${alert.source==='demo'?'[演示] ':''}${alert.rule_name}`,{body:`${alert.name} · ${alert.symbol}\nK线 ${alert.bar_time}`,tag:`alert-${alert.id}`,icon:'/icon.svg'});
    }
    lastAlert=Math.max(lastAlert,...alerts.map(x=>x.id));
    if(state.page==='signals'&&state.screenAuto&&!$('#dialog').open){
      const status=await api('/status');
      if(state.page==='signals'){
        state.status=status;
        if(status.session.active)await updateRuleScreen();
        else if(state.ruleScreen){state.ruleScreen.session=status.session;state.ruleScreen.reference_only=true;renderRuleScreen();}
      }
    }
    if(state.page==='dashboard'&&!$('#dialog').open){await loadCore();if(state.page==='dashboard')renderDashboard();}
  }catch{}finally{polling=false;}
}
async function boot() {
  state.page=Object.hasOwn(labels,location.hash.slice(1))?location.hash.slice(1):'dashboard';
  shell();
  try{const alerts=await api('/alerts');lastAlert=Math.max(0,...alerts.map(x=>x.id));}catch{}
  await navigate(state.page);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  setInterval(poll,60000);
}
window.addEventListener('hashchange',()=>{const page=location.hash.slice(1);if(page!==state.page)navigate(page);});
boot();
