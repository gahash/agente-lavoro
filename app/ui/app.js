"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let STATO = null;

async function api(path, body, method) {
  const r = await fetch(path, {
    method: method || (body !== undefined ? "POST" : "GET"),
    headers: {"Content-Type": "application/json", "X-Token": window.TOKEN},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Errore ${r.status}`);
  return data;
}
function toast(msg, err) {
  const d = document.createElement("div"); d.className = "t" + (err ? " err" : ""); d.textContent = msg;
  $("#toast").appendChild(d); setTimeout(() => d.remove(), err ? 9000 : 4500);
}
// esegue un'azione su un pulsante mostrando lo stato di attesa
async function run(btn, fn, okMsg) {
  const html = btn?.innerHTML; if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span> ' + html; }
  try { const r = await fn(); if (r && r.ok === false) toast(r.errore || "Operazione non riuscita", true); else if (okMsg) toast(typeof okMsg === "function" ? okMsg(r) : okMsg); return r; }
  catch (e) { toast(e.message, true); }
  finally { if (btn) { btn.disabled = false; btn.innerHTML = html; } }
}
function modal(html) { $("#modal-box").innerHTML = html; $("#modal").classList.remove("hidden"); }
function closeModal() { $("#modal").classList.add("hidden"); }
$("#modal").addEventListener("click", e => { if (e.target.id === "modal") closeModal(); });
const score = p => { const c = p === 0 ? "s-bad" : p >= 7 ? "s-hi" : p >= 5 ? "s-mid" : "s-lo"; return `<span class="score ${c}">${p ?? "–"}</span>`; };
const CAT = {rosso:"🔴 Lavoro/cliente", arancio:"🟠 Collaborazione", giallo:"🟡 Informazioni", bianco:"⚪ Newsletter", stop:"⛔ Spam/phishing"};
const dt = s => s ? new Date(s).toLocaleString("it-IT", {day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit"}) : "";

async function refreshStato() {
  STATO = await api("/api/stato");
  const n = STATO.numeri;
  $("#b-bozze").textContent = n.bozze_da_approvare || "";
  $("#b-posta").textContent = (n.posta_da_gestire + n.posta_allarmi) || "";
  const ai = $("#ai-stato");
  if (STATO.modelli.length) { ai.className = "pill ok"; ai.textContent = "AI locale: " + STATO.impostazioni.modello; }
  else { ai.className = "pill bad"; ai.textContent = "AI locale non attiva"; }
}

// ------------------------------------------------------------------ viste
const V = {};

V.home = async m => {
  await refreshStato(); const n = STATO.numeri;
  m.innerHTML = `<h1>Buongiorno Gaspare</h1><p class="sub">${new Date().toLocaleDateString("it-IT",{weekday:"long",day:"numeric",month:"long"})} — cosa c'è da fare oggi</p>
  ${!STATO.modelli.length ? `<div class="warnbox">Il modello AI locale non risponde. Avvia <b>Ollama</b> (deve esserci <b>llama3.1:8b</b>) e ricarica.</div>` : ""}
  ${!STATO.credenziali.imap_password.impostato ? `<div class="warnbox">Credenziali email non inserite: vai su <a href="#" onclick="go('impostazioni')">Impostazioni</a>.</div>` : ""}
  <div class="grid">
    <div class="card kpi"><b>${n.bozze_da_approvare}</b><span>bozze da approvare</span></div>
    <div class="card kpi"><b>${n.posta_da_gestire}</b><span>email da gestire</span></div>
    <div class="card kpi"><b style="color:var(--bad)">${n.posta_allarmi}</b><span>email sospette</span></div>
    <div class="card kpi"><b>${n.opportunita_top}</b><span>annunci ≥ ${STATO.impostazioni.soglia_annunci}</span></div>
    <div class="card kpi"><b>${n.aziende_nuove}</b><span>PMI da lavorare</span></div>
    <div class="card kpi"><b>${n.quota_pmi_residua}</b><span>contatti PMI disponibili oggi</span></div>
    <div class="card kpi"><b>${n.follow_up_scaduti}</b><span>follow-up da fare</span></div>
  </div>
  <h2>✅ Cose da fare oggi <a href="#" data-go="todo" class="small" style="font-weight:400">tutte →</a></h2>
  <div class="card" style="padding:0" id="home-todo"></div>
  <h2>Azioni rapide</h2>
  <div class="row">
    <button id="q-posta">📬 Controlla posta</button>
    <button id="q-lavoro">💼 Cerca annunci</button>
    <button class="sec" id="q-rep">📝 Report del mattino</button>
    <button class="sec" id="q-xls">📊 Esporta Excel</button>
  </div>
  <div id="rep" class="card md small" style="display:none"></div>
  <h2>Pianificazione automatica (con l'app aperta)</h2>
  <div class="small muted">${STATO.pianificazione.map(j => `${esc(j.id)}: ${esc(j.prossima)}`).join(" · ")}</div>
  <p class="small muted">Le routine preparano solo dati, analisi e bozze. Nessun messaggio parte senza la tua approvazione.</p>`;
  const disegnaTodo = async () => { const l = await aggiornaBadgeTodo(); $("#home-todo").innerHTML = todoHtml(l.filter(a => !a.fatto).slice(0, 8), true); };
  await disegnaTodo(); todoEvents(m, disegnaTodo);
  $("#q-posta").onclick = e => run(e.target, () => api("/api/posta/controlla", {}), r => `Posta: ${r.nuovi} nuovi messaggi`);
  $("#q-lavoro").onclick = e => run(e.target, () => api("/api/lavoro/cerca", {ai: true}), r => `Annunci: ${r.nuovi} nuovi su ${r.letti}, ${r.valutati_ai} valutati con AI`);
  $("#q-rep").onclick = e => run(e.target, async () => { const r = await api("/api/report/mattino", {}); const b = $("#rep"); b.style.display = ""; b.textContent = r.testo; });
  $("#q-xls").onclick = e => run(e.target, () => api("/api/export", {}), r => "Salvato: " + r.file);
};

// ---------------- cose da fare
function todoHtml(lista, compatta) {
  return lista.map(a => `<div class="todo ${a.fatto ? "done" : ""} ${a.priorita === 1 && !a.fatto ? "prio1" : ""}">
    <input type="checkbox" data-done="${a.id}" ${a.fatto ? "checked" : ""}>
    <span class="t-ora">${esc(a.ora || "")}</span>
    <span class="t-tit">${esc(a.titolo)}${a.dettaglio ? `<br><span class="small muted">${esc(a.dettaglio)}</span>` : ""}</span>
    ${a.vista ? `<a href="#" data-go="${a.vista}" class="small">apri →</a>` : ""}
    ${compatta ? "" : `<span class="t-x" data-del="${a.id}" title="Elimina">✕</span>`}</div>`).join("") || `<p class="muted" style="padding:10px">Niente da fare. 🎉</p>`;
}
function todoEvents(m, ridisegna) {
  m.addEventListener("change", e => { const id = e.target.dataset.done; if (id) api(`/api/attivita/${id}`, {fatto: e.target.checked}).then(ridisegna); });
  m.addEventListener("click", e => {
    if (e.target.dataset.go) { e.preventDefault(); go(e.target.dataset.go); }
    if (e.target.dataset.del) api(`/api/attivita/${e.target.dataset.del}`, {elimina: true}).then(ridisegna);
  });
}
async function aggiornaBadgeTodo(lista) {
  lista = lista || await api("/api/attivita");
  $("#b-todo").textContent = lista.filter(a => !a.fatto && a.priorita === 1).length || "";
  return lista;
}

V.todo = async m => {
  const oggi = new Date().toISOString().slice(0, 10);
  const giorno = V.todo.giorno || oggi;
  const lista = await api("/api/attivita?giorno=" + giorno);
  aggiornaBadgeTodo();
  const fatte = lista.filter(a => a.fatto).length, pct = lista.length ? Math.round(fatte / lista.length * 100) : 0;
  m.innerHTML = `<h1>Cose da fare</h1><p class="sub">La tua routine quotidiana + quello che emerge da posta, bozze, pipeline e annunci. Le voci rosse sono prioritarie.</p>
  <div class="row"><input type="date" id="giorno" value="${giorno}"><button class="sec sm" id="oggi">Oggi</button>
   <span class="muted small">${fatte}/${lista.length} completate</span></div>
  <div class="prog"><i style="width:${pct}%"></i></div>
  <div class="row"><input id="ora" type="time" style="width:110px"><input id="tit" placeholder="Aggiungi un'attività… (Invio)" style="flex:1"><button id="add">Aggiungi</button></div>
  <div class="card" style="padding:0">${todoHtml(lista)}</div>
  <p class="small muted">La routine fissa si modifica in Impostazioni → Routine quotidiana. Dalla chat puoi scrivere: <code>+ 15:00 chiamare Rossi</code></p>`;
  const add = () => { const t = $("#tit").value.trim(); if (!t) return; api("/api/attivita", {titolo: t, ora: $("#ora").value, giorno}).then(() => go("todo")); };
  $("#add").onclick = add; $("#tit").onkeydown = e => { if (e.key === "Enter") add(); };
  $("#giorno").onchange = e => { V.todo.giorno = e.target.value; go("todo"); };
  $("#oggi").onclick = () => { V.todo.giorno = null; go("todo"); };
  todoEvents(m, () => go("todo"));
};

// ---------------- chat
V.chat = async m => {
  const storia = await api("/api/chat");
  const SUGG = ["Cosa devo fare oggi?", "Quali sono i 3 annunci migliori e perché?", "Riassumi la mia pipeline",
                "Ci sono email urgenti o sospette?", "Preparami 5 domande per un colloquio da sviluppatore backend",
                "Quanto chiedere come tariffa giornaliera da freelance per sviluppo AI in Italia?"];
  m.innerHTML = `<div class="chatwrap"><div class="row" style="justify-content:space-between;margin:0">
    <div><h1>Chiedi all'assistente</h1><p class="sub" style="margin:0">AI locale (${esc(STATO?.impostazioni.modello)}) — conosce i dati dell'app. Nulla esce dal computer.</p></div>
    <button class="sec sm" id="clr">🗑 Nuova conversazione</button></div>
   <div class="msgs" id="msgs">${storia.map(x => `<div class="msg ${x.ruolo === "utente" ? "u" : "a"}">${esc(x.testo)}</div>`).join("")}</div>
   ${storia.length ? "" : `<div class="sugg">${SUGG.map(s => `<button class="sec sm" data-s="${esc(s)}">${esc(s)}</button>`).join("")}</div>`}
   <div class="chatbar"><textarea id="q" placeholder="Scrivi una domanda… (Invio per inviare, Maiusc+Invio per andare a capo). '+ 10:00 testo' aggiunge alle cose da fare"></textarea>
   <button id="send">Invia</button></div></div>`;
  const box = $("#msgs"); box.scrollTop = box.scrollHeight;
  const invia = async testo => {
    testo = (testo ?? $("#q").value).trim(); if (!testo) return;
    $("#q").value = ""; $(".sugg")?.remove(); $("#send").disabled = true;
    box.insertAdjacentHTML("beforeend", `<div class="msg u">${esc(testo)}</div><div class="msg a"><span class="spin"></span></div>`);
    const out = box.lastElementChild; box.scrollTop = box.scrollHeight;
    try {
      const r = await fetch("/api/chat", {method: "POST", headers: {"Content-Type": "application/json", "X-Token": window.TOKEN}, body: JSON.stringify({testo})});
      if (!r.ok) throw new Error((await r.json()).detail);
      const rd = r.body.getReader(), dec = new TextDecoder(); let txt = "";
      for (;;) { const {done, value} = await rd.read(); if (done) break; txt += dec.decode(value, {stream: true}); out.textContent = txt; box.scrollTop = box.scrollHeight; }
      if (/aggiunto alle cose da fare/i.test(txt)) aggiornaBadgeTodo();
    } catch (e) { out.textContent = "⚠️ " + e.message; }
    finally { $("#send").disabled = false; $("#q").focus(); }
  };
  $("#send").onclick = () => invia();
  $("#q").onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); invia(); } };
  $("#clr").onclick = () => api("/api/chat", undefined, "DELETE").then(() => go("chat"));
  m.onclick = e => { if (e.target.dataset.s) invia(e.target.dataset.s); };
  $("#q").focus();
};

V.lavoro = async m => {
  const [lista, ricerche] = await Promise.all([api("/api/lavoro?min=0"), api("/api/lavoro/ricerche")]);
  const soglia = STATO?.impostazioni.soglia_annunci ?? 7;
  m.innerHTML = `<h1>Opportunità di lavoro</h1><p class="sub">Fonti con API pubbliche (Remote OK, Remotive, Himalayas, We Work Remotely, Arbeitnow) + annunci che apri tu nel browser.</p>
  <div class="row"><button id="cerca">🔎 Cerca nuovi annunci</button>
    <label style="margin:0"><input type="checkbox" id="solo" checked> solo ≥ ${soglia}</label>
    <input id="filtro" placeholder="Filtra per testo…" style="flex:1;max-width:280px"></div>
  <details class="card" style="margin-bottom:12px"><summary><b>Altri portali</b> — LinkedIn e Indeed si importano da <a href="#" data-go2="crm">🔗 Collegamenti</a>; questi si aprono nel browser</summary>
   <div class="row" style="margin-top:10px">${ricerche.map(r => `<button class="sec sm" data-url="${esc(r.url)}">${esc(r.nome)}</button>`).join("")}</div></details>
  <table><thead><tr><th>Punt.</th><th>Ruolo / azienda</th><th>Remoto / compenso</th><th>Motivazione</th><th>Stato</th><th></th></tr></thead><tbody id="tb"></tbody></table>`;
  const draw = () => {
    const f = $("#filtro").value.toLowerCase(), solo = $("#solo").checked;
    $("#tb").innerHTML = lista.filter(o => (!solo || o.punteggio >= soglia) && (!f || JSON.stringify(o).toLowerCase().includes(f))).map(o => `
      <tr><td>${score(o.punteggio)}</td>
      <td><b>${esc(o.ruolo)}</b><br><span class="muted">${esc(o.azienda)}</span> · <span class="tag">${esc(o.fonte)}</span><br><a href="#" data-url="${esc(o.link)}" class="small">apri annuncio ↗</a></td>
      <td class="small">${esc(o.remoto)}<br>${esc(o.compenso)}<br>${esc(o.tipo)}</td>
      <td class="small" style="max-width:340px">${esc(o.motivazione)}</td>
      <td><select data-st="${o.id}">${["Nuovo","Bozza pronta","Candidato","Colloquio","Scartato"].map(s => `<option ${s===o.stato?"selected":""}>${s}</option>`).join("")}</select></td>
      <td style="white-space:nowrap">${o.sospetto ? '<span class="tag" style="color:var(--bad)">sospetto</span>' :
        `${["LinkedIn","Indeed"].includes(o.fonte) ? `<button class="sm sec" data-an="${o.id}">🧠 Analizza</button> ` : ""}<button class="sm" data-cand="${o.id}">✍️ Candidatura</button> <button class="sm sec" data-li="${o.id}">LinkedIn</button>`}</td></tr>`).join("") ||
      `<tr><td colspan="6" class="muted">Nessun annuncio. Premi "Cerca nuovi annunci".</td></tr>`;
  };
  draw(); $("#filtro").oninput = draw; $("#solo").onchange = draw;
  $("#cerca").onclick = e => run(e.target, async () => { const r = await api("/api/lavoro/cerca", {ai: true}); toast(`${r.nuovi} nuovi su ${r.letti} · ${r.valutati_ai} valutati con AI`); if (r.errori.length) toast(r.errori.join(" | "), true); go("lavoro"); });
  m.onclick = async e => {
    const t = e.target;
    if (t.dataset.url) { e.preventDefault(); run(t, () => api("/api/browser/apri", {url: t.dataset.url})); }
    if (t.dataset.go2) { e.preventDefault(); return go(t.dataset.go2); }
    if (t.dataset.an) run(t, () => api(`/api/lavoro/${t.dataset.an}/analizza`, {}), r => `Valutato: punteggio ${r.punteggio}`).then(() => go("lavoro"));
    if (t.dataset.cand) run(t, () => api(`/api/lavoro/${t.dataset.cand}/candidatura`, {}), "Bozza di candidatura creata → Da approvare").then(refreshStato);
    if (t.dataset.li) run(t, () => api(`/api/lavoro/${t.dataset.li}/linkedin`, {}), "Messaggio LinkedIn creato → Da approvare").then(refreshStato);
  };
  m.onchange = e => { if (e.target.dataset.st) api(`/api/lavoro/${e.target.dataset.st}/stato`, {stato: e.target.value}); };
};

V.pmi = async m => {
  const [settori, lista] = await Promise.all([api("/api/pmi/settori"), api("/api/pmi")]);
  const n = STATO?.numeri;
  m.innerHTML = `<h1>Clienti PMI</h1><p class="sub">Aziende da dati pubblici (OpenStreetMap + sito web). Massimo ${STATO?.impostazioni.max_pmi_giorno} nuovi contatti al giorno — oggi ne restano <b>${n?.quota_pmi_residua}</b>.</p>
  <div class="row"><select id="set">${settori.map(s => `<option>${esc(s)}</option>`).join("")}</select>
   <input id="citta" placeholder="Città (es. Milano)" value="${esc(localStorage.citta || "")}">
   <button id="cerca">🔎 Trova aziende</button></div>
  <table><thead><tr><th>Azienda</th><th>Contatti</th><th>Analisi</th><th>Stato</th><th></th></tr></thead><tbody>
  ${lista.map(a => `<tr><td><b>${esc(a.nome)}</b><br><span class="small muted">${esc(a.settore)} · ${esc(a.citta)}</span><br><a href="#" data-url="${esc(a.sito)}" class="small">${esc(a.sito)}</a></td>
   <td class="small"><input data-mail="${a.id}" value="${esc(a.email)}" placeholder="email pubblica" style="width:190px"><br>${esc(a.telefono)}</td>
   <td class="small" style="max-width:380px">${esc(a.analisi) || '<span class="muted">—</span>'}<br><i class="muted">${esc(a.servizio)}</i></td>
   <td>${a.opt_out ? '<span class="tag" style="color:var(--bad)">opt-out</span>' : esc(a.stato)}</td>
   <td style="white-space:nowrap">${a.opt_out ? "" : `<button class="sm sec" data-an="${a.id}">🔍 Analizza</button> <button class="sm" data-pr="${a.id}" ${a.analisi ? "" : "disabled"}>✍️ Proposta</button>`}
   <button class="sm sec" data-no="${a.id}" title="Scarta">✕</button></td></tr>`).join("") || `<tr><td colspan="5" class="muted">Nessuna azienda: scegli settore e città.</td></tr>`}
  </tbody></table>`;
  $("#cerca").onclick = e => { const c = $("#citta").value.trim(); if (!c) return toast("Inserisci una città", true); localStorage.citta = c;
    run(e.target, () => api("/api/pmi/cerca", {settore: $("#set").value, citta: c}), r => `${r.nuove} nuove aziende (${r.trovate} trovate)`).then(() => go("pmi")); };
  m.onclick = e => { const t = e.target;
    if (t.dataset.url) { e.preventDefault(); run(t, () => api("/api/browser/apri", {url: t.dataset.url})); }
    if (t.dataset.an) run(t, () => api(`/api/pmi/${t.dataset.an}/analizza`, {}), "Analisi completata").then(() => go("pmi"));
    if (t.dataset.pr) run(t, () => api(`/api/pmi/${t.dataset.pr}/proposta`, {}), "Proposta creata → Da approvare").then(() => { refreshStato(); go("pmi"); });
    if (t.dataset.no) api(`/api/pmi/${t.dataset.no}/aggiorna`, {stato: "Scartato"}).then(() => go("pmi"));
  };
  m.onchange = e => { if (e.target.dataset.mail) api(`/api/pmi/${e.target.dataset.mail}/aggiorna`, {email: e.target.value.trim()}).then(() => toast("Email salvata")); };
};

V.bozze = async m => {
  const tab = V.bozze.tab || "da_approvare";
  const lista = await api("/api/bozze?stato=" + tab);
  m.innerHTML = `<h1>Da approvare</h1><p class="sub">Niente parte senza il tuo OK. Modifica il testo, approva, poi invia (o copia nelle Bozze della casella).</p>
  <div class="row">${[["da_approvare","Da approvare"],["approvata","Approvate"],["inviata","Inviate"],["scartata","Scartate"]].map(([k,l]) =>
    `<button class="${k===tab?"":"sec"} sm" data-tab="${k}">${l}</button>`).join("")}</div>
  ${lista.map(b => `<div class="card draft" style="margin-bottom:12px" data-id="${b.id}">
    <div class="row" style="justify-content:space-between;margin:0"><span><span class="tag">${esc(b.tipo)}</span> <span class="small muted">${dt(b.creato)}</span></span>
      <span class="small muted">${esc(b.note)}</span></div>
    <label>A</label><input class="f-dest" value="${esc(b.destinatario)}" style="width:100%" placeholder="email destinatario">
    <label>Oggetto</label><input class="f-ogg" value="${esc(b.oggetto)}" style="width:100%">
    <label>Testo</label><textarea class="f-corpo">${esc(b.corpo)}</textarea>
    <div class="row" style="margin:10px 0 0">
      ${tab === "da_approvare" ? `<button class="ok" data-a="approva">✅ Approva</button><button class="sec" data-a="salva">💾 Salva modifiche</button><button class="bad" data-a="scarta">Scarta</button>` : ""}
      ${tab === "approvata" ? `<button data-a="invia">📤 Invia ora</button><button class="sec" data-a="casella">📥 Copia nelle Bozze della casella</button><button class="sec" data-a="riapri">↩︎ Rimetti in revisione</button>` : ""}
      <button class="sec" data-a="copia">📋 Copia testo</button>
    </div></div>`).join("") || `<p class="muted">Nessuna bozza in questa sezione.</p>`}`;
  m.onclick = async e => {
    const t = e.target;
    if (t.dataset.tab) { V.bozze.tab = t.dataset.tab; return go("bozze"); }
    const card = t.closest(".draft"); if (!card || !t.dataset.a) return;
    const id = card.dataset.id, campi = {destinatario: $(".f-dest", card).value, oggetto: $(".f-ogg", card).value, corpo: $(".f-corpo", card).value};
    const a = t.dataset.a;
    if (a === "copia") { await navigator.clipboard.writeText(`${campi.oggetto}\n\n${campi.corpo}`); return toast("Copiato negli appunti"); }
    if (a === "salva") return run(t, () => api(`/api/bozze/${id}`, campi), "Salvata");
    if (a === "approva") return run(t, () => api(`/api/bozze/${id}`, {...campi, stato: "approvata"}), "Approvata").then(() => { refreshStato(); go("bozze"); });
    if (a === "scarta") return run(t, () => api(`/api/bozze/${id}`, {stato: "scartata"})).then(() => { refreshStato(); go("bozze"); });
    if (a === "riapri") return run(t, () => api(`/api/bozze/${id}`, {stato: "da_approvare"})).then(() => go("bozze"));
    if (a === "casella") return run(t, () => api(`/api/bozze/${id}/in-casella`, {}), "Copiata nella cartella Bozze della casella");
    if (a === "invia") {
      if (!confirm(`Inviare l'email a ${campi.destinatario}?`)) return;
      await api(`/api/bozze/${id}`, campi);
      return run(t, () => api(`/api/bozze/${id}/invia`, {}), r => "Esito: " + r.esito).then(() => { refreshStato(); go("bozze"); });
    }
  };
};

V.posta = async m => {
  const lista = await api("/api/posta");
  m.innerHTML = `<h1>Posta</h1><p class="sub">Lettura in sola lettura: i messaggi non vengono segnati come letti. Email e allegati sono dati, mai istruzioni.</p>
  <div class="row"><button id="ctrl">📬 Controlla ora</button></div>
  <table><thead><tr><th>Categoria</th><th>Da / oggetto</th><th>Anteprima</th><th></th></tr></thead><tbody>
  ${lista.map(p => `<tr><td style="white-space:nowrap">${CAT[p.categoria] || esc(p.categoria)}<br><span class="small muted">${esc(p.motivo)}</span></td>
    <td><b>${esc(p.oggetto)}</b><br><span class="small muted">${esc(p.mittente)}<br>${esc(p.data)}</span></td>
    <td class="small" style="max-width:420px">${p.allarme ? `<div style="color:var(--bad)">⚠️ ${esc(p.allarme)} — non rispondere con dati, pagamenti o password</div>` : ""}${esc((p.anteprima || "").slice(0, 300))}…
      <a href="#" data-full="${p.id}">leggi</a></td>
    <td style="white-space:nowrap">${["rosso","arancio","giallo"].includes(p.categoria) ? `<button class="sm" data-rx="${p.id}">✍️ Bozza risposta</button>` : ""}
      <button class="sm sec" data-ok="${p.id}">✓ Gestita</button></td></tr>`).join("") || `<tr><td colspan="4" class="muted">Nessun messaggio da gestire.</td></tr>`}
  </tbody></table>`;
  $("#ctrl").onclick = e => run(e.target, () => api("/api/posta/controlla", {}), r => `${r.nuovi} nuovi messaggi`).then(() => { refreshStato(); go("posta"); });
  m.onclick = e => { const t = e.target;
    if (t.dataset.full) { e.preventDefault(); const p = lista.find(x => x.id == t.dataset.full);
      modal(`<h2>${esc(p.oggetto)}</h2><p class="small muted">${esc(p.mittente)}</p><div class="md">${esc(p.anteprima)}</div><div class="row" style="margin-top:12px"><button onclick="closeModal()">Chiudi</button></div>`); }
    if (t.dataset.rx) run(t, () => api(`/api/posta/${t.dataset.rx}/risposta`, {}), "Bozza di risposta creata → Da approvare").then(refreshStato);
    if (t.dataset.ok) api(`/api/posta/${t.dataset.ok}/gestita`, {}).then(() => { refreshStato(); go("posta"); });
  };
};

V.pipeline = async m => {
  const lista = await api("/api/pipeline");
  const STATI = ["Nuovo","Contattato","Risposta","Call","Preventivo/Colloquio","Trattativa","Vinto","Perso"];
  const oggi = new Date().toISOString().slice(0, 10);
  m.innerHTML = `<h1>Pipeline</h1><p class="sub">Lavoro, clienti e collaborazioni. Le righe si creano da sole quando invii una bozza; puoi aggiungerne a mano.</p>
  <div class="row"><button id="nuovo">➕ Nuova voce</button><button class="sec" id="xls">📊 Esporta Excel</button></div>
  <table><thead><tr><th>Tipo</th><th>Azienda / contatto</th><th>Stato</th><th>Prossimo passo</th><th>Valore €</th><th></th></tr></thead><tbody>
  ${lista.map(p => `<tr><td><span class="tag">${esc(p.tipo)}</span></td><td><b>${esc(p.azienda)}</b><br><span class="small muted">${esc(p.contatto)} · ${esc(p.canale)}</span></td>
    <td><select data-st="${p.id}">${STATI.map(s => `<option ${s===p.stato?"selected":""}>${s}</option>`).join("")}</select></td>
    <td class="small">${esc(p.prossimo_passo)}<br><b style="color:${p.data_prossimo && p.data_prossimo <= oggi ? "var(--bad)" : "inherit"}">${esc(p.data_prossimo)}</b></td>
    <td>${p.valore ?? ""}</td>
    <td style="white-space:nowrap"><button class="sm sec" data-ed="${p.id}">Modifica</button> ${p.stato === "Contattato" ? `<button class="sm" data-fu="${p.id}">Follow-up (${p.solleciti}/2)</button>` : ""}</td></tr>`).join("") ||
    `<tr><td colspan="6" class="muted">Pipeline vuota.</td></tr>`}</tbody></table>`;
  let editId = null;
  const form = (p = {}) => (editId = p.id || null, modal(`<h2>${p.id ? "Modifica" : "Nuova"} voce</h2><div class="cols">
    ${[["azienda","Azienda"],["contatto","Contatto (email)"],["canale","Canale"],["prossimo_passo","Prossimo passo"],["data_prossimo","Data prossimo passo (AAAA-MM-GG)"],["valore","Valore stimato €"],["fonte","Fonte"],["link","Link"]]
      .map(([k,l]) => `<div><label>${l}</label><input id="p-${k}" value="${esc(p[k] ?? "")}" style="width:100%"></div>`).join("")}
    <div><label>Tipo</label><select id="p-tipo">${["lavoro","cliente","collaborazione"].map(s => `<option ${s===p.tipo?"selected":""}>${s}</option>`).join("")}</select></div></div>
    <label>Note (scopo, condizioni, scadenze, pagamenti attesi)</label><textarea id="p-note" style="min-height:100px">${esc(p.note ?? "")}</textarea>
    <div class="row" style="margin-top:12px"><button id="p-save">Salva</button><button class="sec" onclick="closeModal()">Annulla</button></div>`));
  m.onclick = e => { const t = e.target;
    if (t.id === "nuovo") form();
    if (t.id === "xls") run(t, () => api("/api/export", {}), r => "Salvato: " + r.file);
    if (t.dataset.ed) form(lista.find(x => x.id == t.dataset.ed));
    if (t.dataset.fu) run(t, () => api(`/api/pipeline/${t.dataset.fu}/follow-up`, {}), "Follow-up creato → Da approvare").then(refreshStato);
  };
  m.onchange = e => { if (e.target.dataset.st) api("/api/pipeline", {id: e.target.dataset.st, stato: e.target.value}).then(() => toast("Stato aggiornato")); };
  $("#modal").onclick = e => { if (e.target.id === "p-save") {
    const d = {}; ["azienda","contatto","canale","prossimo_passo","data_prossimo","valore","fonte","link","tipo","note"].forEach(k => d[k] = $("#p-" + k).value);
    if (editId) d.id = editId;
    if (d.valore === "") delete d.valore;
    api("/api/pipeline", d).then(() => { closeModal(); go("pipeline"); }).catch(err => toast(err.message, true)); } };
};

V.crm = async m => {
  const lead = await api("/api/crm/lead");
  const s = STATO.impostazioni;
  const ric = s.ricerche_portali || [];
  m.innerHTML = `<h1>Collegamenti</h1><p class="sub">LinkedIn, Indeed e il gestionale si collegano allo stesso modo: accedi tu <b>una volta</b> nel browser dell'app (anche con verifica in due passaggi) e la sessione resta salvata. L'app non conosce le tue password.</p>
  <div class="card" style="margin-bottom:16px"><h2 style="margin-top:0">🌐 Il tuo Chrome</h2>
    <p class="small muted" style="margin-top:0">Un Chrome tutto tuo, usato anche dall'app (collegamento "Chrome (Agente Lavoro)" sul Desktop). Accedi con il tuo account Google e attiva la sincronizzazione: ritrovi password salvate, segnalibri e accessi, e da lì ti colleghi a tutto ciò che serve.</p>
    <div class="row" style="margin:0"><button id="chrome">🌐 Apri il mio Chrome</button><button class="sec" id="google">🔑 Collega account Google</button></div></div>
  <div class="card" style="margin-bottom:16px"><div class="row" style="margin:0">
    <span id="st-linkedin" class="tag">LinkedIn: ?</span><span id="st-indeed" class="tag">Indeed: ?</span><span id="st-gestionale" class="tag">Gestionale: ?</span>
    <button class="sec sm" id="verifica">🔄 Verifica collegamenti</button></div></div>
  <div class="cols">
   <div class="card"><h2 style="margin-top:0">in LinkedIn</h2>
    <div class="row"><button data-colleg="linkedin">🔗 Collega / apri</button></div>
    <label>Cerca e importa annunci (remoto e ibrido, Italia, ultimi 3 giorni)</label>
    <div class="row">${ric.map(r => `<button class="sec sm" data-cerca="linkedin" data-parole="${esc(r)}">${esc(r)}</button>`).join("")}</div></div>
   <div class="card"><h2 style="margin-top:0">Indeed</h2>
    <div class="row"><button data-colleg="indeed">🔗 Collega / apri</button></div>
    <label>Cerca e importa annunci (da remoto, Italia, ultimi 3 giorni)</label>
    <div class="row">${ric.map(r => `<button class="sec sm" data-cerca="indeed" data-parole="${esc(r)}">${esc(r)}</button>`).join("")}</div></div>
  </div>
  <div class="card" style="margin-top:16px"><div class="row" style="margin:0"><button id="importa">📥 Importa annunci dalla pagina LinkedIn/Indeed aperta</button>
    <span class="small muted">Gli annunci importati compaiono in Opportunità lavoro: premi "🧠 Analizza" per leggerli per intero e valutarli con l'AI. Messaggi e candidature su LinkedIn/Indeed restano manuali (le bozze sono in Da approvare).</span></div></div>
  <h2>Gestionale gasparepettinati.it</h2>
  <div class="cols"><div class="card">
    <div class="row"><button id="login">🔗 Collega / apri il gestionale</button><button class="sec" id="leggi">📥 Leggi tabelle della pagina aperta</button></div>
    <div id="menu" class="small"></div></div>
   <div class="card"><h2 style="margin-top:0">Browser</h2>
    <div class="row"><input id="url" placeholder="https://…" style="flex:1"><button id="apri">Apri</button></div>
    <div class="row"><button id="anal">🧠 Analizza annuncio nella pagina aperta</button><button class="sec" id="chiudi">Stacca l'app dal browser</button></div>
    <p class="small muted">Apri un annuncio su LinkedIn/Indeed/InfoJobs (con il tuo login), poi "Analizza": l'AI locale estrae dati e punteggio e lo aggiunge alle opportunità.</p></div></div>
  <h2>Dati letti dal gestionale (${lead.length})</h2>
  <table><thead><tr><th>Letto</th><th>Dati</th></tr></thead><tbody>
  ${lead.map(l => { const d = JSON.parse(l.dati); return `<tr><td class="small">${dt(l.letto)}</td><td class="small">${Object.entries(d).map(([k,v]) => `<b>${esc(k)}:</b> ${esc(v)}`).join(" · ")}</td></tr>`; }).join("") ||
   `<tr><td colspan="2" class="muted">Ancora nulla. Accedi, apri la pagina dei lead/contatti e premi "Leggi tabelle".</td></tr>`}</tbody></table>`;
  const showMenu = r => { if (r?.menu?.length) $("#menu").innerHTML = "<p class='muted'>Sezioni trovate — clic per aprire e leggere:</p>" + r.menu.map(x => `<button class="sm sec" data-read="${esc(x.url)}">${esc(x.testo)}</button>`).join(" "); };
  const mostraStato = st => { for (const [k, v] of Object.entries(st || {})) { const el = $("#st-" + k); if (el) { el.textContent = `${k[0].toUpperCase() + k.slice(1)}: ${v ? "collegato ✅" : "non collegato"}`; el.style.color = v ? "var(--ok)" : "var(--muted)"; } } };
  $("#chrome").onclick = e => run(e.target, () => api("/api/browser/avvia", {}), "Chrome aperto");
  $("#google").onclick = e => run(e.target, () => api("/api/browser/google", {}), r => r.messaggio);
  $("#verifica").onclick = e => run(e.target, () => api("/api/portali/stato", {})).then(mostraStato);
  $("#importa").onclick = e => run(e.target, () => api("/api/portali/importa", {}), r => `${r.portale}: ${r.nuovi} nuovi annunci su ${r.letti}`);
  m.addEventListener("click", e => { const t = e.target;
    if (t.dataset.colleg) run(t, () => api(`/api/portali/${t.dataset.colleg}/collega`, {}), r => r.collegato ? "Già collegato ✅" : r.messaggio);
    if (t.dataset.cerca) run(t, () => api(`/api/portali/${t.dataset.cerca}/cerca`, {parole: t.dataset.parole}), r => `${r.portale}: ${r.nuovi} nuovi annunci su ${r.letti}`);
  });
  $("#login").onclick = e => run(e.target, () => api("/api/crm/login", {}), r => r.collegato ? "Gestionale collegato ✅" : r.messaggio).then(showMenu);
  $("#leggi").onclick = e => run(e.target, () => api("/api/crm/leggi", {}), r => `${r.tabelle.length} tabelle lette`).then(r => { showMenu(r); go("crm"); });
  $("#apri").onclick = e => { let u = $("#url").value.trim(); if (!/^https?:/.test(u)) u = "https://" + u; run(e.target, () => api("/api/browser/apri", {url: u})); };
  $("#anal").onclick = e => run(e.target, () => api("/api/browser/analizza", {}), r => `Annuncio aggiunto: ${r.ruolo} — punteggio ${r.punteggio}`);
  $("#chiudi").onclick = e => run(e.target, () => api("/api/browser/chiudi", {}));
  m.onclick = e => { if (e.target.dataset.read) run(e.target, () => api("/api/crm/leggi", {url: e.target.dataset.read}), r => `${r.tabelle?.length ?? 0} tabelle lette`).then(() => go("crm")); };
};

// ------------------------------------------------------------------ progetti GitHub
// pulsante a due tempi: il primo clic chiede conferma, il secondo esegue
function conferma2(btn, testo, fn) {
  if (btn.dataset.armed) { delete btn.dataset.armed; return fn(); }
  const orig = btn.innerHTML; btn.dataset.armed = "1"; btn.innerHTML = "⚠️ " + testo;
  setTimeout(() => { if (btn.dataset.armed) { delete btn.dataset.armed; btn.innerHTML = orig; } }, 6000);
}
const GRAV = {critico: ["🔴", "var(--bad)"], personale: ["🟠", "var(--warn)"], avviso: ["⚪", "var(--muted)"]};
const esito = a => !a || a.n_file == null ? '<span class="tag">da analizzare</span>'
  : a.ok_pubblico ? '<span class="tag" style="color:var(--ok)">✅ pronto anche per pubblico</span>'
  : a.ok_privato ? '<span class="tag" style="color:var(--warn)">🟠 solo privato (dati personali)</span>'
  : '<span class="tag" style="color:var(--bad)">🔴 bloccato</span>';

V.progetti = async m => {
  const {progetti: lista, github} = await api("/api/progetti");
  m.innerHTML = `<h1>Progetti GitHub</h1><p class="sub">Carica lo ZIP di un progetto: l'app controlla segreti (password, chiavi, token), dati personali e file sensibili.
    Se spunti <b>Pulisci</b> li toglie lei. Il repository nasce <b>privato</b>; diventa pubblico solo con la tua conferma e se il controllo è pulito.</p>
  <div class="card" style="margin-bottom:16px">
    <div class="row"><span class="tag" style="color:${github.collegato ? "var(--ok)" : "var(--bad)"}">GitHub: ${github.collegato ? "collegato come " + esc(github.account) + " ✅" : "non collegato"}</span>
      ${github.collegato ? "" : `<span class="small muted">Apri un terminale e lancia <code>gh auth login --web</code>, poi ricarica questa pagina.</span>`}</div>
    <div class="row" style="margin:0"><input type="file" id="zip" accept=".zip,application/zip">
      <label style="margin:0;font-size:14px;color:var(--ink)"><input type="checkbox" id="pul"> 🧹 <b>Pulisci</b> (toglie segreti, dati personali, .env, database, log, node_modules…)</label>
      <button id="up">⬆️ Carica e controlla</button></div>
    <p class="small muted" style="margin-bottom:0">Lo ZIP resta sul PC (in ${esc(STATO.cartella_dati)}\\progetti). La cronologia git dentro lo ZIP non viene mai caricata.</p></div>
  <table><thead><tr><th>Progetto</th><th>Caricato</th><th>File</th><th>Controllo</th><th>GitHub</th><th></th></tr></thead><tbody>
  ${lista.map(p => { const a = p.riassunto || {}; return `<tr><td><b>${esc(p.nome)}</b><div class="small muted">${esc(p.file_zip)}${p.pulisci ? " · 🧹 pulito" : ""}</div></td>
    <td class="small">${dt(p.caricato)}</td><td class="small">${a.n_file ?? "–"} file<br>${a.peso_mb ?? "–"} MB</td>
    <td>${esito(a)}<div class="small muted">🔴 ${a.n_critici ?? 0} · 🟠 ${a.n_personali ?? 0} · ⚪ ${a.n_avvisi ?? 0}</div></td>
    <td class="small">${p.repo ? `<a href="${esc(p.repo.url)}" target="_blank">${esc(p.repo.nome)}</a><br>${p.repo.pubblico ? "🌍 pubblico" : "🔒 privato"}` : "–"}</td>
    <td><button class="sm" data-apri="${esc(p.slug)}">Apri</button></td></tr>`; }).join("") ||
    `<tr><td colspan="6" class="muted">Nessun progetto. Fai uno ZIP della cartella del progetto e caricalo qui sopra.</td></tr>`}</tbody></table>`;

  $("#up").onclick = e => {
    const f = $("#zip").files[0];
    if (!f) return toast("Scegli prima un file .zip", true);
    run(e.target, async () => {
      const r = await fetch(`/api/progetti/carica?nome=${encodeURIComponent(f.name)}&pulisci=${$("#pul").checked ? 1 : 0}`,
        {method: "POST", headers: {"X-Token": window.TOKEN, "Content-Type": "application/zip"}, body: f});
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || `Errore ${r.status}`);
      return d;
    }, "Caricato e controllato").then(d => { if (d) { go("progetti").then(() => dettaglioProgetto(d)); } });
  };
  m.addEventListener("click", e => { const s = e.target.dataset.apri; if (s) api(`/api/progetti/${encodeURIComponent(s)}`).then(dettaglioProgetto).catch(err => toast(err.message, true)); });
};

