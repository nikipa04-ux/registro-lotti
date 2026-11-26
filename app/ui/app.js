/* Registro Lotti - client.
   L'UI è "stupida" di proposito: chiede i dati alle API e li mostra.
   Nessuna regola di business qui: scadenze, contatori, colori, totali,
   validazioni arrivano dal server (app/logic). Qui c'è solo navigazione
   e rendering. */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n) => Number(n).toLocaleString("it-IT", { maximumFractionDigits: 3 });
const eur = (n) => n == null ? "—" : n.toFixed(2).replace(".", ",") + "\u00A0€";

// Oggi, come lo conosce il SERVER (non l'orologio del browser)
let OGGI = new Date().toISOString().slice(0, 10);

// Badge della scadenza: il server riporta i giorni, qui si colora e basta.
// (Rappresentazione: la REGOLA di quali lotti contare sta nel server.)
function badgeScadenza(riga) {
  const g = riga.giorni;
  if (g < 0) return '<span class="badge b-gray">scaduto</span>';
  if (g <= 3) return '<span class="badge b-red">' + esc(riga.scadenza || riga.data_scadenza) + ' · ' + g + 'g</span>';
  if (g <= 7) return '<span class="badge b-amber">' + esc(riga.scadenza || riga.data_scadenza) + ' · ' + g + 'g</span>';
  return '<span class="badge b-green">' + esc(riga.scadenza || riga.data_scadenza) + '</span>';
}

function consBadge(c) {
  return '<span class="badge b-gray">🧊 ' + esc(c || "Da sistemare") + '</span>';
}

/* ===================== Navigazione a sezioni ===================== */

const sezioniCaricate = {};

function mostraSezione(nome) {
  document.querySelectorAll("main section").forEach(s => { s.hidden = s.id !== "sez-" + nome; });
  document.querySelectorAll("nav button[data-sez]").forEach(b =>
    b.classList.toggle("active", b.dataset.sez === nome));
  if (!sezioniCaricate[nome]) {
    sezioniCaricate[nome] = true;
    if (nome === "arrivi") avviaArrivi();
    if (nome === "scadenze") avviaScadenze();
    if (nome === "magazzino") avviaMagazzino();
    if (nome === "produzioni") avviaProduzioni();
    if (nome === "ricette") avviaRicette();
    if (nome === "anagrafiche") avviaAnagrafiche();
    if (nome === "produttore") avviaProduttore();
  }
}

document.querySelectorAll("nav button[data-sez]").forEach(b =>
  b.addEventListener("click", () => mostraSezione(b.dataset.sez)));

/* ========================= Dashboard ========================= */

function renderStats(stats) {
  $("stats").innerHTML =
    '<div class="stat"><div class="n" style="color:var(--red)">' + stats.scadenze_critiche + '</div>' +
    '<div class="l">Scadenze critiche (≤3 giorni)</div></div>' +
    '<div class="stat"><div class="n">' + stats.arrivi_settimana + '</div>' +
    '<div class="l">Arrivi ultima settimana</div></div>' +
    '<div class="stat"><div class="n">' + stats.produzioni + '</div>' +
    '<div class="l">Produzioni registrate</div></div>';
}

function renderScadenze(righe) {
  if (!righe.length) {
    $("tabella-scadenze").innerHTML =
      '<table><tr><td class="empty">Nessuna scadenza imminente: tutto in ordine.</td></tr></table>';
    return;
  }
  const corpo = righe.map(r =>
    "<tr><td><b>" + esc(r.prodotto) + "</b><br><span class='mono'>" + esc(r.lotto) + "</span></td>" +
    "<td>" + esc(r.fornitore) + "</td>" +
    '<td class="td-scad">' + badgeScadenza(r) + "</td></tr>").join("");
  $("tabella-scadenze").innerHTML =
    "<table><tr><th>Prodotto</th><th>Origine</th><th>Scadenza</th></tr>" + corpo + "</table>";
}

async function caricaDashboard() {
  const conn = $("conn");
  try {
    const risposta = await fetch("/api/dashboard");
    if (!risposta.ok) throw new Error("HTTP " + risposta.status);
    const dati = await risposta.json();
    conn.textContent = "server attivo";
    conn.className = "conn ok";
    OGGI = dati.oggi;
    const oggi = new Date(dati.oggi + "T12:00:00");
    $("sub-oggi").textContent = "Oggi è " +
      oggi.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    renderStats(dati.stats);
    renderScadenze(dati.in_scadenza);
  } catch (e) {
    conn.textContent = "server non raggiungibile (avvia avvia.bat e ricarica)";
    conn.className = "conn err";
    $("tabella-scadenze").innerHTML =
      '<div class="loading">Il server non risponde sulla porta 8000.</div>';
  }
}

/* =========================== Arrivi =========================== */

let INGREDIENTI = [];   // pool per combo + filtri (famiglia NULL = ingrediente)
let FORNITORI = [];
let PRODOTTI_LAB = [];  // prodotti di laboratorio (con famiglia)
let PRODUCIBILI = [];   // prodotti CON ricetta: solo loro si possono produrre

async function caricaAnagrafiche() {
  const [ing, forn, lab] = await Promise.all([
    fetch("/api/anagrafiche/prodotti?ingrediente=true"),
    fetch("/api/anagrafiche/fornitori"),
    fetch("/api/anagrafiche/prodotti?ingrediente=false"),
  ]);
  if (!ing.ok || !forn.ok || !lab.ok) throw new Error("anagrafiche non raggiungibili");
  INGREDIENTI = await ing.json();
  FORNITORI = await forn.json();
  PRODOTTI_LAB = await lab.json();
}

async function avviaArrivi() {
  try {
    await caricaAnagrafiche();
  } catch (e) {
    $("tabella-arrivi").innerHTML = '<div class="loading">Il server non risponde.</div>';
    return;
  }
  popolaFiltriArrivi();
  caricaArrivi();
}

function popolaFiltriArrivi() {
  $("fil-ingrediente").innerHTML = '<option value="0">Tutti gli ingredienti</option>' +
    INGREDIENTI.map(p => '<option value="' + p.id + '">' + esc(p.nome) + '</option>').join("");
  $("fil-fornitore").innerHTML = '<option value="0">Tutti i fornitori</option>' +
    FORNITORI.map(f => '<option value="' + f.id + '">' + esc(f.nome) + '</option>').join("");
}

/* -------- Lista con filtri a cascata (come la demo) -------- */

function renderArrivi(dati) {
  $("contatore-arrivi").textContent = dati.n_filtrati + " di " + dati.n_totale + " arrivi";
  if (!dati.righe.length) {
    $("tabella-arrivi").innerHTML =
      '<table><tr><td class="empty">Nessun arrivo corrisponde ai filtri.</td></tr></table>';
    return;
  }
  const corpo = dati.righe.map(r => {
    const marca = r.marca_effettiva
      ? '<span class="badge b-gray">🏷 ' + esc(r.marca_effettiva) + '</span>' : "—";
    const prezzi = r.prezzo_unitario == null
      ? "<td class='num'>—</td><td class='num'>—</td><td class='num'>—</td><td class='num'>—</td>"
      : "<td class='num'>" + eur(r.prezzo_unitario) + "</td>" +
        "<td class='num'>" + eur(r.totale) + "</td>" +
        "<td class='num'><span class='badge b-gray'>" + fmt(r.iva) + "%</span></td>" +
        "<td class='num'><b>" + eur(r.totale_iva) + "</b></td>";
    return '<tr data-id="' + r.id + '">' +
      "<td><b>" + esc(r.prodotto) + "</b></td>" +
      "<td>" + marca + "</td>" +
      "<td class='mono'>" + esc(r.codice_lotto) + "</td>" +
      "<td>" + esc(r.fornitore) + "</td>" +
      "<td>" + esc(r.data_arrivo) + "</td>" +
      '<td class="td-scad">' + badgeScadenza(r) + "</td>" +
      "<td>" + fmt(r.quantita) + "\u00A0" + esc(r.um || "") + "</td>" +
      prezzi + "</tr>";
  }).join("");
  $("tabella-arrivi").innerHTML =
    "<table><tr><th>Prodotto</th><th>Marca</th><th>Lotto</th><th>Fornitore</th>" +
    "<th>Arrivo</th><th>Scadenza</th><th>Q.tà</th>" +
    "<th class='num'>Prezzo unit.</th><th class='num'>Totale</th><th class='num'>IVA</th>" +
    "<th class='num'>Totale + IVA</th></tr>" + corpo + "</table>";
  document.querySelectorAll("#tabella-arrivi tr[data-id]").forEach(tr =>
    tr.addEventListener("click", () => apriDettaglioArrivo(Number(tr.dataset.id))));
}

async function caricaArrivi() {
  try {
    const p = new URLSearchParams({
      testo: $("cerca-arrivi").value.trim(),
      fornitore_id: $("fil-fornitore").value,
      prodotto_id: $("fil-ingrediente").value,
      finestra: $("fil-scadenza").value,
    });
    const risposta = await fetch("/api/arrivi?" + p);
    if (!risposta.ok) throw new Error("HTTP " + risposta.status);
    renderArrivi(await risposta.json());
  } catch (e) {
    $("tabella-arrivi").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
}

let timerRicerca = null;
$("cerca-arrivi").addEventListener("input", () => {
  clearTimeout(timerRicerca);
  timerRicerca = setTimeout(caricaArrivi, 250);
});
["fil-fornitore", "fil-ingrediente", "fil-scadenza"].forEach(id =>
  $(id).addEventListener("change", caricaArrivi));

/* -------- Dettaglio lotto in ingresso (tracciabilità) -------- */

async function apriDettaglioArrivo(id) {
  $("dettaglio-arrivo").hidden = false;
  $("dettaglio-arrivo-testo").innerHTML = '<div class="loading">carico i dati…</div>';
  $("dettaglio-arrivo").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const risposta = await fetch("/api/arrivi/" + id);
    if (!risposta.ok) throw new Error("HTTP " + risposta.status + " dal server.");
    const dati = await risposta.json();
    if (dati.errore) throw new Error(dati.errore);
    if (!dati.lotto || !dati.usato_in)
      throw new Error("Il server risponde con un formato vecchio: chiudi la " +
        "finestra del server e riavvialo con avvia.bat, poi ricarica la pagina.");
    const l = dati.lotto;
    const usato = (dati.usato_in || []).length
      ? "<table><tr><th>Produzione</th><th>Data</th><th>Quantità usata</th></tr>" +
        dati.usato_in.map(u =>
          "<tr><td class='mono'>" + esc(u.codice_lotto) + "</td><td>" + esc(u.data_produzione) +
          "</td><td>" + fmt(u.quantita_usata) + " " + esc(l.um || "") + "</td></tr>").join("") +
        "</table>"
      : "<p class='muted'>Nessuna produzione ha ancora usato questo lotto.</p>";
    $("dettaglio-arrivo-testo").innerHTML =
      "<div class='det-riga'><span>Prodotto</span><b>" + esc(l.prodotto) +
      (l.marca_effettiva ? " · " + esc(l.marca_effettiva) : "") + "</b></div>" +
      "<div class='det-riga'><span>Fornitore</span><b>" + esc(l.fornitore) + "</b></div>" +
      "<div class='det-riga'><span>Lotto fornitore</span><b class='mono'>" + esc(l.codice_lotto) + "</b></div>" +
      "<div class='det-riga'><span>Arrivo</span><b>" + esc(l.data_arrivo) + "</b></div>" +
      "<div class='det-riga'><span>Scadenza</span><b>" + esc(l.data_scadenza) +
      "</b> " + badgeScadenza(l) + "</div>" +
      "<div class='det-riga'><span>Quantità</span><b>" + fmt(l.quantita) + " " + esc(l.um || "") +
      "</b> · rimasti <b>" + fmt(l.quantita_residua) + " " + esc(l.um || "") + "</b></div>" +
      (l.prezzo_unitario != null
        ? "<div class='det-riga'><span>Costo</span><b>€ " + fmt(l.prezzo_unitario) + "/" + esc(l.um || "u.m.") +
          (l.iva != null ? " + IVA " + fmt(l.iva) + "%" : "") + " · totale " + eur(l.totale) +
          " → " + eur(l.totale_iva) + "</b></div>" : "") +
      "<h2 style='margin-top:14px'>Usato in</h2>" + usato +
      "<div class='f-azioni'>" +
      '<button class="btn sec mini rosso" id="arr-elimina">🗑 Elimina</button></div>';
    $("arr-elimina").addEventListener("click", async () => {
      // eliminazione protetta: rifiutata se il lotto è già in un verbale di produzione
      if (!confirm("Eliminare l'arrivo " + l.codice_lotto + " (" + l.prodotto +
        ")? Possibile solo se nessuna produzione lo ha ancora consumato.")) return;
      const r = await fetch("/api/arrivi/" + id, { method: "DELETE" });
      if (r.status === 204) {
        $("dettaglio-arrivo").hidden = true;
        flashArrivi("Arrivo eliminato.");
        caricaArrivi();
        sezioniCaricate.produzioni = false;
        sezioniCaricate.magazzino = false;
        sezioniCaricate.scadenze = false;
        sezioniCaricate.dashboard = false;
      } else {
        const c = await r.json();
        alert(typeof c.detail === "string" ? c.detail : "Eliminazione rifiutata.");
      }
    });
  } catch (e) {
    $("dettaglio-arrivo-testo").innerHTML = '<div class="loading">' + esc(e.message) + "</div>";
  }
}

$("chiudi-dettaglio").addEventListener("click", () => { $("dettaglio-arrivo").hidden = true; });

/* ============ Combobox con typeahead e creazione rapida ============ */
/* Come la demo: tendina raggruppata (conservazione per gli ingredienti,
   famiglia per i prodotti di laboratorio); se il nome digitato non
   esiste, primo elemento "➕ Crea 'nome'" che apre la creazione rapida. */

const CHIUDI_DD = [];  // funzioni che chiudono le tendine aperte

function creaCombo(cfg) {
  // cfg: {input, tendina, idNascosto, pool(), gruppo(p)->etichetta, hint, onPick, onCrea}
  let aperta = false;
  const chiudi = () => { aperta = false; cfg.tendina.hidden = true; };
  CHIUDI_DD.push(chiudi);

  function renderTendina(q) {
    const testo = q.trim().toLowerCase();
    const pool = cfg.pool();
    const cands = pool.filter(x =>
      !testo || x.nome.toLowerCase().includes(testo) ||
      (x.sigla || "").toLowerCase().includes(testo));
    let html = "";
    const gruppi = {};
    cands.forEach(p => {
      const c = cfg.gruppo ? cfg.gruppo(p) : "Tutti";
      (gruppi[c] = gruppi[c] || []).push(p);
    });
    html += Object.entries(gruppi).map(([cat, ps]) =>
      '<div class="cat">' + esc(cat) + "</div>" +
      ps.map(p =>
        '<div class="it" data-id="' + p.id + '"><span>' + esc(p.nome) + '</span>' +
        '<span class="sig">' + esc(p.sigla || "") + "</span></div>").join("")).join("");
    if (!cands.length) {
      html += '<div class="vuoto">Nessun risultato</div>';
    }
    // REGOLA: il bottone ➕ sta SEMPRE in fondo alla tendina. Qualunque cosa
    // uno abbia digitato, la creazione è a un clic: da qui nascono l'ingrediente,
    // il fornitore, il prodotto o la ricetta mancante.
    if (cfg.onCrea) {
      html += '<div class="new" data-crea="1">' +
        (q.trim() ? '➕ Crea "' + esc(q.trim()) + '"…' : "➕ Crea nuovo…") + "</div>";
    }
    cfg.tendina.innerHTML = html;
    cfg.tendina.querySelectorAll(".it").forEach(el =>
      el.addEventListener("mousedown", (e) => {
        e.preventDefault();
        scegli(Number(el.dataset.id));
      }));
    const crea = cfg.tendina.querySelector(".new");
    if (crea) crea.addEventListener("mousedown", (e) => {
      e.preventDefault();
      chiudi();
      cfg.onCrea(q.trim());
    });
  }

  function scegli(id) {
    const p = cfg.pool().find(x => x.id === id);
    if (!p) return;
    cfg.idNascosto.value = String(id);
    cfg.input.value = p.nome;
    chiudi();
    if (cfg.hint) {
      cfg.hint.innerHTML = cfg.hintTesto(p);
      cfg.hint.hidden = false;
    }
    if (cfg.onPick) cfg.onPick(p);
  }

  cfg.input.addEventListener("input", () => {
    cfg.idNascosto.value = "";      // il testo digitato non è più una scelta
    if (cfg.hint) cfg.hint.hidden = true;
    aperta = true;
    cfg.tendina.hidden = false;
    renderTendina(cfg.input.value);
  });
  cfg.input.addEventListener("focus", () => {
    aperta = true;
    cfg.tendina.hidden = false;
    renderTendina(cfg.input.value);
  });
  cfg.input.addEventListener("blur", () => setTimeout(() => aperta && chiudi(), 150));
  cfg.input.addEventListener("keydown", (e) => { if (e.key === "Escape") chiudi(); });
}

document.addEventListener("mousedown", (e) => {
  if (!e.target.closest(".combo")) CHIUDI_DD.forEach(chiudi => chiudi());
});

/* --------- Form nuovo arrivo (le regole sono del server) -------- */

function apriFormArrivo() {
  $("overlay-arrivo").hidden = false;
  $("na-errore").hidden = true;
  $("qc-prod").hidden = true;
  $("qc-forn").hidden = true;
  ["na-prodotto", "na-fornitore", "na-marca", "na-lotto"].forEach(id => $(id).value = "");
  ["na-prodotto-id", "na-fornitore-id"].forEach(id => $(id).value = "");
  $("hint-prod").hidden = true;
  $("na-um").textContent = "";
  $("na-arrivo").value = OGGI;      // default: oggi, come lo vede il server
  ["na-scadenza", "na-quantita", "na-prezzo", "na-iva"].forEach(id => $(id).value = "");
  $("na-prodotto").focus();
}

function chiudiFormArrivo() { $("overlay-arrivo").hidden = true; }

$("btn-nuovo-arrivo").addEventListener("click", apriFormArrivo);
$("btn-nuovo-arrivo-dash").addEventListener("click", () => { mostraSezione("arrivi"); apriFormArrivo(); });
$("na-annulla").addEventListener("click", chiudiFormArrivo);
$("overlay-arrivo").addEventListener("click", (e) => { if (e.target === e.currentTarget) chiudiFormArrivo(); });

// La marca dell'anagrafica è solo un DEFAULT: nel lotto consegnato può cambiare
creaCombo({
  input: $("na-prodotto"), tendina: $("dd-prod"),
  idNascosto: $("na-prodotto-id"),
  gruppo: p => "🧊 " + (p.conservazione || "Da sistemare"),
  hint: $("hint-prod"),
  hintTesto: p => consBadge(p.conservazione) + " conservazione abituale di questo ingrediente",
  onPick: (p) => {
    $("na-um").textContent = p.unita_misura ? "(" + p.unita_misura + ")" : "";
    if (!$("na-marca").value && p.marca) $("na-marca").value = p.marca;
  },
  pool: () => INGREDIENTI,
  onCrea: async (nome) => {
    $("qc-prod").hidden = false;
    $("qc-prod-nome").value = nome;
    // RIFIN 53: anche la creazione rapida suggerisce la densità dal nome,
    // con lo stesso hint della modale grande (poi il testo resta tuo)
    $("qc-densita").value = "";
    QC_DENS_AUTO = true;
    $("qc-densita-hint").textContent = "Con la densità puoi scrivere i grammi anche su un liquido in litri. Se lasci il campo vuoto, la prende da sola dalla tabella Densità tipiche.";
    suggerisciDensitaQc();
    // gli allergeni si scelgono subito: se serve, l'elenco si carica ora
    if (!ANAG_ALLERGENI.length) { try { await caricaAllergeni(); } catch (e) { /* chips vuote */ } }
    // RIFIN 43: anche l'u.m. viene dall'anagrafica, con tendina ➕ come in
    // Produzioni: se serve (anagrafiche mai aperte in sessione) la si carica
    if (!UMS.length) {
      try {
        const r = await fetch("/api/anagrafiche/unita-misura");
        if (r.ok) UMS = await r.json();
      } catch (e) { /* tendina con le sole u.m. di sistema */ }
    }
    QC_ALLERGENI = new Set();
    renderChipsAllergeni("qc-chips", QC_ALLERGENI, true);
    $("qc-cons").focus();
  },
});

creaCombo({
  input: $("na-fornitore"), tendina: $("dd-forn"),
  idNascosto: $("na-fornitore-id"),
  gruppo: () => "Tutti i fornitori",
  pool: () => FORNITORI,
  onCrea: (nome) => {
    $("qc-forn").hidden = false;
    $("qc-forn-nome").value = nome;
    $("qc-forn-piva").value = "";
    $("qc-forn-piva").focus();
  },
});

/* RIFIN 43: l'u.m. del nuovo ingrediente prende la stessa tendina delle
   Produzioni (pool completo: sistema + anagrafica + u.m. libere) con ➕
   che crea l'u.m. in Anagrafiche senza lasciare il form Arrivi. */
async function creaUmDaQc(nome) {
  if (!nome) return mostraErroreForm("Inserisci un nome.");
  try {
    const r = await fetch("/api/anagrafiche/unita-misura", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome })
    });
    const corpo = await r.json().catch(() => ({}));
    if (!r.ok) return mostraErroreForm(typeof corpo.detail === "string" ? corpo.detail : "Creazione rifiutata.");
    UMS.push(corpo);
    if (ANAG_UM !== UMS && !ANAG_UM.some(u => u.id === corpo.id)) ANAG_UM.push(corpo);
    sezioniCaricate.anagrafiche = false;
    $("qc-um").value = corpo.nome;
    $("qc-um-id").value = String(corpo.id);
  } catch (e) {
    mostraErroreForm("Il server non risponde.");
  }
}

creaCombo({
  input: $("qc-um"), tendina: $("dd-qcum"), idNascosto: $("qc-um-id"),
  pool: poolUmCombo,
  gruppo: u => GRUPPO_UM[u.nome] === "massa" ? "⚖ Massa (g ↔ kg)" :
              GRUPPO_UM[u.nome] === "volume" ? "🧪 Volume (ml ↔ lt)" :
              "🥣 Laboratorio (non converte)",
  onCrea: creaUmDaQc
});

/* -------- Creazione rapida ingrediente / fornitore -------- */

let QC_ALLERGENI = new Set();   // allergeni scelti nel pannello "➕ Nuovo ingrediente"

$("qc-annulla").addEventListener("click", () => { $("qc-prod").hidden = true; });
$("qc-forn-annulla").addEventListener("click", () => { $("qc-forn").hidden = true; });

$("qc-chips").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip-allergene");
  if (!chip) return;
  const id = Number(chip.dataset.id);
  if (QC_ALLERGENI.has(id)) QC_ALLERGENI.delete(id);
  else QC_ALLERGENI.add(id);
  renderChipsAllergeni("qc-chips", QC_ALLERGENI, true);
});

function mostraErroreForm(testo) {
  $("na-errore").textContent = testo;
  $("na-errore").hidden = false;
}

