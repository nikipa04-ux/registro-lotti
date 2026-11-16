/* Registro Lotti - dashboard.
   L'UI è "stupida" di proposito: chiede i dati a /api/dashboard e li mostra.
   Nessuna regola di business qui: scadenze, contatori e colori arrivano
   dal server (app/logic/dashboard.py). */

const $ = (id) => document.getElementById(id);

// Badge della scadenza: rosso <=3 giorni, ambra <=7, verde oltre.
// (Rappresentazione: la REGOLA di quali lotti contare sta nel server,
//  qui si colora solo in base ai giorni che il server riporta.)
function badgeScadenza(riga) {
  const g = riga.giorni;
  if (g < 0) return '<span class="badge b-gray">scaduto</span>';
  if (g <= 3) return '<span class="badge b-red">' + riga.scadenza + ' · ' + g + 'g</span>';
  if (g <= 7) return '<span class="badge b-amber">' + riga.scadenza + ' · ' + g + 'g</span>';
  return '<span class="badge b-green">' + riga.scadenza + '</span>';
}

function esc(s) {
  // Sicurezza di base: il testo del DB non entra mai come HTML grezzo
  return String(s).replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

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
    "<td>" + badgeScadenza(r) + "</td></tr>").join("");
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

caricaDashboard();
