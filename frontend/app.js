"use strict";
const $ = (id) => document.getElementById(id);
const quoteFmt = (n, currency) => new Intl.NumberFormat("pt-BR", {style:"currency", currency: currency === "USD" ? "USD" : "BRL", maximumFractionDigits:2}).format(n);
const qtyFmt = (n) => new Intl.NumberFormat("pt-BR", {maximumFractionDigits:8}).format(n);
const stampFmt = (s) => s ? String(s).slice(0,10).split("-").reverse().join("/") : "—";
let selected = null, assets = [];
function notice(text) { $("notice").textContent = text || ""; }
async function api(path, options={}) {
 const response = await fetch(path, {headers:{"Content-Type":"application/json"}, ...options});
 let data;
 try {data=await response.json();}catch {throw new Error("Resposta inválida do servidor");}
 if (!response.ok) {
   const detail=data.detail;
   throw new Error(typeof detail==="string" ? detail : (detail && detail.error) || "Falha na requisição ("+response.status+")");
 }
 return data;
}
function addCell(row, text, className="") {
 const td=document.createElement("td"); td.textContent=String(text); if(className)td.className=className;row.append(td);return td;
}
function addButton(parent, text, action, className="ghost"){
 const button=document.createElement("button");button.type="button";button.textContent=text;button.className=className;button.addEventListener("click",action);parent.append(button);
}
async function loadAssets(){
 const data=await api("/api/assets"); assets=data.items;const tbody=$("asset-rows");tbody.replaceChildren();
 if(!assets.length){const tr=tbody.insertRow();addCell(tr,"Nenhum ativo cadastrado.");return;}
 for(const asset of assets){
  const tr=tbody.insertRow();
  const ticker=addCell(tr,"");addButton(ticker,asset.symbol,()=>selectAsset(asset.symbol),"ticker");
  const q=asset.quote;addCell(tr,q?quoteFmt(q.close,q.currency):"Sem preço");
  addCell(tr,q?stampFmt(q.observed_at):"—","light");
  const actions=addCell(tr,"");
  addButton(actions,"↻",()=>refreshOne(asset.symbol), "ghost");
  addButton(actions,"×",()=>removeAsset(asset.symbol),"ghost");
 }
 if(!selected || !assets.some(x=>x.symbol===selected))selected=assets[0].symbol;
 await selectAsset(selected);
}
function chartDraw(points,currency){
 const svg=$("chart");svg.replaceChildren();
 const vals=points.map(p=>Number(p.close)).filter(Number.isFinite);
 $("chart-empty").hidden=vals.length>0;
 if(!vals.length)return;
 const width=760,height=300,left=72,right=15,top=22,bottom=38;
 const min=Math.min(...vals),max=Math.max(...vals),spread=Math.max(max-min,max*0.01,1);
 const lo=min-spread*0.12,hi=max+spread*0.12;
 const x=i=>left+(width-left-right)*(vals.length===1?0.5:i/(vals.length-1));
 const y=v=>top+(height-top-bottom)*(hi-v)/(hi-lo);
 const ns="http://www.w3.org/2000/svg";
 for(let i=0;i<5;i++){
   const value=lo+(hi-lo)*i/4;
   const line=document.createElementNS(ns,"line");
   line.setAttribute("x1",left);line.setAttribute("x2",width-right);
   line.setAttribute("y1",y(value));line.setAttribute("y2",y(value));line.setAttribute("class","grid-line");svg.append(line);
   const label=document.createElementNS(ns,"text");
   label.setAttribute("x",left-9);label.setAttribute("y",y(value)+4);label.setAttribute("text-anchor","end");label.setAttribute("class","grid-text");
   label.textContent=new Intl.NumberFormat("pt-BR",{notation:"compact",maximumFractionDigits:1}).format(value);svg.append(label);
 }
 const line=document.createElementNS(ns,"polyline");
 line.setAttribute("points",vals.map((v,i)=>x(i)+","+y(v)).join(" "));
 line.setAttribute("class","line");svg.append(line);
 const title=document.createElementNS(ns,"title");
 title.textContent="De "+quoteFmt(vals[0],currency)+" a "+quoteFmt(vals[vals.length-1],currency);
 line.append(title);
 const first=document.createElementNS(ns,"text");first.setAttribute("x",left);first.setAttribute("y",height-7);first.setAttribute("class","grid-text");first.textContent=stampFmt(points[0].observed_at);svg.append(first);
 const last=document.createElementNS(ns,"text");last.setAttribute("x",width-right);last.setAttribute("y",height-7);last.setAttribute("text-anchor","end");last.setAttribute("class","grid-text");last.textContent=stampFmt(points[points.length-1].observed_at);svg.append(last);
}
async function selectAsset(symbol){
 selected=symbol;$("chart-title").textContent="Histórico • "+symbol;
 try{
  const result=await api("/api/assets/"+encodeURIComponent(symbol)+"/history?period="+encodeURIComponent($("period").value));
  $("chart-subtitle").textContent=result.count+" observações disponíveis";
  chartDraw(result.points,result.points.at(-1)?.currency||"BRL");
 }catch(e){notice(e.message);chartDraw([],"BRL");}
}
async function refreshOne(symbol){
 notice("Consultando "+symbol+"...");
 try{await api("/api/assets/"+encodeURIComponent(symbol)+"/refresh?force=true",{method:"POST"});notice("Cotações de "+symbol+" atualizadas.");}
 catch(e){notice("Não foi possível atualizar "+symbol+": "+e.message);}
 await Promise.all([loadAssets(),loadPortfolio()]);
}
async function removeAsset(symbol){
 if(!confirm("Retirar "+symbol+" da lista de acompanhamento? O histórico e a posição serão mantidos."))return;
 try{await api("/api/assets/"+encodeURIComponent(symbol),{method:"DELETE"});if(selected===symbol)selected=null;await loadAssets();await loadModels();}
 catch(e){notice(e.message);}
}
async function loadPortfolio(){
 const data=await api("/api/portfolio");const overview=$("overview");overview.replaceChildren();
 const summaries=[["Ativos acompanhados",String(assets.length),"Tickers na lista"]];
 for(const group of data.by_currency){
  summaries.push(["Custo • "+group.currency,quoteFmt(group.invested,group.currency),group.positions+" posição(ões)"]);
  summaries.push(["Resultado • "+group.currency,group.complete?quoteFmt(group.pnl,group.currency):"Incompleto",group.complete?"Estimativa não realizada":"Existem posições sem preço válido"]);
 }
 if(summaries.length===1)summaries.push(["Carteira","Sem posições","Cadastre uma posição abaixo"],["Atualização","Sob demanda","Use o botão superior"]);
 for(const [label,value,subtitle] of summaries){
  const card=document.createElement("article");card.className="metric";
  const small=document.createElement("small");small.textContent=label;
  const strong=document.createElement("strong");strong.textContent=value;
  const em=document.createElement("em");em.textContent=subtitle;
  card.append(small,strong,em);overview.append(card);
 }
 const tbody=$("position-rows");tbody.replaceChildren();
 if(!data.positions.length){const row=tbody.insertRow();addCell(row,"Nenhuma posição cadastrada.");return;}
 for(const p of data.positions){
  const tr=tbody.insertRow();
  addCell(tr,p.symbol);addCell(tr,qtyFmt(p.quantity));
  addCell(tr,quoteFmt(p.avg_cost,p.currency));
  addCell(tr,p.last_price==null?"—":quoteFmt(p.last_price,p.currency));
  addCell(tr,p.market_value==null?"—":quoteFmt(p.market_value,p.currency));
  addCell(tr,p.pnl==null?"—":quoteFmt(p.pnl,p.currency)+" ("+p.pnl_pct+"%)",p.pnl>=0?"positive":"negative");
  const actions=addCell(tr,"");
  addButton(actions,"Editar",()=>{$("pos-symbol").value=p.symbol;$("pos-quantity").value=p.quantity;$("pos-cost").value=p.avg_cost;$("pos-currency").value=p.currency;$("pos-quantity").focus();});
  addButton(actions,"×",async()=>{if(!confirm("Excluir a posição de "+p.symbol+"?"))return;try{await api("/api/portfolio/positions/"+encodeURIComponent(p.symbol),{method:"DELETE"});await loadPortfolio();}catch(e){notice(e.message);}});
 }
}
async function loadModels(){
 try{
  const data=await api("/api/models");
  const tbody=$("model-rows");tbody.replaceChildren();
  if(!data.assets.length){const row=tbody.insertRow();addCell(row,"Nenhum ativo acompanhado.");return;}
  for(const item of data.assets){
    const tr=tbody.insertRow();
    addCell(tr,item.symbol);
    addCell(tr,item.status==="selected"?"Validado":item.status==="candidate"?"Candidato — ainda não supera referência":"Aguardando treinamento",item.status==="selected"?"positive":"light");
    const best=item.selected;
    addCell(tr,best?best.family.toUpperCase():"—");
    addCell(tr,best?best.metrics.test.rmse_pct.toFixed(3)+"%":"—");
    const cell=addCell(tr,"");
    if(best){addButton(cell,"Prever D+1",()=>showForecast(item.symbol),"ghost");}
  }
 }catch(e){$("model-output").textContent="Modelos indisponíveis: "+e.message;}
}
async function showForecast(symbol){
 $("model-output").textContent="Consultando previsão validada de "+symbol+"...";
 try{
  const result=await api("/api/models/"+encodeURIComponent(symbol)+"/forecast");
  const stale=result.stale_model?" • modelo com treino antigo":"";
  $("model-output").textContent="Previsão experimental "+symbol+" ("+result.family.toUpperCase()+") para "+stampFmt(result.forecast_for)+": "+quoteFmt(result.predicted_next_close,result.currency)+" • fechamento conhecido "+stampFmt(result.latest_price_date)+" • não é recomendação de investimento"+stale;
 }catch(e){$("model-output").textContent="Previsão de "+symbol+" indisponível: "+e.message;}
}