async function creaIngredienteRapido() {
  const nome = $("qc-prod-nome").value.trim();
  if (!nome) return mostraErroreForm("Inserisci un nome.");
  try {
    const risposta = await fetch("/api/anagrafiche/prodotti", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nome: nome,
        conservazione: $("qc-cons").value,
        unita_misura: $("qc-um").value.trim(),
        sigla: $("qc-sigla").value.trim() || null,
        marca: $("qc-marca").value.trim() || null,
        denominazione_legale: $("qc-denom").value.trim() || null,
        densita: $("qc-densita").value === "" ? null : Number($("qc-densita").value),
        allergeni: [...QC_ALLERGENI],
      }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok) return mostraErroreForm(typeof corpo.detail === "string" ? corpo.detail : "Controlla i dati del nuovo ingrediente.");
    await caricaAnagrafiche();
    popolaFiltriArrivi();
    $("na-prodotto-id").value = String(corpo.id);
    $("na-prodotto").value = corpo.nome;
    $("hint-prod").innerHTML = consBadge(corpo.conservazione) + " conservazione abituale di questo ingrediente";
    $("hint-prod").hidden = false;
    $("na-um").textContent = corpo.unita_misura ? "(" + corpo.unita_misura + ")" : "";
    if (!$("na-marca").value && corpo.marca) $("na-marca").value = corpo.marca;
    $("qc-prod").hidden = true;
    $("qc-densita").value = "";          // RIFIN 53: reset per la prossima creazione
    QC_DENS_AUTO = true;
    QC_ALLERGENI = new Set();
    flashArrivi('Ingrediente "' + corpo.nome + '" creato in anagrafica' +
      (corpo.densita ? " (densità " + corpo.densita + " g/ml)" : "") + ".");
  } catch (e) {
    mostraErroreForm("Il server non risponde.");
  }
}

async function creaFornitoreRapido() {
  const nome = $("qc-forn-nome").value.trim();
  if (!nome) return mostraErroreForm("Inserisci un nome.");
  try {
    const risposta = await fetch("/api/anagrafiche/fornitori", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome, piva: $("qc-forn-piva").value.trim() || null }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok) return mostraErroreForm(typeof corpo.detail === "string" ? corpo.detail : "Controlla i dati del nuovo fornitore.");
    await caricaAnagrafiche();
    popolaFiltriArrivi();
    $("na-fornitore-id").value = String(corpo.id);
    $("na-fornitore").value = corpo.nome;
    $("qc-forn").hidden = true;
    flashArrivi('Fornitore "' + corpo.nome + '" creato in anagrafica.');
  } catch (e) {
    mostraErroreForm("Il server non risponde.");
  }
}

$("qc-crea").addEventListener("click", creaIngredienteRapido);
$("qc-forn-crea").addEventListener("click", creaFornitoreRapido);

/* -------- Salvataggio arrivo -------- */

async function salvaArrivo() {
  if (!$("na-prodotto-id").value) return mostraErroreForm("Scegli l'ingrediente dalla tendina (o crealo con ➕).");
  if (!$("na-fornitore-id").value) return mostraErroreForm("Scegli il fornitore dalla tendina (o crealo con ➕).");
  if (!$("na-lotto").value.trim()) return mostraErroreForm("Manca il codice lotto dell'etichetta.");
  if (!$("na-arrivo").value || !$("na-scadenza").value) return mostraErroreForm("Inserisci data di arrivo e di scadenza.");
  const quantita = Number($("na-quantita").value);
  if (!quantita || quantita <= 0) return mostraErroreForm("La quantità deve essere maggiore di zero.");

  $("na-salva").disabled = true;
  try {
    const risposta = await fetch("/api/arrivi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prodotto_id: Number($("na-prodotto-id").value),
        fornitore_id: Number($("na-fornitore-id").value),
        codice_lotto: $("na-lotto").value.trim(),
        data_arrivo: $("na-arrivo").value,
        data_scadenza: $("na-scadenza").value,
        quantita: quantita,
        marca: $("na-marca").value.trim() || null,
        prezzo_unitario: $("na-prezzo").value === "" ? null : Number($("na-prezzo").value),
        iva: $("na-iva").value === "" ? null : Number($("na-iva").value),
      }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok) {
      const msg = typeof corpo.detail === "string" ? corpo.detail : "Controlla i dati inseriti.";
      return mostraErroreForm(msg);
    }
    chiudiFormArrivo();
    flashArrivi("Lotto " + corpo.codice_lotto + " di " + corpo.prodotto + " registrato: ora è in magazzino.");
    caricaArrivi();
    sezioniCaricate.magazzino = false;   // la giacenza è cambiata
    sezioniCaricate.scadenze = false;
  } catch (e) {
    mostraErroreForm("Il server non risponde.");
  } finally {
    $("na-salva").disabled = false;
  }
}

$("na-salva").addEventListener("click", salvaArrivo);

function flashArrivi(testo) {
  const f = $("flash-arrivi");
  f.textContent = "✔ " + testo;
  f.hidden = false;
  clearTimeout(f._timer);
  f._timer = setTimeout(() => { f.hidden = true; }, 5000);
}

/* ========================= Scadenze ========================= */
/* Il registro HACCP vero: chi scade prima viene prima. Le due card (arrivi
   e produzioni) condividono la finestra del selettore, con ricerche
   indipendenti. Gli scaduti si vedono SOLO col filtro "Scaduti" (scelta
   di Nicolas): vanno buttati, non nascosti tra chi scade domani. */

let SCAD_FINESTRA = "7";   // default 7 giorni (scelta di Nicolas, 18/11/2026)
let SCAD_DATI = null;

async function avviaScadenze() {
  caricaScadenze();
}

async function caricaScadenze() {
  try {
    const r = await fetch("/api/magazzino/scadenze?finestra=" + SCAD_FINESTRA);
    if (!r.ok) throw new Error();
    SCAD_DATI = await r.json();
    renderSezScadenze();
  } catch (e) {
    $("tabella-scad-ing").innerHTML = "";
    $("tabella-scad-pro").innerHTML =
      '<div class="loading">Il server non risponde.</div>';
  }
}

function renderSezScadenze() {
  const ing = SCAD_DATI.filter(r => r.tipo === "ingresso");
  const pro = SCAD_DATI.filter(r => r.tipo === "interno");
  $("contatore-scad").textContent =
    ing.length + " ingredienti · " + pro.length + " prodotti";
  renderScadIng(ing);
  renderScadPro(pro);
}

function testoScad(r) {
  // la ricerca copre nome, lotto, marca e fornitore (regola trasversale)
  return (r.prodotto + " " + r.lotto + " " + (r.marca || "") + " " +
    (r.fornitore || "")).toLowerCase();
}

function renderScadIng(ing) {
  const cerca = ($("cerca-scad-ing").value || "").trim().toLowerCase();
  const righe = cerca ? ing.filter(r => testoScad(r).includes(cerca)) : ing;
  if (!righe.length) {
    $("tabella-scad-ing").innerHTML = '<table><tr><td class="empty">' +
      (cerca ? "Nessun ingrediente corrisponde alla ricerca." :
        "Nessun ingrediente in scadenza in questa finestra.") + "</td></tr></table>";
    return;
  }
  $("tabella-scad-ing").innerHTML =
    "<table><tr><th>Prodotto / lotto</th><th>Marca</th><th>Origine</th>" +
    "<th class='num'>In casa</th><th>Scadenza</th></tr>" +
    righe.map(r => rigaScad(r)).join("") + "</table>";
  document.querySelectorAll("#tabella-scad-ing tr[data-id]").forEach(tr =>
    tr.addEventListener("click", () => vaiADettaglioArrivo(Number(tr.dataset.id))));
}

function renderScadPro(pro) {
  const cerca = ($("cerca-scad-pro").value || "").trim().toLowerCase();
  const righe = cerca ? pro.filter(r => testoScad(r).includes(cerca)) : pro;
  if (!righe.length) {
    $("tabella-scad-pro").innerHTML = '<table><tr><td class="empty">' +
      (cerca ? "Nessun prodotto corrisponde alla ricerca." :
        "Nessun prodotto in scadenza in questa finestra.") + "</td></tr></table>";
    return;
  }
  $("tabella-scad-pro").innerHTML =
    "<table><tr><th>Prodotto / lotto</th><th class='num'>Q.tà</th>" +
    "<th>Scadenza</th></tr>" +
    righe.map(r =>
      "<tr class='click' data-id='" + r.id + "'>" +
      "<td><b>" + esc(r.prodotto) + "</b> " + consBadge(r.conservazione) +
      "<br><span class='mono'>" + esc(r.lotto) + "</span></td>" +
      "<td class='num'>" + fmt(r.quantita) + "\u00A0" + esc(r.um || "") + "</td>" +
      '<td class="td-scad">' + badgeScadenza(r) + "</td></tr>"
    ).join("") + "</table>";
  document.querySelectorAll("#tabella-scad-pro tr[data-id]").forEach(tr =>
    tr.addEventListener("click", () => vaiADettaglioProduzione(Number(tr.dataset.id))));
}

function rigaScad(r) {
  return "<tr class='click' data-id='" + r.id + "'>" +
    "<td><b>" + esc(r.prodotto) + "</b> " + consBadge(r.conservazione) +
    "<br><span class='mono'>" + esc(r.lotto) + "</span></td>" +
    "<td>" + marcaBadge(r.marca) + "</td>" +
    "<td>arrivo · " + esc(r.fornitore) + "</td>" +
    "<td class='num'>" + fmt(r.quantita) + "\u00A0" + esc(r.um || "") + "</td>" +
    '<td class="td-scad">' + badgeScadenza(r) + "</td></tr>";
}

$("scad-finestra").addEventListener("change", e => {
  SCAD_FINESTRA = e.target.value;
  caricaScadenze();
});
$("cerca-scad-ing").addEventListener("input", () => renderSezScadenze());
$("cerca-scad-pro").addEventListener("input", () => renderSezScadenze());

/* ========================= Magazzino ========================= */
/* Tutto letto, niente scritto: le giacenze sono arrivi meno consumi e il
   server calcola anche coperture e rifornimenti attesi. I chip di
   conservazione filtrano le due card insieme (specifica del prototipo). */

let MAG_FILTRO = "";    // "" = tutte le conservazioni
let MAG_DATI = null;    // ultima risposta, per rifiltrare senza rifetch

async function avviaMagazzino() {
  caricaMagazzino();
}

async function caricaMagazzino() {
  $("dettaglio-magazzino").hidden = true;   // dati nuovi: il pannello vecchio si chiude
  try {
    const r = await fetch("/api/magazzino");
    if (!r.ok) throw new Error();
    MAG_DATI = await r.json();
    renderMagazzino(MAG_DATI);
  } catch (e) {
    $("mag-da-ordinare").innerHTML = "";
    $("tabella-magazzino").innerHTML =
      '<div class="loading">Il server non risponde.</div>';
  }
}

function renderMagazzino(dati) {
  renderChipsMagazzino(dati);
  renderDaOrdinare(dati);
  renderGiacenze(dati);
  renderEsauriti(dati);
}

function consOf(r) {
  return r.conservazione || "Da sistemare";
}

function renderChipsMagazzino(dati) {
  // conteggio per conservazione = lotti in giacenza (come da specifica)
  const conteggi = {};
  dati.righe.forEach(r => {
    const c = consOf(r);
    conteggi[c] = (conteggi[c] || 0) + r.n_lotti;
  });
  const tot = dati.righe.reduce((s, r) => s + r.n_lotti, 0);
  $("mag-chips").innerHTML = chipMag("", "Tutti", tot) +
    Object.keys(conteggi).sort().map(c => chipMag(c, c, conteggi[c])).join("");
}

function chipMag(valore, etichetta, n) {
  const emoji = valore === "Frigo" ? "🧊 " : valore === "Freezer" ? "❄️ "
    : valore === "Magazzino" ? "📦 " : "";
  return '<button class="chip-filtro' +
    (valore === MAG_FILTRO ? " attivo" : "") +
    '" data-cons="' + esc(valore) + '">' + emoji + esc(etichetta) + " · " + n + "</button>";
}

$("mag-chips").addEventListener("click", e => {
  const b = e.target.closest(".chip-filtro");
  if (!b || !MAG_DATI) return;
  MAG_FILTRO = b.dataset.cons;
  renderMagazzino(MAG_DATI);   // rifiltro i dati già in casa, senza rifetch
});

function renderDaOrdinare(dati) {
  const ordine = { rosso: 0, ambra: 1 };
  const righe = dati.stat
    .filter(s => s.da_ordinare && (MAG_FILTRO === "" || consOf(s) === MAG_FILTRO))
    .sort((a, b) => (ordine[a.livello] - ordine[b.livello]) || (a.copertura - b.copertura));
  if (!righe.length) {
    $("mag-da-ordinare").innerHTML =
      '<table><tr><td class="empty">Niente da ordinare: tutte le coperture oltre i 7 giorni.</td></tr></table>';
    return;
  }
  $("mag-da-ordinare").innerHTML =
    "<table><tr><th>Prodotto</th><th class='num'>Giacenza</th>" +
    "<th class='num'>Consumo med./g</th><th class='num'>Copertura</th>" +
    "<th>Ultimo arrivo</th><th>Prossimo atteso</th></tr>" +
    righe.map(s =>
      "<tr data-lotti data-prod='" + s.prodotto_id + "'><td><b>" + esc(s.nome) + "</b> " + consBadge(s.conservazione) + "</td>" +
      "<td class='num'><b>" + fmt(s.giacenza_tot) + "</b>\u00A0" + esc(s.um || "") + "</td>" +
      "<td class='num'>" + (s.consumo_medio == null ? "—" :
        fmt(s.consumo_medio) + "\u00A0" + esc(s.um || "")) + "</td>" +
      "<td class='num'>" + badgeCopertura(s) + "</td>" +
      "<td>" + esc(s.ultimo_arrivo) + "</td>" +
      "<td>" + esc(s.prossimo_atteso || "—") + "</td></tr>"
    ).join("") + "</table>";
}

function badgeCopertura(s) {
  if (s.copertura == null) return '<span class="badge b-gray">—</span>';
  const testo = fmt(s.copertura) + " giorni";
  if (s.livello === "rosso") return '<span class="badge b-red">' + testo + "</span>";
  if (s.livello === "ambra") return '<span class="badge b-amber">' + testo + "</span>";
  return '<span class="badge b-green">' + testo + "</span>";
}

/* gli ESAURITI (RIFIN 38): lotti chiusi a zero, senza giacenza. Consumati
   dalle produzioni o azzerati a mano (es. il latte del bar): il lotto NON
   si cancella, si legge qui per la tracciabilità. */
function renderEsauriti(dati) {
  const righe = (dati.esauriti || []).filter(r => MAG_FILTRO === "" || consOf(r) === MAG_FILTRO);
  if (!righe.length) {
    $("mag-esauriti").innerHTML =
      '<table><tr><td class="empty">Nessun lotto esaurito.</td></tr></table>';
    return;
  }
  $("mag-esauriti").innerHTML =
    "<table><tr><th>Prodotto</th><th>Marca</th><th>Lotto</th><th>Fornitore</th>" +
    "<th class='num'>Arrivato</th><th>Esaurito il</th><th>Come</th></tr>" +
    righe.map(r =>
      "<tr data-lotti data-lotto='" + r.id + "'><td><b>" + esc(r.prodotto) + "</b> " +
      consBadge(r.conservazione) + "</td>" +
      "<td>" + marcaBadge(r.marca) + "</td>" +
      "<td class='mono'>" + esc(r.codice_lotto) + "</td>" +
      "<td>" + esc(r.fornitore) + "</td>" +
      "<td class='num'>" + fmt(r.quantita) + "</td>" +
      "<td>" + esc(r.esaurito_il || "—") + "</td>" +
      "<td>" + (r.come === "azzerato"
        ? '<span class="badge b-red" title="azzerato a mano: consumo fuori produzione">0 azzerato</span>'
        : '<span class="badge b-gray" title="chiuso dai consumi delle produzioni">⚙ produzioni</span>') +
      "</td></tr>"
    ).join("") + "</table>";
}

function renderGiacenze(dati) {
  const stat = {};
  dati.stat.forEach(s => { stat[s.prodotto_id] = s; });
  const gruppi = [];   // nell'ordine alfabetico del server: righe già ordinate
  dati.righe.forEach(r => {
    const g = gruppi.find(x => x.s.prodotto_id === r.prodotto_id);
    if (g) g.marche.push(r);
    else gruppi.push({ s: stat[r.prodotto_id] || r, marche: [r] });
  });
  const visibili = gruppi.filter(g => MAG_FILTRO === "" || consOf(g.s) === MAG_FILTRO);
  if (!visibili.length) {
    $("tabella-magazzino").innerHTML =
      '<table><tr><td class="empty">Nessuna giacenza' +
      (MAG_FILTRO ? " in " + esc(MAG_FILTRO) : "") + ".</td></tr></table>";
    return;
  }
  $("tabella-magazzino").innerHTML =
    "<table><tr><th>Prodotto</th><th>Marca</th><th class='num'>Giacenza</th>" +
    "<th class='num'>Consumo med./g</th><th class='num'>Copertura</th>" +
    "<th class='num'>Arrivi</th><th>Ultimo arrivo</th><th>Prossimo atteso</th></tr>" +
    visibili.map(g => rigaMagazzino(g)).join("") + "</table>";
}

function rigaMagazzino(g) {
  const s = g.s, multi = g.marche.length > 1;
  // click su una riga → pannello laterale "Lotti in giacenza";
  // sulla figlia si porta anche la MARCA, che nel pannello va in cima
  const padri =
    "<tr class='riga-mag-box' data-lotti data-prod='" + s.prodotto_id + "'>" +
    "<td><b>" + esc(s.nome) + "</b> " + consBadge(s.conservazione) + "</td>" +
    "<td>" + (multi ? '<span class="muted">' + g.marche.length + " marche</span>"
      : marcaBadge(g.marche[0].marca)) + "</td>" +
    "<td class='num'><b>" + fmt(s.giacenza_tot) + "</b>\u00A0" + esc(s.um || "") +
    ' <span class="muted">(' + g.marche.reduce((t, m) => t + m.n_lotti, 0) + " lotti)</span></td>" +
    "<td class='num'>" + (s.consumo_medio == null ? "—" :
      fmt(s.consumo_medio) + "\u00A0" + esc(s.um || "")) + "</td>" +
    "<td class='num'>" + badgeCopertura(s) + "</td>" +
    "<td class='num'>" + s.n_arrivi +
    (s.cadenza == null ? "" : ' <span class="muted">(ogni ~' + Math.round(s.cadenza) + "g)</span>") + "</td>" +
    "<td>" + esc(s.ultimo_arrivo) + "</td>" +
    "<td>" + esc(s.prossimo_atteso || "—") + "</td></tr>";
  const figlie = multi ? g.marche.map(m =>
    "<tr class='riga-figlia' data-lotti data-prod='" + s.prodotto_id +
    "' data-marca='" + esc(m.marca) + "'><td></td>" +
    "<td class='td-marca'>└ " + marcaBadge(m.marca) + "</td>" +
    "<td class='num'>" + fmt(m.giacenza) + "\u00A0" + esc(s.um || "") + "</td>" +
    "<td colspan='5'></td></tr>"
  ).join("") : "";
  return padri + figlie;
}

function marcaBadge(marca) {
  return marca && marca !== "—"
    ? '<span class="badge b-gray">🏷 ' + esc(marca) + "</span>" : "—";
}

/* --- Pannello laterale "Lotti in giacenza" (RIFIN 36) --- */

["tabella-magazzino", "mag-da-ordinare"].forEach(id =>
  $(id).addEventListener("click", e => {
    const tr = e.target.closest("tr[data-lotti]");
    if (!tr || !MAG_DATI) return;
    apriLottiMagazzino(Number(tr.dataset.prod), tr.dataset.marca || "");
  }));

async function apriLottiMagazzino(prodotto_id, marca) {
  MAG_PANNELLO_LOTTI = { prodotto_id, marca };   // il ◀ della scheda torna qui
  $("dettaglio-magazzino").hidden = false;
  $("titolo-dettaglio-mag").textContent = "Lotti in giacenza";
  $("dettaglio-magazzino-testo").innerHTML = '<div class="loading">carico i dati…</div>';
  // pannello laterale destro (schermi larghi): niente scroll da nessuna parte
  if (getComputedStyle($("dettaglio-magazzino")).position !== "fixed")
    $("dettaglio-magazzino").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const r = await fetch("/api/magazzino/lotti/" + prodotto_id);
    const dati = await r.json();
    if (!r.ok) throw new Error(typeof dati.detail === "string" ? dati.detail : "Lotti non raggiungibili.");
    renderLottiGiacenza(prodotto_id, dati, marca);
  } catch (e) {
    $("dettaglio-magazzino-testo").innerHTML = '<div class="loading">' + esc(e.message) + "</div>";
  }
}

function renderLottiGiacenza(prodotto_id, lotti, marca) {
  const s = MAG_DATI.stat.find(x => x.prodotto_id === prodotto_id) || {};
  const um = s.um || "";
  // raggruppo per marca, in ordine FEFO (già dal server); la marca CLICCATA
  // (riga figlia) va in cima: è quella che ti interessa (scelta di Nicolas)
  const gruppi = [];
  lotti.forEach(l => {
    let g = gruppi.find(x => x.marca === l.marca);
    if (g) g.lotti.push(l);
    else gruppi.push({ marca: l.marca, lotti: [l] });
  });
  gruppi.sort((a, b) =>
    (a.marca === marca ? 0 : 1) - (b.marca === marca ? 0 : 1));
  const tot = lotti.reduce((t, l) => t + l.quantita_residua, 0);
  let html =
    "<div class='det-riga'><span>Prodotto</span><b>" + esc(s.nome || "") + "</b></div>" +
    "<div class='det-riga'><span>In giacenza</span><b>" + fmt(tot) + "\u00A0" + esc(um) +
    "</b> · " + lotti.length + " lott" + (lotti.length === 1 ? "o" : "i") +
    " · " + gruppi.length + " march" + (gruppi.length === 1 ? "a" : "e") + "</div>";
  gruppi.forEach(g => {
    const residua = g.lotti.reduce((t, l) => t + l.quantita_residua, 0);
    html += "<h2 style='margin-top:14px'>" + marcaBadge(g.marca) +
      ' <span class="muted">' + fmt(residua) + "\u00A0" + esc(um) + " · " +
      g.lotti.length + " lott" + (g.lotti.length === 1 ? "o" : "i") + "</span></h2>" +
      "<table><tr><th>Lotto</th><th>Fornitore</th><th>Arrivo</th>" +
      "<th class='num'>Rimasto</th><th class='td-scad'>Scadenza</th><th class='num'>Costo</th></tr>" +
      g.lotti.map(l =>
        "<tr data-lotto='" + l.id + "'>" +
        "<td class='mono'>" + esc(l.codice_lotto) + "</td>" +
        "<td>" + esc(l.fornitore) + "</td>" +
        "<td>" + esc(l.data_arrivo) + "</td>" +
        "<td class='num'>" + fmt(l.quantita_residua) + "\u00A0" + esc(um) +
        " <span class='muted'>di " + fmt(l.quantita) + "</span></td>" +
        "<td class='td-scad'>" + esc(l.data_scadenza) + " " + badgeScadenza(l) + "</td>" +
        "<td class='num'>" + (l.prezzo_unitario == null ? "—" :
          eur(l.prezzo_unitario) + "/" + esc(um) +
          (l.iva != null ? " <span class='muted'>+ IVA " + fmt(l.iva) + "%</span>" : "")) +
        "</td></tr>"
      ).join("") + "</table>";
  });
  $("dettaglio-magazzino-testo").innerHTML = html;
}

// click su un LOTTO del pannello → scheda completa di tracciabilità
// (stessi dati del dettaglio di Arrivi: arrivo, scadenza, costi e "Usato in")
// dentro lo STESSO pannello, col tasto ◀ per tornare alla lista dei lotti.
// Da "Esauriti" invece niente lista a cui tornare: ◀ chiude il pannello
$("dettaglio-magazzino-testo").addEventListener("click", e => {
  const tr = e.target.closest("tr[data-lotto]");
  if (tr && !e.target.closest("button")) apriSchedaLottoMagazzino(Number(tr.dataset.lotto));
});

// righe della card Esauriti → stessa scheda di tracciabilità del lotto
$("mag-esauriti").addEventListener("click", e => {
  const tr = e.target.closest("tr[data-lotto]");
  if (tr && !e.target.closest("button")) apriSchedaLottoMagazzino(Number(tr.dataset.lotto), true);
});

