'use strict';
const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = { token:'', settings:{}, campaigns:[], selected:null, detail:null, leads:[], campaign:null, usage:[], loading:false };
const priorityLabels = {high:'Alta',medium:'Média',low:'Baixa',review:'Em revisão',excluded:'Fora do perfil'};
const stageLabels = {new:'Novo lead',reviewing:'Em análise',contacted:'Contatado',interested:'Interessado',discarded:'Descartado',do_not_contact:'Não contatar'};
const runLabels = {queued:'Na fila',running:'Em andamento',completed:'Concluída',partial:'Parcial',failed:'Falhou',cancelled:'Cancelada',interrupted:'Interrompida',importing:'Importando'};
const instagramLabels = {not_searched:'Não pesquisado',not_found:'Não localizado',candidate:'Candidato · revisar',confirmed:'Confirmado pelo operador',rejected:'Candidato rejeitado',error:'Pesquisa incompleta'};
const formatNumber = value => value == null ? '—' : Number(value).toLocaleString('pt-BR');
const date = value => { try { return new Intl.DateTimeFormat('pt-BR',{dateStyle:'short',timeStyle:'short',timeZone:'America/Sao_Paulo'}).format(new Date(value)); } catch { return 'Data não informada'; } };

function externalURL(value) { try {const u=new URL(value);return ['http:','https:'].includes(u.protocol) ? u.href : null;}catch{return null;} }
function externalLink(url,label,css='') {const safe=externalURL(url);return safe?`<a href="${escapeHTML(safe)}" target="_blank" rel="noopener noreferrer" class="${css}">${escapeHTML(label)}</a>`:escapeHTML(label);}
async function api(path,options={}) {
  const headers = {'Content-Type':'application/json','X-Radar-Token':state.token,...options.headers};
  const response = await fetch(path,{...options,headers});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || 'Não foi possível concluir a operação.');
  return data;
}
let toastTimer;
function toast(message){$('#toast').textContent=message;$('#toast').classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.add('hidden'),4500);}
function showError(id,error){const el=$(id);el.textContent=error.message;el.classList.remove('hidden');}
function filters(){return {q:$('#search').value,priority:$('#priority-filter').value,stage:$('#stage-filter').value};}
function visibleLeads(){const f=filters();return state.leads.filter(l=>(!f.q||[l.name,l.address,l.city,l.category].join(' ').toLocaleLowerCase().includes(f.q.toLocaleLowerCase()))&&(!f.priority||l.analysis?.priority===f.priority)&&(!f.stage||l.stage===f.stage));}

