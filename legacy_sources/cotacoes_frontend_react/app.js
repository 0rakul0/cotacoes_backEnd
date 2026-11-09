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
 try{await api("/api/assets/"+encodeURIComponent(symbol),{method:"DELETE"});if(selected===symbol)selected=null;await loadAssets();}
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
$("asset-form").addEventListener("submit",async event=>{
 event.preventDefault();const symbol=$("symbol").value.trim().toUpperCase();
 try{await api("/api/assets",{method:"POST",body:JSON.stringify({symbol})});$("symbol").value="";await loadAssets();notice("Ativo adicionado. Clique em ↻ para baixar o histórico.");}
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
(async()=>{try{await api("/api/health");$("api-status").textContent="● API conectada";await loadAssets();await loadPortfolio();}catch(e){$("api-status").textContent="● API indisponível";notice(e.message);}})();