let MAG_PANNELLO_LOTTI = null;   // {prodotto_id, marca}: dove era aperta la lista

async function apriSchedaLottoMagazzino(id, daEsauriti = false) {
  // aperta dagli ESAURITI non c'è lista a cui tornare: ◀ chiude
  if (daEsauriti) MAG_PANNELLO_LOTTI = null;
  // RIFIN 40: dalla card Esauriti il pannello non è mai stato svelato:
  // senza questi comandi il click "non faceva comparire nulla"
  $("dettaglio-magazzino").hidden = false;
  if (getComputedStyle($("dettaglio-magazzino")).position !== "fixed")
    $("dettaglio-magazzino").scrollIntoView({ behavior: "smooth", block: "nearest" });
  $("titolo-dettaglio-mag").textContent = "Scheda lotto";
  $("dettaglio-magazzino-testo").innerHTML = '<div class="loading">carico i dati…</div>';
  try {
    const risposta = await fetch("/api/arrivi/" + id);
    if (!risposta.ok) throw new Error("HTTP " + risposta.status + " dal server.");
    const dati = await risposta.json();
    if (!dati.lotto || !dati.usato_in)
      throw new Error("Il server risponde con un formato vecchio: riavvialo con avvia.bat e ricarica la pagina.");
    const l = dati.lotto;
    const usato = (dati.usato_in || []).length
      ? "<table><tr><th>Produzione</th><th>Data</th><th class='num'>Quantità usata</th></tr>" +
        dati.usato_in.map(u =>
          "<tr><td class='mono'>" + esc(u.codice_lotto) + "</td><td>" + esc(u.data_produzione) +
          "</td><td class='num'>" + fmt(u.quantita_usata) + "\u00A0" + esc(l.um || "") + "</td></tr>").join("") +
        "</table>"
      : "<p class='muted'>Nessuna produzione ha ancora usato questo lotto.</p>";
    $("dettaglio-magazzino-testo").innerHTML =
      '<p><button class="btn sec mini" id="mag-torna-lotti">' +
      (daEsauriti ? "◀ Esauriti" : "◀ Lotti in giacenza") + "</button></p>" +
      "<div class='det-riga'><span>Prodotto</span><b>" + esc(l.prodotto) +
      (l.marca_effettiva ? " · " + esc(l.marca_effettiva) : "") + "</b></div>" +
      "<div class='det-riga'><span>Fornitore</span><b>" + esc(l.fornitore) + "</b></div>" +
      "<div class='det-riga'><span>Lotto fornitore</span><b class='mono'>" + esc(l.codice_lotto) + "</b></div>" +
      "<div class='det-riga'><span>Arrivo</span><b>" + esc(l.data_arrivo) + "</b></div>" +
      "<div class='det-riga'><span>Scadenza</span><b>" + esc(l.data_scadenza) +
      "</b> " + badgeScadenza(l) + "</div>" +
      "<div class='det-riga'><span>Quantità</span><b>" + fmt(l.quantita) + "\u00A0" + esc(l.um || "") +
      "</b> · rimasti <b>" + fmt(l.quantita_residua) + "\u00A0" + esc(l.um || "") + "</b></div>" +
      (l.prezzo_unitario != null
        ? "<div class='det-riga'><span>Costo</span><b>€ " + fmt(l.prezzo_unitario) + "/" + esc(l.um || "u.m.") +
          (l.iva != null ? " + IVA " + fmt(l.iva) + "%" : "") + " · totale " + eur(l.totale) +
          " → " + eur(l.totale_iva) + "</b></div>" : "") +
      (l.data_esaurimento
        ? "<div class='det-riga'><span>Esaurito il</span><b>" + esc(l.data_esaurimento) +
          "</b> <span class='badge b-red'>0 azzerato</span></div>" : "") +
      "<h2 style='margin-top:14px'>Usato in</h2>" + usato +
      (l.data_esaurimento
        ? "<div class='f-azioni'>" +
          '<div class="hint">Azzerato per sbaglio? Ripristino la residua com\'era prima: ' +
          'il lotto esce da "Esauriti" e torna in giacenza.</div>' +
          '<button class="btn sec mini" id="mag-ripristina-lotto">↩ Ripristina residua</button></div>'
        : "") +
      (l.quantita_residua > 0
        ? "<div class='f-azioni'>" +
          '<div class="hint">Finito fuori produzione? (es. il latte del bar): la residua va a 0 ' +
          "e il lotto finisce in \"Esauriti\", senza cancellarsi: la tracciabilità resta.</div>" +
          '<button class="btn sec mini rosso" id="mag-azzera-lotto">0 Azzera residua</button></div>'
        : "");
    $("mag-torna-lotti").addEventListener("click", () => {
      if (MAG_PANNELLO_LOTTI)
        apriLottiMagazzino(MAG_PANNELLO_LOTTI.prodotto_id, MAG_PANNELLO_LOTTI.marca);
      else
        $("dettaglio-magazzino").hidden = true;   // niente lista dietro: chiudi
    });
    const azzera = $("mag-azzera-lotto");
    if (azzera) azzera.addEventListener("click", async () => {
      if (!confirm("Azzerare il lotto " + l.codice_lotto + "? La residua (" +
        fmt(l.quantita_residua) + " " + (l.um || "") + ") va a 0. Il lotto NON si cancella: " +
        "resta in \"Esauriti\" per la tracciabilità.")) return;
      try {
        const r = await fetch("/api/arrivi/" + l.id + "/azzera", { method: "POST" });
        if (!r.ok) {
          const corpo = await r.json().catch(() => ({}));
          throw new Error(typeof corpo.detail === "string" ? corpo.detail : "Azzeramento rifiutato.");
        }
        $("dettaglio-magazzino").hidden = true;
        sezioniCaricate.magazzino = false;
        sezioniCaricate.scadenze = false;   // un lotto a 0 non è più "in scadenza"
        sezioniCaricate.dashboard = false;
        avviaMagazzino();
      } catch (e) {
        alert(e.message);
      }
    });
    const ripristina = $("mag-ripristina-lotto");
    if (ripristina) ripristina.addEventListener("click", async () => {
      // quanto tornerà in residua: la foto pre-azzeramento, o la
      // quantità originale se azzerato prima della RIFIN 39
      const residua = l.residua_pre_azzeramento != null
        ? l.residua_pre_azzeramento : l.quantita;
      if (!confirm("Ripristinare il lotto " + l.codice_lotto + "? La residua torna a " +
        fmt(residua) + " " + (l.um || "") + ": il lotto esce da \"Esauriti\" " +
        "e rientra in giacenza.")) return;
      try {
        const r = await fetch("/api/arrivi/" + l.id + "/ripristina", { method: "POST" });
        if (!r.ok) {
          const corpo = await r.json().catch(() => ({}));
          throw new Error(typeof corpo.detail === "string" ? corpo.detail : "Ripristino rifiutato.");
        }
        $("dettaglio-magazzino").hidden = true;
        sezioniCaricate.magazzino = false;
        sezioniCaricate.scadenze = false;
        sezioniCaricate.dashboard = false;
        avviaMagazzino();
      } catch (e) {
        alert(e.message);
      }
    });
  } catch (e) {
    $("dettaglio-magazzino-testo").innerHTML = '<div class="loading">' + esc(e.message) + "</div>";
  }
}

$("chiudi-dettaglio-mag").addEventListener("click", () => { $("dettaglio-magazzino").hidden = true; });

/* ========================= Produzioni ========================= */

async function avviaProduzioni() {
  try {
    await caricaAnagrafiche();
    // l'elenco delle u.m. del selettore "quantità prodotta" (RIFIN 34):
    // se manca (anagrafiche mai aperte in questa sessione) lo si carica ora
    if (!UMS.length) {
      try {
        const r = await fetch("/api/anagrafiche/unita-misura");
        if (r.ok) UMS = await r.json();
      } catch (e) { /* resta il pool dai prodotti */ }
    }
    // REGOLA: si produce solo ciò che HA ricetta. La tendina "Prodotto
    // da produrre" nasce quindi dalle RICETTE, e da lì prende i suoi dati
    // (prodotto, famiglia, sigla, u.m.): un prodotto senza ricetta non
    // viene neanche suggerito, la creazione passa dal ➕ in fondo.
    const ric = await fetch("/api/ricette");
    if (!ric.ok) throw new Error("ricette non raggiungibili");
    PRODUCIBILI = (await ric.json()).map(x => ({
      id: x.prodotto_id, nome: x.prodotto, sigla: x.sigla,
      famiglia: x.famiglia, unita_misura: x.um,
    }));
  } catch (e) {
    $("tabella-produzioni").innerHTML = '<div class="loading">Il server non risponde.</div>';
    return;
  }
  caricaProduzioni();
}

function renderProduzioni(righe) {
  $("contatore-produzioni").textContent = righe.length + " produzioni";
  if (!righe.length) {
    $("tabella-produzioni").innerHTML =
      '<table><tr><td class="empty">Nessuna produzione: la prima nasce da una ricetta.</td></tr></table>';
    return;
  }
  const corpo = righe.map(r =>
    '<tr data-id="' + r.id + '">' +
    "<td><b>" + esc(r.prodotto) + "</b>" +
    (r.famiglia ? ' <span class="badge b-gray">' + esc(r.famiglia) + "</span>" : "") +
    (r.ricetta_modificata
      ? ' <span class="badge b-amber" title="Rispetto alla ricetta master il verbale ha ingredienti in più o in meno (snapshot al momento della produzione)">✏️ ricetta modificata</span>'
      : "") + "</td>" +
    "<td class='mono'>" + esc(r.codice_lotto) + "</td>" +
    "<td>" + esc(r.data_produzione) + "</td>" +
    '<td class="td-scad">' + badgeScadenza(r) + "</td>" +
    "<td>" + r.n_consumi + " lotti usati</td></tr>").join("");
  $("tabella-produzioni").innerHTML =
    "<table><tr><th>Prodotto</th><th>Lotto interno</th><th>Data produzione</th>" +
    "<th>Scadenza</th><th>Consumi</th></tr>" + corpo + "</table>";
  document.querySelectorAll("#tabella-produzioni tr[data-id]").forEach(tr =>
    tr.addEventListener("click", () => apriDettaglioProduzione(Number(tr.dataset.id))));
}

async function caricaProduzioni() {
  try {
    const risposta = await fetch("/api/produzioni?testo=" +
      encodeURIComponent($("cerca-produzioni").value.trim()));
    if (!risposta.ok) throw new Error("HTTP " + risposta.status);
    renderProduzioni(await risposta.json());
  } catch (e) {
    $("tabella-produzioni").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
}

let timerRicercaProd = null;
$("cerca-produzioni").addEventListener("input", () => {
  clearTimeout(timerRicercaProd);
  timerRicercaProd = setTimeout(caricaProduzioni, 250);
});

/* -------- Dettaglio lotto interno (tracciabilità + etichetta) -------- */

async function apriDettaglioProduzione(id) {
  $("dettaglio-produzione").hidden = false;
  $("dettaglio-produzione-testo").innerHTML = '<div class="loading">carico i dati…</div>';
  $("dettaglio-produzione").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const risposta = await fetch("/api/produzioni/" + id);
    if (!risposta.ok) throw new Error("HTTP " + risposta.status + " dal server.");
    const dati = await risposta.json();
    if (dati.errore) throw new Error(dati.errore);
    if (!dati.lotto || !dati.deriva_da || !dati.usato_in || !dati.etichetta)
      throw new Error("Il server risponde con un formato vecchio: chiudi la " +
        "finestra del server e riavvialo con avvia.bat, poi ricarica la pagina.");
    const l = dati.lotto;
    const deriva = dati.deriva_da.map(d =>
      "<div class='det-riga'><span>" + esc(d.ingrediente) +
      (d.fornitore ? " · " + esc(d.fornitore) : "") + "</span>" +
      "<span><span class='mono'>" + esc(d.codice_lotto) + "</span> · " +
      fmt(d.quantita_usata) + " " + esc(d.um || "") +
      " <span class='muted'>(" + esc(d.origine) + ")</span></span></div>").join("") ||
      "<p class='muted'>nessuna origine</p>";
    const usato = dati.usato_in.map(u =>
      "<div class='det-riga'><span>" + esc(u.codice_lotto) + "</span>" +
      "<span>" + esc(u.data_produzione) + " · " + fmt(u.quantita_usata) + "</span></div>").join("") ||
      "<p class='muted'>non ancora utilizzato</p>";
    const etich = dati.etichetta;
    const righeEtich = (etich.righe || []).map(r => "<li>" + esc(r.denominazione) + "</li>").join("");
    const allergeni = (etich.allergeni || []).length
      ? "<p><b>Contiene (allergeni):</b> " + etich.allergeni.map(esc).join(", ") + "</p>"
      : "<p class='muted'>Nessun allergene dichiarato dagli ingredienti usati.</p>";
    $("dettaglio-produzione-testo").innerHTML =
      "<div class='det-riga'><span>Prodotto</span><b>" + esc(l.prodotto) +
      (l.famiglia ? ' <span class="badge b-gray">' + esc(l.famiglia) + "</span>" : "") +
      (l.ricetta_modificata
        ? ' <span class="badge b-amber" title="Rispetto alla ricetta master il verbale ha ingredienti in più o in meno (snapshot al momento della produzione)">✏️ ricetta modificata</span>'
        : "") + "</b></div>" +
      "<div class='det-riga'><span>Lotto interno</span><b class='mono'>" + esc(l.codice_lotto) + "</b> (generato dal server)</div>" +
      "<div class='det-riga'><span>Data produzione</span><b>" + esc(l.data_produzione) +
      (l.qta_prodotta != null ? " · " + fmt(l.qta_prodotta) + " " + esc(l.um || "") : "") + "</b></div>" +
      "<div class='det-riga'><span>Scadenza</span><b>" + esc(l.data_scadenza) + "</b> " + badgeScadenza(l) + "</div>" +
      "<h2 style='margin-top:14px'>Deriva da (verbale dei consumi)</h2>" + deriva +
      "<h2 style='margin-top:14px'>Etichetta ingredienti calcolata</h2>" +
      "<p class='muted' style='margin:0 0 6px'>Ordine per quantità d'uso (Reg. UE 1169/2011): la quantità non si dichiara.</p>" +
      "<ol class='etichetta'>" + righeEtich + "</ol>" + allergeni +
      "<h2 style='margin-top:14px'>Usato in</h2>" + usato +
      "<div class='f-azioni'>" +
      '<button class="btn mini" id="prod-etichetta">🏷 Etichetta PDF</button>' +
      '<button class="btn sec mini rosso" id="prod-elimina">🗑 Elimina</button></div>';
    // il PDF nasce già pronto: griglia di etichette sul foglio A4
    $("prod-etichetta").addEventListener("click", () => {
      window.open("/api/produzioni/" + id + "/etichetta.pdf", "_blank");
    });
    $("prod-elimina").addEventListener("click", async () => {
      // eliminazione protetta: rifiutata se il lotto interno è consumato da altre produzioni
      if (!confirm("Eliminare la produzione " + l.codice_lotto + " (" + l.prodotto +
        ")? Possibile solo se nessun'altra produzione la consuma. I lotti d'arrivo usati verranno ripristinati.")) return;
      const r = await fetch("/api/produzioni/" + id, { method: "DELETE" });
      if (r.status === 204) {
        $("dettaglio-produzione").hidden = true;
        flashProduzioni("Produzione eliminata, giacenze ripristinate.");
        caricaProduzioni();
        sezioniCaricate.arrivi = false;
        sezioniCaricate.magazzino = false;
        sezioniCaricate.scadenze = false;
        sezioniCaricate.dashboard = false;
      } else {
        const c = await r.json();
        alert(typeof c.detail === "string" ? c.detail : "Eliminazione rifiutata.");
      }
    });
  } catch (e) {
    $("dettaglio-produzione-testo").innerHTML = '<div class="loading">' + esc(e.message) + "</div>";
  }
}

$("chiudi-dettaglio-prod").addEventListener("click", () => { $("dettaglio-produzione").hidden = true; });

/* ----- Nuova produzione: flusso guidato dalla ricetta (FEFO) ----- */

let PROPOSTA = null;   // la proposta del server per il prodotto scelto
let RIGHE = [];         // stato delle righe (ricetta + aggiunte), il verbale
let PANNELLO_ASSEGNA = null;   // indice della riga con il pannello "Assegna lotti" aperto
let RICETTA_DA_PRODUZIONE = null;  // prodotto_id quando la ricetta nasce dal form produzione

/* u.m. della QUANTITÀ PRODOTTA: NP_UM è quella CANONICA del prodotto,
   NP_UM_SCELTA quella con cui l'operatore pesa. Uguali = niente da fare.
   La conversione è la stessa regola di um.py: solo g<->kg e ml<->lt. */
let NP_UM = null, NP_UM_SCELTA = null;
let NP_RESA_PREFILL = null;   // il default della ricetta, da svuotare se si cambia TIPO di u.m.

function popolaUmQta(um) {
  NP_UM = um || null;
  NP_UM_SCELTA = NP_UM;
  NP_RESA_PREFILL = null;
  // la tendina appare SOLO se il prodotto ha una u.m. canonica: senza una
  // base nota una u.m. libera qui escluderebbe il lotto dal FEFO (regola
  // che c'è sempre stata). Con la base c'è tutto il parco: in laboratorio
  // si produce anche a teglie/porzioni.
  $("np-qta-um").hidden = !NP_UM;
  $("np-qta-um-id").value = idUmInPool(NP_UM);
  $("np-qta-um").value = NP_UM || "";
}

function apriFormProduzione() {
  $("overlay-produzione").hidden = false;
  $("np-errore").hidden = true;
  PROPOSTA = null;
  RIGHE = [];
  PANNELLO_ASSEGNA = null;
  popolaUmQta("");   // il prodotto non si sa ancora: niente u.m. da offrire
  $("np-prodotto").value = "";
  $("np-prodotto-id").value = "";
  $("np-hint").hidden = true;
  $("np-um").textContent = "";
  $("np-data").value = OGGI;
  $("np-scadenza").value = "";
  $("np-qta").value = "";
  $("np-ricetta").innerHTML = '<div class="loading">scegli il prodotto: la proposta FEFO comparirà qui</div>';
  $("qc-npprod").hidden = true;
  $("qc-npprod-nome").value = "";
  $("qc-npsigla").value = "";
  $("np-prodotto").focus();
}

// RIFIN 48: candidato nato dal ➕ DEL FORM PRODUZIONE, questa sessione.
// Dedicata (non NUOVO_CANDIDATO_ID): aprire e annullare la modale ricetta
// nel mezzo (l'offerta della proposta: "non ha ancora ricetta, creala")
// NON deve farlo perdere: l'utente è ancora DENTRO il flusso produzione.
// Si eliminano SOLO le estranee: niente più all'annullare della produzione,
// e alla RICETTA SALVATA lo fa sparire lui (è diventato vero)
let CANDIDATO_DA_PRODUZIONE = null;

function chiudiFormProduzione() {
  $("overlay-produzione").hidden = true;
  // RIFIN 48: abbandonato il form produzione senza avergli dato la
  // ricetta: il candidato appena nato (zero storia) se ne va, il nome
  // resta libero. Se la ricetta l'aveva salvata, la variabile è nulla
  eliminaCandidatoAbbandonato(CANDIDATO_DA_PRODUZIONE);
  CANDIDATO_DA_PRODUZIONE = null;
}

$("btn-nuova-produzione").addEventListener("click", apriFormProduzione);
$("btn-nuova-produzione-dash").addEventListener("click", () => { mostraSezione("produzioni"); apriFormProduzione(); });
$("np-annulla").addEventListener("click", chiudiFormProduzione);
$("overlay-produzione").addEventListener("click", (e) => { if (e.target === e.currentTarget) chiudiFormProduzione(); });

// cambio u.m. della quantità prodotta (RIFIN 35: tendina a cascata come
// tutte le altre, pool dall'anagrafica u.m. + ➕ Crea in fondo): stesso
// TIPO -> conversione automatica; tipo diverso (pz, teglie, porzioni) ->
// NESSUN calcolo: il default della ricetta non vale più e si svuota,
// il numero lo scrive l'operatore
function cambiaUmQta(nuova) {
  if (nuova === NP_UM_SCELTA) return;
  const f = fattoreUm(NP_UM_SCELTA, nuova);
  NP_UM_SCELTA = nuova;
  const q = Number($("np-qta").value);
  if (f != null) {
    if (q > 0) $("np-qta").value = num3(q * f);
  } else if (NP_RESA_PREFILL != null && q === NP_RESA_PREFILL) {
    $("np-qta").value = "";
  }
}

async function creaUmDaProduzione(nome) {
  // ➕ della tendina u.m.: crea l'u.m. in ANAGRAFICHE senza lasciare il form
  // (REGOLA: la creazione non fa mai cambiare schermata), poi la seleziona.
  // La card ⚖️ la rivedrà al prossimo passaggio (sezioniCaricate resettato).
  if (!nome) return mostraErroreProduzione("Inserisci un nome.");
  try {
    const r = await fetch("/api/anagrafiche/unita-misura", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome })
    });
    const corpo = await r.json().catch(() => ({}));
    if (!r.ok) return mostraErroreProduzione(typeof corpo.detail === "string" ? corpo.detail : "Creazione rifiutata.");
    UMS.push(corpo);
    if (ANAG_UM !== UMS && !ANAG_UM.some(u => u.id === corpo.id)) ANAG_UM.push(corpo);
    sezioniCaricate.anagrafiche = false;
    $("np-qta-um").value = corpo.nome;
    $("np-qta-um-id").value = String(corpo.id);
    cambiaUmQta(corpo.nome);
  } catch (e) {
    mostraErroreProduzione("Il server non risponde.");
  }
}

creaCombo({
  input: $("np-qta-um"), tendina: $("dd-npum"), idNascosto: $("np-qta-um-id"),
  pool: poolUmCombo,
  gruppo: u => GRUPPO_UM[u.nome] === "massa" ? "⚖ Massa (g ↔ kg)" :
              GRUPPO_UM[u.nome] === "volume" ? "🧪 Volume (ml ↔ lt)" :
              "🥣 Laboratorio (non converte)",
  onPick: u => cambiaUmQta(u.nome),
  onCrea: creaUmDaProduzione
});

// normalizzazione al blur (ritardo per non interferire con quello di
// creaCombo): testo digitato che combacia ESATTAMENTE una u.m. del pool ->
// selezionata; altrimenti si ripristina la scelta precedente
$("np-qta-um").addEventListener("blur", () => {
  setTimeout(() => {
    const campo = $("np-qta-um");
    if (campo.hidden || $("np-qta-um-id").value) return;
    const testo = campo.value.trim().toLowerCase();
    if (testo) {
      const u = poolUmCombo().find(x => x.nome.toLowerCase() === testo);
      if (u) {
        campo.value = u.nome;
        $("np-qta-um-id").value = u.id > 0 ? String(u.id) : "";
        cambiaUmQta(u.nome);
        return;
      }
    }
    campo.value = NP_UM_SCELTA || "";
  }, 220);
});

creaCombo({
  input: $("np-prodotto"), tendina: $("dd-npprod"),
  idNascosto: $("np-prodotto-id"),
  gruppo: p => "🥣 " + (p.famiglia || "Senza famiglia"),
  hint: $("np-hint"),
  hintTesto: p => p.famiglia ? '<span class="badge b-gray">' + esc(p.famiglia) + "</span> famiglia della ricetta" : "",
  pool: () => PRODUCIBILI,
  onPick: (p) => {
    $("np-um").textContent = p.unita_misura ? "(" + p.unita_misura + ")" : "";
    popolaUmQta(p.unita_misura);
    caricaProposta(p.id);
  },
  onCrea: (nome) => {
    // REGOLA: la creazione non fa mai cambiare schermata, parte dal menu a cascata
    $("qc-npprod").hidden = false;
    $("qc-npprod-nome").value = nome;
    $("qc-npsigla").focus();
  },
});