function renderCampaigns(){
  $('#mobile-campaign').innerHTML=state.campaigns.length?state.campaigns.map(c=>`<option value="${escapeHTML(c.id)}" ${c.id===state.selected?'selected':''}>${escapeHTML(c.config.niche)} · ${escapeHTML(c.config.city.split(',')[0])} · ${date(c.created_at)}</option>`).join(''):'<option value="">Nenhuma campanha</option>';
  $('#campaign-list').innerHTML=state.campaigns.length?state.campaigns.map(c=>`<button class="campaign-item ${c.id===state.selected?'selected':''}" data-campaign="${escapeHTML(c.id)}"><strong>${escapeHTML(c.config.niche)}</strong><small>${escapeHTML(c.config.city.split(',')[0])} · ${escapeHTML(runLabels[c.state]||c.state)}</small></button>`).join(''):'<p class="side-muted">Suas buscas aparecerão aqui.</p>';
}
async function selectCampaign(id){state.selected=id;localStorage.setItem('radar:lastCampaign',id);await loadSelected();renderCampaigns();}
async function loadSelected(){
  if(!state.selected)return;
  const selected=state.selected;
  const result=await api(`/api/campaigns/${encodeURIComponent(selected)}`);
  if(state.selected!==selected)return;
  state.campaign=result.campaign;state.leads=result.leads;state.usage=result.usage;
  render();
}
function render(){
  const c=state.campaign;
  if(c){
    $('#campaign-title').textContent=c.config.niche;
    $('#campaign-subtitle').textContent=`${c.config.city.split(',').slice(0,2).join(' · ')} · ${date(c.created_at)}`;
    const badge=$('#source-badge');badge.textContent=c.config.source==='demo'?'DADOS FICTÍCIOS':c.config.source==='import'?'BASE IMPORTADA':'COLETA REAL';badge.className='badge '+(c.config.source==='demo'?'demo':'neutral');
    const notices=[...c.warnings];
    if(['failed','partial','interrupted','cancelled'].includes(c.state))notices.unshift(c.message);
    $('#notice').innerHTML=notices.map(n=>`<p>${escapeHTML(n)}</p>`).join('');$('#notice').classList.toggle('hidden',notices.length===0);
    const active=['queued','running'].includes(c.state);$('#run-progress').classList.toggle('hidden',!active);$('#run-message').textContent=c.message||'Aguardando início…';$('#progress').value=c.progress;
    $('#results-caption').textContent=`${runLabels[c.state]||c.state} · ${c.config.source==='demo'?'Amostra fictícia para explorar o produto':c.message}`;
  }
  $('#stat-total').textContent=state.leads.length;
  $('#stat-high').textContent=state.leads.filter(l=>l.analysis?.priority==='high'&&!['discarded','do_not_contact'].includes(l.stage)).length;
  $('#stat-contact').textContent=state.leads.filter(l=>l.phone||l.instagram_status==='confirmed').length;
  $('#stat-low').textContent=state.leads.filter(l=>l.analysis?.visibility==='low').length;
  const rows=visibleLeads();$('#result-count').textContent=rows.length;
  $('#lead-rows').innerHTML=rows.map((lead,i)=>{
    const a=lead.analysis||{};
    const initials=lead.name.split(' ').slice(0,2).map(w=>w[0]).join('').toUpperCase();
    const phone=lead.phone?`<span>${escapeHTML(lead.phone)}</span>`:'<small>Telefone não informado</small>';
    const instagram=lead.instagram&&lead.instagram_status!=='rejected'?externalLink(lead.instagram,lead.instagram_status==='confirmed'?'Instagram confirmado':'Instagram · revisar'):'<small>Instagram não confirmado</small>';
    return `<tr><td><div class="company"><span class="avatar tone${i%4}" aria-hidden="true">${escapeHTML(initials)}</span><div><button data-lead="${lead.id}">${escapeHTML(lead.name)}</button><small>${escapeHTML(lead.borough||lead.category||lead.city)}</small></div></div></td><td><span class="rating"><span class="star" aria-hidden="true">★</span>${formatNumber(lead.rating)} <small>${formatNumber(lead.reviews)} avaliações</small></span><span class="rank">${a.rank_median!=null?`${formatNumber(a.rank_median)}ª posição mediana · ${a.rank_samples} amostra(s)`:'Visibilidade não medida'}</span></td><td><div class="contacts">${phone}${instagram}</div></td><td><div class="score-cell"><span class="badge ${a.priority||'review'}">${priorityLabels[a.priority]||'Analisando'}</span><span class="score-number">${a.score??'—'}</span></div></td><td><span class="stage">${stageLabels[lead.stage]||lead.stage}</span></td><td><button class="row-open" data-lead="${lead.id}" aria-label="Abrir ficha de ${escapeHTML(lead.name)}">⋯</button></td></tr>`;
  }).join('');
  $('#empty').classList.toggle('hidden',rows.length>0);
  if(state.selected){$('#empty h3').textContent=state.leads.length?'Nenhuma empresa com esses filtros.':'Nenhuma empresa nesta campanha ainda.';$('#empty p').textContent=state.leads.length?'Ajuste a busca ou os filtros para voltar à lista.':state.campaign.message||'Aguarde o processamento da campanha.';$('#demo-button').classList.add('hidden');$('#empty small').classList.add('hidden');}
  $('#table-summary').textContent=`${rows.length} de ${state.leads.length} empresas`;
  $('#export-button').disabled=!rows.length;
  $('#usage-caption').textContent=state.usage.map(u=>`${u.provider==='typesafe'?'Jev':'Busca'}: ${u.calls} chamada(s)${u.cost!=null?' · US$ '+u.cost.toFixed(4):''}${u.tokens!=null?' · '+u.tokens+' tokens':''}${u.incomplete?' · '+u.incomplete+' sem sucesso confirmado':''}`).join(' | ');
}
function showView(view){$('#leads-view').classList.toggle('hidden',view!=='leads');$('#integrations-view').classList.toggle('hidden',view!=='integrations');$('#nav-leads').classList.toggle('active',view==='leads');$('#nav-integrations').classList.toggle('active',view==='integrations');$('#breadcrumb').textContent=view==='leads'?'Oportunidades':'Integrações';}
function newCampaign(){showView('leads');$('#campaign-error').classList.add('hidden');$('#campaign-dialog').showModal();estimate();}
function estimate(){const form=$('#campaign-form');const data=new FormData(form);const queries=data.get('keywords').split('\n').filter(x=>x.trim()).length||1;const points=data.get('coordinates').split('\n').filter(x=>x.trim()).length||1;const total=queries*points+Number(data.get('limit'))*(Number(data.has('enrich'))+Number(data.has('use_jev')&&state.settings.jev));$('#call-estimate').textContent=data.get('source')==='demo'?'Demonstração: até 10 empresas fictícias e nenhuma chamada de API.':`Até ${total} chamadas nesta campanha. Limite configurado: ${state.settings.run_limit}. ${!state.settings.dataforseo?'Configure a busca em Integrações antes de iniciar.':''}`;}

