/* Deterministic review is authoritative. Optional AI is a separate, unverified draft. */
const $ = s => document.querySelector(s);
const state = { report: null, selected: null, ai: false, busy: false, pending: null, notes: {}, drafts: {} };
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const amount = v => { if (v == null) return "Not available"; const [n,f=""] = String(v).split("."); return n.replace(/\B(?=(\d{3})+(?!\d))/g,",") + "." + (f.replace(/0+$/,"") || "").padEnd(2,"0"); };
const label = v => ({matched:"Reconciled",mismatch:"Mismatch",insufficient_evidence:"Insufficient evidence",above_budget:"Above budget",below_budget:"Below budget",on_budget:"On budget"}[v] || v.replaceAll("_"," "));
function notice(text, error=false){ $("#notice").textContent=text; $("#notice").className=error?"error":""; }
async function api(url,options){ const response=await fetch(url,options); const body=await response.json(); if(!response.ok) throw new Error(typeof body.detail==="string"?body.detail:body.error || "Request failed. Check your inputs and try again."); return body; }
function lock(busy){ state.busy=busy; ["refresh","sample","export","csv"].forEach(id=>$("#"+id).disabled=busy); $("#upload-form button").disabled=busy; }
async function refresh(){
  if(state.busy) return;
  const threshold=$("#threshold").value;
  if(threshold==="" || !Number.isFinite(Number(threshold)) || Number(threshold)<0){ notice("Enter a nonnegative materiality threshold.",true); return; }
  lock(true); notice("Calculating your reviewâ€¦");
  try {
    const params=new URLSearchParams({min_abs_variance:threshold}); if($("#period").value) params.set("period",$("#period").value);
    const report=await api("/api/review?"+params);
    state.report=report; state.selected=report.findings.some(f=>f.id===state.selected)?state.selected:report.findings[0]?.id;
    $("#period").innerHTML='<option value="">All loaded periods</option>'+report.available_periods.map(p=>'<option value="'+esc(p)+'">'+esc(p)+'</option>').join("");
    if(report.policy.period && !report.available_periods.includes(report.policy.period)){ const option=new Option(report.policy.period,report.policy.period); $("#period").add(option); }
    $("#period").value=report.policy.period || "";
    render(); notice(report.status==="no_data"?"No budget records for this period. Missing data has not been treated as observed zero.":"Review ready. No AI was used.");
  } catch(error){ notice(error.message,true); }
  finally{ lock(false); $("#export").disabled=!state.report; $("#csv").disabled=!state.report; }
}
function render(){
  const r=state.report,t=r.totals;
  $("#metrics").innerHTML=[["Recorded budget",amount(t.budget_exact)],["Recorded actual",amount(t.actual_exact)],["Actual âˆ’ budget",amount(t.variance_exact)],["Material findings",t.material_count+" / "+t.group_count]].map(([name,value])=>'<div class="metric"><span>'+name+'</span><strong>'+(r.status==="no_data"?"Not available":esc(value))+'</strong></div>').join("");
  $("#coverage").textContent=t.matched_count+" reconciled Â· "+t.mismatch_count+" mismatches Â· "+t.insufficient_count+" with insufficient evidence";
  const warnings=[];
  if(r.quality.unmapped_transaction_rows.length) warnings.push(r.quality.unmapped_transaction_rows.length+" transaction rows have no matching budget scope; see source rows in the exported packet.");
  if(r.quality.duplicate_candidate_rows) warnings.push(r.quality.duplicate_candidate_rows+" transaction rows belong to identical-row duplicate candidates. They remain in totals.");
  $("#quality").textContent=warnings.join(" ");
  $("#methods").innerHTML=r.methodology.map(m=>"<li>"+esc(m)+"</li>").join("");
  $("#identity").textContent="Engine "+r.engine_version+" Â· Review "+r.review_id;
  renderQueue(); renderDetail();
}
function renderQueue(){
  if(!state.report) return;
  const search=$("#search").value.toLowerCase();
  const findings=state.report.findings.filter(f=>(!$("#material-only").checked || f.material) && (f.department+" "+f.account+" "+f.period).toLowerCase().includes(search));
  $("#findings").innerHTML=findings.map(f=>'<tr class="'+(f.id===state.selected?"selected":"")+'"><td><button class="row-button" data-finding="'+esc(f.id)+'" aria-pressed="'+(f.id===state.selected)+'">'+esc(f.account)+'</button><small>'+esc(f.department)+" Â· "+esc(f.period)+(f.material?" Â· Material":"")+'</small></td><td class="amount">'+esc(amount(f.variance_exact))+'<small>'+esc(label(f.direction))+'</small></td><td><span class="pill '+f.evidence.reconciliation.status+'">'+label(f.evidence.reconciliation.status)+'</span></td></tr>').join("");
  $("#empty").classList.toggle("hidden",findings.length>0);
  $("#findings").querySelectorAll("[data-finding]").forEach(button=>button.addEventListener("click",()=>{state.selected=button.dataset.finding;renderQueue();renderDetail();}));
}
function noteKey(){return state.report.review_id+":"+state.selected;}
function renderDetail(){
  const f=state.report.findings.find(f=>f.id===state.selected);
  if(!f){ $("#detail").innerHTML='<div class="empty">No finding selected. Choose a period with data.</div>'; return; }
  const e=f.evidence,rec=e.reconciliation,c=f.comparison,key=noteKey(),note=state.notes[key] || {};
  const flags=f.flags.map(flag=>'<div class="flag">'+esc(label(flag))+'</div>').join("");
  $("#detail").innerHTML='<span class="scope">'+esc(f.period)+" / "+esc(f.department)+'</span><h2>'+esc(f.account)+'</h2><span class="pill '+rec.status+'">'+label(rec.status)+'</span><div class="detail-stats">'+[["Budget",f.budget_exact],["Actual",f.actual_exact],["Variance",f.variance_exact]].map(([n,v])=>'<div><small>'+n+'</small><strong>'+esc(amount(v))+'</strong></div>').join("")+'</div><p class="subtle">'+esc(label(f.direction))+" Â· "+(f.variance_percent===null?"Percentage unavailable: zero budget.":esc(Number(f.variance_percent).toFixed(2))+"% of absolute budget.")+'</p>'+flags+
  '<h3>Prior-month comparison</h3><p class="subtle">'+(c.status==="missing"?"No matching "+esc(c.period)+" records. No change is calculated.":esc(c.period)+" actual: "+esc(amount(c.actual_exact))+" Â· Change: "+esc(amount(c.change_exact)))+'</p>'+
  '<h3>Transaction evidence</h3><div class="evidence-summary">Full matching ledger: <strong>'+esc(amount(e.total_amount_exact))+'</strong><br>Ledger minus recorded actual: '+esc(amount(rec.ledger_minus_actual_exact))+'<br>Showing '+e.transaction_count+" of "+e.matching_transaction_count+" transactions Â· Displayed subtotal: "+esc(amount(e.returned_amount_exact))+'</div>'+
  '<details><summary>Inspect transaction rows and source references</summary><div class="table-wrap"><table><thead><tr><th>Source / vendor</th><th>Amount</th><th>Memo</th></tr></thead><tbody>'+e.transactions.map(t=>'<tr><td>Row '+t.source_row+" Â· "+esc(t.vendor)+'<span class="source-id">'+esc(t.source_id)+'</span></td><td class="amount">'+esc(amount(t.amount_exact))+'</td><td>'+esc(t.memo)+'</td></tr>').join("")+'</tbody></table></div>'+(e.transactions.length?"":'<p class="subtle">No matching transaction evidence was supplied.</p>')+'</details>'+
  '<details><summary>Inspect budget source references</summary>'+f.budget_evidence.map(b=>'<p class="subtle">Row '+b.source_row+' · Budget '+esc(amount(b.budget))+' · Actual '+esc(amount(b.actual))+'</p><span class="source-id">'+esc(b.source_id)+'</span>').join("")+'<p class="subtle">One-based loaded budget data rows, excluding the CSV header.</p></details>'+
  '<p class="subtle">'+esc(f.conclusion)+'</p>'+
  '<section class="review-note"><label for="note">Analyst note</label><textarea id="note" placeholder="Record context, missing evidence, or follow-up actions.">'+esc(note.text || "")+'</textarea><label class="check"><input id="reviewed" type="checkbox" '+(note.reviewed?"checked":"")+'>I have reviewed this finding</label><small class="subtle">Personal review marker, not an approval or audit signature. Included in JSON exports.</small></section>'+
  '<section class="ai-box"><h3>Optional AI investigation</h3><p class="subtle">Sends this finding and up to 25 supporting transaction rows to OpenAI. Uses API credits. The result is a draft for your review.</p><button id="investigate" '+(!state.ai || state.pending?"disabled":"")+'>'+(state.pending?"AI investigation runningâ€¦":"Investigate with AI")+'</button><p class="subtle">'+(state.ai?"One bounded request. Your calculated review is unchanged.":"AI is unavailable. Configure a server API key to enable it; all review features work without one.")+'</p><div id="draft"></div></section>';
  $("#note").addEventListener("input",saveNote); $("#reviewed").addEventListener("change",saveNote);
  $("#investigate").addEventListener("click",investigate);
  if(state.drafts[key]) renderDraft(state.drafts[key]);
}
function saveNote(){ state.notes[noteKey()]={text:$("#note").value,reviewed:$("#reviewed").checked}; }
async function investigate(){
  if(!state.ai || state.pending) return;
  const r=state.report,id=state.selected,key=noteKey(); state.pending=key; renderDetail();
  try{
    const result=await api("/api/review/investigate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({review_id:r.review_id,finding_id:id,period:r.policy.period,min_abs_variance:r.policy.min_abs_variance})});
    state.drafts[key]=result.draft;
    notice("AI draft ready. Source-reference existence was checked; claim accuracy still requires review.");
  } catch(error){notice(error.message,true);}
  finally{state.pending=null; if(state.report) renderDetail();}
}
function renderDraft(d){
  $("#draft").innerHTML='<div class="draft"><strong>AI draft Â· Not verified</strong><p>'+esc(d.limitation)+'</p><h4>Suggested observations</h4><ul>'+d.observations.map(o=>'<li>'+esc(o.claim)+o.source_ids.map(s=>'<span class="source-id">'+esc(s)+'</span>').join("")+'</li>').join("")+'</ul><h4>Hypotheses, not established causes</h4><ul>'+d.hypotheses.map(s=>'<li>'+esc(s)+'</li>').join("")+'</ul><h4>Questions to resolve</h4><ul>'+d.questions.map(s=>'<li>'+esc(s)+'</li>').join("")+'</ul></div>';
}
function download(content,type,name){ const url=URL.createObjectURL(new Blob([content],{type})); const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
function exportJSON(){
  const r=state.report;if(!r)return;
  const annotations=r.findings.map(f=>({finding_id:f.id,...(state.notes[r.review_id+":"+f.id]||{}),ai_draft:state.drafts[r.review_id+":"+f.id]||null}));
  download(JSON.stringify({...r,analyst_annotations:annotations},null,2),"application/json","varianceiq-review-"+r.review_id.slice(0,12)+".json");
}
function exportCSV(){
  const cell=(v,text=false)=>{ let s=String(v??"");if(text && /^[\s]*[=+\-@]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'; };
  const cols=["period","department","account","budget_exact","actual_exact","variance_exact","direction","material","reconciliation"];
  const rows=state.report.findings.map(f=>cols.map((c,i)=>cell(c==="reconciliation"?f.evidence.reconciliation.status:f[c],i<3 || i>5)).join(","));
  download(cols.join(",")+"\r\n"+rows.join("\r\n"),"text/csv;charset=utf-8","varianceiq-findings.csv");
}
$("#refresh").addEventListener("click",refresh);
$("#search").addEventListener("input",renderQueue);
$("#material-only").addEventListener("change",renderQueue);
$("#export").addEventListener("click",exportJSON);
$("#csv").addEventListener("click",exportCSV);
$("#sample").addEventListener("click",async()=>{if(state.busy)return;lock(true);try{await api("/api/reset",{method:"POST"});$("#period").value="";}catch(e){notice(e.message,true);return;}finally{lock(false);}await refresh();});
$("#upload-form").addEventListener("submit",async event=>{
  event.preventDefault();if(state.busy)return;const fd=new FormData();const budget=$("#budget-file").files[0],tx=$("#transactions-file").files[0];
  if([budget,tx].filter(Boolean).some(f=>f.size>5*1024*1024)){notice("Each CSV must be 5 MB or smaller.",true);return;}
  fd.append("budget_file",budget);if(tx)fd.append("transactions_file",tx);lock(true);notice("Validating uploaded dataâ€¦");
  try{await api("/api/upload",{method:"POST",body:fd});$("#period").value="";}catch(e){notice(e.message,true);return;}finally{lock(false);}
  await refresh();
});
api("/api/health").then(h=>{state.ai=h.key_configured;$("#ai-state").textContent=state.ai?"AI available on request":"Review ready Â· AI not configured";if(state.report)renderDetail();}).catch(()=>{$("#ai-state").textContent="AI availability unknown";});
refresh();