/* -------- Creazione rapida prodotto dal form produzione -------- */
$("qc-npprod-annulla").addEventListener("click", () => { $("qc-npprod").hidden = true; });

$("qc-npprod-crea").addEventListener("click", async () => {
  const nome = $("qc-npprod-nome").value.trim();
  if (!nome) return mostraErroreProduzione("Inserisci un nome.");
  try {
    const risposta = await fetch("/api/ricette/nuovo-prodotto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // niente più u.m.: al prodotto di laboratorio pensa la resa
      // della ricetta ('5 kg'), che è già autosufficiente
      body: JSON.stringify({
        nome: nome,
        sigla: $("qc-npsigla").value.trim() || null,
      }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok) return mostraErroreProduzione(typeof corpo.detail === "string" ? corpo.detail : "Creazione rifiutata.");
    PRODOTTI_LAB.push(corpo);
    // RIFIN 48: appena nato SENZA ricetta: se questo form si abbandona
    // prima di completarlo, lui se ne va con l'annulla del form
    CANDIDATO_DA_PRODUZIONE = corpo.id;
    $("qc-npprod").hidden = true;
    $("np-prodotto-id").value = String(corpo.id);
    $("np-prodotto").value = corpo.nome;
    $("np-um").textContent = corpo.unita_misura ? "(" + corpo.unita_misura + ")" : "";
    popolaUmQta(corpo.unita_misura);
    // RIFIN 49: lo hai creato per PRODURLO, e senza ricetta non si produce:
    // la modale ricetta si apre SUBITO sopra il form. Al salvataggio il
    // flusso torna qui con la proposta FEFO già pronta; se invece la
    // annulli, dietro resta la proposta col suo "➕ Crea la ricetta di X ora"
    caricaProposta(corpo.id);
    apriRicettaDaProduzione(corpo.id);
  } catch (e) {
    mostraErroreProduzione("Il server non risponde.");
  }
});

// Apre la modale ricetta sopra il form produzione: al salvataggio si torna alla proposta
async function apriRicettaDaProduzione(prodotto_id) {
  const p = PRODUCIBILI.find(x => x.id === prodotto_id) ||
            PRODOTTI_LAB.find(x => x.id === prodotto_id);
  if (!p) return;
  if (!FAMIGLIE.length) { try { await caricaFamiglie(); } catch (e) { /* resta creabile a mano */ } }
  RICETTA_DA_PRODUZIONE = prodotto_id;
  apriFormRicetta({ prodotto: p, righe: [] });
  $("nr-titolo").textContent = "Nuova ricetta: " + p.nome;
}

// Ripropone la FEFO quando cambia la quantità di una riga (o viene esclusa):
// la split è la stessa aritmetica del server, che comunque rivalida al salvataggio
function splitFefo(lotti, qta) {
  const assegnazioni = [];
  let residuo = qta;
  for (const lotto of lotti) {
    if (residuo <= 0) break;
    const presa = Math.min(residuo, lotto.quantita_residua || 0);
    if (presa > 0) assegnazioni.push({ lotto, quantita: presa });
    residuo -= presa;
  }
  return { assegnazioni, mancante: Math.max(0, residuo) };
}

/* ---- u.m.: la regola di um.py vale anche qui. Si converte SOLO dentro
   lo stesso gruppo (g<->kg, ml<->lt), mai fra tipi diversi e mai per le
   u.m. libere (pz, teglie, vasetti). Il verbale viaggia SEMPRE in u.m.
   canonica: la u.m. scelta serve solo a chi guarda la bilancia. ---- */

const GRUPPO_UM = { g: "massa", kg: "massa", ml: "volume", lt: "volume" };
const PESO_UM = { g: 1, kg: 1000, ml: 1, lt: 1000 };
const FRATELLO_UM = { g: "kg", kg: "g", ml: "lt", lt: "ml" };

function fattoreUm(da, a) {
  if (!GRUPPO_UM[da] || !GRUPPO_UM[a] || GRUPPO_UM[da] !== GRUPPO_UM[a]) return null;
  return PESO_UM[da] / PESO_UM[a];
}

/* RIFIN 51: il ponte PESO<->VOLUME, ammesso SOLO con la densità (g/ml)
   dichiarata nella scheda dell'ingrediente: 500 g di latte (1,03) sono
   0,485 lt. Senza densità il divieto resta: 500 g di latte e 500 g di
   olio NON sono lo stesso volume. Vale lo stesso qui e in um.py. */
function fattoreLiquido(da, a, densita) {
  if (da === a) return 1;
  if (!densita || !GRUPPO_UM[da] || !GRUPPO_UM[a] ||
      GRUPPO_UM[da] === GRUPPO_UM[a]) return null;
  return GRUPPO_UM[da] === "massa"
    ? PESO_UM[da] / densita / PESO_UM[a]
    : PESO_UM[da] * densita / PESO_UM[a];
}

function fattoreRiga(da, a, densita) {
  return fattoreUm(da, a) != null ? fattoreUm(da, a) : fattoreLiquido(da, a, densita);
}

function num3(x) {
  // il numero riconvertito non trascina dietro decinali fantasma
  const v = Math.round(x * 1000) / 1000;
  return v ? String(Number(v.toFixed(3))) : "";
}

function opzioniUm(um, scelta, densita) {
  if (!um) return "";   // niente u.m.: niente tendina
  let lista = [um];
  if (FRATELLO_UM[um]) lista.push(FRATELLO_UM[um]);
  // RIFIN 51: con la densità dichiarata in scheda, il ponte peso<->volume
  // apre anche il gruppo dell'altro tipo (g/kg su un liquido, ml/lt sul resto)
  if (densita && GRUPPO_UM[um]) {
    const altre = GRUPPO_UM[um] === "massa" ? ["ml", "lt"] : ["g", "kg"];
    lista = lista.concat(altre.filter(x => !lista.includes(x)));
  }
  if (lista.length < 2) return "";   // u.m. libera: nessuna conversione ammessa
  return lista.map(u =>
    '<option value="' + u + '"' + (scelta === u ? " selected" : "") + ">" + u + "</option>"
  ).join("");
}

// pool della tendina u.m. "quantità prodotta" (RIFIN 35): prima le 4 di
// sistema (g kg ml lt, id negativi: NON sono righe di anagrafica), poi
// l'anagrafica delle u.m. (RIFIN 34, id veri per il ➕/blur), poi le u.m.
// libere digitate nei form prodotti senza passar dall'anagrafica.
function poolUmCombo() {
  const viste = new Set(["g", "kg", "ml", "lt"]);
  const pool = ["g", "kg", "ml", "lt"].map((n, i) => ({ id: -(i + 1), nome: n }));
  const custom = [];
  for (const u of UMS)
    if (u.nome && !viste.has(u.nome)) { viste.add(u.nome); custom.push(u); }
  custom.sort((a, b) => a.nome.localeCompare(b.nome));
  for (const p of INGREDIENTI.concat(PRODOTTI_LAB).concat(PRODUCIBILI)) {
    const n = p.unita_misura;
    if (n && !viste.has(n)) { viste.add(n); pool.push({ id: -(1000 + pool.length), nome: n }); }
  }
  return pool.concat(custom);
}

// id di anagrafica di una u.m., "" se non è una riga dell'anagrafica
function idUmInPool(nome) {
  if (!nome) return "";
  const u = poolUmCombo().find(x => x.nome === nome);
  return u && u.id > 0 ? String(u.id) : "";
}

function selUmRiga(i, riga) {
  // nella riga: select quando ci sono alternative, badge grigia se no
  const opzioni = opzioniUm(riga.um, riga.umSel, riga.densita);
  return opzioni
    ? '<select data-rum="' + i + '" class="rum-sel" title="Cambia u.m. della riga: il numero si riconverte da solo, il verbale resta in u.m. canonica">' + opzioni + "</select>"
    : '<span class="badge b-gray">' + esc(riga.um || "") + "</span>";
}

function qtaVista(riga) {
  // il numero mostrato è nella u.m. SCELTA, riga.qta resta sempre canonica
  if (!riga.qta || !riga.umSel || riga.umSel === riga.um) return riga.qta || "";
  return num3(riga.qta * (fattoreRiga(riga.um, riga.umSel, riga.densita) || 1));
}

// La FEFO è la PROPOSTA; l'assegnazione A MANO è l'eccezione scelta
// dall'operatore (la realtà del laboratorio non è mai perfetta) e vince
// finché non la si riallinea con il "↩ Riallinea a FEFO" del pannello.
function totManuale(assegnazioni) {
  return (assegnazioni || []).reduce((somma, a) => somma + (a.quantita || 0), 0);
}

function assegnazioniDi(riga) {
  if (riga.assegnazioni) {
    const tot = totManuale(riga.assegnazioni);
    const qta = riga.qta || 0;
    return {
      manuali: true,
      assegnazioni: riga.assegnazioni,
      mancante: Math.max(0, qta - tot),
      eccedenza: Math.max(0, tot - qta),
    };
  }
  return { manuali: false, ...splitFefo(riga.lotti || [], riga.qta || 0), eccedenza: 0 };
}

function chipsDi(riga) {
  const { manuali, assegnazioni, mancante, eccedenza } = assegnazioniDi(riga);
  const vis = assegnazioni.slice(0, 2);
  const extra = assegnazioni.length - vis.length;
  let html = vis.map(a =>
    '<div class="check-chip"><span class="mono">' + esc(a.lotto.codice_lotto) + "</span> " +
    "<b>× " + fmt(a.quantita) + " " + esc(riga.um || "") + "</b> " +
    '<span class="badge b-gray">' + esc(a.lotto.data_scadenza) + "</span>" +
    (manuali ? ' <span class="badge b-amber">a mano</span>' : "") +
    '<div class="muted">' + (a.lotto.origine === "ingresso" ? esc(a.lotto.fornitore || "") : "lotto interno") + "</div></div>"
  ).join("");
  if (extra > 0) html += '<div class="muted">+ ' + extra + " altro/i lotto/i</div>";
  if (manuali && eccedenza > 0)
    html += '<div class="warn">⚠ I lotti scelti superano di ' + fmt(eccedenza) + " " + esc(riga.um || "") + ' la quantità della riga (pannello "Assegna lotti").</div>';
  if (mancante > 0) html += manuali
    ? '<div class="warn">⚠ Assegnazione a mano incompleta: mancano ' + fmt(mancante) + " " + esc(riga.um || "") + ' (sistema con "Assegna lotti" o ↩ FEFO).</div>'
    : '<div class="warn">⚠ Giacenze insufficienti: mancano ' + fmt(mancante) + " " + esc(riga.um || "") + "</div>";
  if (!assegnazioni.length && !(riga.qta > 0)) html += '<div class="muted">Indica una quantità: l\'assegnazione FEFO comparirà qui.</div>';
  else if (!assegnazioni.length) html += ingredienteAcquistato(riga)
    ? '<div class="warn">⚠ Nessun lotto in magazzino: ⚖ Assegna lotti → ➕ registra il lotto che hai davanti.</div>'
    : '<div class="warn">⚠ Nessun lotto disponibile di questo ingrediente</div>';
  return html;
}

function renderRighe() {
  const cont = $("np-ricetta");
  if (!PROPOSTA) {
    cont.innerHTML = '<div class="loading">scegli il prodotto: la proposta FEFO comparirà qui</div>';
    return;
  }
  let html = "";
  // Live: il verbale sta divergendo dalla ricetta master? Le quantità
  // corrette non contano, contano gli ingredienti aggiunti/esclusi.
  const nAggiunte = RIGHE.filter(r => r.fonte === "aggiunta" && r.nome).length;
  const nEscluse = (PROPOSTA.righe || []).filter((_, i) => !RIGHE[i] || !RIGHE[i].attiva).length;
  if (nAggiunte + nEscluse > 0)
    html += '<div class="warn" style="margin:0 0 10px">✏️ Verbale diverso dalla ricetta master (' +
      nAggiunte + " aggiunto/i, " + nEscluse +
      " escluso/i): questo lotto verrà marcato «ricetta modificata».</div>";
  PROPOSTA.righe.forEach((r, i) => {
    const riga = RIGHE[i];
    if (!riga.attiva) {
      html += '<div class="riga esclusa"><span class="muted">' + esc(r.nome) +
        ': esclusa da questa produzione</span>' +
        '<button class="btn sec mini" data-ripristina="' + i + '">↩ ripristina</button></div>';
      return;
    }
    html += '<div class="riga">' +
      '<div class="riga-testa">' +
      '<input type="number" step="0.001" min="0" value="' + qtaVista(riga) + '" data-qta="' + i + '" class="qta-input">' +
      '<b>' + esc(r.nome) + '</b> ' + selUmRiga(i, riga) +
      (r.famiglia ? ' <span class="badge b-gray">' + esc(r.famiglia) + "</span>" : "") +
      '<span class="muted">da ricetta: ' + fmt(r.qta_ricetta) + "</span>" +
      '<button class="btn sec mini" data-assegna="' + i + '" title="Scegli tu quali lotti usare (e quanto da ciascuno), oppure registra al volo un lotto non in elenco">⚖ Assegna lotti</button>' +
      '<button class="btn sec mini rosso" data-escludi="' + i + '" title="Escludi questa riga solo per questa produzione">✕</button>' +
      "</div>" +
      '<div class="chips" data-chips="' + i + '">' + chipsDi(riga) + "</div>" +
      (PANNELLO_ASSEGNA === i ? pannelloAssegna(riga) : "") +
      "</div>";
  });
  // Righe aggiunte (fuori ricetta): valgono solo per questa produzione
  RIGHE.forEach((r, i) => {
    if (r.fonte !== "aggiunta") return;
    if (!r.nome) {
      // Aggiunta appena aperta: prima si sceglie l'ingrediente
      const opzioni = [...INGREDIENTI, ...PRODOTTI_LAB]
        .map(p => '<option value="' + p.id + '">' + esc(p.nome) + "</option>").join("");
      html += '<div class="riga aggiunta"><div class="riga-testa">' +
        '<select data-addsel="' + i + '" class="sel-aggiunta">' +
        '<option value="0">— scegli ingrediente —</option>' + opzioni + "</select>" +
        '<button class="btn sec mini rosso" data-escludi="' + i + '" title="Rimuovi aggiunta">✕</button>' +
        "</div></div>";
      return;
    }
    html += '<div class="riga aggiunta">' +
      '<div class="riga-testa">' +
      '<input type="number" step="0.001" min="0" value="' + qtaVista(r) + '" data-qta="' + i + '" class="qta-input">' +
      "<b>" + esc(r.nome) + '</b> ' + selUmRiga(i, r) +
      '<span class="badge b-amber">aggiunta</span>' +
      (r.nome ? '<button class="btn sec mini" data-assegna="' + i + '" title="Scegli tu quali lotti usare (e quanto da ciascuno), oppure registra al volo un lotto non in elenco">⚖ Assegna lotti</button>' : "") +
      '<button class="btn sec mini rosso" data-escludi="' + i + '" title="Rimuovi aggiunta">✕</button>' +
      "</div>" +
      '<div class="chips" data-chips="' + i + '">' + chipsDi(r) + "</div>" +
      (PANNELLO_ASSEGNA === i ? pannelloAssegna(r) : "") +
      "</div>";
  });
  html += '<button class="btn sec" id="np-aggiungi">+ Aggiungi ingrediente</button>';
  cont.innerHTML = html;

  cont.querySelectorAll("[data-qta]").forEach(inp =>
    inp.addEventListener("input", () => {
      const r = RIGHE[Number(inp.dataset.qta)];
      // il numero digitato è nella u.m. SCELTA: il verbale (chips, FEFO,
      // scarico) lavora sempre in u.m. CANONICA. RIFIN 51: con la densità
      // la scelta può anche attraversare peso<->volume (500 g -> 0,485 lt)
      const f = r.umSel && r.umSel !== r.um ? fattoreRiga(r.umSel, r.um, r.densita) || 1 : 1;
      r.qta = (Number(inp.value) || 0) * f;
      const chips = cont.querySelector('[data-chips="' + inp.dataset.qta + '"]');
      if (chips) chips.innerHTML = chipsDi(r);
    }));
  cont.querySelectorAll("[data-rum]").forEach(sel =>
    sel.addEventListener("change", () => {
      const r = RIGHE[Number(sel.dataset.rum)];
      r.umSel = sel.value;
      // il numero si riconverte alla nuova u.m., riga.qta non cambia affatto
      const inp = cont.querySelector('[data-qta="' + sel.dataset.rum + '"]');
      if (inp) inp.value = qtaVista(r);
    }));
  cont.querySelectorAll("[data-escludi]").forEach(btn =>
    btn.addEventListener("click", () => {
      const i = Number(btn.dataset.escludi);
      PANNELLO_ASSEGNA = null;   // il pannello non sopravvive a spostamenti di riga
      if (RIGHE[i].fonte === "aggiunta") RIGHE.splice(i, 1);
      else RIGHE[i].attiva = false;
      renderRighe();
    }));
  cont.querySelectorAll("[data-addsel]").forEach(sel =>
    sel.addEventListener("change", async () => {
      const i = Number(sel.dataset.addsel);
      const p = [...INGREDIENTI, ...PRODOTTI_LAB].find(x => x.id === Number(sel.value));
      if (!p) return;   // "— scegli ingrediente —" rimane
      RIGHE[i].nome = p.nome;
      RIGHE[i].um = p.unita_misura;
      RIGHE[i].umSel = p.unita_misura || "";   // la u.m. scelta riparte dall'anagrafica
      RIGHE[i].densita = p.densita || null;    // RIFIN 51: ponte peso<->volume
      RIGHE[i].ingrediente_id = p.id;   // serve al pannello ⚖ (registra lotto al volo)
      RIGHE[i].assegnazioni = null;   // lotti nuovi: si riparte dalla FEFO
      PANNELLO_ASSEGNA = null;
      try {
        const r = await fetch("/api/produzioni/lotti?ingrediente_id=" + p.id);
        RIGHE[i].lotti = await r.json();
      } catch (e) { RIGHE[i].lotti = []; }
      renderRighe();
    }));
  cont.querySelectorAll("[data-ripristina]").forEach(btn =>
    btn.addEventListener("click", () => {
      PANNELLO_ASSEGNA = null;
      RIGHE[Number(btn.dataset.ripristina)].attiva = true;
      renderRighe();
    }));
  // ⚖ Assegna lotti: l'eccezione a mano alla proposta FEFO
  cont.querySelectorAll("[data-assegna]").forEach(btn =>
    btn.addEventListener("click", () => {
      PANNELLO_ASSEGNA = Number(btn.dataset.assegna);
      renderRighe();
    }));
  cont.querySelectorAll("[data-assegna-qta]").forEach(inp =>
    inp.addEventListener("input", aggiornaTotaleAssegna));
  const aOk = cont.querySelector("#np-assegna-ok");
  if (aOk) {
    aOk.addEventListener("click", confermaAssegna);
    cont.querySelector("#np-assegna-annulla").addEventListener("click", () => {
      PANNELLO_ASSEGNA = null;
      renderRighe();
    });
    cont.querySelector("#np-assegna-fefo").addEventListener("click", () => {
      const riga = RIGHE[PANNELLO_ASSEGNA];
      if (riga) riga.assegnazioni = null;   // si torna alla proposta automatica
      PANNELLO_ASSEGNA = null;
      renderRighe();
    });
    aggiornaTotaleAssegna();
    // ➕ "Il lotto non è in elenco? Registralo": creazione senza cambiar schermata
    const alMostra = cont.querySelector("#al-mostra");
    if (alMostra) {
      const alForm = cont.querySelector("#al-form");
      alMostra.addEventListener("click", () => {
        alForm.hidden = false;
        alMostra.hidden = true;
        cont.querySelector("#al-codice").focus();
      });
      cont.querySelector("#al-annulla").addEventListener("click", () => {
        alForm.hidden = true;
        alMostra.hidden = false;
      });
      cont.querySelector("#al-qcf-annulla").addEventListener("click", () => {
        cont.querySelector("#al-qcf").hidden = true;
      });
      cont.querySelector("#al-qcf-crea").addEventListener("click", creaFornitoreDaAssegna);
      cont.querySelector("#al-crea").addEventListener("click", registraLottoAssegna);
      creaCombo({
        input: cont.querySelector("#al-fornitore"), tendina: cont.querySelector("#dd-alforn"),
        idNascosto: cont.querySelector("#al-fornitore-id"),
        gruppo: () => "Tutti i fornitori",
        pool: () => FORNITORI,
        onCrea: (nome) => {
          cont.querySelector("#al-qcf").hidden = false;
          cont.querySelector("#al-qcf-nome").value = nome;
          cont.querySelector("#al-qcf-piva").focus();
        },
      });
    }
  }
  const agg = cont.querySelector("#np-aggiungi");
  if (agg) agg.addEventListener("click", aggiungiRiga);
}

function aggiungiRiga() {
  // Riga aggiunta "in attesa": l'operatore sceglie l'ingrediente dal select
  // renderizzato da renderRighe (così sopravvive a ogni re-render finché non sceglie)
  RIGHE.push({ fonte: "aggiunta", nome: null, um: "", lotti: [], qta: 0, attiva: true, umSel: null });
  renderRighe();
}

/* ---- ⚖ Assegna lotti: quanto prendere da ogni lotto, a mano ---- */

function ingredienteAcquistato(riga) {
  // famiglia NULL = ingrediente acquistato: solo lui può nascere da un
  // arrivo (specchio della guardia di registra_arrivo, che respinge i
  // prodotti di laboratorio: quelli nascono da una produzione)
  return !!riga.ingrediente_id && INGREDIENTI.some(x => x.id === riga.ingrediente_id);
}

function pannelloAssegna(riga) {
  // Si parte dalle assegnazioni correnti: a mano se ci sono, sennò la FEFO
  const attuali = riga.assegnazioni || splitFefo(riga.lotti || [], riga.qta || 0).assegnazioni;
  const lotti = riga.lotti || [];
  let html = '<div class="assegna-pannello">' +
    '<div class="muted">Quanto prendi da ogni lotto? La somma deve coincidere con la quantità della riga: <b>' +
    fmt(riga.qta || 0) + " " + esc(riga.um || "") + "</b>.</div>";
  html += lotti.map(l => {
    const presa = attuali.find(a => a.lotto && a.lotto.id === l.id);
    return '<div class="assegna-riga">' +
      '<input type="number" step="0.001" min="0" class="qta-input" data-assegna-qta="' + l.id + '" value="' + (presa ? presa.quantita : "") + '">' +
      '<span class="mono">' + esc(l.codice_lotto) + "</span> " +
      '<span class="badge b-gray">' + esc(l.data_scadenza) + "</span> " +
      '<span class="muted">residuo ' + fmt(l.quantita_residua || 0) + " " + esc(riga.um || "") + "</span> " +
      '<span class="muted">' + (l.origine === "ingresso" ? esc(l.fornitore || "") : "lotto interno") + "</span>" +
      "</div>";
  }).join("");
  if (!lotti.length)
    html += '<div class="muted">Nessun lotto in elenco per questo ingrediente.</div>';
  html += '<div class="f-azioni">' +
    '<span id="np-assegna-tot" class="muted"></span>' +
    '<button class="btn" id="np-assegna-ok">Conferma</button>' +
    '<button class="btn sec" id="np-assegna-fefo" title="Torna alla proposta automatica">↩ Riallinea a FEFO</button>' +
    '<button class="btn sec" id="np-assegna-annulla">Annulla</button>' +
    "</div>";
  // REGOLA COMBOBOX: il ➕ sta SEMPRE in fondo. Il lotto realmente usato
  // potrebbe non essere ancora registrato (la merce arriva, la burocrazia
  // dopo): qui nasce un VERO arrivo, così la tracciabilità resta intatta
  if (ingredienteAcquistato(riga)) {
    const mancante = Math.max(0, (riga.qta || 0) - totManuale(attuali));
    html += '<div class="assegna-registra">' +
      '<button class="btn sec mini" id="al-mostra">➕ Il lotto non è in elenco? Registralo</button>' +
      '<div id="al-form" hidden>' +
      '<div class="assegna-riga">' +
      '<input type="text" id="al-codice" autocomplete="off" placeholder="Codice lotto (dall\'etichetta)">' +
      '<input type="number" step="0.001" min="0" class="qta-input" id="al-qta" placeholder="' + esc(riga.um || "quantità") + '" value="' + (mancante || "") + '">' +
      '<input type="date" id="al-scadenza">' +
      "</div>" +
      '<div class="assegna-riga">' +
      '<div class="combo">' +
      '<input type="text" id="al-fornitore" autocomplete="off" placeholder="Fornitore (cerca o ➕)…">' +
      '<div class="combo-dd" id="dd-alforn" hidden></div>' +
      "</div>" +
      '<input type="hidden" id="al-fornitore-id">' +
      "</div>" +
      '<div class="assegna-riga" id="al-qcf" hidden>' +
      '<input type="text" id="al-qcf-nome" placeholder="Nome del fornitore">' +
      '<input type="text" id="al-qcf-piva" placeholder="P.IVA (facoltativa)">' +
      '<button class="btn mini" id="al-qcf-crea">Crea</button>' +
      '<button class="btn sec mini" id="al-qcf-annulla">Annulla</button>' +
      "</div>" +
      '<div class="assegna-riga">' +
      '<button class="btn mini" id="al-crea">Registra il lotto</button>' +
      '<button class="btn sec mini" id="al-annulla">Annulla</button>' +
      '<span class="muted">arrivo di oggi: marca e prezzi li completi in Arrivi</span>' +
      "</div>" +
      "</div></div>";
  } else if (!lotti.length) {
    html += '<div class="muted">Questo prodotto nasce da una produzione: un arrivo qui non si registra.</div>';
  }
  html += "</div>";
  return html;
}

async function creaFornitoreDaAssegna() {
  // Creazione rapida fornitore dentro il pannello ⚖ (pattern qc-forn di Arrivi)
  const nome = $("al-qcf-nome").value.trim();
  if (!nome) return mostraErroreProduzione("Inserisci un nome.");
  try {
    const risposta = await fetch("/api/anagrafiche/fornitori", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome, piva: $("al-qcf-piva").value.trim() || null }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok)
      return mostraErroreProduzione(typeof corpo.detail === "string" ? corpo.detail : "Controlla i dati del nuovo fornitore.");
    FORNITORI.push(corpo);
    $("al-fornitore-id").value = String(corpo.id);
    $("al-fornitore").value = corpo.nome;
    $("al-qcf").hidden = true;
  } catch (e) {
    mostraErroreProduzione("Il server non risponde.");
  }
}

