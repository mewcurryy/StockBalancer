# StockBalancer Web (POC)

Website sederhana (Flask + HTML/CSS/JS vanilla, tanpa build step) yang membungkus
logic agent yang sudah ada: `reasoning_engine.py` (mode `rule_based`) dan
`mock_sap_client.py` (simulasi SAP, tersimpan sebagai file JSON lokal).

Tidak butuh API key atau koneksi internet sama sekali — semuanya jalan 100% lokal.

## Cara menjalankan

```bash
cd stockbalancer-web
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Buka **http://127.0.0.1:5000** di browser.

## Alur di halaman web

1. **Input** — tabel stok 4 gudang x 2 material. Klik angka di kolom "Stok Saat Ini"
   untuk mengubah skenario, lalu klik **Simpan Perubahan Stok**.
2. **Process** — klik **Jalankan Analisis Agent**. Ini menjalankan siklus penuh:
   scan stok → deteksi ketimpangan → reasoning engine → keputusan → (kalau disetujui)
   membuat "Material Document" mock di SAP, dan meng-update angka stok.
3. **Output** — daftar setiap kandidat ketimpangan yang ditemukan, disetujui atau
   ditolak, lengkap dengan alasannya. Kalau disetujui, ada nomor dokumen mock.

Di bawahnya juga ada:
- **Uji Reasoning Engine Secara Manual** — form untuk mencoba reasoning engine dengan
  angka bebas, tanpa menyentuh data gudang atau ledger.
- **Riwayat Dokumen SAP (mock)** — semua dokumen yang pernah dibuat agent, dari
  `data/mock_sap_ledger.json`.

Tombol **Reset ke Data Awal** mengembalikan `data/stock_data.json` ke kondisi semula
dan mengosongkan ledger — berguna untuk demo berulang kali.

## Catatan tentang data contoh default

Dengan angka default di `data/stock_data.json`, reasoning engine (`reason_with_rules`)
menghitung "potensi kerugian akibat stockout" hanya berdasarkan selisih antara
`demand_harian x lead_time` dan stok tujuan saat ini. Karena lead time di data dummy
relatif pendek (2–5 hari), beberapa kasus yang lolos deteksi ketimpangan (stok di
bawah reorder point) ternyata belum defisit dalam jangka waktu itu — sehingga
**bisa saja semua kandidat awal menghasilkan "TRANSFER DITOLAK"**. Ini bukan bug, tapi
konsekuensi wajar dari logika cost-benefit yang sudah kamu tulis sendiri.

Kalau untuk demo kamu ingin memastikan setidaknya satu kasus **disetujui**, cara paling
gampang: sebelum klik "Jalankan Analisis Agent", turunkan salah satu angka "Stok Saat
Ini" di gudang tujuan jadi jauh lebih kecil (misal 5–10), lalu simpan dan jalankan lagi.
Atau gunakan panel "Uji Reasoning Engine Secara Manual" di bawah, yang sudah diisi
contoh angka yang menghasilkan keputusan "disetujui".

## Struktur file

```
stockbalancer-web/
├── app.py                     Flask app + semua endpoint API
├── reasoning_engine.py        Reasoning engine (rule_based / claude) — tidak diubah
├── mock_sap_client.py         Simulasi SAP (ledger JSON lokal) — tidak diubah
├── requirements.txt
├── data/
│   ├── stock_data.json        Data stok yang aktif (bisa berubah lewat UI)
│   ├── stock_data.default.json  Backup untuk tombol "Reset ke Data Awal"
│   ├── shipping_cost.json
│   └── mock_sap_ledger.json   Riwayat dokumen mock (terisi otomatis)
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── app.js
```
