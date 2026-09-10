const fmtIDR = (n) => "Rp" + Number(n).toLocaleString("id-ID");

// Angka positif = agent memperkirakan hemat/untung, negatif = rugi kalau dipaksa transfer
const fmtImpact = (n) => (n >= 0 ? `Hemat ${fmtIDR(n)}` : `Rugi ${fmtIDR(Math.abs(n))}`);

let currentStockData = null;

function setStatus(mode, label) {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusLabel");
  dot.className = "status-dot" + (mode ? " " + mode : "");
  text.textContent = label;
}

// input

function renderStockTable(stockData) {
  currentStockData = stockData;
  const head = document.getElementById("stockTableHead");
  const body = document.getElementById("stockTableBody");

  head.innerHTML = `
    <th>Material</th>
    <th>Gudang</th>
    <th>Stok Saat Ini</th>
    <th>Reorder Point</th>
    <th>Demand Harian</th>
  `;

  body.innerHTML = "";
  const { materials, warehouses, warehouse_names } = stockData;

  Object.entries(materials).forEach(([matCode, mat]) => {
    warehouses.forEach((wh) => {
      const stock = mat.stock[wh];
      const reorder = mat.reorder_point[wh];
      const isLow = stock < reorder;
      const isHigh = stock > reorder * 1.5;

      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${mat.name}</td>
        <td>${warehouse_names[wh]}</td>
        <td>
          <input type="number" min="0"
                 class="stock-input ${isLow ? "cell-danger" : isHigh ? "cell-warning" : ""}"
                 data-material="${matCode}" data-warehouse="${wh}" value="${stock}">
        </td>
        <td>${reorder}</td>
        <td>${mat.avg_daily_demand[wh]}</td>
      `;
      body.appendChild(row);
    });
  });
}

async function loadState() {
  const res = await fetch("/api/state");
  const data = await res.json();
  renderStockTable(data.stock_data);
}

async function saveStock() {
  const inputs = document.querySelectorAll(".stock-input");
  const updates = Array.from(inputs).map((el) => ({
    material_code: el.dataset.material,
    warehouse: el.dataset.warehouse,
    quantity: parseInt(el.value || "0", 10),
  }));

  const btn = document.getElementById("btnSaveStock");
  btn.disabled = true;
  btn.textContent = "Menyimpan...";

  const res = await fetch("/api/state/stock", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });
  const data = await res.json();
  renderStockTable(data.stock_data);

  btn.disabled = false;
  btn.textContent = "Simpan Perubahan Stok";
}

async function resetState() {
  if (!confirm("Reset semua data stok ke kondisi awal dan kosongkan riwayat dokumen?")) return;
  await fetch("/api/state/reset", { method: "POST" });
  await loadState();
  await loadLedger();
  document.getElementById("resultsFeed").innerHTML = "";
  document.getElementById("resultsEmpty").style.display = "block";
  document.getElementById("runHint").textContent = "";
  setStatus("", "Agent siap");
}

// process and output

function renderResults(results) {
  const feed = document.getElementById("resultsFeed");
  const empty = document.getElementById("resultsEmpty");
  feed.innerHTML = "";

  if (results.length === 0) {
    empty.style.display = "block";
    empty.textContent = "Tidak ada ketimpangan stok yang terdeteksi saat ini, semua gudang dalam kondisi seimbang.";
    return;
  }
  empty.style.display = "none";

  results.forEach((r) => {
    const approved = r.decision.recommend_transfer && r.decision.suggested_quantity > 0;
    const card = document.createElement("div");
    card.className = "result-card " + (approved ? "approved" : "rejected");

    card.innerHTML = `
      <div class="result-top">
        <div class="result-route">
          ${r.material_name} - ${r.source_wh_name}<span class="arrow">&rarr;</span>${r.target_wh_name}
        </div>
        <span class="badge ${approved ? "approved" : "rejected"}">
          ${approved ? "TRANSFER DISETUJUI" : "TRANSFER DITOLAK"}
        </span>
      </div>
      <div class="result-meta">
        <span>Stok sumber: ${r.source_stock}</span>
        <span>Stok tujuan: ${r.target_stock}</span>
        <span>Ongkos kirim: ${fmtIDR(r.shipping_cost)}</span>
        <span>Lead time: ${r.lead_time_days} hari</span>
        <span>${fmtImpact(r.decision.estimated_impact_idr)}</span>
      </div>
      <p class="result-reasoning">${r.decision.reasoning}</p>
      ${
        approved
          ? `<div class="result-doc">Dokumen SAP (mock): ${r.action.MaterialDocument} · qty ${r.action.QuantityInEntryUnit} · movement type ${r.action.GoodsMovementType}</div>`
          : ""
      }
    `;
    feed.appendChild(card);
  });
}

async function runAgent() {
  const btn = document.getElementById("btnRun");
  const label = document.getElementById("btnRunLabel");
  const hint = document.getElementById("runHint");

  btn.disabled = true;
  label.textContent = "Agent sedang berjalan...";
  setStatus("running", "Memproses...");
  hint.textContent = "";

  try {
    const res = await fetch("/api/run", { method: "POST" });
    const data = await res.json();
    renderResults(data.results);
    hint.textContent = `${data.candidate_count} kandidat ketimpangan ditemukan dan dievaluasi.`;
    setStatus("done", "Selesai");
    await loadState();
    await loadLedger();
  } catch (e) {
    hint.textContent = "Terjadi error saat menjalankan agent. Cek console browser untuk detail.";
    setStatus("", "Error");
    console.error(e);
  } finally {
    btn.disabled = false;
    label.textContent = "Jalankan Analisis Agent";
  }
}

// --------------------------------------------------------------------
// Simulator manual
// --------------------------------------------------------------------

async function runSimulation(e) {
  e.preventDefault();
  const box = document.getElementById("simResult");
  box.textContent = "Memproses...";

  const context = {
    material_name: document.getElementById("sim_material_name").value,
    source_wh: document.getElementById("sim_source_wh").value,
    source_stock: parseFloat(document.getElementById("sim_source_stock").value),
    source_reorder: parseFloat(document.getElementById("sim_source_reorder").value),
    target_wh: document.getElementById("sim_target_wh").value,
    target_stock: parseFloat(document.getElementById("sim_target_stock").value),
    target_reorder: parseFloat(document.getElementById("sim_target_reorder").value),
    target_demand: parseFloat(document.getElementById("sim_target_demand").value),
    margin_per_unit: parseFloat(document.getElementById("sim_margin").value),
    shipping_cost: parseFloat(document.getElementById("sim_shipping").value),
    lead_time_days: parseFloat(document.getElementById("sim_leadtime").value),
  };

  const res = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(context),
  });
  const data = await res.json();

  if (data.error) {
    box.innerHTML = `<p class="result-reasoning">${data.error}</p>`;
    return;
  }

  const d = data.decision;
  const approved = d.recommend_transfer && d.suggested_quantity > 0;
  box.innerHTML = `
    <div class="result-card ${approved ? "approved" : "rejected"}">
      <div class="result-top">
        <div class="result-route">${context.source_wh}<span class="arrow">&rarr;</span>${context.target_wh}</div>
        <span class="badge ${approved ? "approved" : "rejected"}">${approved ? "DIREKOMENDASIKAN" : "DITOLAK"}</span>
      </div>
      <div class="result-meta">
        <span>Kuantitas disarankan: ${d.suggested_quantity}</span>
        <span>${fmtImpact(d.estimated_impact_idr)}</span>
      </div>
      <p class="result-reasoning">${d.reasoning}</p>
    </div>
  `;
}

// --------------------------------------------------------------------
// Ledger
// --------------------------------------------------------------------

async function loadLedger() {
  const res = await fetch("/api/ledger");
  const data = await res.json();
  const body = document.getElementById("ledgerTableBody");
  const empty = document.getElementById("ledgerEmpty");
  body.innerHTML = "";

  if (!data.documents || data.documents.length === 0) {
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  data.documents
    .slice()
    .reverse()
    .forEach((doc) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${doc.MaterialDocument}</td>
        <td>${doc.Material}</td>
        <td>${doc.Plant}</td>
        <td>${doc.QuantityInEntryUnit} ${doc.EntryUnit}</td>
        <td>${doc.GoodsMovementType}</td>
        <td>${doc.PostingDate}</td>
      `;
      body.appendChild(row);
    });
}

// --------------------------------------------------------------------
// Init
// --------------------------------------------------------------------

document.getElementById("btnSaveStock").addEventListener("click", saveStock);
document.getElementById("btnReset").addEventListener("click", resetState);
document.getElementById("btnRun").addEventListener("click", runAgent);
document.getElementById("simForm").addEventListener("submit", runSimulation);

loadState();
loadLedger();