function dettaglioProgetto(p) {
  const a = p.analisi || {}, pz = p.pulizia, r = p.repo;
  const trovati = (a.trovati || []).filter(t => t.gravita !== "avviso"), avvisi = (a.trovati || []).filter(t => t.gravita === "avviso");
  const riga = t => `<tr><td>${GRAV[t.gravita][0]}</td><td class="small">${esc(t.tipo)}</td><td class="small"><code>${esc(t.file)}</code>:${t.riga}</td><td class="small"><code>${esc(t.anteprima)}</code></td></tr>`;
  modal(`<h2 style="margin-top:0">📦 ${esc(p.nome)}</h2>
   <div class="row">${esito(a)}<span class="tag">${a.n_file ?? 0} file · ${a.peso_mb ?? 0} MB</span>
     <span class="tag">🔴 ${a.n_critici ?? 0} critici</span><span class="tag">🟠 ${a.n_personali ?? 0} dati personali</span><span class="tag">⚪ ${a.n_avvisi ?? 0} avvisi</span></div>
   ${pz ? `<div class="card" style="margin-bottom:10px"><b>🧹 Pulizia fatta</b> — ${pz.rimossi.length} file/cartelle tolti, ${pz.sostituiti.reduce((n, x) => n + x.sostituzioni, 0)} valori sostituiti con <code>***RIMOSSO***</code> in ${pz.sostituiti.length} file${pz.env_example.length ? `, creati ${pz.env_example.map(esc).join(", ")}` : ""}.
     <details><summary class="small">Dettaglio</summary><div class="small"><b>Tolti:</b> ${pz.rimossi.map(x => `<code>${esc(x)}</code>`).join(" ") || "nessuno"}<br>
     <b>Modificati:</b> ${pz.sostituiti.map(x => `<code>${esc(x.file)}</code> (${x.sostituzioni})`).join(" ") || "nessuno"}</div></details></div>` : ""}
   ${(a.sensibili || []).length ? `<div class="warnbox">File sensibili che verrebbero caricati: ${a.sensibili.map(esc).join(", ")}</div>` : ""}
   ${(a.grandi || []).length ? `<div class="warnbox">File oltre 95 MB (GitHub li rifiuta): ${a.grandi.map(esc).join(", ")}</div>` : ""}
   ${trovati.length ? `<h2>Da sistemare</h2><table><tbody>${trovati.slice(0, 200).map(riga).join("")}</tbody></table>` : `<p style="color:var(--ok)">✅ Nessun segreto né dato personale nei file da caricare.</p>`}
   ${avvisi.length ? `<details><summary class="small">⚪ ${avvisi.length} avvisi (email di lavoro, indirizzi IP): controlla che vadano bene</summary><table><tbody>${avvisi.slice(0, 200).map(riga).join("")}</tbody></table></details>` : ""}
   <details><summary class="small">📄 File che verrebbero caricati (${a.n_file ?? 0})</summary><pre class="small" style="max-height:220px;overflow:auto">${(a.file || []).map(esc).join("\n")}</pre></details>
   <div class="row" style="margin-top:12px"><label style="margin:0;font-size:14px;color:var(--ink)"><input type="checkbox" id="d-pul" ${p.pulisci ? "checked" : ""}> 🧹 Pulisci</label>
     <button class="sec" id="d-ana">🔄 Rianalizza</button><button class="sec" id="d-dir">📂 Apri cartella</button>
     <span class="small muted">Puoi correggere i file a mano nella cartella e poi premere Rianalizza.</span></div>
   ${r ? `<div class="card"><b>GitHub:</b> <a href="${esc(r.url)}" target="_blank">${esc(r.url)}</a> — ${r.pubblico ? "🌍 pubblico" : "🔒 privato"}
       ${r.pubblico ? "" : `<div class="row" style="margin:10px 0 0"><button id="d-pubb" ${a.ok_pubblico ? "" : "disabled"}>🌍 Rendi pubblico</button>
       ${a.ok_pubblico ? "" : `<span class="small muted">Prima togli i dati personali (attiva Pulisci e Rianalizza).</span>`}</div>`}</div>`
   : `<div class="card"><h2 style="margin-top:0">⬆️ Pubblica su GitHub</h2>
       <label>Nome del repository</label><input id="d-nome" value="${esc(p.slug)}" style="width:100%">
       <label>Descrizione</label><input id="d-desc" value="${esc(p.nome)}" style="width:100%">
       <label style="font-size:14px;color:var(--ink)"><input type="radio" name="vis" value="0" checked> 🔒 Privato (consigliato: lo rendi pubblico dopo)</label>
       <label style="font-size:14px;color:var(--ink)"><input type="radio" name="vis" value="1" ${a.ok_pubblico ? "" : "disabled"}> 🌍 Pubblico ${a.ok_pubblico ? "" : "— non disponibile: ci sono dati personali o segreti"}</label>
       <div class="row" style="margin-top:10px"><button id="d-pub" ${a.ok_privato ? "" : "disabled"}>⬆️ Pubblica su GitHub</button>
       ${a.ok_privato ? "" : `<span class="small" style="color:var(--bad)">Bloccato: attiva Pulisci e premi Rianalizza, oppure correggi i file.</span>`}</div></div>`}
   <div class="row" style="margin-top:12px;justify-content:space-between"><button class="sec sm" id="d-del">🗑️ Elimina copia locale</button><button class="sec" onclick="closeModal()">Chiudi</button></div>`);
  const slug = encodeURIComponent(p.slug), box = $("#modal-box");
  const ricarica = d => go("progetti").then(() => dettaglioProgetto(d));
  $("#d-ana", box).onclick = e => run(e.target, () => api(`/api/progetti/${slug}/prepara`, {pulisci: $("#d-pul").checked}), "Analisi aggiornata").then(d => d && ricarica(d));
  $("#d-dir", box).onclick = e => run(e.target, () => api(`/api/progetti/${slug}/cartella`, {}));
  $("#d-del", box).onclick = e => conferma2(e.target, "Elimino la copia nell'app (GitHub non viene toccato). Clicca di nuovo",
    () => run(e.target, () => api(`/api/progetti/${slug}`, undefined, "DELETE"), "Copia locale eliminata").then(() => { closeModal(); go("progetti"); }));
  const pub = $("#d-pub", box);
  if (pub) pub.onclick = e => {
    const pubblico = box.querySelector('input[name=vis]:checked').value === "1";
    conferma2(e.target, `Carico su GitHub come ${pubblico ? "PUBBLICO" : "privato"}? Clicca di nuovo per confermare`,
      () => run(e.target, () => api(`/api/progetti/${slug}/pubblica`, {conferma: true, pubblico, nome_repo: $("#d-nome").value, descrizione: $("#d-desc").value}),
        d => "Pubblicato: " + d.repo.url).then(d => d && ricarica(d)));
  };
  const pubb = $("#d-pubb", box);
  if (pubb) pubb.onclick = e => conferma2(e.target, "Diventa visibile a tutti. Clicca di nuovo per confermare",
    () => run(e.target, () => api(`/api/progetti/${slug}/rendi-pubblico`, {conferma: true}), "Ora è pubblico 🌍").then(d => d && ricarica(d)));
}