async function registraLottoAssegna() {
  // Il lotto digitato a mano diventa un VERO arrivo (tracciabilità intatta:
  // scarico giacenze e verbale puntano a un lotto che esiste davvero).
  // Arrivo = oggi; marca e prezzi si completano in Arrivi quando si vuole.
  const riga = RIGHE[PANNELLO_ASSEGNA];
  if (!riga || !riga.ingrediente_id) return;
  const codice = $("al-codice").value.trim();
  const quantita = Number($("al-qta").value);
  const scadenza = $("al-scadenza").value;
  const fornitore_id = Number($("al-fornitore-id").value) || 0;
  if (!codice) return mostraErroreProduzione("Manca il codice lotto dell'etichetta.");
  if (!quantita || quantita <= 0) return mostraErroreProduzione("La quantità del lotto deve essere maggiore di zero.");
  if (!scadenza) return mostraErroreProduzione("Inserisci la data di scadenza del lotto.");
  if (!fornitore_id) return mostraErroreProduzione("Scegli il fornitore (o crealo con ➕).");
  try {
    const risposta = await fetch("/api/arrivi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prodotto_id: riga.ingrediente_id,
        fornitore_id: fornitore_id,
        codice_lotto: codice,
        data_arrivo: OGGI,
        data_scadenza: scadenza,
        quantita: quantita,
      }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok)
      return mostraErroreProduzione(typeof corpo.detail === "string" ? corpo.detail : "Registrazione rifiutata.");
    const nuovo = {
      id: corpo.id, codice_lotto: corpo.codice_lotto,
      data_scadenza: corpo.data_scadenza, quantita_residua: corpo.quantita_residua,
      origine: "ingresso", fornitore: corpo.fornitore,
    };
    riga.lotti = riga.lotti || [];
    riga.lotti.push(nuovo);
    // Il lotto appena registrato è quello che l'operatore ha davanti:
    // la MANO lo mette in cima e la FEFO copre il resto della riga
    const bisogno = riga.qta || 0;
    const dalNuovo = Math.min(quantita, bisogno);
    const dalResto = splitFefo(riga.lotti.filter(l => l.id !== nuovo.id), bisogno - dalNuovo).assegnazioni;
    riga.assegnazioni = (dalNuovo > 0 ? [{ lotto: nuovo, quantita: dalNuovo }] : []).concat(dalResto);
    // un arrivo in più: Arrivi e Dashboard rivedranno il mondo al prossimo passaggio
    sezioniCaricate.arrivi = false;
    sezioniCaricate.magazzino = false;
    sezioniCaricate.scadenze = false;
    sezioniCaricate.dashboard = false;
    renderRighe();   // il pannello si riapre col lotto nuovo già in elenco
  } catch (e) {
    mostraErroreProduzione("Il server non risponde.");
  }
}

function lettiDalPannello() {
  // [lotto, quantita] di ogni input > 0 del pannello aperto
  const riga = RIGHE[PANNELLO_ASSEGNA];
  const presi = [];
  if (!riga) return presi;
  $("np-ricetta").querySelectorAll("[data-assegna-qta]").forEach(inp => {
    const qta = Number(inp.value) || 0;
    const lotto = (riga.lotti || []).find(l => l.id === Number(inp.dataset.assegnaQta));
    if (qta > 0 && lotto) presi.push({ lotto, quantita: qta });
  });
  return presi;
}

function aggiornaTotaleAssegna() {
  const riga = RIGHE[PANNELLO_ASSEGNA];
  const span = $("np-ricetta").querySelector("#np-assegna-tot");
  const ok = $("np-ricetta").querySelector("#np-assegna-ok");
  if (!riga || !span || !ok) return;
  const presi = lettiDalPannello();
  const tot = totManuale(presi);
  const qta = riga.qta || 0;
  let testo, valido = true;
  const sfora = presi.find(a => a.quantita > (a.lotto.quantita_residua || 0) + 1e-9);
  if (sfora) { testo = "⚠ Il lotto " + sfora.lotto.codice_lotto + " non ha tutta questa giacenza."; valido = false; }
  else if (tot < qta - 1e-9) { testo = "⚠ Mancano " + fmt(qta - tot) + " " + (riga.um || "") + " per coprire la riga."; valido = false; }
  else if (tot > qta + 1e-9) { testo = "⚠ Superi la riga di " + fmt(tot - qta) + " " + (riga.um || "") + "."; valido = false; }
  else testo = "✔ Somma: " + fmt(tot) + " / " + fmt(qta) + " " + (riga.um || "");
  span.textContent = testo;
  ok.disabled = !valido;
}

function confermaAssegna() {
  const riga = RIGHE[PANNELLO_ASSEGNA];
  if (!riga) { PANNELLO_ASSEGNA = null; renderRighe(); return; }
  aggiornaTotaleAssegna();   // nessuna conferma sporca: si rivalida ora
  if ($("np-ricetta").querySelector("#np-assegna-ok").disabled) return;
  const presi = lettiDalPannello();
  // nessuna quantità a mano = nessuna eccezione: si torna alla proposta FEFO
  riga.assegnazioni = presi.length ? presi : null;
  PANNELLO_ASSEGNA = null;
  renderRighe();
}

async function caricaProposta(prodotto_id) {
  $("np-ricetta").innerHTML = '<div class="loading">calcolo la proposta FEFO…</div>';
  try {
    const risposta = await fetch("/api/produzioni/proposta?prodotto_id=" + prodotto_id);
    const dati = await risposta.json();
    if (!risposta.ok) {
      const msg = typeof dati.detail === "string" ? dati.detail : "La ricetta non è raggiungibile.";
      let html = '<div class="warn">⚠ ' + esc(msg) + "</div>";
      // REGOLA: se la ricetta non esiste, si crea al volo senza cambiare schermata
      if (/ricetta/i.test(msg)) {
        const p = PRODUCIBILI.find(x => x.id === prodotto_id) ||
                  PRODOTTI_LAB.find(x => x.id === prodotto_id);
        html += '<div class="f-azioni" style="margin-top:8px">' +
          '<button class="btn" id="np-crea-ricetta">➕ Crea la ricetta' +
          (p ? " di " + esc(p.nome) : "") + " ora</button></div>";
      }
      $("np-ricetta").innerHTML = html;
      const btn = $("np-crea-ricetta");
      if (btn) btn.addEventListener("click", () => apriRicettaDaProduzione(prodotto_id));
      return;
    }
    PROPOSTA = dati;
    // RIFIN 51: la riga parte COME L'HAI SCRITTA in ricetta ('500 g' su un
    // ingrediente in lt): l'operatore vede la bilancia, lo scarico resta in
    // canonica. densita apre il ponte peso<->volume nella tendina
    RIGHE = dati.righe.map(r => ({ ...r, qta: r.qta_ricetta, attiva: true, fonte: "ricetta", umSel: r.um_scritta || r.um || null }));
    PANNELLO_ASSEGNA = null;
    // Prezzo di default della quantità prodotta: la resa della ricetta
    const resa = parseFloat((dati.ricetta.resa || "").replace(",", "."));
    if (resa && !$("np-qta").value) { $("np-qta").value = resa; NP_RESA_PREFILL = resa; }
    renderRighe();
  } catch (e) {
    $("np-ricetta").innerHTML = '<div class="warn">⚠ Il server non risponde.</div>';
  }
}

function mostraErroreProduzione(testo) {
  $("np-errore").textContent = testo;
  $("np-errore").hidden = false;
}

async function salvaProduzione() {
  if (!$("np-prodotto-id").value) return mostraErroreProduzione("Scegli il prodotto da produrre.");
  if (!$("np-data").value || !$("np-scadenza").value) return mostraErroreProduzione("Inserisci data di produzione e di scadenza.");
  // il numero digitato: stesso TIPO -> ricondotto in u.m. CANONICA; tipo
  // diverso (pz, teglie, porzioni) -> nessuna conversione possibile, il
  // lotto registra la quantità nell'u.m. scelta (snapshot um_prodotta)
  let fattoreQta = 1, umProdotta = null;
  if (NP_UM && NP_UM_SCELTA && NP_UM_SCELTA !== NP_UM) {
    const f = fattoreUm(NP_UM_SCELTA, NP_UM);
    if (f != null) fattoreQta = f;        // g<->kg, ml<->lt: si salva in canonica
    else umProdotta = NP_UM_SCELTA;       // inconvertibile: si salva così com'è
  }
  const qtaProdotta = $("np-qta").value === ""
    ? null
    : Number($("np-qta").value) * fattoreQta;
  if (qtaProdotta !== null && qtaProdotta <= 0) return mostraErroreProduzione("La quantità prodotta deve essere maggiore di zero.");

  // Il verbale: consumi calcolati con la stessa FEFO mostrata,
  // oppure i lotti scelti A MANO con "⚖ Assegna lotti"
  const consumi = [];
  for (const r of RIGHE.filter(x => x.attiva && x.qta > 0)) {
    let assegnazioni;
    let mancante = 0;
    if (r.assegnazioni) {
      // scelta a mano: la somma deve COINCIDERE con la quantità della riga
      assegnazioni = r.assegnazioni;
      const tot = totManuale(assegnazioni);
      if (tot < r.qta - 1e-9)
        return mostraErroreProduzione('La riga "' + r.nome + '" non è coperta dai lotti scelti: mancano ' +
          fmt(r.qta - tot) + " " + (r.um || "") + ' (sistema con "Assegna lotti" o ↩ FEFO).');
      if (tot > r.qta + 1e-9)
        return mostraErroreProduzione('La riga "' + r.nome + '": i lotti scelti superano la quantità di ' +
          fmt(tot - r.qta) + " " + (r.um || "") + ".");
      const sfora = assegnazioni.find(a => a.quantita > (a.lotto.quantita_residua || 0) + 1e-9);
      if (sfora)
        return mostraErroreProduzione("Giacenza insufficiente nel lotto " + sfora.lotto.codice_lotto + ".");
    } else {
      ({ assegnazioni, mancante } = splitFefo(r.lotti || [], r.qta));
    }
    if (mancante > 0) return mostraErroreProduzione('Giacenze insufficienti per "' + r.nome + '": mancano ' + fmt(mancante) + " " + esc(r.um || "") + ".");
    for (const a of assegnazioni) {
      consumi.push({
        origine: a.lotto.origine,
        lotto_origine_id: a.lotto.id,
        quantita_usata: a.quantita,
      });
    }
  }
  if (!consumi.length) return mostraErroreProduzione("Nessun consumo: una produzione senza consumi non è un verbale.");

  $("np-salva").disabled = true;
  try {
    const risposta = await fetch("/api/produzioni", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prodotto_id: Number($("np-prodotto-id").value),
        data_produzione: $("np-data").value,
        data_scadenza: $("np-scadenza").value,
        qta_prodotta: qtaProdotta,
        um_prodotta: umProdotta,
        consumi: consumi,
      }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok) {
      const msg = typeof corpo.detail === "string" ? corpo.detail : "Controlla i dati inseriti.";
      return mostraErroreProduzione(msg);
    }
    chiudiFormProduzione();
    flashProduzioni("Lotto " + corpo.codice_lotto + " creato: consumi registrati e giacenze scaricate.");
    caricaProduzioni();
    sezioniCaricate.arrivi = false;   // le giacenze sono cambiate
    sezioniCaricate.magazzino = false;
    sezioniCaricate.scadenze = false;
    if (!$("sez-arrivi").hidden) avviaArrivi();
  } catch (e) {
    mostraErroreProduzione("Il server non risponde.");
  } finally {
    $("np-salva").disabled = false;
  }
}

$("np-salva").addEventListener("click", salvaProduzione);

function flashProduzioni(testo) {
  const f = $("flash-produzioni");
  f.textContent = "✔ " + testo;
  f.hidden = false;
  clearTimeout(f._timer);
  f._timer = setTimeout(() => { f.hidden = true; }, 5000);
}

/* =========================== Ricette =========================== */
/* Il MASTER: crea e corregge le ricette. La famiglia del prodotto nasce
   qui (combobox con ➕: l'utente ne crea quante vuole). Il prodotto da
   produrre è la lista che esiste in quel momento: nessun suggerimento
   automatico, se non c'è lo si crea con ➕. */

let FAMIGLIE = [];
let RIGHE_R = [];     // righe della ricetta in editing
let RICETTA_IN_EDIT = null;   // prodotto_id quando si modifica, null se nuova
// RIFIN 45: prodotto appena nato dal ➕ (con ricetta ancora da salvare).
// Se il form si CHIUDE senza salvare, il candidato (che non ha storia:
// niente ricetta, arrivi, produzioni) viene eliminato: il nome non resta
// mai intrappolato da una creazione abbandonata a metà
let NUOVO_CANDIDATO_ID = null;

async function avviaRicette() {
  try {
    // il pool del prodotto è tutta l'anagrafica che esiste in quel
    // momento: niente liste speciali, niente suggerimenti automatici
    await Promise.all([caricaAnagrafiche(), caricaFamiglie()]);
  } catch (e) {
    $("tabella-ricette").innerHTML = '<div class="loading">Il server non risponde.</div>';
    return;
  }
  caricaRicette();
}

async function caricaFamiglie() {
  const r = await fetch("/api/anagrafiche/famiglie");
  if (!r.ok) throw new Error("famiglie non raggiungibili");
  FAMIGLIE = await r.json();
}

function impostaFamigliaForm(id, nome) {
  // la famiglia è una combobox: testo visibile + id nascosto
  $("nr-famiglia-id").value = id ? String(id) : "";
  $("nr-famiglia").value = nome || "";
  $("qc-fam").hidden = true;
}

async function caricaRicette() {
  try {
    const r = await fetch("/api/ricette?testo=" +
      encodeURIComponent($("cerca-ricette").value.trim()));
    if (!r.ok) throw new Error("HTTP " + r.status);
    renderRicette(await r.json());
  } catch (e) {
    $("tabella-ricette").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
}

// La resa della ricetta è testo libero che può già contenere l'u.m.
// ('5 kg', '60 pz'): in tabella l'u.m. si mostra solo se la resa NON
// finisce già con lei (altrimenti verrebbe '5 kg kg').
function resaHaGiaUm(resa, um) {
  if (!um) return true;
  const t = (resa || "").trim().toLowerCase();
  return t.endsWith(String(um).trim().toLowerCase());
}

function renderRicette(righe) {
  $("contatore-ricette").textContent = righe.length + " ricette";
  if (!righe.length) {
    $("tabella-ricette").innerHTML =
      '<table><tr><td class="empty">Nessuna ricetta: crea la prima con «+ Nuova ricetta».</td></tr></table>';
    return;
  }
  const corpo = righe.map(r =>
    '<tr data-id="' + r.prodotto_id + '">' +
    "<td><b>" + esc(r.prodotto) + "</b>" +
    (r.famiglia ? ' <span class="badge b-gray">' + esc(r.famiglia) + "</span>" : "") + "</td>" +
    "<td>" + esc(r.resa || "—") +
    (!resaHaGiaUm(r.resa, r.um) ? " <span class='muted'>" + esc(r.um) + "</span>" : "") + "</td>" +
    "<td>" + r.n_righe + " ingredienti</td>" +
    "<td>" + (r.procedimento ? "sì" : "<span class='muted'>—</span>") + "</td></tr>").join("");
  $("tabella-ricette").innerHTML =
    "<table><tr><th>Prodotto</th><th>Resa</th><th>Ingredienti</th><th>Procedimento</th></tr>" +
    corpo + "</table>";
  document.querySelectorAll("#tabella-ricette tr[data-id]").forEach(tr =>
    tr.addEventListener("click", () => apriDettaglioRicetta(Number(tr.dataset.id))));
}

async function apriDettaglioRicetta(prodotto_id) {
  $("dettaglio-ricetta").hidden = false;
  $("dettaglio-ricetta-testo").innerHTML = '<div class="loading">carico i dati…</div>';
  $("dettaglio-ricetta").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const risposta = await fetch("/api/ricette/" + prodotto_id);
    if (!risposta.ok) throw new Error("HTTP " + risposta.status + " dal server.");
    const dati = await risposta.json();
    if (dati.errore) throw new Error(dati.errore);
    const righe = dati.righe.map(r =>
      "<div class='det-riga'><span>" + esc(r.nome) +
      (r.famiglia_ingrediente ? ' <span class="badge b-gray">' + esc(r.famiglia_ingrediente) + "</span>" : "") +
      "</span><b>" + fmt(r.quantita) + " " + esc(r.um || "") + "</b></div>").join("");
    $("dettaglio-ricetta-testo").innerHTML =
      "<div class='det-riga'><span>Prodotto</span><b>" + esc(dati.prodotto.nome) +
      (dati.famiglia ? ' <span class="badge b-gray">' + esc(dati.famiglia) + "</span>" : "") + "</b></div>" +
      "<div class='det-riga'><span>Resa</span><b>" + esc(dati.resa || "—") + "</b></div>" +
      "<div class='det-riga'><span>Sigla lotto</span><b class='mono'>" + esc(dati.prodotto.sigla || "—") + "</b></div>" +
      "<h2 style='margin-top:14px'>Ingredienti (dose completa)</h2>" + righe +
      (dati.procedimento
        ? "<h2 style='margin-top:14px'>Procedimento</h2><p style='white-space:pre-line'>" + esc(dati.procedimento) + "</p>"
        : "") +
      "<div class='f-azioni'>" +
      '<button class="btn sec" id="ric-modifica">✏️ Modifica</button>' +
      '<button class="btn sec mini rosso" id="ric-elimina">🗑 Elimina</button></div>';
    $("ric-modifica").addEventListener("click", () => apriFormRicetta(dati));
    $("ric-elimina").addEventListener("click", async () => {
      if (!confirm("Eliminare la ricetta di " + dati.prodotto.nome +
        "? Possibile solo se non ci sono produzioni.")) return;
      const r = await fetch("/api/ricette/" + prodotto_id, { method: "DELETE" });
      if (r.status === 204) {
        $("dettaglio-ricetta").hidden = true;
        flashRicette("Ricetta eliminata.");
        sezioniCaricate.produzioni = false;
        avviaRicette();
      } else {
        const c = await r.json();
        alert(typeof c.detail === "string" ? c.detail : "Eliminazione rifiutata.");
      }
    });
  } catch (e) {
    $("dettaglio-ricetta-testo").innerHTML = '<div class="loading">' + esc(e.message) + "</div>";
  }
}

/* -------- Modale nuova/modifica ricetta -------- */

// Resa divisa: quantità (numero) + unità di misura. Nel database resta il
// testo combinato ('5 kg': lo capiscono etichetta e foodcost), ma il form
// lavora separato: base per il futuro calcolatore dinamico.
function dividiResa(resa) {
  const t = (resa || "").trim();
  if (!t) return { qta: "", um: "" };
  const m = t.match(/^([0-9]+(?:[.,][0-9]+)?)(?:\s+(.*))?$/);
  if (m) return { qta: m[1], um: m[2] || "" };
  // resa libera storica ('una teglia'): resta intera nel campo u.m.
  return { qta: "", um: t };
}

function unisciResa(qta, um) {
  const q = (qta || "").trim();
  const u = (um || "").trim();
  if (q && u) return q + " " + u;
  if (q) return q;
  return u || null;
}

function apriFormRicetta(dati) {
  // dati = dettaglio ricetta (modifica) oppure null (nuova)
  $("overlay-ricetta").hidden = false;
  $("nr-errore").hidden = true;
  $("qc-rprod").hidden = true;
  $("qc-fam").hidden = true;
  // RIFIN 45: il form si apre su un prodotto GIÀ noto: nessun candidato
  // in attesa da eliminare (chi crea un prodotto nuovo lo dichiara
  // DOPO questa chiamata, riassegnando la variabile)
  NUOVO_CANDIDATO_ID = null;
  $("nr-procedimento").value = "";
  $("nr-resa-qta").value = "";
  $("nr-resa-um").value = "";
  RIGHE_R = [];
  impostaFamigliaForm(dati ? dati.famiglia_id : null, dati ? dati.famiglia : null);
  if (dati) {
    RICETTA_IN_EDIT = dati.prodotto.id;
    $("nr-titolo").textContent = "Modifica ricetta: " + dati.prodotto.nome;
    $("nr-prodotto").value = dati.prodotto.nome;
    $("nr-prodotto").disabled = true;
    $("nr-prodotto-id").value = String(dati.prodotto.id);
    $("nr-um").textContent = dati.prodotto.unita_misura ? "(" + dati.prodotto.unita_misura + ")" : "";
    const RESA = dividiResa(dati.resa);
    $("nr-resa-qta").value = RESA.qta;
    $("nr-resa-um").value = RESA.um;
    $("nr-procedimento").value = dati.procedimento || "";
    RIGHE_R = dati.righe.map(r => ({
      ingrediente_id: r.ingrediente_id, nome: r.nome,
      um: r.um, umSel: r.um_scritta || r.um,   // RIFIN 51: come l'avevi scritta
      densita: r.densita || null,
      qta: r.quantita,
    }));
    $("nr-hint").hidden = true;
  } else {
    RICETTA_IN_EDIT = null;
    $("nr-titolo").textContent = "Nuova ricetta";
    $("nr-prodotto").disabled = false;
    $("nr-prodotto").value = "";
    $("nr-prodotto-id").value = "";
    $("nr-um").textContent = "";
    $("nr-hint").hidden = true;
  }
  if (!RIGHE_R.length) aggiungiRigaR();
  else renderRigheRicetta();
  $("nr-prodotto").focus();
}

