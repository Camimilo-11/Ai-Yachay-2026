/* Visor offline: carga las predicciones guardadas, sin ejecutar otra estimación. */
(() => {
  'use strict';
  let data;
  try {data=JSON.parse(document.getElementById('demo-data').textContent);}
  catch {document.getElementById('status').textContent='Abre demo/index.html. La plantilla se utiliza para regenerar el visor, no para la presentación.';document.getElementById('status').classList.add('error');return;}
  if(!window.DemoCharts||!Array.isArray(data.scenarios)||!data.scenarios.length){document.getElementById('status').textContent='Faltan archivos de la demo. Conserva index.html, app.js, charts.js y styles.css en la misma carpeta.';document.getElementById('status').classList.add('error');return;}
  const $=id=>document.getElementById(id);
  const state={scenario:data.scenarios[0],index:0,method:'RTI_EM_Fisher',timer:null};
  const fmt=(value,digits=3)=>Number.isFinite(value)?value.toFixed(digits):'—';
  const position=value=>value?`(${value.map(v=>fmt(v,2)).join(', ')}) m`:'Sin estimación';
  const method=()=>data.methods.find(m=>m.id===state.method);
  const current=()=>state.scenario.cases[state.index];
  const option=(value,label)=>{const node=document.createElement('option');node.value=value;node.textContent=label;return node;};
  function stop() {if(state.timer!==null)clearInterval(state.timer);state.timer=null;$('play').textContent='Recorrer casos';$('play').setAttribute('aria-pressed','false');}
  function fillScenarios(preferred) {
    const filtered=data.scenarios.filter(s=>$('frequency').value==='all'||s.frequencyMHz===Number($('frequency').value));
    $('scenario').replaceChildren(...filtered.map(s=>option(s.id,s.label)));
    state.scenario=filtered.find(s=>s.id===preferred)||filtered[0];$('scenario').value=state.scenario.id;state.index=0;stop();render();
  }
  function renderStatus() {
    const s=state.scenario,el=$('status');el.className='status';
    if(s.status==='ok') el.textContent=`Ejecución guardada completa · semilla ${s.config.seed} · ${s.cases.length} consultas de prueba · EM convergió.`;
    else if(s.status==='em_not_converged') {el.classList.add('warning');el.textContent=`EM no convergió en ${s.em?.iterations??600} iteraciones. Las predicciones guardadas se muestran para analizar este caso de fallo.`;}
    else {el.classList.add('error');el.textContent=`Calibración insuficiente. ${s.reason||'El escenario no ofrece una estimación válida.'}`;}
  }
  function renderCase() {
    const s=state.scenario,c=current(),p=c.predictions[state.method],m=method();
    $('case').max=s.cases.length-1;$('case').value=state.index;$('case-label').textContent=`${state.index+1} / ${s.cases.length}`;
    $('case-error').textContent=Number.isFinite(p?.error)?`${fmt(p.error,2)} m`:'—';
    $('truth-position').textContent=$('show-truth').checked?position(c.truth):'Oculta en el visor';
    $('estimated-position').textContent=position(p?.position);
    $('available-links').textContent=`${c.links.filter(l=>l.valid).length} / ${c.links.length}`;
    $('frequency-label').textContent=`${s.frequencyMHz/1000} GHz`.replace('.',',');
    $('geometry-label').textContent=`${s.config.room_m} × ${s.config.room_m} m · ${s.gridSize} × ${s.gridSize} celdas`;
    $('method-label').textContent=m.label;$('method-description').textContent=m.description;
    const messages={insufficient_links:'Esta consulta tiene muy pocos enlaces para estimar una posición.',no_fingerprints:'No hay huellas válidas para los enlaces disponibles.',nonfinite_estimate:'El estimador no produjo un resultado finito.'};
    $('case-message').textContent=p?.position?'':messages[p?.status]||s.reason||'No se guardó una predicción para esta consulta.';
    $('field-controls').hidden=!$('show-field').checked;
    DemoCharts.scene($('scene'),s,c,p,$('show-truth').checked,$('show-links').checked,$('show-field').checked,Number($('field-node').value));
    DemoCharts.rss($('rss-chart'),s,c);renderTable();
  }
  function renderTable() {
    const s=state.scenario,c=current(),body=$('results-body');body.replaceChildren();
    data.methods.forEach(m=>{
      const row=document.createElement('tr');if(m.id===state.method)row.classList.add('active');
      const first=document.createElement('td'),button=document.createElement('button');button.type='button';button.className='method-button';button.textContent=m.label;
      button.setAttribute('aria-pressed',String(m.id===state.method));button.addEventListener('click',()=>{stop();state.method=m.id;$('method').value=m.id;renderCase();document.querySelector('.method-button[aria-pressed="true"]').focus({preventScroll:true});});first.append(button);row.append(first);
      const metric=s.metrics[m.id],values=[fmt(metric?.mean_error_m),fmt(metric?.rmse_m),metric?`${metric.valid_cases}/${metric.total_cases}`:'—',fmt(c.predictions[m.id]?.error)];
      values.forEach(value=>{const td=document.createElement('td');td.textContent=value;row.append(td);});body.append(row);
    });
    $('results-note').textContent=!Object.keys(s.metrics).length?'La calibración de este escenario no alcanzó los datos necesarios. Se conserva el fallo y se dejan las métricas sin valor.':s.id==='base'?'En el caso base el control del centro tiene el menor error medio. El piloto demuestra que la cadena se ejecuta; la tabla no prueba superioridad de EM. RTI + EM coincide con su Tikhonov equivalente.':'Cada cifra agrega las consultas de este escenario y una sola semilla. RTI + EM y su control Tikhonov equivalente coinciden; una mejor densidad del ruido no garantiza menor error de posición.';
  }
  function reading(label,value) {const div=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;div.append(dt,dd);return div;}
  function renderNoise() {
    const s=state.scenario,em=s.em,v=s.validation;$('em-parameters').replaceChildren();
    $('em-state').textContent=em?(em.converged?'Ajuste convergente':'Sin convergencia'):'Ajuste no disponible';
    if(em) $('em-parameters').append(reading('Peso p',fmt(em.p)),reading('σ₁',`${fmt(em.sigma1_db)} dB`),reading('σ₂',`${fmt(em.sigma2_db)} dB`),reading('Iteraciones',String(em.iterations)),reading('Residuos de calibración',String(em.n_residuals)),reading('Factor Fisher γ',fmt(em.fisher_gamma)));
    else $('em-parameters').append(reading('Calibración','Insuficiente'));
    DemoCharts.noise($('noise-chart'),s);
    const target=$('validation-results');target.replaceChildren();
    if(Number.isFinite(v.gmm_mean_log_density)&&Number.isFinite(v.gaussian_mean_log_density)) {
      const title=document.createElement('strong');title.textContent=`Validación independiente · ${v.n} residuos`;
      const detail=document.createElement('p');detail.textContent=`Densidad logarítmica media: mezcla EM ${fmt(v.gmm_mean_log_density)}; gaussiana ${fmt(v.gaussian_mean_log_density)}. Un valor mayor indica mejor ajuste predictivo del ruido.`;
      const note=document.createElement('p');note.className='micro';note.textContent='El histograma usa calibración y los valores de esta comparación usan validación. Con RSS cuantizado, la densidad continua se interpreta como una medida exploratoria.';target.append(title,detail,note);
    } else target.textContent='No hay comparación de validación disponible para este escenario.';
  }
  function render() {
    const previousNode=$('field-node').value;$('field-node').replaceChildren(...state.scenario.nodes.map((_,i)=>option(String(i),`Nodo N${i}`)));$('field-node').value=previousNode&&Number(previousNode)<state.scenario.nodes.length?previousNode:'0';
    $('scenario-description').textContent=state.scenario.description;renderStatus();renderCase();renderNoise();
    $('source-label').textContent=`Fuente: ${state.scenario.sourcePath} · SHA-256 del resumen: ${state.scenario.summaryHash.slice(0,12)}…`;
  }
  function setCase(index) {state.index=(index+state.scenario.cases.length)%state.scenario.cases.length;renderCase();}
  function tab(id,focus=false) {
    document.querySelectorAll('[role=tab]').forEach(button=>{const selected=button.id===id;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;$(button.getAttribute('aria-controls')).hidden=!selected;if(selected&&focus)button.focus();});
  }
  data.methods.forEach(m=>$('method').append(option(m.id,m.label)));$('method').value=state.method;
  $('frequency').value='2400';fillScenarios('base');
  $('frequency').addEventListener('change',()=>fillScenarios());
  $('scenario').addEventListener('change',()=>{stop();state.scenario=data.scenarios.find(s=>s.id===$('scenario').value);state.index=0;render();});
  $('method').addEventListener('change',()=>{state.method=$('method').value;renderCase();});
  $('case').addEventListener('input',()=>{stop();setCase(Number($('case').value));});
  $('previous').addEventListener('click',()=>{stop();setCase(state.index-1);});$('next').addEventListener('click',()=>{stop();setCase(state.index+1);});
  $('play').setAttribute('aria-pressed','false');$('play').addEventListener('click',()=>{if(state.timer!==null){stop();return;}$('play').textContent='Pausar';$('play').setAttribute('aria-pressed','true');state.timer=setInterval(()=>setCase(state.index+1),1300);});
  $('show-truth').addEventListener('change',renderCase);$('show-links').addEventListener('change',renderCase);$('show-field').addEventListener('change',renderCase);$('field-node').addEventListener('change',renderCase);
  $('reset').addEventListener('click',()=>{$('frequency').value='2400';state.method='RTI_EM_Fisher';$('method').value=state.method;$('show-truth').checked=true;$('show-links').checked=true;$('show-field').checked=false;fillScenarios('base');});
  const tabs=[...document.querySelectorAll('[role=tab]')];tabs.forEach((button,index)=>{button.addEventListener('click',()=>tab(button.id));button.addEventListener('keydown',event=>{const moves={ArrowRight:(index+1)%tabs.length,ArrowLeft:(index+tabs.length-1)%tabs.length,Home:0,End:tabs.length-1};if(event.key in moves){event.preventDefault();tab(tabs[moves[event.key]].id,true);}});});
  $('fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{$('fullscreen').textContent='Usa F11 en el navegador';}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});window.addEventListener('pagehide',stop);
})();