V.impostazioni = async m => {
  await refreshStato(); const s = STATO.impostazioni, c = STATO.credenziali;
  m.innerHTML = `<h1>Impostazioni</h1><p class="sub">Dati salvati in <code>${esc(STATO.cartella_dati)}</code>. Le credenziali vanno nel Gestore credenziali di Windows (cifrate), mai su file.</p>
  <div class="cols">
   <div class="card"><h2 style="margin-top:0">🔐 Credenziali</h2>
    ${Object.entries(c).map(([k,v]) => `<label>${esc(v.label)} ${v.impostato ? "✅" : "❌"}</label>
      <input id="c-${k}" type="${k.includes("password") ? "password" : "text"}" value="${esc(v.valore)}" placeholder="${v.impostato && k.includes("password") ? "•••••••• (salvata — scrivi per sostituire)" : ""}" style="width:100%" autocomplete="off">`).join("")}
    <div class="row" style="margin-top:12px"><button id="save-c">Salva credenziali</button></div>
    <p class="small muted">Per l'email conviene una "password per app" o una casella con permessi limitati.</p></div>
   <div class="card"><h2 style="margin-top:0">🛡️ Sicurezza invii</h2>
    <label><input type="checkbox" id="s-auto" ${STATO.avvio_automatico ? "checked" : ""}> Avvia con Windows (all'accensione del PC)</label>
    <label>Max nuovi contatti PMI al giorno</label><input id="s-max_pmi_giorno" type="number" value="${s.max_pmi_giorno}">
    <label>Soglia punteggio annunci</label><input id="s-soglia_annunci" type="number" step="0.5" value="${s.soglia_annunci}">
    <label>Giorni prima del follow-up</label><input id="s-follow_up_giorni" type="number" value="${s.follow_up_giorni}">
    <h2>🧠 Modello AI locale</h2>
    <label>Modello Ollama</label><select id="s-modello">${(STATO.modelli.length ? STATO.modelli : [s.modello]).map(x => `<option ${x===s.modello?"selected":""}>${esc(x)}</option>`).join("")}</select>
    <label>Indirizzo Ollama</label><input id="s-ollama_url" value="${esc(s.ollama_url)}" style="width:100%"></div>
   <div class="card"><h2 style="margin-top:0">📬 Server posta</h2>
    ${[["imap_host","Server IMAP"],["imap_port","Porta IMAP"],["smtp_host","Server SMTP"],["smtp_port","Porta SMTP"],["cartella_bozze","Cartella bozze"]].map(([k,l]) => `<label>${l}</label><input id="s-${k}" value="${esc(s[k])}" style="width:100%">`).join("")}
    <h2>🌐 Gestionale & browser</h2>
    <label>Pagina di login</label><input id="s-crm_url_login" value="${esc(s.crm_url_login)}" style="width:100%">
    <label>Pagina lead/contatti</label><input id="s-crm_url_lead" value="${esc(s.crm_url_lead)}" style="width:100%">
    <label>Browser</label><select id="s-browser_canale">${["chrome","msedge"].map(x => `<option ${x===s.browser_canale?"selected":""}>${x}</option>`).join("")}</select>
    <h2>🔗 LinkedIn · Indeed</h2>
    <label>Ricerche (separate da virgola)</label><textarea id="s-ricerche_portali" style="min-height:60px">${esc((s.ricerche_portali || []).join(", "))}</textarea>
    <label><input type="checkbox" id="s-portali_auto" ${s.portali_auto ? "checked" : ""}> Ogni mattina importa da LinkedIn, Indeed e gestionale (solo se collegati; apre Chrome per qualche minuto)</label></div>
   <div class="card"><h2 style="margin-top:0">👤 Profilo (fonte di verità per le bozze)</h2>
    <label>Posizionamento</label><input id="s-headline" value="${esc(s.headline)}" style="width:100%">
    <label>Firma</label><input id="s-firma" value="${esc(s.firma)}" style="width:100%">
    <label>Competenze (separate da virgola)</label><textarea id="s-competenze" style="min-height:70px">${esc(s.competenze.join(", "))}</textarea>
    <label>Forme di collaborazione</label><textarea id="s-contratti" style="min-height:60px">${esc(s.contratti.join(", "))}</textarea>
    <label>Parole chiave annunci</label><textarea id="s-parole_chiave" style="min-height:60px">${esc(s.parole_chiave.join(", "))}</textarea>
    <label>Progetti vetrina (uno per riga: nome | tema | link)</label><textarea id="s-progetti" style="min-height:100px">${esc(s.progetti_vetrina.map(p => `${p.nome} | ${p.tema} | ${p.link || ""}`).join("\n"))}</textarea>
    <h2>🗓️ Routine quotidiana (lun-ven)</h2>
    <label>Una voce per riga: ora | attività | sezione (home, bozze, posta, lavoro, pmi, pipeline, crm — facoltativa)</label>
    <textarea id="s-routine" style="min-height:200px">${esc((s.routine || []).map(r => `${r.ora} | ${r.titolo}${r.vista ? " | " + r.vista : ""}`).join("\n"))}</textarea>
    <h2>⏰ Orari</h2>
    <label>Ricerca annunci</label><input id="s-ricerca_lavoro_ora" value="${esc(s.ricerca_lavoro_ora)}">
    <label>Report mattino / sera</label><input id="s-report_mattino" value="${esc(s.report_mattino)}"> <input id="s-report_sera" value="${esc(s.report_sera)}">
   </div></div>
  <div class="row" style="margin-top:16px"><button id="save-s">💾 Salva impostazioni</button></div>`;
  $("#s-auto").onchange = e => run(null, () => api("/api/avvio-automatico", {attivo: e.target.checked}),
    r => r.attivo ? "Partirà all'accensione del PC" : "Avvio automatico disattivato");
  $("#save-c").onclick = e => { const d = {}; Object.keys(c).forEach(k => { const v = $("#c-" + k).value; if (v !== "" || !k.includes("password")) d[k] = v; });
    run(e.target, () => api("/api/credenziali", d), "Credenziali salvate nel Gestore credenziali di Windows").then(() => go("impostazioni")); };
  $("#save-s").onclick = e => {
    const lst = id => $(id).value.split(",").map(x => x.trim()).filter(Boolean);
    const d = {max_pmi_giorno: +$("#s-max_pmi_giorno").value, soglia_annunci: +$("#s-soglia_annunci").value,
      follow_up_giorni: +$("#s-follow_up_giorni").value, modello: $("#s-modello").value, ollama_url: $("#s-ollama_url").value,
      imap_host: $("#s-imap_host").value, imap_port: +$("#s-imap_port").value, smtp_host: $("#s-smtp_host").value, smtp_port: +$("#s-smtp_port").value,
      cartella_bozze: $("#s-cartella_bozze").value, crm_url_login: $("#s-crm_url_login").value, crm_url_lead: $("#s-crm_url_lead").value,
      browser_canale: $("#s-browser_canale").value, ricerche_portali: lst("#s-ricerche_portali"), portali_auto: $("#s-portali_auto").checked, headline: $("#s-headline").value, firma: $("#s-firma").value,
      competenze: lst("#s-competenze"), contratti: lst("#s-contratti"), parole_chiave: lst("#s-parole_chiave"),
      progetti_vetrina: $("#s-progetti").value.split("\n").filter(x => x.trim()).map(r => { const [nome, tema, link] = r.split("|").map(x => (x || "").trim()); return {nome, tema, link}; }),
      routine: $("#s-routine").value.split("\n").filter(x => x.trim()).map(r => { const [ora, titolo, vista] = r.split("|").map(x => (x || "").trim()); return titolo ? {ora, titolo, vista: vista || ""} : {ora: "", titolo: ora, vista: ""}; }),
      ricerca_lavoro_ora: $("#s-ricerca_lavoro_ora").value, report_mattino: $("#s-report_mattino").value, report_sera: $("#s-report_sera").value};
    run(e.target, () => api("/api/impostazioni", d), "Impostazioni salvate").then(refreshStato);
  };
};