function chiudiFormRicetta() {
  $("overlay-ricetta").hidden = true;
  RICETTA_DA_PRODUZIONE = null;    // annullata: il form produzione resta aperto sotto
  RICETTA_DA_ANAGRAFICA = null;    // annullata: la scheda anagrafica resta aperta sotto
  // RIFIN 45: chiuso senza salvare SUBITO DOPO un ➕: il candidato non ha
  // ricetta né storia, lo si elimina (best effort: se il browser muore,
  // penserà il backend al prossimo tentativo, riusando la riga)
  eliminaCandidatoAbbandonato(NUOVO_CANDIDATO_ID);
  NUOVO_CANDIDATO_ID = null;
}

// l'eliminazione BEST EFFORT del candidato rimasto a metà (RIFIN 45/48):
// stessa cura in chiudiFormRicetta e chiudiFormProduzione
function eliminaCandidatoAbbandonato(id) {
  if (id === null || id === undefined) return;
  PRODOTTI_LAB = PRODOTTI_LAB.filter(p => p.id !== id);
  fetch("/api/anagrafiche/prodotti/" + id, { method: "DELETE" })
    .then(() => { sezioniCaricate.anagrafiche = false; })
    .catch(() => { /* offline: la riga vuota non dà fastidio */ });
}

function aggiungiRigaR() {
  RIGHE_R.push({ ingrediente_id: null, nome: null, um: "", umSel: null, densita: null, qta: 0 });
  renderRigheRicette();
}

function renderRigheRicette() {
  const cont = $("nr-righe");
  if (!RIGHE_R.length) {
    cont.innerHTML = '<div class="muted">Nessuna riga.</div>';
    return;
  }
  const opzioni = (gruppo, pool) =>
    '<optgroup label="' + gruppo + '">' +
    pool.map(p => '<option value="' + p.id + '">' + esc(p.nome) + "</option>").join("") +
    "</optgroup>";
  let html = "";
  RIGHE_R.forEach((r, i) => {
    const sel = '<select data-rsel="' + i + '" class="sel-aggiunta"' +
      (r.ingrediente_id ? " disabled" : "") + ">" +
      '<option value="0">— scegli ingrediente —</option>' +
      opzioni("Ingredienti", INGREDIENTI) +
      opzioni("Prodotti di laboratorio", PRODOTTI_LAB) + "</select>";
    html += '<div class="riga aggiunta"><div class="riga-testa">' +
      (r.ingrediente_id
        ? "<b>" + esc(r.nome) + "</b> " + selUmRiga(i, r)
        : sel) +
      '<input type="number" step="0.001" min="0" value="' + qtaVista(r) +
      '" data-rqta="' + i + '" class="qta-input" placeholder="q.tà">' +
      '<button class="btn sec mini rosso" data-rdel="' + i + '" title="Rimuovi riga">✕</button>' +
      "</div></div>";
  });
  cont.innerHTML = html;

  cont.querySelectorAll("[data-rsel]").forEach(sel =>
    sel.addEventListener("change", () => {
      const i = Number(sel.dataset.rsel);
      const p = [...INGREDIENTI, ...PRODOTTI_LAB].find(x => x.id === Number(sel.value));
      if (!p) return;
      RIGHE_R[i].ingrediente_id = p.id;
      RIGHE_R[i].nome = p.nome;
      RIGHE_R[i].um = p.unita_misura || "";
      RIGHE_R[i].umSel = p.unita_misura || "";   // RIFIN 51: riparte dall'anagrafica
      RIGHE_R[i].densita = p.densita || null;     // ponte peso<->volume se c'è
      renderRigheRicette();
    }));
  cont.querySelectorAll("[data-rqta]").forEach(inp =>
    inp.addEventListener("input", () => {
      const r = RIGHE_R[Number(inp.dataset.rqta)];
      // il numero digitato è nella u.m. SCELTA, r.qta resta SEMPRE canonica:
      // la salva il backend, che converte di nuovo come qui (um.py)
      const f = r.umSel && r.umSel !== r.um ? fattoreRiga(r.umSel, r.um, r.densita) || 1 : 1;
      r.qta = (Number(inp.value) || 0) * f;
    }));
  cont.querySelectorAll("[data-rum]").forEach(sel =>
    sel.addEventListener("change", () => {
      const r = RIGHE_R[Number(sel.dataset.rum)];
      r.umSel = sel.value;
      // il numero si riconverte alla nuova u.m., r.qta non cambia affatto
      const inp = cont.querySelector('[data-rqta="' + sel.dataset.rum + '"]');
      if (inp) inp.value = qtaVista(r);
    }));
  cont.querySelectorAll("[data-rdel]").forEach(btn =>
    btn.addEventListener("click", () => {
      RIGHE_R.splice(Number(btn.dataset.rdel), 1);
      renderRigheRicette();
    }));
}

function mostraErroreRicetta(testo) {
  $("nr-errore").textContent = testo;
  $("nr-errore").hidden = false;
}

async function salvaRicetta() {
  const prodotto_id = Number($("nr-prodotto-id").value) || null;
  if (!prodotto_id) return mostraErroreRicetta("Scegli il prodotto dalla tendina (o crealo con ➕).");
  const famiglia_id = Number($("nr-famiglia-id").value) || null;
  if (!famiglia_id)
    return mostraErroreRicetta("Scegli una famiglia (oppure creane una nuova con ➕).");
  const righe = RIGHE_R.filter(r => r.ingrediente_id);
  if (!righe.length) return mostraErroreRicetta("Aggiungi almeno un ingrediente.");
  if (righe.some(r => !r.qta || r.qta <= 0))
    return mostraErroreRicetta("Tutte le quantità devono essere maggiori di zero.");

  $("nr-salva").disabled = true;
  try {
    const risposta = await fetch("/api/ricette", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prodotto_id: prodotto_id,
        famiglia_id: famiglia_id,
        famiglia_nuova: null,
        resa: unisciResa($("nr-resa-qta").value, $("nr-resa-um").value),
        procedimento: $("nr-procedimento").value.trim() || null,
        righe: righe.map(r => ({
          ingrediente_id: r.ingrediente_id, quantita: r.qta,
          // RIFIN 51: come l'hai scritta ('500' + 'g'): il backend converte
          // e la conserva, il laboratorio la ritrova nel libro ricette
          um: r.umSel && r.umSel !== r.um ? r.umSel : null,
        })),
      }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok) {
      mostraErroreRicetta(typeof corpo.detail === "string"
        ? corpo.detail : "Il server ha rifiutato la ricetta.");
      return;
    }
    // RIFIN 45: ricetta salvata = il prodotto è VERO: nessun candidato
    // in attesa da ripulire alla chiusura (che sia nato da un form
    // ricetta, RIFIN 45, o dal ➕ del form produzione, RIFIN 48)
    NUOVO_CANDIDATO_ID = null;
    CANDIDATO_DA_PRODUZIONE = null;
    if (RICETTA_DA_ANAGRAFICA) {
      // la ricetta nasce dalla scheda anagrafica: si torna lì, aggiornata
      const pid = RICETTA_DA_ANAGRAFICA;
      RICETTA_DA_ANAGRAFICA = null;
      $("overlay-ricetta").hidden = true;
      anagCombosRivedonoIlMondo();
      if (!$("sez-anagrafiche").hidden) {
        caricaProdottiAnag();
        caricaFamiglieAnag();
        apriDettaglioAnagrafica(pid);
      }
      flashAnagrafiche("Ricetta di " + corpo.prodotto.nome + " salvata.");
      return;
    }
    if (RICETTA_DA_PRODUZIONE) {
      // la ricetta nasce dal form produzione: torniamo lì e riproponiamo la FEFO
      const pid = RICETTA_DA_PRODUZIONE;
      RICETTA_DA_PRODUZIONE = null;
      $("overlay-ricetta").hidden = true;
      // il prodotto è diventato producibile: entra SUBITO nella tendina,
      // con i dati che la ricetta gli ha appena dato (famiglia in primis)
      PRODUCIBILI = PRODUCIBILI.filter(x => x.id !== corpo.prodotto.id);
      PRODUCIBILI.push({
        id: corpo.prodotto.id, nome: corpo.prodotto.nome,
        sigla: corpo.prodotto.sigla, unita_misura: corpo.prodotto.unita_misura,
        famiglia: corpo.famiglia,
      });
      // RIFIN 50: la resa ha appena (ri)scritto l'U.M. CANONICA del
      // prodotto ('5 kg' -> kg): la tendina u.m. della quantità prodotta
      // diventa visibile, SUGGERITA col valore della resa e liberamente
      // cambiabile (parco dell'anagrafica + ➕ Crea)
      $("np-um").textContent = corpo.prodotto.unita_misura
        ? "(" + corpo.prodotto.unita_misura + ")" : "";
      popolaUmQta(corpo.prodotto.unita_misura);
      // e le altre sezioni rivedranno il mondo al prossimo passaggio
      sezioniCaricate.produzioni = false;
      sezioniCaricate.arrivi = false;
      sezioniCaricate.anagrafiche = false;
      caricaProposta(pid);
      return;
    }
    chiudiFormRicetta();
    flashRicette("Ricetta di " + corpo.prodotto.nome + " salvata.");
    $("dettaglio-ricetta").hidden = true;
    // le combo di produzioni e i filtri di arrivi devono rivedere il mondo
    sezioniCaricate.produzioni = false;
    sezioniCaricate.arrivi = false;
    sezioniCaricate.anagrafiche = false;   // la ricetta può cambiare famiglie/prodotti
    avviaRicette();
  } catch (e) {
    mostraErroreRicetta("Il server non risponde.");
  } finally {
    $("nr-salva").disabled = false;
  }
}

function flashRicette(testo) {
  const f = $("flash-ricette");
  f.textContent = "✔ " + testo;
  f.hidden = false;
  clearTimeout(f._timer);
  f._timer = setTimeout(() => { f.hidden = true; }, 5000);
}

$("btn-nuova-ricetta").addEventListener("click", () => apriFormRicetta(null));
// 🖨 il libro ricette HACCP: il server compone il PDF e il browser lo apre
$("btn-libro-ricette").addEventListener("click", () => {
  window.open("/api/ricette/libro.pdf", "_blank");
});
// ➕ Aggiungi ingrediente: STATICO, staccato dalla tab delle righe, così
// resta visibile anche dopo aver eliminato tutte le righe (prima spariva)
$("nr-aggiungi").addEventListener("click", aggiungiRigaR);
$("nr-annulla").addEventListener("click", chiudiFormRicetta);
$("nr-salva").addEventListener("click", salvaRicetta);
$("overlay-ricetta").addEventListener("click", (e) => { if (e.target === e.currentTarget) chiudiFormRicetta(); });
$("chiudi-dettaglio-ric").addEventListener("click", () => { $("dettaglio-ricetta").hidden = true; });

let timerRicercaRic = null;
$("cerca-ricette").addEventListener("input", () => {
  clearTimeout(timerRicercaRic);
  timerRicercaRic = setTimeout(caricaRicette, 250);
});

creaCombo({
  input: $("nr-prodotto"), tendina: $("dd-rprod"),
  idNascosto: $("nr-prodotto-id"),
  gruppo: p => p.famiglia_id ? "🥣 " + (p.famiglia || "") : "Senza famiglia",
  hint: $("nr-hint"),
  hintTesto: p => p.unita_misura
    ? "u.m. <b>" + esc(p.unita_misura) + "</b>" + (p.sigla ? " · sigla <b>" + esc(p.sigla) + "</b>" : "")
    : "",
  // tutta l'anagrafica (ingredienti + prodotti di laboratorio): anche un
  // prodotto nato dal ➕ e rimasto senza famiglia resta raggiungibile
  pool: () => INGREDIENTI.concat(PRODOTTI_LAB),
  onPick: async (p) => {
    $("nr-um").textContent = p.unita_misura ? "(" + p.unita_misura + ")" : "";
    // il salvataggio è un upsert: se il prodotto scelto ha già una
    // ricetta, la si apre in MODIFICA (mai sovrascritture cieche)
    try {
      const r = await fetch("/api/ricette/" + p.id);
      const dati = await r.json();
      if (!dati.errore) apriFormRicetta(dati);
    } catch (e) { /* resta "nuova": al limite lo scopre il salvataggio */ }
  },
  onCrea: (nome) => {
    $("qc-rprod-nome").value = nome;
    $("qc-rsigla").value = "";
    $("qc-rprod").hidden = false;
    $("qc-rsigla").focus();
  },
});

$("qc-rprod-annulla").addEventListener("click", () => { $("qc-rprod").hidden = true; });

$("qc-rprod-crea").addEventListener("click", async () => {
  const nome = $("qc-rprod-nome").value.trim();
  if (!nome) return mostraErroreRicetta("Inserisci un nome.");
  try {
    const risposta = await fetch("/api/ricette/nuovo-prodotto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // niente più u.m.: al prodotto di laboratorio pensa la resa
      // della ricetta ('5 kg'), che è già autosufficiente
      body: JSON.stringify({
        nome: nome,
        sigla: $("qc-rsigla").value.trim() || null,
      }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok) {
      mostraErroreRicetta(typeof corpo.detail === "string" ? corpo.detail : "Creazione rifiutata.");
      return;
    }
    PRODOTTI_LAB.push(corpo);
    $("qc-rprod").hidden = true;
    // RIFIN 45: appena nato, ancora senza ricetta: se il form si chiude
    // senza salvare, lui torna via con l'annulla
    NUOVO_CANDIDATO_ID = corpo.id;
    $("nr-prodotto-id").value = String(corpo.id);
    $("nr-prodotto").value = corpo.nome;
    $("nr-um").textContent = corpo.unita_misura ? "(" + corpo.unita_misura + ")" : "";
  } catch (e) {
    mostraErroreRicetta("Il server non risponde.");
  }
});

/* Famiglia della ricetta: stessa combobox, con creazione rapida ➕
   (la famiglia è solo un nome: nasce qui e la vede la card Anagrafiche) */
creaCombo({
  input: $("nr-famiglia"), tendina: $("dd-fam"),
  idNascosto: $("nr-famiglia-id"),
  gruppo: f => "🏷 Famiglie esistenti",
  pool: () => FAMIGLIE,
  onCrea: (nome) => {
    $("qc-fam-nome").value = nome;
    $("qc-fam").hidden = false;
    $("qc-fam-nome").focus();
  },
});

$("qc-fam-annulla").addEventListener("click", () => { $("qc-fam").hidden = true; });

$("qc-fam-crea").addEventListener("click", async () => {
  const nome = $("qc-fam-nome").value.trim();
  if (!nome) return mostraErroreRicetta("Inserisci un nome.");
  try {
    const risposta = await fetch("/api/anagrafiche/famiglie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome }),
    });
    const corpo = await risposta.json();
    if (!risposta.ok) {
      mostraErroreRicetta(typeof corpo.detail === "string"
        ? corpo.detail : "Creazione rifiutata.");
      return;
    }
    FAMIGLIE.push(corpo);
    $("qc-fam").hidden = true;
    $("nr-famiglia-id").value = String(corpo.id);
    $("nr-famiglia").value = corpo.nome;
    sezioniCaricate.anagrafiche = false;   // la card Famiglie la deve rivedere
    flashRicette('Famiglia "' + corpo.nome + '" creata in anagrafica.');
  } catch (e) {
    mostraErroreRicetta("Il server non risponde.");
  }
});

/* ============================ Avvio ============================ */

mostraSezione("dashboard");
caricaDashboard();

/* =========================== Anagrafiche =========================== */
/* La casa dei dati che nascono una volta sola: conservazione e
   denominazione legale con l'INGREDIENTE, contatti con il FORNITORE,
   famiglia con la RICETTA (master: qui non si tocca, al massimo la si
   apre). I prodotti di laboratorio EREDITANO gli allergeni dalla ricetta:
   mai scritti a mano. Eliminazioni PROTETTE ovunque. */

let ANAG_ALLERGENI = [];
let ANAG_FAMIGLIE = [];         // cache della card famiglie (rinomina inline)
let ANAG_UM = [];              // cache della card unità di misura
let ANAG_UM_EDIT = null;       // id u.m. in rinomina inline
let UMS = [];                  // elenco u.m. per i selettori (produzione, ecc.)
let ANAG_FAM_FILTRO = null;     // famiglia scelta per la card Prodotti
let ANAG_FAM_EDIT = null;       // id famiglia in rinomina inline
let ANAG_ATTIVI = new Set();    // allergeni attivi nella scheda ingrediente
let NAI_ATTIVI = new Set();     // allergeni attivi nella modale nuovo ingrediente
let NAI_DENOM_AUTO = true;      // la denominazione segue il nome finché non si edita
let NAI_DENS_AUTO = true;       // RIFIN 51: la densità suggerita dal nome finché non si edita a mano
let QC_DENS_AUTO = true;        // RIFIN 53: lo stesso per la creazione rapida (Arrivi)
let ANAG_DETTAGLIO = null;      // dati della scheda aperta
let RICETTA_DA_ANAGRAFICA = null;  // prodotto_id: la ricetta nasce dalla scheda

async function avviaAnagrafiche() {
  try {
    await caricaAllergeni();
  } catch (e) { ANAG_ALLERGENI = []; }
  if (!FAMIGLIE.length) { try { await caricaFamiglie(); } catch (e) { /* ok */ } }
  caricaIngredientiAnag();
  caricaProdottiAnag();
  caricaFornitoriAnag();
  caricaFamiglieAnag();
  caricaUnitaAnag();
}

function flashAnagrafiche(testo) {
  const f = $("flash-anagrafiche");
  f.textContent = "✔ " + testo;
  f.hidden = false;
  clearTimeout(f._timer);
  f._timer = setTimeout(() => { f.hidden = true; }, 5000);
}

function anagCombosRivedonoIlMondo() {
  // nome/marca/conservazione/famiglia cambiati: le combo e le liste rivedono tutto
  sezioniCaricate.arrivi = false;
  sezioniCaricate.produzioni = false;
  sezioniCaricate.ricette = false;
  sezioniCaricate.magazzino = false;
  sezioniCaricate.scadenze = false;
}

function badgeAllergeni(alls) {
  if (!alls || !alls.length) return '<span style="color:var(--muted)">—</span>';
  const nomi = alls.map(a => typeof a === "string" ? a : a.nome);
  return nomi.slice(0, 2).map(n => '<span class="badge b-red">⚠ ' + esc(n) + "</span>").join(" ") +
    (nomi.length > 2
      ? ' <span class="badge b-red" title="' + esc(nomi.slice(2).join(", ")) + '">+' + (nomi.length - 2) + "</span>"
      : "");
}

async function caricaAllergeni() {
  const r = await fetch("/api/anagrafiche/allergeni");
  if (!r.ok) throw new Error("allergeni non raggiungibili");
  ANAG_ALLERGENI = await r.json();
}

function renderChipsAllergeni(dove, attivi, editabile) {
  $(dove).innerHTML = ANAG_ALLERGENI.map(a => {
    const on = attivi.has(a.id);
    return '<span class="badge ' + (on ? "b-red" : "b-gray") + ' chip-allergene" data-id="' + a.id +
      '" title="' + esc(a.descrizione || a.nome) + '">' + (on ? "⚠ " : "") + esc(a.nome) + "</span>";
  }).join("");
}

/* ---- le quattro card ---- */

