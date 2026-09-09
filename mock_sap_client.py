import json
import os
import datetime
import itertools

LEDGER_PATH = os.path.join("data", "mock_sap_ledger.json")

_doc_counter = itertools.count(100001)


def _load_ledger():
    if not os.path.exists(LEDGER_PATH):
        return {"documents": []}
    with open(LEDGER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_ledger(ledger):
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)


def get_material_stock(material=None, plant=None):
    """
    Versi mock dari GET /A_MaterialStock. Mengembalikan histori dokumen
    yang sudah pernah "dieksekusi" lewat mock ini, meniru bentuk response
    SAP OData (list of records di key 'd.results').
    """
    ledger = _load_ledger()
    results = ledger["documents"]
    if material:
        results = [r for r in results if r["Material"] == material]
    if plant:
        results = [r for r in results if r["Plant"] == plant]
    return {"d": {"results": results}}


def post_goods_movement(material, plant, storage_location, quantity, unit="PC",
                         movement_type="501", posting_date=None):
    """
    Versi mock dari POST ke API_MATERIAL_DOCUMENT_SRV. Tidak memanggil
    jaringan apapun - hanya mencatat "dokumen" baru ke file ledger lokal
    dan mengembalikan nomor dokumen palsu, dengan struktur field yang
    meniru response SAP asli (MaterialDocument, MaterialDocumentYear, dst).
    """
    if posting_date is None:
        posting_date = datetime.date.today().isoformat() + "T00:00:00"

    doc_number = f"MOCK-{next(_doc_counter)}"

    record = {
        "MaterialDocument": doc_number,
        "MaterialDocumentYear": str(datetime.date.today().year),
        "PostingDate": posting_date,
        "GoodsMovementType": movement_type,
        "Material": material,
        "Plant": plant,
        "StorageLocation": storage_location,
        "QuantityInEntryUnit": str(quantity),
        "EntryUnit": unit,
        "Source": "mock_sap_client (simulasi SAP saja)",
    }

    ledger = _load_ledger()
    ledger["documents"].append(record)
    _save_ledger(ledger)

    return {"d": record}