V.registro = async m => {
  const ev = await api("/api/eventi");
  m.innerHTML = `<h1>Registro attività</h1><p class="sub">Tutto ciò che l'app ha fatto (senza password né dati sensibili).</p>
  <table><thead><tr><th>Quando</th><th>Modulo</th><th>Evento</th></tr></thead><tbody>
  ${ev.map(e => `<tr><td class="small" style="white-space:nowrap">${dt(e.quando)}</td><td><span class="tag">${esc(e.modulo)}</span></td>
    <td class="small" style="${e.livello === "errore" ? "color:var(--bad)" : ""}">${esc(e.messaggio)}</td></tr>`).join("")}</tbody></table>`;
};

// ------------------------------------------------------------------ navigazione
async function go(v) {
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.v === v));
  // contenitore nuovo a ogni vista: i listener della vista precedente spariscono con lui
  const host = $("#main"); host.innerHTML = "";
  const m = document.createElement("div"); host.appendChild(m);
  m.innerHTML = '<p class="muted"><span class="spin"></span> Caricamento…</p>';
  try { if (!STATO) await refreshStato(); await V[v](m); } catch (e) { m.innerHTML = `<div class="warnbox">${esc(e.message)}</div>`; }
}
window.go = go; window.closeModal = closeModal;
$("#nav").onclick = e => { const a = e.target.closest("a"); if (a) go(a.dataset.v); };
go("home");
setInterval(() => refreshStato().catch(() => {}), 60000);
// promemoria: quando arriva l'ora di un'attività non ancora fatta
const avvisate = new Set();
setInterval(async () => {
  const ora = new Date().toTimeString().slice(0, 5);
  try {
    for (const a of await aggiornaBadgeTodo()) {
      if (!a.fatto && a.ora === ora && !avvisate.has(a.id)) { avvisate.add(a.id); toast(`⏰ ${a.ora} — ${a.titolo}`); }
    }
  } catch {}
}, 30000);
aggiornaBadgeTodo().catch(() => {});