async function caricaIngredientiAnag() {
  try {
    const r = await fetch("/api/anagrafiche/ingredienti?testo=" +
      encodeURIComponent($("cerca-anag-ing").value.trim()));
    if (!r.ok) throw new Error("HTTP " + r.status);
    const righe = await r.json();
    $("anag-conta-ing").textContent = righe.length;
    $("tabella-anag-ing").innerHTML = righe.length
      ? "<table><tr><th>Nome</th><th>Marca</th><th>Conservazione</th><th>Allergeni</th><th>U.m.</th><th>Sigla</th><th>Arrivi</th></tr>" +
        righe.map(p =>
          '<tr data-id="' + p.id + '"><td><b>' + esc(p.nome) + "</b>" +
          (p.denominazione_legale
            ? '<div class="muted" style="font-size:11px">' + esc(p.denominazione_legale) + "</div>"
            : "") + "</td>" +
          "<td>" + (p.marca ? esc(p.marca) : "—") + "</td>" +
          "<td>" + consBadge(p.conservazione) + "</td>" +
          "<td>" + badgeAllergeni(p.allergeni) + "</td>" +
          "<td>" + esc(p.unita_misura || "") + "</td>" +
          '<td class="mono">' + esc(p.sigla || "—") + "</td>" +
          '<td><span class="badge b-gray">' + p.n_arrivi + "</span></td></tr>"
        ).join("") + "</table>"
      : '<p class="muted" style="padding:10px">Nessun ingrediente corrisponde.</p>';
  } catch (e) {
    $("tabella-anag-ing").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
}

async function caricaProdottiAnag() {
  try {
    const r = await fetch("/api/anagrafiche/prodotti-lab?testo=" +
      encodeURIComponent($("cerca-anag-pro").value.trim()) +
      "&famiglia_id=" + (ANAG_FAM_FILTRO ? ANAG_FAM_FILTRO.id : 0));
    if (!r.ok) throw new Error("HTTP " + r.status);
    const righe = await r.json();
    $("anag-conta-pro").textContent = righe.length;
    $("tabella-anag-pro").innerHTML = righe.length
      ? "<table><tr><th>Nome</th><th>Famiglia</th><th>Allergeni (da ricetta)</th><th>Sigla</th><th>Produzioni</th></tr>" +
        righe.map(p =>
          '<tr data-id="' + p.id + '"><td><b>' + esc(p.nome) + "</b></td>" +
          "<td>" + (p.famiglia
            ? '<span class="badge b-gray">' + esc(p.famiglia) + "</span>"
            : '<span class="muted">—</span>') + "</td>" +
          "<td>" + badgeAllergeni(p.allergeni) + "</td>" +
          '<td class="mono">' + esc(p.sigla || "—") + "</td>" +
          '<td><span class="badge b-gray">' + p.n_produzioni + "</span></td></tr>"
        ).join("") + "</table>"
      : '<p class="muted" style="padding:10px">Nessun prodotto corrisponde.</p>';
  } catch (e) {
    $("tabella-anag-pro").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
  caricaCandidatiAnag();
}

/* ---- RIFIN 47: i CANDIDATI senza ricetta, visibili e gestibili ----
   Un prodotto nato dal ➕ e mai completato non sparisce nel limbo: la
   riga in fondo alla card Prodotti lo lista; lo si completa (la ricetta
   lo fa nascere per davvero) o lo si elimina (protetto: se nel frattempo
   ha preso storia, il server rifiuta e spiega). */
let CANDIDATI_ANAG = [];

async function caricaCandidatiAnag() {
  try {
    const r = await fetch("/api/anagrafiche/candidati");
    CANDIDATI_ANAG = r.ok ? await r.json() : [];
  } catch (e) { CANDIDATI_ANAG = []; }
  const box = $("anag-candidati");
  if (!CANDIDATI_ANAG.length) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  box.innerHTML =
    "<b>⏳ " + CANDIDATI_ANAG.length + " in attesa di ricetta</b>" +
    " (nati dal ➕ e mai completati): completarli li fa nascere per davvero, eliminarli libera il nome." +
    CANDIDATI_ANAG.map(c =>
      '<div class="riga"><span>➕ ' + esc(c.nome) + "</span><span>" +
      '<button class="btn sec mini" data-cand-comp="' + c.id + '" title="Aprigli la ricetta: da candidato diventa prodotto">✏ Completa</button> ' +
      '<button class="btn sec mini rosso" data-cand-del="' + c.id + '" title="Elimina il candidato (libera il nome)">🗑</button>' +
      "</span></div>").join("");
}

$("anag-candidati").addEventListener("click", async (e) => {
  const comp = e.target.closest("[data-cand-comp]");
  const del = e.target.closest("[data-cand-del]");
  if (comp) {
    const p = CANDIDATI_ANAG.find(x => x.id === Number(comp.dataset.candComp));
    if (!p) return;
    // come il ➕ Nuovo della card: apre la modale ricetta sul candidato,
    // al salvataggio si torna qui (scheda aperta, tutto aggiornato)
    RICETTA_DA_ANAGRAFICA = p.id;
    if (!FAMIGLIE.length) { try { await caricaFamiglie(); } catch (e2) { /* si crea a mano */ } }
    apriFormRicetta({ prodotto: { id: p.id, nome: p.nome, unita_misura: p.unita_misura }, righe: [] });
    $("nr-titolo").textContent = "Nuova ricetta: " + p.nome;
    return;
  }
  if (del) {
    const p = CANDIDATI_ANAG.find(x => x.id === Number(del.dataset.candDel));
    if (!p) return;
    try {
      const r = await fetch("/api/anagrafiche/prodotti/" + p.id, { method: "DELETE" });
      if (r.status === 204) {
        PRODOTTI_LAB = PRODOTTI_LAB.filter(x => x.id !== p.id);
        flashAnagrafiche('Candidato "' + p.nome + '" eliminato: nome libero.');
        caricaCandidatiAnag();
      } else {
        const c = await r.json().catch(() => ({}));
        flashAnagrafiche("❌ " + (typeof c.detail === "string" ? c.detail : "Eliminazione rifiutata."));
      }
    } catch (e2) {
      flashAnagrafiche("❌ Il server non risponde.");
    }
  }
});

async function caricaFornitoriAnag() {
  try {
    const r = await fetch("/api/anagrafiche/fornitori?testo=" +
      encodeURIComponent($("cerca-anag-for").value.trim()));
    if (!r.ok) throw new Error("HTTP " + r.status);
    const righe = await r.json();
    $("anag-conta-for").textContent = righe.length;
    $("tabella-anag-for").innerHTML = righe.length
      ? "<table><tr><th>Nome</th><th>Arrivi</th></tr>" +
        righe.map(f =>
          '<tr data-forn="' + f.id + '"><td><b>' + esc(f.nome) + "</b>" +
          (f.piva ? '<div class="muted mono" style="font-size:11px">' + esc(f.piva) + "</div>" : "") + "</td>" +
          '<td><span class="badge b-gray">' + f.n_arrivi + "</span></td></tr>"
        ).join("") + "</table>"
      : '<p class="muted" style="padding:10px">Nessun fornitore corrisponde.</p>';
  } catch (e) {
    $("tabella-anag-for").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
}

async function caricaFamiglieAnag() {
  try {
    const r = await fetch("/api/anagrafiche/famiglie");
    if (!r.ok) throw new Error("HTTP " + r.status);
    ANAG_FAMIGLIE = await r.json();
    renderFamiglieAnag();
  } catch (e) {
    $("tabella-anag-fam").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
}

/* ---- Unità di misura: stessa filosofia delle famiglie ----
   Elenco per i selettori dell'app; le 4 di sistema (badge "di sistema")
   non si toccano: alimentano le conversioni g<->kg e ml<->lt. */

async function caricaUnitaAnag() {
  try {
    const r = await fetch("/api/anagrafiche/unita-misura");
    if (!r.ok) throw new Error("HTTP " + r.status);
    ANAG_UM = await r.json();
    UMS = ANAG_UM;   // stesso elenco per i selettori (produzione, ecc.)
    renderUnitaAnag();
  } catch (e) {
    $("tabella-anag-um").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
}

function renderUnitaAnag() {
  $("anag-conta-um").textContent = ANAG_UM.length;
  $("tabella-anag-um").innerHTML = ANAG_UM.map(u => {
    if (ANAG_UM_EDIT === u.id) {
      return '<div class="anag-fam-riga"><input id="um-edit-nome" value="' + esc(u.nome) + '">' +
        '<button class="btn" id="um-edit-salva">Salva</button>' +
        '<button class="btn sec" id="um-edit-annulla">Annulla</button></div>';
    }
    const sistema = u.sistema
      ? ' <span class="badge b-blue" title="Unità di sistema: alimenta le conversioni g↔kg e ml↔lt, non si rinomina né si elimina">⚙ di sistema</span>'
      : " <span class=\"muted\">✏️</span>";
    return '<div class="anag-fam-riga">' +
      '<span class="anag-nome-fam" data-rinomina="' + u.id + '" data-sistema="' + (u.sistema ? 1 : 0) +
      '" title="' + (u.sistema ? "Unità di sistema: protetta" : "Clic per rinominare") + '"><b>' +
      esc(u.nome) + "</b>" + sistema + "</span>" +
      '<span class="badge b-gray">' + u.n_prodotti +
      (u.n_prodotti === 1 ? " prodotto" : " prodotti") + "</span>" +
      (u.sistema ? "" :
        '<button class="btn sec mini rosso" data-elimina="' + u.id + '" data-nome="' + esc(u.nome) +
        '" title="Elimina u.m. (solo se non usata)">✕</button>') +
      "</div>";
  }).join("") || '<p class="muted" style="padding:10px">Nessuna unità di misura.</p>';
  if (ANAG_UM_EDIT !== null) {
    $("um-edit-nome").focus();
    $("um-edit-salva").addEventListener("click", async () => {
      const nome = $("um-edit-nome").value.trim();
      if (!nome) return mostraErroreUm("Inserisci il nome dell'unità di misura.");
      try {
        const r = await fetch("/api/anagrafiche/unita-misura/" + ANAG_UM_EDIT, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nome: nome }),
        });
        if (!r.ok) {
          const c = await r.json();
          return mostraErroreUm(typeof c.detail === "string" ? c.detail : "Rinomina rifiutata.");
        }
        ANAG_UM_EDIT = null;
        $("anag-um-errore").hidden = true;
        flashAnagrafiche('U.m. rinominata: i prodotti che la usano la seguono.');
        caricaUnitaAnag();
        caricaIngredientiAnag();
        caricaProdottiAnag();
        anagCombosRivedonoIlMondo();
      } catch (e) {
        mostraErroreUm("Il server non risponde.");
      }
    });
    $("um-edit-annulla").addEventListener("click", () => {
      ANAG_UM_EDIT = null;
      $("anag-um-errore").hidden = true;
      renderUnitaAnag();
    });
  }
}

function mostraErroreUm(testo) {
  $("anag-um-errore").textContent = testo;
  $("anag-um-errore").hidden = false;
}

function renderFamiglieAnag() {
  $("anag-conta-fam").textContent = ANAG_FAMIGLIE.length;
  $("tabella-anag-fam").innerHTML = ANAG_FAMIGLIE.map(f => {
    if (ANAG_FAM_EDIT === f.id) {
      return '<div class="anag-fam-riga"><input id="fam-edit-nome" value="' + esc(f.nome) + '">' +
        '<button class="btn" id="fam-edit-salva">Salva</button>' +
        '<button class="btn sec" id="fam-edit-annulla">Annulla</button></div>';
    }
    return '<div class="anag-fam-riga">' +
      '<span class="anag-nome-fam" data-rinomina="' + f.id + '" title="Clic per rinominare"><b>' +
      esc(f.nome) + '</b> <span class="muted">✏️</span></span>' +
      '<span class="badge b-gray" data-filtro="' + f.id + '" data-nome="' + esc(f.nome) +
      '" title="Clic: mostra i prodotti di questa famiglia" style="cursor:pointer">' +
      f.n_prodotti + (f.n_prodotti === 1 ? " prodotto" : " prodotti") + "</span>" +
      '<button class="btn sec mini rosso" data-elimina="' + f.id + '" data-nome="' + esc(f.nome) +
      '" title="Elimina famiglia (solo se non usata)">✕</button></div>';
  }).join("") || '<p class="muted" style="padding:10px">Nessuna famiglia.</p>';
  if (ANAG_FAM_EDIT !== null) {
    $("fam-edit-nome").focus();
    $("fam-edit-salva").addEventListener("click", async () => {
      const nome = $("fam-edit-nome").value.trim();
      if (!nome) return mostraErroreFamiglia("Inserisci il nome della famiglia.");
      try {
        const r = await fetch("/api/anagrafiche/famiglie/" + ANAG_FAM_EDIT, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nome: nome }),
        });
        if (!r.ok) {
          const c = await r.json();
          return mostraErroreFamiglia(typeof c.detail === "string" ? c.detail : "Rinomina rifiutata.");
        }
        ANAG_FAM_EDIT = null;
        $("anag-fam-errore").hidden = true;
        flashAnagrafiche("Famiglia rinominata: si aggiorna ovunque.");
        caricaFamiglieAnag();
        caricaProdottiAnag();
        anagCombosRivedonoIlMondo();
      } catch (e) {
        mostraErroreFamiglia("Il server non risponde.");
      }
    });
    $("fam-edit-annulla").addEventListener("click", () => {
      ANAG_FAM_EDIT = null;
      $("anag-fam-errore").hidden = true;
      renderFamiglieAnag();
    });
  }
}

function mostraErroreFamiglia(testo) {
  $("anag-fam-errore").textContent = testo;
  $("anag-fam-errore").hidden = false;
}

function setFiltroFamiglia(f) {
  ANAG_FAM_FILTRO = f;
  const d = $("anag-filtro-fam");
  if (f) {
    d.hidden = false;
    d.innerHTML = '<span class="badge b-amber" style="cursor:pointer" title="Clic: toglie il filtro famiglia">🏷 ' +
      esc(f.nome) + " ✕</span>";
    d.firstElementChild.addEventListener("click", () => setFiltroFamiglia(null));
  } else {
    d.hidden = true;
  }
  caricaProdottiAnag();
}

/* ---- click delle liste (delegation: il container non si ricrea) ---- */

$("tabella-anag-ing").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-id]");
  if (tr) apriDettaglioAnagrafica(Number(tr.dataset.id));
});

$("tabella-anag-pro").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-id]");
  if (tr) apriDettaglioAnagrafica(Number(tr.dataset.id));
});

$("tabella-anag-for").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-forn]");
  if (tr) apriDettaglioFornitore(Number(tr.dataset.forn));
});

$("tabella-anag-fam").addEventListener("click", (e) => {
  const rin = e.target.closest("[data-rinomina]");
  if (rin) {
    ANAG_FAM_EDIT = Number(rin.dataset.rinomina);
    return renderFamiglieAnag();
  }
  const fil = e.target.closest("[data-filtro]");
  if (fil) return setFiltroFamiglia({ id: Number(fil.dataset.filtro), nome: fil.dataset.nome });
  const del = e.target.closest("[data-elimina]");
  if (del) {
    if (!confirm('Eliminare la famiglia "' + del.dataset.nome +
      '"? Possibile solo se nessun prodotto la usa.')) return;
    fetch("/api/anagrafiche/famiglie/" + del.dataset.elimina, { method: "DELETE" })
      .then(r => {
        if (r.status === 204) {
          flashAnagrafiche("Famiglia eliminata.");
          caricaFamiglieAnag();
          if (ANAG_FAM_FILTRO && ANAG_FAM_FILTRO.id === Number(del.dataset.elimina))
            setFiltroFamiglia(null);
        } else {
          return r.json().then(c =>
            mostraErroreFamiglia(typeof c.detail === "string" ? c.detail : "Eliminazione rifiutata."));
        }
      })
      .catch(() => mostraErroreFamiglia("Il server non risponde."));
  }
});

$("tabella-anag-um").addEventListener("click", (e) => {
  const rin = e.target.closest("[data-rinomina]");
  if (rin) {
    if (rin.dataset.sistema === "1")
      return mostraErroreUm("Le unità di sistema (g, kg, ml, lt) alimentano le conversioni: non si rinominano.");
    ANAG_UM_EDIT = Number(rin.dataset.rinomina);
    return renderUnitaAnag();
  }
  const del = e.target.closest("[data-elimina]");
  if (del) {
    if (!confirm('Eliminare l\'unità di misura "' + del.dataset.nome +
      '"? Possibile solo se nessun prodotto la usa.')) return;
    fetch("/api/anagrafiche/unita-misura/" + del.dataset.elimina, { method: "DELETE" })
      .then(r => {
        if (r.status === 204) {
          flashAnagrafiche('Unità di misura eliminata.');
          caricaUnitaAnag();
        } else {
          return r.json().then(c =>
            mostraErroreUm(typeof c.detail === "string" ? c.detail : "Eliminazione rifiutata."));
        }
      })
      .catch(() => mostraErroreUm("Il server non risponde."));
  }
});

let timerAnagIng = null, timerAnagPro = null, timerAnagFor = null;
$("cerca-anag-ing").addEventListener("input", () => {
  clearTimeout(timerAnagIng);
  timerAnagIng = setTimeout(caricaIngredientiAnag, 250);
});
$("cerca-anag-pro").addEventListener("input", () => {
  clearTimeout(timerAnagPro);
  timerAnagPro = setTimeout(caricaProdottiAnag, 250);
});
$("cerca-anag-for").addEventListener("input", () => {
  clearTimeout(timerAnagFor);
  timerAnagFor = setTimeout(caricaFornitoriAnag, 250);
});

/* ---- la scheda di dettaglio (pannello in-page) ---- */

function vaiADettaglioArrivo(id) {
  mostraSezione("arrivi");
  apriDettaglioArrivo(id);
}

function vaiADettaglioProduzione(id) {
  mostraSezione("produzioni");
  apriDettaglioProduzione(id);
}

function rigaArrivi(arrivi) {
  return "<h2 style='margin-top:14px'>Arrivi recenti</h2>" +
    (arrivi.length
      ? "<table><tr><th>Lotto</th><th>Prodotto</th><th>Arrivo</th><th>Scadenza</th><th>Q.tà</th><th class='num'>Totale + IVA</th></tr>" +
        arrivi.map(a =>
          '<tr class="vai-arrivo" data-arrivo="' + a.id + '"><td class="mono">' + esc(a.codice_lotto) + "</td>" +
          "<td>" + esc(a.prodotto) + "</td><td>" + esc(a.data_arrivo) + "</td>" +
          '<td class="td-scad">' + badgeScadenza(a) + "</td><td>" + fmt(a.quantita) + " " + esc(a.um || "") + "</td>" +
          '<td class="num"><b>' + eur(a.totale_iva) + "</b></td></tr>"
        ).join("") + "</table>"
      : '<p class="muted">Nessun arrivo registrato.</p>');
}

function rigaProduzioni(produzioni) {
  return "<h2 style='margin-top:14px'>Produzioni recenti</h2>" +
    (produzioni.length
      ? "<table><tr><th>Lotto interno</th><th>Data produzione</th><th>Scadenza</th><th>Q.tà</th></tr>" +
        produzioni.map(l =>
          '<tr class="vai-produzione" data-produzione="' + l.id + '"><td class="mono">' + esc(l.codice_lotto) + "</td>" +
          "<td>" + esc(l.data_produzione) + "</td>" + '<td class="td-scad">' + badgeScadenza(l) + "</td>" +
          "<td>" + fmt(l.qta_prodotta) + " " + esc(l.um || "") + "</td></tr>"
        ).join("") + "</table>"
      : '<p class="muted">Nessuna produzione registrata.</p>');
}

function selezionaCons(sel) {
  return ["Frigo", "Freezer", "Magazzino"].map(c =>
    '<option value="' + c + '"' + (sel === c ? " selected" : "") + ">" +
    (c === "Frigo" ? "🧊 " : c === "Freezer" ? "❄️ " : "📦 ") + c + "</option>"
  ).join("");
}

async function apriDettaglioAnagrafica(id) {
  $("dettaglio-anagrafica").hidden = false;
  $("dettaglio-anagrafica-testo").innerHTML = '<div class="loading">carico i dati…</div>';
  // pannello laterale destro (schermi larghi): non serve scrollare da nessuna parte
  if (getComputedStyle($("dettaglio-anagrafica")).position !== "fixed")
    $("dettaglio-anagrafica").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const r = await fetch("/api/anagrafiche/prodotti/" + id);
    const dati = await r.json();
    if (!r.ok) throw new Error(typeof dati.detail === "string" ? dati.detail : "Scheda non raggiungibile.");
    ANAG_DETTAGLIO = dati;
    if (dati.tipo === "ingrediente") renderSchedaIngrediente(dati);
    else renderSchedaProdotto(dati);
  } catch (e) {
    $("dettaglio-anagrafica-testo").innerHTML = '<div class="loading">' + esc(e.message) + "</div>";
  }
}

async function apriDettaglioFornitore(id) {
  $("dettaglio-anagrafica").hidden = false;
  $("dettaglio-anagrafica-testo").innerHTML = '<div class="loading">carico i dati…</div>';
  if (getComputedStyle($("dettaglio-anagrafica")).position !== "fixed")
    $("dettaglio-anagrafica").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const r = await fetch("/api/anagrafiche/fornitori/" + id);
    const dati = await r.json();
    if (!r.ok) throw new Error(typeof dati.detail === "string" ? dati.detail : "Scheda non raggiungibile.");
    renderSchedaFornitore(dati);
  } catch (e) {
    $("dettaglio-anagrafica-testo").innerHTML = '<div class="loading">' + esc(e.message) + "</div>";
  }
}

function renderSchedaIngrediente(d) {
  ANAG_ATTIVI = new Set(d.allergeni.map(a => a.id));
  $("dettaglio-anagrafica-testo").innerHTML =
    "<h2 style='margin:0 0 6px'>🛒 " + esc(d.nome) + ' <span class="badge b-gray">ingrediente</span></h2>' +
    "<div class='form-grid'>" +
    "<div><label>Nome *</label><input id='anag-nome' value='" + esc(d.nome) + "'></div>" +
    "<div><label>Denominazione legale *</label><input id='anag-denom' value='" + esc(d.denominazione_legale || "") + "'>" +
    "<div class='hint'>La dicitura dell'etichetta d'acquisto: finisce nell'etichetta dei prodotti finiti.</div></div>" +
    "<div><label>Marca abituale</label><input id='anag-marca' value='" + esc(d.marca || "") + "' placeholder='default degli arrivi'></div>" +
    "<div><label>Conservazione *</label><select id='anag-cons'>" + selezionaCons(d.conservazione) + "</select></div>" +
    "<div><label>Unità di misura *</label><input id='anag-um' value='" + esc(d.unita_misura || "") + "'></div>" +
    "<div><label>Densità g/ml (liquidi)</label><input id='anag-densita' type='number' step='0.001' min='0' value='" + (d.densita || "") + "' placeholder='es. 1,03'>" +
    "<div class='hint'>RIFIN 51: col la densità dichiarata puoi scrivere i grammi anche su un liquido in litri.</div></div>" +
    "<div><label>Sigla (per i lotti in arrivo)</label><input id='anag-sigla' class='mono' value='" + esc(d.sigla || "") + "'></div>" +
    "<div class='full'><label>Note</label><input id='anag-note' value='" + esc(d.note || "") + "'></div>" +
    "<div class='full'><label>Allergeni <span class='muted'>(clic per attivare/disattivare)</span></label>" +
    "<div id='anag-chips' class='chips'></div>" +
    "<div class='hint'>I 14 allergeni obbligatori da etichetta (Reg. UE 1169/2011). I prodotti di laboratorio li ereditano dalla ricetta.</div></div>" +
    "</div>" +
    rigaArrivi(d.arrivi) +
    "<div id='anag-errore' class='f-errore' hidden></div>" +
    "<div class='f-azioni'>" +
    "<button class='btn' id='anag-salva'>Salva modifiche</button>" +
    "<button class='btn sec mini rosso' id='anag-elimina'>🗑 Elimina</button></div>";
  renderChipsAllergeni("anag-chips", ANAG_ATTIVI, true);
  wireChipsDettaglio();
  wireSalvaElimina({
    id: d.id,
    corpo: () => ({
      nome: $("anag-nome").value.trim(),
      denominazione_legale: $("anag-denom").value.trim(),
      marca: $("anag-marca").value.trim(),
      conservazione: $("anag-cons").value,
      unita_misura: $("anag-um").value.trim(),
      densita: $("anag-densita").value === "" ? null : Number($("anag-densita").value),
      sigla: $("anag-sigla").value.trim(),
      note: $("anag-note").value.trim(),
      allergeni: [...ANAG_ATTIVI],
    }),
    tipo: "ingrediente",
    nomeConferma: d.nome,
  });
}

function renderSchedaProdotto(d) {
  $("dettaglio-anagrafica-testo").innerHTML =
    "<h2 style='margin:0 0 6px'>🥣 " + esc(d.nome) + " " +
    (d.famiglia ? '<span class="badge b-gray">' + esc(d.famiglia) + "</span>"
      : '<span class="badge b-amber">senza famiglia</span>') + "</h2>" +
    "<div class='hint'>La famiglia nasce nella ricetta (è il master): qui non si tocca.</div>" +
    "<div class='form-grid'>" +
    "<div><label>Nome *</label><input id='anag-nome' value='" + esc(d.nome) + "'></div>" +
    "<div><label>Sigla (per il codice lotto interno)</label><input id='anag-sigla' class='mono' value='" + esc(d.sigla || "") + "'></div>" +
    "<div><label>Note</label><input id='anag-note' value='" + esc(d.note || "") + "'></div>" +
    "<div class='full'><label>Allergeni (ereditati dalla ricetta)</label><div class='chips'>" +
    (d.allergeni.length
      ? d.allergeni.map(n => '<span class="badge b-red">⚠ ' + esc(n) + "</span>").join(" ")
      : '<span class="muted">nessun allergene dalla ricetta attuale</span>') +
    "</div><div class='hint'>Calcolati dagli ingredienti della ricetta: se cambia la ricetta, cambiano qui. Non si editano a mano.</div></div>" +
    "</div>" +
    "<div class='f-azioni' style='margin-top:10px'>" +
    (d.ha_ricetta
      ? "<button class='btn sec' id='anag-ricetta'>✏️ Modifica la ricetta</button>"
      : "<button class='btn' id='anag-ricetta'>➕ Crea la ricetta di " + esc(d.nome) + " ora</button>") +
    "</div>" +
    rigaProduzioni(d.produzioni || []) +
    "<div id='anag-errore' class='f-errore' hidden></div>" +
    "<div class='f-azioni'>" +
    "<button class='btn' id='anag-salva'>Salva modifiche</button>" +
    "<button class='btn sec mini rosso' id='anag-elimina'>🗑 Elimina</button></div>";
  wireRicettaDallaScheda(d);
  wireSalvaElimina({
    id: d.id,
    corpo: () => ({
      nome: $("anag-nome").value.trim(),
      sigla: $("anag-sigla").value.trim(),
      note: $("anag-note").value.trim(),
    }),
    tipo: "prodotto",
    nomeConferma: d.nome,
  });
}

function renderSchedaFornitore(d) {
  $("dettaglio-anagrafica-testo").innerHTML =
    "<h2 style='margin:0 0 6px'>🚚 " + esc(d.nome) + " " +
    '<span class="badge b-gray">' + d.n_arrivi + " arrivi</span></h2>" +
    "<div class='form-grid'>" +
    "<div><label>Ragione sociale *</label><input id='anag-nome' value='" + esc(d.nome) + "'></div>" +
    "<div><label>Partita IVA</label><input id='anag-piva' class='mono' value='" + esc(d.piva || "") + "'></div>" +
    "<div><label>Telefono</label><input id='anag-tel' value='" + esc(d.telefono || "") + "'></div>" +
    "<div><label>Email</label><input id='anag-email' value='" + esc(d.email || "") + "'></div>" +
    "<div class='full'><label>Note</label><input id='anag-note' value='" + esc(d.note || "") + "'></div>" +
    "</div>" +
    rigaArrivi(d.arrivi) +
    "<div id='anag-errore' class='f-errore' hidden></div>" +
    "<div class='f-azioni'>" +
    "<button class='btn' id='anag-salva'>Salva modifiche</button>" +
    "<button class='btn sec mini rosso' id='anag-elimina'>🗑 Elimina</button></div>";
  wireSalvaEliminaFornitore(d);
}