let activeResearch = null;
const researchRiskRank = {critico:0,atencao:1,monitoramento:2,sem_avaliacao:3};
const researchRiskNames = {critico:"Crítico",atencao:"Atenção",monitoramento:"Monitorar",sem_avaliacao:"Não avaliado"};
function element(tag, text, cls){
 const node=document.createElement(tag);
 if(text!==undefined&&text!==null)node.textContent=String(text);
 if(cls)node.className=cls;
 return node;
}
function contentBlock(parent,label,value){
 const div=element("article",undefined,"metric");
 div.append(element("small",label),element("strong",value));
 parent.append(div);
}
function safeSourceLink(doc){
 const a=element("a",doc.title||doc.id,"source-link");
 const url=new URL(doc.url);
 if(url.protocol==="https:"&&["fnet.bmfbovespa.com.br","www.xpasset.com.br","xpasset.com.br","api.mziq.com"].includes(url.hostname)){
  a.href=url.href;a.target="_blank";a.rel="noopener noreferrer";
 }
 return a;
}
function renderResearch(){
 const data=activeResearch;
 const tbody=$("research-rows");tbody.replaceChildren();
 if(!data||data.status==="sem_documentos"){
  $("research-meta").textContent="Nenhum relatório oficial revisado para esse ativo. Ausência de dados não significa carteira saudável.";
  $("research-metrics").replaceChildren();$("research-alerts").replaceChildren();
  $("research-calendar").replaceChildren();$("research-sources").replaceChildren();
  $("research-detail").replaceChildren();
  const tr=tbody.insertRow();addCell(tr,"Sem inventário documental disponível.");
  return;
 }
 const dateText=stampFmt(data.reference_date);
 $("research-meta").textContent="Referência: "+dateText+" • Cobertura "+(data.coverage==="parcial"?"PARCIAL":"completa")+" • "+
   (data.outdated?"Dados antigos — revisar novos documentos":"Conferir novos comunicados para mudanças")+
   " • "+data.summary.disclosed_holdings+" posições catalogadas";
 const metrics=$("research-metrics");metrics.replaceChildren();
 const alloc=data.overview.allocation_pct||{};
 contentBlock(metrics,"Exposição em CRIs",(alloc.CRI??"—")+"%");
 contentBlock(metrics,"FIIs investidos",(alloc.FII??"—")+"%");
 contentBlock(metrics,"Permutas",(alloc.PERMUTA??"—")+"%");
 const ratio=data.overview.cash_distribution_coverage_ratio;
 contentBlock(metrics,"Cobertura de distribuição",ratio==null?"Não informada":qtyFmt(ratio*100)+"%");
 const alerts=$("research-alerts");alerts.replaceChildren();
 if(!data.findings.length)alerts.append(element("p","Nenhum alerta estruturado. Isso não comprova ausência de riscos.","muted"));
 for(const f of data.findings.slice().sort((a,b)=>(researchRiskRank[a.risk]??3)-(researchRiskRank[b.risk]??3)).slice(0,16)){
  const card=element("article",undefined,"research-alert");
  card.append(element("strong",f.name+" • "+researchRiskNames[f.risk],f.risk==="critico"?"negative":f.risk==="atencao"?"research-warn":"light"));
  for(const flag of f.flags)card.append(element("p",flag.reason+(flag.basis==="regra_de_triagem"?" (alerta por regra)":" (relatado em documento)")));
  alerts.append(card);
 }
 const category=$("research-category").value, risk=$("research-risk").value;
 const positions=data.exposures.filter(h=>(!category||h.category===category)&&(!risk||h.risk===risk))
     .sort((a,b)=>(researchRiskRank[a.risk]??3)-(researchRiskRank[b.risk]??3));
 if(!positions.length){
  const tr=tbody.insertRow();addCell(tr,"Nenhuma posição nesse filtro.");
 }
 for(const h of positions){
  const tr=tbody.insertRow();
  addCell(tr,h.category);
  const identity=addCell(tr,"");
  addButton(identity,h.name,()=>showResearchDetail(h),"ticker");
  identity.append(element("span",h.id,"sub"));
  addCell(tr,h.nav_pct!=null?qtyFmt(h.nav_pct)+"% do PL":h.volume_brl_million!=null?"R$ "+qtyFmt(h.volume_brl_million)+" mi":"—");
  let reference="A confirmar";
  if(h.category==="PERMUTA"){
   reference="Entrega "+(h.delivery_month||"não divulgada")+" • obras "+(h.construction_pct??"n/d")+"% • vendas "+(h.sales_pct??"n/d")+"%";
  }else if(h.category==="CRI"||h.category==="CRA"){
   reference="Vence "+(h.maturity_month||"não informado")+" • "+h.periodicity+
    (h.exact_payment_day?" (dia "+h.exact_payment_day+")":" (dia não informado)");
  }else if(h.category==="IMOVEL"||h.category==="FII"){
   reference=h.vacancy_pct!=null?"Vacância reportada: "+qtyFmt(h.vacancy_pct)+"%":"Vacância não apurada";
  }
  addCell(tr,reference,"light");
  addCell(tr,researchRiskNames[h.risk]||h.risk,h.risk==="critico"?"negative":h.risk==="atencao"?"research-warn":"light");
 }
 const sources=$("research-sources");sources.replaceChildren();
 const byDoc={};for(const doc of data.source_documents)byDoc[doc.id]=doc;
 for(const doc of data.source_documents){
  const div=element("div",undefined,"research-source");
  div.append(safeSourceLink(doc));
  div.append(element("span"," Publicado "+stampFmt(doc.published_at),"light"));
  sources.append(div);
 }
 if(data._calendar){
  const calendar=$("research-calendar");calendar.replaceChildren();
  for(const event of data._calendar.payments){
   const div=element("div",undefined,"research-payment");
   div.append(element("strong",stampFmt(event.payment_date)));
   div.append(element("span",(event.kind==="rendimento_fundo"?"Rendimento do fundo":"Pagamento")+" • "+
       (event.amount_per_unit!=null?quoteFmt(event.amount_per_unit,event.currency||"BRL")+"/cota":"valor não informado")));
   calendar.append(div);
  }
  calendar.append(element("p",data._calendar.uncertain_coupon_dates.length+
    " CRIs/CRAs sem dia exato de cupom no relatório. Não foram inventadas datas.","footnote"));
 }
}
function showResearchDetail(holding){
 const target=$("research-detail");target.replaceChildren();
 target.append(element("strong",holding.name+" • "+holding.category));
 const details=[
  ["Código",holding.id],["Devedor",holding.borrower],["Setor",holding.sector],
  ["Vencimento (mês/ano)",holding.maturity_month],
  ["Frequência do cupom",holding.periodicity],
  ["Dia do cupom",holding.exact_payment_day],
  ["Entrega prevista",holding.delivery_month],
  ["Obras (%)",holding.construction_pct],["Vendas (%)",holding.sales_pct],
  ["Vacância (%), quando divulgada",holding.vacancy_pct],
  ["Garantias / lastro",holding.collateral],
 ];
 const list=element("dl",undefined,"research-definition");
 for(const [label,val] of details){
  if(val==null||val==="nao_informada")continue;
  list.append(element("dt",label),element("dd",val));
 }
 target.append(list);
 for(const flag of holding.flags||[])target.append(element("p",researchRiskNames[flag.severity]+": "+flag.reason,"footnote"));
 target.append(element("p","Dados do relatório na data-base. Documentos adicionais podem alterar a situação.","footnote"));
}
async function loadResearch(symbol){
 const s=(symbol||"").trim().toUpperCase();
 $("research-symbol").value=s;
 $("research-meta").textContent="Consultando inventário documental de "+s+"...";
 try{
  const data=await api("/api/funds/"+encodeURIComponent(s)+"/health");
  if(data.status!=="sem_documentos"){
   const cal=await api("/api/funds/"+encodeURIComponent(s)+"/calendar");
   data._calendar=cal;
  }
  activeResearch=data;renderResearch();
 }catch(err){
  activeResearch=null;renderResearch();
  $("research-meta").textContent="Erro ao carregar documentos: "+err.message;
 }
}
$("research-form").addEventListener("submit",event=>{
 event.preventDefault();loadResearch($("research-symbol").value);
});
$("research-category").addEventListener("change",renderResearch);
$("research-risk").addEventListener("change",renderResearch);
$("asset-form").addEventListener("submit",async event=>{
 event.preventDefault();const symbol=$("symbol").value.trim().toUpperCase();
 try{await api("/api/assets",{method:"POST",body:JSON.stringify({symbol})});$("symbol").value="";await loadAssets();await loadModels();notice("Ativo adicionado. Clique em ↻ para baixar o histórico.");}
 catch(e){notice(e.message);}
});
$("position-form").addEventListener("submit",async event=>{
 event.preventDefault();
 const payload={symbol:$("pos-symbol").value.trim().toUpperCase(),quantity:Number($("pos-quantity").value),avg_cost:Number($("pos-cost").value),currency:$("pos-currency").value};
 try{await api("/api/portfolio/positions",{method:"PUT",body:JSON.stringify(payload)});await Promise.all([loadAssets(),loadPortfolio()]);notice("Posição salva.");}
 catch(e){notice(e.message);}
});
$("period").addEventListener("change",()=>{if(selected)selectAsset(selected);});
$("refresh-all").addEventListener("click",async()=>{
 const button=$("refresh-all");button.disabled=true;const failed=[];
 for(const asset of assets){try{await api("/api/assets/"+encodeURIComponent(asset.symbol)+"/refresh",{method:"POST"});}catch(e){failed.push(asset.symbol);}}
 try{await loadAssets();await loadPortfolio();notice(failed.length?"Falha ao atualizar: "+failed.join(", "):"Consultas concluídas. Consulte a data de cada preço.");}finally{button.disabled=false;}
});
(async()=>{try{await api("/api/health");$("api-status").textContent="● API conectada";await loadAssets();await loadPortfolio();await loadModels();await loadResearch("MXRF11");}catch(e){$("api-status").textContent="● API indisponível";notice(e.message);}})();
