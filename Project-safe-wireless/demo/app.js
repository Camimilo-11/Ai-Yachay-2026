/* Visor offline: carga las predicciones guardadas, sin ejecutar otra estimación. */
(() => {
  'use strict';
  let data;
  try {data=JSON.parse(document.getElementById('demo-data').textContent);}
  catch {document.getElementById('status').textContent='Abre demo/index.html. La plantilla se utiliza para regenerar el visor, no para la presentación.';document.getElementById('status').classList.add('error');return;}
  if(!window.DemoCharts||!Array.isArray(data.scenarios)||!data.scenarios.length){document.getElementById('status').textContent='Faltan archivos de la demo. Conserva index.html, app.js, charts.js y styles.css en la misma carpeta.';document.getElementById('status').classList.add('error');return;}
  const $=id=>document.getElementById(id);
  const state={scenario:data.scenarios[0],index:0,method:'RTI_EM_Fisher',timer:null,trackPoints:[],trackIndex:0,trackTimer:null,trackSource:null,floorplan:'',trackMessage:'Carga un CSV de posiciones para empezar. El archivo se procesa localmente en este navegador.',trackError:false};
  const fmt=(value,digits=3)=>Number.isFinite(value)?value.toFixed(digits):'—';
  const position=value=>value?`(${value.map(v=>fmt(v,2)).join(', ')}) m`:'Sin estimación';
  const method=()=>data.methods.find(m=>m.id===state.method);
  const current=()=>state.scenario.cases[state.index];
  const option=(value,label)=>{const node=document.createElement('option');node.value=value;node.textContent=label;return node;};
  function splitCsvLine(line,delimiter) {
    const cells=[];let cell='',quoted=false;
    for(let i=0;i<line.length;i++){
      const char=line[i];
      if(char==='"'&&line[i+1]==='"'&&quoted){cell+='"';i++;}
      else if(char==='"')quoted=!quoted;
      else if(char===delimiter&&!quoted){cells.push(cell.trim());cell='';}
      else cell+=char;
    }
    cells.push(cell.trim());return cells;
  }
  function parseTrackCsv(source,room) {
    const lines=source.replace(/^\uFEFF/,'').split(/\r?\n/).filter(line=>line.trim());
    if(lines.length<3)throw new Error('El CSV debe tener encabezados y al menos dos posiciones.');
    if(lines.length>5001)throw new Error('El archivo supera el límite de 5.000 posiciones.');
    const header=lines[0],delimiter=(header.match(/;/g)||[]).length>(header.match(/,/g)||[]).length?';':(header.includes('\t')?'\t':',');
    const names=splitCsvLine(header,delimiter).map(value=>value.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/\(m\)/g,'_m').replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,''));
    const find=axis=>names.findIndex(name=>[axis,`${axis}_m`,`pos_${axis}`,`position_${axis}`,`coord_${axis}`,`coordenada_${axis}`].includes(name));
    const xIndex=find('x'),yIndex=find('y');
    if(xIndex<0||yIndex<0)throw new Error('No encontré encabezados x,y. Usa, por ejemplo, x_m,y_m.');
    const points=[];let outside=0;
    for(let i=1;i<lines.length;i++){
      const values=splitCsvLine(lines[i],delimiter),decimalComma=delimiter===';';
      const parse=value=>value.trim()===''?NaN:Number(decimalComma?value.replace(',','.'):value);
      const x=parse(values[xIndex]??''),y=parse(values[yIndex]??'');
      if(!Number.isFinite(x)||!Number.isFinite(y))throw new Error(`Coordenada inválida en la fila ${i+1}.`);
      if(x<0||y<0||x>room||y>room){outside++;continue;}
      points.push([x,y]);
    }
    if(points.length<2)throw new Error('Se necesitan al menos dos posiciones dentro de la sala.');
    return {points,outside};
  }
  function trackStatus(message,error=false) {state.trackMessage=message;state.trackError=error;$('track-status').textContent=message;$('track-status').classList.toggle('error',error);}
  function stopTrack() {if(state.trackTimer!==null)clearInterval(state.trackTimer);state.trackTimer=null;$('track-play').textContent='Reproducir recorrido';$('track-play').setAttribute('aria-pressed','false');}
  function examplePoints() {
    const example=window.DemoTrackExample,scale=state.scenario.config.room_m/example.room_m;
    return example.points.map(point=>point.map(value=>value*scale));
  }
  function loadTrackExample() {
    stopTrack();state.trackSource='example';state.trackPoints=examplePoints();state.trackIndex=state.trackPoints.length-1;state.floorplan='';
    $('track-file').value='';$('floorplan-file').value='';
    trackStatus(`Ejemplo sintético · ${state.trackPoints.length} posiciones con paradas. Estos datos ilustran el visor y no proceden de mediciones reales.`);
    renderTrack();
  }
  function renderTrack() {
    const points=state.trackPoints,room=state.scenario.config.room_m,hasTrack=points.length>=2;
    $('track-geometry').textContent=`${room} × ${room} m`;
    const fits=hasTrack&&points.every(([x,y])=>x<=room&&y<=room);
    if(hasTrack&&!fits){$('track-status').textContent='El recorrido excede la sala del escenario seleccionado. Cambia de escenario o carga coordenadas para esta escala.';$('track-status').classList.add('error');}
    else {$('track-status').textContent=state.trackMessage;$('track-status').classList.toggle('error',state.trackError);}
    const usable=hasTrack&&fits;
    $('track-step').disabled=!usable;$('track-play').disabled=!usable;$('track-clear').disabled=!hasTrack;
    $('track-step').max=usable?points.length-1:0;$('track-step').value=usable?state.trackIndex:0;
    if(usable){
      const distance=points.slice(1).reduce((total,point,index)=>total+Math.hypot(point[0]-points[index][0],point[1]-points[index][1]),0);
      const point=points[state.trackIndex];
      $('track-step-label').textContent=`${state.trackIndex+1} / ${points.length}`;$('track-count').textContent=String(points.length);$('track-distance').textContent=`${fmt(distance,2)} m`;$('track-position').textContent=`(${fmt(point[0],2)}, ${fmt(point[1],2)}) m`;
      DemoCharts.tracking($('track-chart'),points,room,state.trackIndex,state.floorplan);
    } else {
      $('track-step-label').textContent='—';$('track-count').textContent='—';$('track-distance').textContent='—';$('track-position').textContent='—';
      DemoCharts.tracking($('track-chart'),[],room,0,'');
    }
  }
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
    if(state.trackSource==='example')state.trackPoints=examplePoints();
    $('scenario-description').textContent=state.scenario.description;renderStatus();renderCase();renderNoise();renderTrack();
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
  $('track-file').addEventListener('change',async event=>{
    const file=event.target.files?.[0];if(!file)return;stopTrack();
    if(file.size>5*1024*1024){trackStatus('El CSV supera el límite de 5 MB.',true);event.target.value='';return;}
    try{
      const parsed=parseTrackCsv(await file.text(),state.scenario.config.room_m);
      state.trackSource='csv';state.trackPoints=parsed.points;state.trackIndex=parsed.points.length-1;
      trackStatus(`${file.name}: ${parsed.points.length} posiciones cargadas.${parsed.outside?` Se omitieron ${parsed.outside} filas fuera de la sala.`:''}`);
      renderTrack();
    }catch(error){trackStatus(error.message||'No se pudo leer el CSV.',true);}
  });
  $('floorplan-file').addEventListener('change',event=>{
    const file=event.target.files?.[0];if(!file)return;
    if(!['image/png','image/jpeg'].includes(file.type)||file.size>8*1024*1024){trackStatus('El plano debe ser PNG o JPG y pesar menos de 8 MB.',true);event.target.value='';return;}
    const reader=new FileReader();reader.onload=()=>{state.floorplan=String(reader.result);trackStatus(`Plano cargado: ${file.name}. Se ajusta a ${state.scenario.config.room_m} × ${state.scenario.config.room_m} m.`);renderTrack();};reader.onerror=()=>trackStatus('No se pudo leer el plano.',true);reader.readAsDataURL(file);
  });
  $('track-step').addEventListener('input',()=>{stopTrack();state.trackIndex=Number($('track-step').value);renderTrack();});
  $('track-play').setAttribute('aria-pressed','false');$('track-play').addEventListener('click',()=>{
    if(state.trackTimer!==null){stopTrack();return;}
    if(state.trackIndex>=state.trackPoints.length-1)state.trackIndex=0;
    $('track-play').textContent='Pausar recorrido';$('track-play').setAttribute('aria-pressed','true');renderTrack();
    state.trackTimer=setInterval(()=>{if(state.trackIndex>=state.trackPoints.length-1){stopTrack();return;}state.trackIndex++;renderTrack();},450);
  });
  $('track-clear').addEventListener('click',()=>{
    stopTrack();state.trackSource=null;state.trackPoints=[];state.trackIndex=0;state.floorplan='';$('track-file').value='';$('floorplan-file').value='';trackStatus('Carga un CSV de posiciones o pulsa Restaurar ejemplo. El archivo se procesa localmente en este navegador.');renderTrack();
  });
  $('track-example').addEventListener('click',loadTrackExample);
  $('reset').addEventListener('click',()=>{$('frequency').value='2400';state.method='RTI_EM_Fisher';$('method').value=state.method;$('show-truth').checked=true;$('show-links').checked=true;$('show-field').checked=false;fillScenarios('base');});
  const tabs=[...document.querySelectorAll('[role=tab]')];tabs.forEach((button,index)=>{button.addEventListener('click',()=>tab(button.id));button.addEventListener('keydown',event=>{const moves={ArrowRight:(index+1)%tabs.length,ArrowLeft:(index+tabs.length-1)%tabs.length,Home:0,End:tabs.length-1};if(event.key in moves){event.preventDefault();tab(tabs[moves[event.key]].id,true);}});});
  $('fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{$('fullscreen').textContent='Usa F11 en el navegador';}});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();stopTrack();}});window.addEventListener('pagehide',()=>{stop();stopTrack();});
  if(window.DemoTrackExample){loadTrackExample();tab('tab-track');}
})();