function openLead(id){
  const lead=state.leads.find(l=>l.id===id);if(!lead)return;
  state.detail=id;
  const a=lead.analysis||{},fit=a.fit||{};
  const fitLabel=fit.method==='jev'?`Jev ${fit.model||''} · confiança ${Math.round((fit.confidence||0)*100)}%`:fit.method==='error'?'Jev indisponível · revisão necessária':'Regras locais · sem avaliação de IA';
  const observations=lead.observations.map(o=>`<div class="observation"><strong>${escapeHTML(o.query)} · posição ${o.rank??'não medida'}</strong><small>${escapeHTML(o.location)} · ${date(o.observed_at)} · limite ${o.depth} resultados</small>${o.source_url?externalLink(o.source_url,'Conferir busca'):''}</div>`).join('');
  $('#lead-detail').innerHTML=`<div class="modal-top"><div><div class="eyebrow">FICHA DA EMPRESA</div><h2>${escapeHTML(lead.name)}</h2></div><button class="icon-button close-dialog" aria-label="Fechar ficha">×</button></div><p class="detail-address">${escapeHTML(lead.address||'Endereço não informado')}</p><div class="score-cell"><span class="badge ${a.priority||'review'}">${priorityLabels[a.priority]||'Em análise'} · ${a.score??'—'}/100</span><span class="badge neutral">${a.completeness??0}% dos campos disponíveis</span></div>${state.campaign.config.source==='demo'?'<p class="notice">Empresa fictícia. Estes dados não representam um negócio real.</p>':''}${lead.region_review?'<p class="notice">Cidade não retornada de forma estruturada. Confira a região antes da abordagem.</p>':''}<div class="detail-block"><h3>Informações principais</h3><div class="detail-pairs"><div><span>Telefone comercial</span><p>${escapeHTML(lead.phone||'Não informado')}</p></div><div><span>Categoria</span><p>${escapeHTML(lead.category||'Não informada')}</p></div><div><span>Site</span><p>${lead.website?externalLink(lead.website,new URL(lead.website).hostname):'Não informado pela fonte'}</p></div><div><span>Avaliações</span><p>${formatNumber(lead.rating)} / 5 · ${formatNumber(lead.reviews)} avaliações</p></div></div><div class="detail-links">${lead.maps_url?externalLink(lead.maps_url,'Abrir no Google Maps','button secondary'):''}${lead.source_url?externalLink(lead.source_url,'Ver fonte','button secondary'):''}</div><p class="explain">Coletado em ${date(lead.collected_at)}. Telefone informado não significa WhatsApp confirmado.</p></div><div class="detail-block"><h3>Por que conferir esta empresa?</h3><ul class="reasons">${(a.reasons||[]).map(r=>`<li><b>+${r.points}</b><span>${escapeHTML(r.text)}</span></li>`).join('')||'<li>Dados insuficientes para pontuar.</li>'}</ul><p class="explain">${escapeHTML(fitLabel)}. Pontuação v1 de triagem; não estima intenção de compra.</p></div><div class="detail-block"><h3>Instagram</h3><p class="explain">${escapeHTML(instagramLabels[lead.instagram_status]||'Não pesquisado')} · ${escapeHTML(lead.instagram_source||'Sem fonte disponível.')}</p>${(lead.instagram_candidates||[]).map(candidate=>`<div class="observation">${externalLink(candidate.url,candidate.title||candidate.url)}<small>${escapeHTML(candidate.description)}</small></div>`).join('')}<label>Link do perfil<input id="detail-instagram" type="url" placeholder="https://www.instagram.com/perfil/" value="${escapeHTML(lead.instagram||'')}"></label><div class="detail-links"><button class="button secondary" id="confirm-instagram">Confirmar identidade</button><button class="text-button" id="reject-instagram">Rejeitar candidato</button></div><p class="explain">Confirme após comparar nome, cidade e contatos com a fonte. O modelo não confirma a identidade sozinho.</p></div><div class="detail-block"><h3>Visibilidade observada</h3>${observations||'<p class="explain">Não há medição de posição para esta empresa.</p>'}<p class="explain">Mediana somente das posições encontradas. Não mede todas as buscas nem toda a cidade.</p></div><div class="detail-block"><h3>Acompanhamento</h3><label>Etapa<select id="detail-stage">${Object.entries(stageLabels).map(([key,label])=>`<option value="${key}" ${lead.stage===key?'selected':''}>${label}</option>`).join('')}</select></label><label class="notes-label">Suas observações<textarea id="detail-notes" rows="4" maxlength="5000" placeholder="Registre o que precisa conferir ou o contexto da conversa.">${escapeHTML(lead.notes)}</textarea></label><p id="detail-error" class="form-error hidden" role="alert"></p><div class="modal-footer"><button id="delete-lead" class="text-button danger">Excluir empresa</button><button id="save-lead" class="button primary">Salvar acompanhamento</button></div></div>`;
  if(!$('#lead-dialog').open)$('#lead-dialog').showModal();
  $('#save-lead').onclick=async()=>{try{await saveLead({});toast('Acompanhamento salvo.');$('#lead-dialog').close();}catch(e){showError('#detail-error',e);}};
  $('#confirm-instagram').onclick=()=>updateInstagram('confirmed');
  $('#reject-instagram').onclick=()=>updateInstagram('rejected');
  $('#delete-lead').onclick=async()=>{if(!confirm('Excluir esta empresa de todas as campanhas e apagar seu histórico?'))return;try{await api('/api/leads/'+id,{method:'DELETE'});$('#lead-dialog').close();await loadSelected();toast('Empresa excluída.');}catch(e){showError('#detail-error',e);}};
}
async function saveLead(extra){await api('/api/leads/'+state.detail,{method:'PATCH',body:JSON.stringify({stage:$('#detail-stage').value,notes:$('#detail-notes').value,...extra})});await loadSelected();}
async function updateInstagram(status){try{await saveLead({instagram:$('#detail-instagram').value,instagram_status:status});openLead(state.detail);toast(status==='confirmed'?'Identidade confirmada pelo operador.':'Candidato rejeitado.');}catch(e){showError('#detail-error',e);}}