function wireChipsDettaglio() {
  $("anag-chips").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip-allergene");
    if (!chip) return;
    const id = Number(chip.dataset.id);
    if (ANAG_ATTIVI.has(id)) ANAG_ATTIVI.delete(id);
    else ANAG_ATTIVI.add(id);
    renderChipsAllergeni("anag-chips", ANAG_ATTIVI, true);
  });
}

function wireRicettaDallaScheda(d) {
  $("anag-ricetta").addEventListener("click", async () => {
    RICETTA_DA_ANAGRAFICA = d.id;
    if (d.ha_ricetta) {
      try {
        const r = await fetch("/api/ricette/" + d.id);
        const dati = await r.json();
        if (!r.ok) {
          RICETTA_DA_ANAGRAFICA = null;
          return alert(typeof dati.detail === "string" ? dati.detail : "Ricetta non raggiungibile.");
        }
        apriFormRicetta(dati);
      } catch (e) {
        RICETTA_DA_ANAGRAFICA = null;
        alert("Il server non risponde.");
      }
    } else {
      if (!FAMIGLIE.length) { try { await caricaFamiglie(); } catch (e) { /* si crea a mano */ } }
      apriFormRicetta({ prodotto: d, righe: [] });
      $("nr-titolo").textContent = "Nuova ricetta: " + d.nome;
    }
  });
}

function wireSalvaElimina(cfg) {
  $("anag-salva").addEventListener("click", async () => {
    try {
      const r = await fetch("/api/anagrafiche/prodotti/" + cfg.id, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg.corpo()),
      });
      const dati = await r.json();
      if (!r.ok) {
        $("anag-errore").textContent = typeof dati.detail === "string" ? dati.detail : "Controlla i dati.";
        $("anag-errore").hidden = false;
        return;
      }
      flashAnagrafiche("Anagrafica di " + dati.nome + " aggiornata.");
      anagCombosRivedonoIlMondo();
      if (cfg.tipo === "ingrediente") caricaIngredientiAnag();
      else caricaProdottiAnag();
      ANAG_DETTAGLIO = dati;
      if (dati.tipo === "ingrediente") renderSchedaIngrediente(dati);
      else renderSchedaProdotto(dati);
    } catch (e) {
      $("anag-errore").textContent = "Il server non risponde.";
      $("anag-errore").hidden = false;
    }
  });
  $("anag-elimina").addEventListener("click", async () => {
    if (!confirm('Eliminare "' + cfg.nomeConferma + '"? Possibile solo se non ci sono arrivi, produzioni o ricette che la usano.')) return;
    try {
      const r = await fetch("/api/anagrafiche/prodotti/" + cfg.id, { method: "DELETE" });
      if (r.status === 204) {
        $("dettaglio-anagrafica").hidden = true;
        flashAnagrafiche("Anagrafica eliminata.");
        caricaIngredientiAnag();
        caricaProdottiAnag();
        anagCombosRivedonoIlMondo();
      } else {
        const c = await r.json();
        alert(typeof c.detail === "string" ? c.detail : "Eliminazione rifiutata.");
      }
    } catch (e) {
      alert("Il server non risponde.");
    }
  });
}

function wireSalvaEliminaFornitore(d) {
  $("anag-salva").addEventListener("click", async () => {
    try {
      const r = await fetch("/api/anagrafiche/fornitori/" + d.id, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome: $("anag-nome").value.trim(),
          piva: $("anag-piva").value.trim(),
          telefono: $("anag-tel").value.trim(),
          email: $("anag-email").value.trim(),
          note: $("anag-note").value.trim(),
        }),
      });
      const dati = await r.json();
      if (!r.ok) {
        $("anag-errore").textContent = typeof dati.detail === "string" ? dati.detail : "Controlla i dati.";
        $("anag-errore").hidden = false;
        return;
      }
      flashAnagrafiche("Anagrafica di " + dati.nome + " aggiornata.");
      anagCombosRivedonoIlMondo();
      caricaFornitoriAnag();
      renderSchedaFornitore(dati);
    } catch (e) {
      $("anag-errore").textContent = "Il server non risponde.";
      $("anag-errore").hidden = false;
    }
  });
  $("anag-elimina").addEventListener("click", async () => {
    if (!confirm('Eliminare il fornitore "' + d.nome + '"? Possibile solo se non ha arrivi registrati.')) return;
    try {
      const r = await fetch("/api/anagrafiche/fornitori/" + d.id, { method: "DELETE" });
      if (r.status === 204) {
        $("dettaglio-anagrafica").hidden = true;
        flashAnagrafiche("Fornitore eliminato.");
        caricaFornitoriAnag();
        anagCombosRivedonoIlMondo();
      } else {
        const c = await r.json();
        alert(typeof c.detail === "string" ? c.detail : "Eliminazione rifiutata.");
      }
    } catch (e) {
      alert("Il server non risponde.");
    }
  });
}

$("dettaglio-anagrafica-testo").addEventListener("click", (e) => {
  const va = e.target.closest(".vai-arrivo");
  if (va) return vaiADettaglioArrivo(Number(va.dataset.arrivo));
  const vp = e.target.closest(".vai-produzione");
  if (vp) return vaiADettaglioProduzione(Number(vp.dataset.produzione));
});

$("chiudi-dettaglio-anag").addEventListener("click", () => { $("dettaglio-anagrafica").hidden = true; });

/* ---- le tre modali "+ Nuovo" ---- */

function chiudiOverlay(id) { $(id).hidden = true; }
["overlay-anag-ing", "overlay-anag-for", "overlay-anag-pro", "overlay-anag-dens"].forEach(o =>
  $(o).addEventListener("click", (e) => { if (e.target === e.currentTarget) chiudiOverlay(o); })
);

/* Escape: chiude la finestra modale aperta (una sola è visibile alla volta) */
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("overlay-ricetta").hidden) return chiudiFormRicetta();
  if (!$("overlay-produzione").hidden) return chiudiFormProduzione();
  if (!$("overlay-arrivo").hidden) return chiudiFormArrivo();
  for (const o of ["overlay-anag-pro", "overlay-anag-for", "overlay-anag-ing",
                   "overlay-anag-dens"])
    if (!$(o).hidden) return chiudiOverlay(o);
});

$("anag-nuovo-ing").addEventListener("click", () => {
  ["nai-nome", "nai-denom", "nai-um", "nai-sigla", "nai-marca", "nai-note", "nai-densita"].forEach(i => $(i).value = "");
  $("nai-cons").value = "Frigo";
  NAI_ATTIVI = new Set();
  NAI_DENOM_AUTO = true;
  NAI_DENS_AUTO = true;
  $("nai-densita-hint").textContent = "Il ponte peso↔volume: con la densità puoi scrivere i grammi anche su un liquido in litri (500 g di latte = 0,485 lt nello scarico). Trucco da banco: pesa 100 ml, i grammi letti SONO la densità.";
  $("nai-errore").hidden = true;
  renderChipsAllergeni("nai-chips", NAI_ATTIVI, true);
  $("overlay-anag-ing").hidden = false;
  $("nai-nome").focus();
});

/* RIFIN 51: la densità si SUGGERISCE dal nome (caterva tipica dei liquidi
   di pasticceria, catalogo in um.py): proposta visibile e modificabile,
   mai un numero invisibile. Se il campo l'hai già toccato, non si tocca. */
async function suggerisciDensita() {
  const nome = $("nai-nome").value.trim();
  if (!NAI_DENS_AUTO || !nome || $("nai-densita").value) return;
  try {
    const r = await fetch("/api/anagrafiche/densita-suggerita?nome=" + encodeURIComponent(nome));
    const corpo = await r.json();
    if (corpo.densita) {
      $("nai-densita").value = corpo.densita;
      $("nai-densita-hint").textContent = "Suggerita per '" + corpo.parola + "': controllala e correggila se serve (il valore resta tuo).";
    }
  } catch (e) { /* offline: il campo resta libero, zero fastidi */ }
}

$("nai-nome").addEventListener("input", () => {
  if (NAI_DENOM_AUTO) $("nai-denom").value = $("nai-nome").value;  // suggerita dal nome
  suggerisciDensita();
});

/* RIFIN 53: la creazione rapida di Arrivi suggerisce la densità dal nome
   con la stessa regola della modale grande: prefill finché il campo è
   vuoto, poi il numero è dell'utente (meglio: del suo banco di prova). */
async function suggerisciDensitaQc() {
  const nome = $("qc-prod-nome").value.trim();
  if (!QC_DENS_AUTO || !nome || $("qc-densita").value) return;
  try {
    const r = await fetch("/api/anagrafiche/densita-suggerita?nome=" + encodeURIComponent(nome));
    const corpo = await r.json();
    if (corpo.densita) {
      $("qc-densita").value = corpo.densita;
      $("qc-densita-hint").textContent = "Suggerita per '" + corpo.parola + "' (tabella Densità tipiche): controllala e correggila se serve.";
    }
  } catch (e) { /* offline: campo libero, e il backend la eredita comunque */ }
}

$("qc-prod-nome").addEventListener("input", suggerisciDensitaQc);
$("qc-densita").addEventListener("input", () => { QC_DENS_AUTO = false; });
$("nai-denom").addEventListener("input", () => { NAI_DENOM_AUTO = false; });
$("nai-densita").addEventListener("input", () => { NAI_DENS_AUTO = false; });

/* ============ DENSITÀ TIPICHE (RIFIN 52): catalogo personalizzabile ============
   Le voci aggiunte qui VINCONO sulle predefinite del codice (um.py); il
   matcher resta quello di sempre (parola intera, la più lunga vince). */
let DENS_CUSTOM = [];

function densEsc(t) {
  return String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function mostraErroreDensita(msg) {
  $("dens-errore").textContent = msg;
  $("dens-errore").hidden = false;
}

function renderDensitaTipiche(predefinite) {
  const riga = (parola, d, mia) =>
    '<div class="dens-riga"><span class="parola">' + densEsc(parola) + "</span>" +
    "<span>" + String(d).replace(".", ",") + " g/ml " +
    (mia ? '<button class="btn sec" data-dens-del="' + densEsc(parola) + '" title="Togli la tua voce">✕</button>'
         : '<span class="badge b-gray">catalogo</span>') + "</span></div>";
  $("dens-lista").innerHTML =
    (DENS_CUSTOM.length ? ""
      : '<div class="dens-riga hint">Nessuna voce tua: il suggerimento arriva tutto dal catalogo interno.</div>') +
    DENS_CUSTOM.map(v => riga(v.parola, v.densita, true)).join("") +
    '<div class="dens-riga hint">Predefinite (non si eliminano: per cambiarle aggiungi la stessa parola con il tuo valore):</div>' +
    predefinite.map(v => riga(v.parola, v.densita, false)).join("");
}

async function apriDensitaTipiche() {
  $("dens-parola").value = "";
  $("dens-val").value = "";
  $("dens-errore").hidden = true;
  $("overlay-anag-dens").hidden = false;
  $("dens-lista").innerHTML = '<div class="loading">carico i dati…</div>';
  try {
    const r = await fetch("/api/anagrafiche/densita-custom");
    const corpo = await r.json();
    DENS_CUSTOM = corpo.custom || [];
    renderDensitaTipiche(corpo.predefinite || []);
  } catch (e) {
    $("dens-lista").innerHTML = '<div class="loading">Il server non risponde.</div>';
  }
}

$("anag-dens-btn").addEventListener("click", apriDensitaTipiche);
$("dens-chiudi").addEventListener("click", () => chiudiOverlay("overlay-anag-dens"));

$("dens-lista").addEventListener("click", async (e) => {
  const del = e.target.closest("[data-dens-del]");
  if (!del) return;
  if (!confirm('Togliere la tua voce "' + del.dataset.densDel +
    '"? Se esiste anche nel catalogo interno, quella torna a farsi avanti.')) return;
  try {
    const r = await fetch("/api/anagrafiche/densita-custom/" +
      encodeURIComponent(del.dataset.densDel), { method: "DELETE" });
    if (r.status === 204) { flashAnagrafiche("Voce tolta."); apriDensitaTipiche(); }
    else mostraErroreDensita("Eliminazione rifiutata.");
  } catch (e) { mostraErroreDensita("Il server non risponde."); }
});

$("dens-aggiungi").addEventListener("click", async () => {
  const parola = $("dens-parola").value.trim();
  const val = $("dens-val").value;
  if (!parola) return mostraErroreDensita("Inserisci la parola del nome (es. latte).");
  if (!val) return mostraErroreDensita("Inserisci la densità in g/ml (es. 1,04).");
  $("dens-errore").hidden = true;
  try {
    const r = await fetch("/api/anagrafiche/densita-custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parola: parola, densita: Number(val) }),
    });
    if (!r.ok) {
      const c = await r.json();
      return mostraErroreDensita(typeof c.detail === "string" ? c.detail : "Creazione rifiutata.");
    }
    flashAnagrafiche('Voce "' + parola + '" salvata: vince sul catalogo.');
    apriDensitaTipiche();
  } catch (e) { mostraErroreDensita("Il server non risponde."); }
});

$("nai-chips").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip-allergene");
  if (!chip) return;
  const id = Number(chip.dataset.id);
  if (NAI_ATTIVI.has(id)) NAI_ATTIVI.delete(id);
  else NAI_ATTIVI.add(id);
  renderChipsAllergeni("nai-chips", NAI_ATTIVI, true);
});

$("nai-annulla").addEventListener("click", () => chiudiOverlay("overlay-anag-ing"));

$("nai-salva").addEventListener("click", async () => {
  const nome = $("nai-nome").value.trim();
  if (!nome) { $("nai-errore").textContent = "Inserisci il nome."; $("nai-errore").hidden = false; return; }
  try {
    const r = await fetch("/api/anagrafiche/ingredienti", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nome: nome,
        denominazione_legale: $("nai-denom").value.trim(),
        marca: $("nai-marca").value.trim() || null,
        conservazione: $("nai-cons").value,
        unita_misura: $("nai-um").value.trim(),
        sigla: $("nai-sigla").value.trim() || null,
        densita: $("nai-densita").value === "" ? null : Number($("nai-densita").value),
        note: $("nai-note").value.trim() || null,
        allergeni: [...NAI_ATTIVI],
      }),
    });
    const corpo = await r.json();
    if (!r.ok) {
      $("nai-errore").textContent = typeof corpo.detail === "string" ? corpo.detail : "Controlla i dati.";
      $("nai-errore").hidden = false;
      return;
    }
    chiudiOverlay("overlay-anag-ing");
    flashAnagrafiche('Ingrediente "' + corpo.nome + '" creato.');
    caricaIngredientiAnag();
    anagCombosRivedonoIlMondo();
    apriDettaglioAnagrafica(corpo.id);
  } catch (e) {
    $("nai-errore").textContent = "Il server non risponde.";
    $("nai-errore").hidden = false;
  }
});

$("anag-nuovo-for").addEventListener("click", () => {
  ["naf-nome", "naf-piva", "naf-tel", "naf-email", "naf-note"].forEach(i => $(i).value = "");
  $("naf-errore").hidden = true;
  $("overlay-anag-for").hidden = false;
  $("naf-nome").focus();
});

$("naf-annulla").addEventListener("click", () => chiudiOverlay("overlay-anag-for"));

$("naf-salva").addEventListener("click", async () => {
  const nome = $("naf-nome").value.trim();
  if (!nome) { $("naf-errore").textContent = "Inserisci la ragione sociale."; $("naf-errore").hidden = false; return; }
  try {
    const r = await fetch("/api/anagrafiche/fornitori", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nome: nome,
        piva: $("naf-piva").value.trim() || null,
        telefono: $("naf-tel").value.trim() || null,
        email: $("naf-email").value.trim() || null,
        note: $("naf-note").value.trim() || null,
      }),
    });
    const corpo = await r.json();
    if (!r.ok) {
      $("naf-errore").textContent = typeof corpo.detail === "string" ? corpo.detail : "Controlla i dati.";
      $("naf-errore").hidden = false;
      return;
    }
    chiudiOverlay("overlay-anag-for");
    flashAnagrafiche('Fornitore "' + corpo.nome + '" creato.');
    caricaFornitoriAnag();
    anagCombosRivedonoIlMondo();
    apriDettaglioFornitore(corpo.id);
  } catch (e) {
    $("naf-errore").textContent = "Il server non risponde.";
    $("naf-errore").hidden = false;
  }
});

/* ---- nuovo prodotto di laboratorio: l'anagrafica nasce qui,
   la ricetta SUBITO dopo (gerarchia: il master è la ricetta) ---- */

$("anag-nuovo-pro").addEventListener("click", () => {
  ["nap-nome", "nap-sigla"].forEach(i => $(i).value = "");
  $("nap-errore").hidden = true;
  $("overlay-anag-pro").hidden = false;
  $("nap-nome").focus();
});

$("nap-annulla").addEventListener("click", () => chiudiOverlay("overlay-anag-pro"));

$("nap-salva").addEventListener("click", async () => {
  const nome = $("nap-nome").value.trim();
  if (!nome) { $("nap-errore").textContent = "Inserisci un nome."; $("nap-errore").hidden = false; return; }
  $("nap-salva").disabled = true;
  try {
    const r = await fetch("/api/ricette/nuovo-prodotto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // niente più u.m.: al prodotto di laboratorio pensa la resa
      // della ricetta ('5 kg'), che è già autosufficiente
      body: JSON.stringify({ nome: nome, sigla: $("nap-sigla").value.trim() || null }),
    });
    const corpo = await r.json();
    if (!r.ok) {
      $("nap-errore").textContent = typeof corpo.detail === "string" ? corpo.detail : "Controlla i dati.";
      $("nap-errore").hidden = false;
      return;
    }
    chiudiOverlay("overlay-anag-pro");
    flashAnagrafiche('Prodotto "' + corpo.nome + '" creato: ora la sua ricetta.');
    // gerarchia stretta: l'anagrafica esiste, ma è la ricetta il master:
    // si apre subito, e al salvataggio si torna qui aggiornati
    RICETTA_DA_ANAGRAFICA = corpo.id;
    if (!FAMIGLIE.length) { try { await caricaFamiglie(); } catch (e) { /* si crea a mano */ } }
    apriFormRicetta({ prodotto: { id: corpo.id, nome: corpo.nome, unita_misura: corpo.unita_misura }, righe: [] });
    $("nr-titolo").textContent = "Nuova ricetta: " + corpo.nome;
    // RIFIN 45: dichiara il candidato DOPO apriFormRicetta (che azzera):
    // annullando la modale senza salvare, lui se ne va col form
    NUOVO_CANDIDATO_ID = corpo.id;
  } catch (e) {
    $("nap-errore").textContent = "Il server non risponde.";
    $("nap-errore").hidden = false;
  } finally {
    $("nap-salva").disabled = false;
  }
});

/* ---- famiglie: nuova riga inline ---- */

$("anag-fam-nuovo").addEventListener("click", () => {
  $("fam-nuova-nome").value = "";
  $("anag-fam-errore").hidden = true;
  $("anag-fam-nuova-riga").hidden = false;
  $("fam-nuova-nome").focus();
});

$("fam-nuova-annulla").addEventListener("click", () => { $("anag-fam-nuova-riga").hidden = true; });

$("fam-nuova-aggiungi").addEventListener("click", async () => {
  const nome = $("fam-nuova-nome").value.trim();
  if (!nome) return mostraErroreFamiglia("Inserisci il nome della famiglia.");
  try {
    const r = await fetch("/api/anagrafiche/famiglie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome }),
    });
    if (!r.ok) {
      const c = await r.json();
      return mostraErroreFamiglia(typeof c.detail === "string" ? c.detail : "Creazione rifiutata.");
    }
    $("anag-fam-nuova-riga").hidden = true;
    $("anag-fam-errore").hidden = true;
    flashAnagrafiche('Famiglia "' + nome + '" creata.');
    caricaFamiglieAnag();
    anagCombosRivedonoIlMondo();
  } catch (e) {
    mostraErroreFamiglia("Il server non risponde.");
  }
});

/* ---- unità di misura: nuova riga inline ---- */

$("anag-um-nuovo").addEventListener("click", () => {
  $("um-nuova-nome").value = "";
  $("anag-um-errore").hidden = true;
  $("anag-um-nuova-riga").hidden = false;
  $("um-nuova-nome").focus();
});

$("um-nuova-annulla").addEventListener("click", () => { $("anag-um-nuova-riga").hidden = true; });

$("um-nuova-aggiungi").addEventListener("click", async () => {
  const nome = $("um-nuova-nome").value.trim();
  if (!nome) return mostraErroreUm("Inserisci il nome dell'unità di misura.");
  try {
    const r = await fetch("/api/anagrafiche/unita-misura", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nome: nome }),
    });
    if (!r.ok) {
      const c = await r.json();
      return mostraErroreUm(typeof c.detail === "string" ? c.detail : "Creazione rifiutata.");
    }
    $("anag-um-nuova-riga").hidden = true;
    $("anag-um-errore").hidden = true;
    flashAnagrafiche('Unità di misura "' + nome + '" creata.');
    caricaUnitaAnag();
  } catch (e) {
    mostraErroreUm("Il server non risponde.");
  }
});

/* ========================= PRODUTTORE ========================= */

async function avviaProduttore() {
  try {
    const r = await fetch("/api/impostazioni");
    const dati = await r.json();
    $("prod-ragione").value = dati.ragione_sociale || "";
    $("prod-indirizzo").value = dati.indirizzo || "";
    $("prod-piva").value = dati.piva || "";
  } catch (e) {
    // server giù: i campi restano vuoti, l'utente riprova a salvare dopo
  }
  aggiornaAnteprimaProduttore();
}

function aggiornaAnteprimaProduttore() {
  const ragione = $("prod-ragione").value.trim();
  const indirizzo = $("prod-indirizzo").value.trim();
  const piva = $("prod-piva").value.trim();
  // in fondo all'etichetta il recapito è UNA riga sola: indirizzo · P.IVA
  const fondo = [indirizzo, piva ? "P.IVA " + piva : ""]
    .filter(p => p).join(" · ");
  // l'anteprima parla subito: mostra il posto che i dati vanno a occupare
  $("ant-ragione").textContent = ragione || "(ragione sociale)";
  $("ant-ragione").classList.toggle("muted", !ragione);
  $("ant-indirizzo").textContent = fondo || "(indirizzo · P.IVA)";
  $("ant-indirizzo").classList.toggle("muted", !fondo);
}

$("prod-ragione").addEventListener("input", aggiornaAnteprimaProduttore);
$("prod-indirizzo").addEventListener("input", aggiornaAnteprimaProduttore);
$("prod-piva").addEventListener("input", aggiornaAnteprimaProduttore);

$("prod-salva").addEventListener("click", async () => {
  const bottone = $("prod-salva");
  bottone.disabled = true;
  try {
    const r = await fetch("/api/impostazioni", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ragione_sociale: $("prod-ragione").value,
        indirizzo: $("prod-indirizzo").value,
        piva: $("prod-piva").value,
      }),
    });
    if (!r.ok) throw new Error("errore http");
    $("prod-errore").hidden = true;
    bottone.textContent = "✔ Salvato";
    setTimeout(() => { bottone.textContent = "💾 Salva"; bottone.disabled = false; }, 1500);
  } catch (e) {
    $("prod-errore").textContent = "Il server non risponde.";
    $("prod-errore").hidden = false;
    bottone.disabled = false;
  }
});
