/* Gráficas del visor; representan únicamente datos exportados del experimento. */
window.DemoCharts = (() => {
  const colors = {ink:'#17364b',teal:'#076b68',orange:'#ba570b',line:'#cfdbdf',muted:'#526878'};
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text = (x,y,label,extra='') => `<text x="${x}" y="${y}" font-size="12" ${extra}>${escape(label)}</text>`;
  const line = (x1,y1,x2,y2,extra='') => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" ${extra}/>`;
  function scene(svg, scenario, sample, prediction, showTruth, showLinks, showField=false, fieldNode=0) {
    const size=520,left=72,top=42,room=scenario.config.room_m;
    const xy=point=>[left+point[0]/room*size,top+size-point[1]/room*size];
    let parts=[`<rect x="${left}" y="${top}" width="${size}" height="${size}" fill="#fbfdfc" stroke="${colors.ink}" stroke-width="2"/>`];
    if(showField) {
      const c=scenario.config,origin=scenario.nodes[fieldNode],cells=32,step=room/cells;
      const threshold=Math.max(c.receiver_sensitivity_dbm,-174+10*Math.log10(c.bandwidth_mhz*1e6)+c.noise_figure_db+c.required_snr_db);
      for(let i=0;i<cells;i++)for(let j=0;j<cells;j++){
        const point=[(i+.5)*step,(j+.5)*step],d=Math.max(.1,Math.hypot(point[0]-origin[0],point[1]-origin[1]));
        const fspl=20*Math.log10(4*Math.PI*d*c.carrier_mhz*1e6/299792458);
        const power=c.tx_power_dbm+c.tx_gain_dbi+c.rx_gain_dbi-fspl-c.extra_loss_db;
        const t=Math.max(0,Math.min(1,(power+100)/70));
        const rgb=[238,243,241].map((v,k)=>Math.round(v+([116,188,167][k]-v)*t));
        const [x,y]=xy([(i)*step,(j+1)*step]);
        parts.push(`<rect class="signal-cell" x="${x}" y="${y}" width="${size/cells+.2}" height="${size/cells+.2}" fill="${power<threshold?'#e4e8eb':`rgb(${rgb.join(',')})`}"><title>FSPL desde N${fieldNode}: ${power.toFixed(1)} dBm</title></rect>`);
      }
      parts.push(`<rect x="${left}" y="${top}" width="${size}" height="${size}" fill="none" stroke="${colors.ink}" stroke-width="2"/>`);
    }
    for(let i=0;i<=scenario.gridSize;i++) {
      const d=i*size/scenario.gridSize;
      if(i>0&&i<scenario.gridSize) parts.push(line(left+d,top,left+d,top+size,'stroke="#e2e9e9"'),line(left,top+d,left+size,top+d,'stroke="#e2e9e9"'));
      parts.push(text(left+d,top+size+25,(i*room/scenario.gridSize).toFixed(1),'text-anchor="middle" font-size="10"'));
    }
    parts.push(text(left+size/2,608,'x (m)','text-anchor="middle"'),text(24,top+size/2,'y (m)',`text-anchor="middle" transform="rotate(-90 24 ${top+size/2})"`),text(left-17,top+5,room.toFixed(1),'text-anchor="end"'),text(left-17,top+size+4,'0','text-anchor="end"'));
    if(showLinks) for(const link of sample.links) {
      const a=xy(scenario.nodes[link.tx]),b=xy(scenario.nodes[link.rx]);
      const opacity=link.valid?Math.min(.67,Math.max(.18,(link.rss+110)/90)):.18;
      const title=`N${link.tx} ↔ N${link.rx}: ${link.valid?link.rss.toFixed(2)+' dBm':'sin medición'}`;
      parts.push(`<g><title>${escape(title)}</title>${line(...a,...b,`stroke="${link.valid?'#4f8e91':'#6d7c83'}" stroke-width="${link.valid?2:1}" opacity="${opacity}" ${link.valid?'':'stroke-dasharray="5 5"'}`)}</g>`);
    }
    if(prediction?.position&&showTruth) {
      const a=xy(sample.truth),b=xy(prediction.position);
      parts.push(line(...a,...b,`stroke="${colors.orange}" stroke-width="2" stroke-dasharray="6 5"`));
    }
    scenario.nodes.forEach((point,i)=>{
      const [x,y]=xy(point);
      parts.push(`<g><title>Nodo N${i}: (${point[0].toFixed(2)}, ${point[1].toFixed(2)}) m</title><rect x="${x-11}" y="${y-11}" width="22" height="22" rx="3" fill="${colors.ink}"/>${text(x,y+4,i,'text-anchor="middle" style="fill:white;font-weight:700"')}</g>`);
    });
    if(showTruth) {
      const [x,y]=xy(sample.truth);
      parts.push(`<g><title>Objetivo simulado: (${sample.truth.map(v=>v.toFixed(2)).join(', ')}) m</title><circle cx="${x}" cy="${y}" r="18" fill="#c5e8dc" stroke="${colors.teal}" stroke-width="2"/><circle cx="${x}" cy="${y-5}" r="4" fill="${colors.teal}"/><path d="M${x-6} ${y+7}Q${x} ${y-6} ${x+6} ${y+7}" fill="${colors.teal}"/></g>`);
    }
    if(prediction?.position) {
      const [x,y]=xy(prediction.position);
      parts.push(`<g><title>Posición estimada: (${prediction.position.map(v=>v.toFixed(2)).join(', ')}) m</title><path d="M${x} ${y-10}L${x+10} ${y}L${x} ${y+10}L${x-10} ${y}Z" fill="${colors.orange}" stroke="white" stroke-width="2"/></g>`);
    } else parts.push(`<rect x="${left+14}" y="${top+14}" width="150" height="30" rx="4" fill="#fff1df"/>${text(left+24,top+34,'Sin posición estimada','style="fill:#784115;font-weight:600"')}`);
    svg.innerHTML=parts.join('');
  }
  function noise(svg, scenario) {
    const h=scenario.histogram,em=scenario.em;
    if(!h||!em) {svg.innerHTML=text(360,150,'No hay ajuste EM disponible para este escenario.','text-anchor="middle"');return;}
    const x0=56,y0=27,w=640,hgt=214,min=h.edges[0],max=h.edges.at(-1);
    const normal=(x,s)=>Math.exp(-.5*(x/s)**2)/(Math.max(s,1e-12)*Math.sqrt(2*Math.PI));
    const gmm=x=>em.p*normal(x,em.sigma1_db)+(1-em.p)*normal(x,em.sigma2_db);
    const gauss=x=>normal(x,h.gaussianSigma);
    const ymax=Math.max(...h.density,...Array.from({length:201},(_,i)=>gmm(min+(max-min)*i/200)))*1.12;
    const sx=x=>x0+(x-min)/(max-min)*w,sy=y=>y0+hgt-y/ymax*hgt;
    let parts=[];
    for(let i=0;i<=4;i++) {const v=ymax*i/4;parts.push(line(x0,sy(v),x0+w,sy(v),'stroke="#e2e9e9"'),text(x0-8,sy(v)+4,v.toFixed(2),'text-anchor="end" font-size="10"'));}
    h.density.forEach((v,i)=>parts.push(`<rect x="${sx(h.edges[i])}" y="${sy(v)}" width="${Math.max(.5,sx(h.edges[i+1])-sx(h.edges[i])-1)}" height="${y0+hgt-sy(v)}" fill="#c8dfd6"/>`));
    for(const [fn,color,dash] of [[gmm,colors.teal,''],[gauss,colors.orange,'stroke-dasharray="6 4"']]) {
      const points=Array.from({length:201},(_,i)=>{const x=min+(max-min)*i/200;return `${sx(x)},${sy(fn(x))}`;}).join(' ');
      parts.push(`<polyline points="${points}" fill="none" stroke="${color}" stroke-width="2.5" ${dash}/>`);
    }
    for(let i=0;i<=6;i++) {const x=min+(max-min)*i/6;parts.push(text(sx(x),y0+hgt+20,x.toFixed(1),'text-anchor="middle" font-size="10"'));}
    parts.push(text(x0,y0-9,'Densidad (1/dB)','font-size="10"'),text(x0+w/2,290,'Residuo RSS (dB)','text-anchor="middle"'),line(440,13,461,13,`stroke="${colors.teal}" stroke-width="3"`),text(467,17,'Mezcla EM','font-size="10"'),line(558,13,579,13,`stroke="${colors.orange}" stroke-width="2" stroke-dasharray="5 3"`),text(585,17,'Gaussiana','font-size="10"'));
    svg.innerHTML=parts.join('');
  }
  function rss(svg, scenario, sample) {
    const values=sample.links.filter(l=>l.valid).map(l=>l.rss);
    const minimum=Math.floor(Math.min(-110,...values.map(v=>v-5))/10)*10;
    const maximum=Math.ceil(Math.max(-20,...values.map(v=>v+5))/10)*10;
    const x0=60,y0=15,w=915,h=205,sy=v=>y0+h-(v-minimum)/(maximum-minimum)*h;
    const step=w/sample.links.length,bw=step*.58;let parts=[];
    for(let i=0;i<=4;i++) {const v=minimum+(maximum-minimum)*i/4;parts.push(line(x0,sy(v),x0+w,sy(v),'stroke="#e2e9e9"'),text(x0-9,sy(v)+4,v.toFixed(0),'text-anchor="end" font-size="10"'));}
    sample.links.forEach((l,i)=>{
      const x=x0+step*(i+.5);
      if(l.valid) parts.push(`<g><title>Enlace N${l.tx} ↔ N${l.rx}: ${l.rss.toFixed(2)} dBm</title><rect x="${x-bw/2}" y="${sy(l.rss)}" width="${bw}" height="${sy(minimum)-sy(l.rss)}" rx="2" fill="${colors.teal}"/>${text(x,sy(l.rss)-6,l.rss.toFixed(1),'text-anchor="middle" font-size="10"')}</g>`);
      else parts.push(text(x,sy(minimum)-12,'—','text-anchor="middle"'));
      parts.push(text(x,y0+h+20,`N${l.tx}–N${l.rx}`,'text-anchor="middle" font-size="10"'));
    });
    const c=scenario.config,threshold=Math.max(c.receiver_sensitivity_dbm,-174+10*Math.log10(c.bandwidth_mhz*1e6)+c.noise_figure_db+c.required_snr_db);
    if(threshold>=minimum&&threshold<=maximum) parts.push(line(x0,sy(threshold),x0+w,sy(threshold),`stroke="${colors.orange}" stroke-width="1.5" stroke-dasharray="5 5"`),`<rect x="${x0+w-240}" y="${sy(threshold)-23}" width="240" height="20" fill="white" opacity=".96"/>`,text(x0+w-4,sy(threshold)-8,`Umbral de recepción ${threshold.toFixed(1)} dBm`,'text-anchor="end" font-size="10" style="fill:#8c460e"'));
    parts.push(text(x0+w/2,273,'Enlaces de la red sintética','text-anchor="middle"'));
    svg.innerHTML=parts.join('');
  }
  return {scene,noise,rss};
})();