document.addEventListener('click',e=>{const close=e.target.closest('.close-dialog');if(close)close.closest('dialog').close();const campaign=e.target.closest('[data-campaign]');if(campaign){showView('leads');selectCampaign(campaign.dataset.campaign).catch(toastError);}const lead=e.target.closest('[data-lead]');if(lead)openLead(lead.dataset.lead);});
const toastError=e=>toast(e.message||'Falha na operação.');
$('#nav-leads').onclick=()=>showView('leads');$('#nav-integrations').onclick=()=>showView('integrations');
$('#new-campaign').onclick=newCampaign;$('#side-new').onclick=newCampaign;
$('#mobile-campaign').onchange=e=>{if(e.target.value)selectCampaign(e.target.value).catch(toastError);};
for(const selector of ['#search','#priority-filter','#stage-filter'])$(selector).addEventListener('input',render);
$('#campaign-form').addEventListener('input',estimate);
$('#campaign-form').addEventListener('submit',async e=>{
  e.preventDefault();const button=$('#campaign-submit');button.disabled=true;$('#campaign-error').classList.add('hidden');
  const data=Object.fromEntries(new FormData(e.target));data.limit=Number(data.limit);data.enrich='enrich' in data;data.use_jev='use_jev' in data;
  try{const created=await api('/api/campaigns',{method:'POST',body:JSON.stringify(data)});$('#campaign-dialog').close();state.campaigns=(await api('/api/campaigns')).campaigns;await selectCampaign(created.id);toast('Campanha adicionada à fila.');}catch(error){showError('#campaign-error',error);}finally{button.disabled=false;}
});
$('#demo-button').onclick=async()=>{const button=$('#demo-button');button.disabled=true;try{const created=await api('/api/campaigns',{method:'POST',body:JSON.stringify({niche:'Loja de moda feminina',city:'São Carlos,São Paulo,Brazil',service:'google',source:'demo',limit:10,keywords:['moda feminina São Carlos','boutique feminina São Carlos','roupas femininas São Carlos']})});state.campaigns=(await api('/api/campaigns')).campaigns;await selectCampaign(created.id);}catch(e){toastError(e);}finally{button.disabled=false;}};
$('#export-button').onclick=()=>{if(state.selected)window.location.href='/api/campaigns/'+encodeURIComponent(state.selected)+'/export?'+new URLSearchParams(filters());};
$('#cancel-campaign').onclick=async()=>{try{await api('/api/campaigns/'+state.selected+'/cancel',{method:'POST',body:'{}'});toast('Cancelamento solicitado. A chamada em andamento poderá terminar.');await loadSelected();}catch(e){toastError(e);}};
$('#import-button').onclick=()=>{$('#import-error').classList.add('hidden');$('#import-dialog').showModal();};
$('#confirm-import').onclick=async()=>{const button=$('#confirm-import');button.disabled=true;try{const file=$('#import-file').files[0];if(!file)throw new Error('Selecione um arquivo JSON.');if(file.size>1000000)throw new Error('O arquivo deve ter até 1 MB.');const data=JSON.parse(await file.text());const created=await api('/api/import',{method:'POST',body:JSON.stringify(data)});$('#import-dialog').close();state.campaigns=(await api('/api/campaigns')).campaigns;await selectCampaign(created.id);toast('Arquivo importado.');}catch(e){showError('#import-error',e);}finally{button.disabled=false;}};

