// Compares the JavaScript offline engine with the Python rule engine on the same questions.
const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..'); const M=path.join(root,'website/magic');
require(path.join(M,'magic-engine.js'));
const E=globalThis.MagicEngine;
const win={}; new Function('window',fs.readFileSync(path.join(M,'magic-data.js'),'utf8'))(win);
E.init(win.MAGIC_DATA.registry,win.MAGIC_DATA.nlp,win.MAGIC_DATA.strings);
const exp=JSON.parse(fs.readFileSync(process.argv[2]||'/tmp/py_expected.json','utf8'));
let diffs=0;
const near=(a,b,t=0.0025)=>Math.abs(a-b)<=t;
for(const e of exp){
  const j=E.route(e.q); const bad=[];
  if(!near(j.confidence,e.conf,1e-9)) bad.push(`conf js=${j.confidence} py=${e.conf}`);
  const js=j.shortlist.map(x=>x[0]).join(','), py=e.short.map(x=>x[0]).join(',');
  if(js!==py) bad.push(`shortlist js=${js} py=${py}`);
  else j.shortlist.forEach((x,i)=>{ if(!near(x[1],e.short[i][1])) bad.push(`score ${x[0]} js=${x[1]} py=${e.short[i][1]}`); });
  if((j.route===null)!==(e.route===null)) bad.push(`route presence js=${!!j.route} py=${!!e.route}`);
  else if(j.route){
    const r=j.route,p=e.route;
    if(r.tool_id!==p.tool||r.mode!==p.mode) bad.push(`tool/mode js=${r.tool_id}/${r.mode} py=${p.tool}/${p.mode}`);
    const ik=Object.keys(r.inputs).sort().join(), pk=Object.keys(p.inputs).sort().join();
    if(ik!==pk) bad.push(`input keys js=${ik} py=${pk}`);
    else Object.keys(p.inputs).forEach(k=>{ if(typeof p.inputs[k]==='number'?!near(r.inputs[k],p.inputs[k],1e-9*Math.max(1,Math.abs(p.inputs[k]))):r.inputs[k]!==p.inputs[k]) bad.push(`input ${k} js=${r.inputs[k]} py=${p.inputs[k]}`); });
    if(JSON.stringify(r.selects)!==JSON.stringify(p.selects)) bad.push(`selects js=${JSON.stringify(r.selects)} py=${JSON.stringify(p.selects)}`);
    if(r.missing.join()!==p.missing.join()) bad.push(`missing js=${r.missing} py=${p.missing}`);
  }
  const jf=E.findFormulas(e.q,6).map(f=>f.tool_id+'|'+f.formula.slice(0,40));
  if(jf.join('#')!==e.formulas.join('#')) bad.push(`formulas differ js=${jf.slice(0,2)} py=${e.formulas.slice(0,2)}`);
  if(bad.length){ diffs++; console.log('DIFF:',e.q.slice(0,60),'\n   ',bad.join('\n    ')); }
}
console.log(`cross-check: ${exp.length-diffs}/${exp.length} questions identical between Python and JavaScript`);
process.exit(diffs?1:0);