async function start(){
  state.settings=await api('/api/status');state.token=state.settings.token;
  $('#dfs-status').textContent=state.settings.dataforseo?'Credenciais configuradas · não testadas':'Aguardando credenciais';$('#jev-status').textContent=state.settings.jev?'Chave configurada · não testada':'Regras locais disponíveis';
  $('#limits-caption').textContent=`Até ${state.settings.run_limit} chamadas por campanha e ${state.settings.daily_limit} por dia UTC. Modelo configurado: ${state.settings.jev_model}.`;
  state.campaigns=(await api('/api/campaigns')).campaigns;
  const last=localStorage.getItem('radar:lastCampaign');
  if(state.campaigns.length)await selectCampaign(state.campaigns.some(c=>c.id===last)?last:state.campaigns[0].id);
  else renderCampaigns();
  setInterval(async()=>{if(state.loading)return;state.loading=true;try{state.campaigns=(await api('/api/campaigns')).campaigns;renderCampaigns();if(state.selected&&!$('#lead-dialog').open)await loadSelected();}catch{$('#results-caption').textContent='Conexão interrompida. Os dados exibidos podem estar desatualizados; verifique o terminal.';}finally{state.loading=false;}},1800);
}
start().catch(e=>{toastError(e);$('#results-caption').textContent='Servidor indisponível. Confira se o aplicativo está em execução e atualize a página.';});

// Optional browser-standard tools. Unsupported browsers keep the same UI.
if(document.modelContext?.registerTool){
  const lifecycle=new AbortController();
  const tools=[{name:'radar_read_visible_leads',title:'Ler empresas filtradas',description:'Read the currently visible leads without making external API calls.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute(input){if(!input||typeof input!=='object'||Object.keys(input).length)throw new Error('Expected empty object.');return {campaign:state.selected,leads:visibleLeads().map(l=>({id:l.id,name:l.name,priority:l.analysis?.priority,score:l.analysis?.score,source:l.source}))};}},{name:'radar_open_campaign_form',title:'Preparar campanha',description:'Open the campaign form. Does not start a search or spend API credits.',inputSchema:{type:'object',properties:{niche:{type:'string'},city:{type:'string'}},additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},execute(input){if(!input||typeof input!=='object'||Object.keys(input).some(k=>!['niche','city'].includes(k)))throw new Error('Invalid fields.');for(const k of ['niche','city'])if(input[k]!==undefined&&(typeof input[k]!=='string'||input[k].length>100))throw new Error('Invalid field.');for(const k of ['niche','city'])if(input[k])$('#campaign-form').elements[k].value=input[k];newCampaign();return {status:'form_open',search_started:false};}}];
  for(const tool of tools){try{Promise.resolve(document.modelContext.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});}catch{}}
  window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
}
