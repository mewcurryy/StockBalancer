import json
import os
import shutil

from flask import Flask, jsonify, request, render_template

import reasoning_engine
import mock_sap_client

app = Flask(__name__)

DATA_DIR = "data"
STOCK_PATH = os.path.join(DATA_DIR, "stock_data.json")
SHIPPING_PATH = os.path.join(DATA_DIR, "shipping_cost.json")
STOCK_DEFAULT_PATH = os.path.join(DATA_DIR, "stock_data.default.json")
LEDGER_PATH = os.path.join(DATA_DIR, "mock_sap_ledger.json")

OVERSTOCK_MULTIPLIER = 1.5  # dianggap overstock kalau stok > reorder_point x 1.5

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def detect_imbalances(stock_data):
    """Cari pasangan gudang (sumber overstock, tujuan understock) untuk material yang sama."""
    imbalances = []
    materials = stock_data["materials"]
    warehouses = stock_data["warehouses"]

    for mat_code, mat in materials.items():
        for source_wh in warehouses:
            for target_wh in warehouses:
                if source_wh == target_wh:
                    continue
                source_stock = mat["stock"][source_wh]
                source_reorder = mat["reorder_point"][source_wh]
                target_stock = mat["stock"][target_wh]
                target_reorder = mat["reorder_point"][target_wh]

                is_overstock = source_stock > source_reorder * OVERSTOCK_MULTIPLIER
                is_understock = target_stock < target_reorder

                if is_overstock and is_understock:
                    imbalances.append(
                        {
                            "material_code": mat_code,
                            "material_name": mat["name"],
                            "margin_per_unit": mat["margin_per_unit_idr"],
                            "source_wh": source_wh,
                            "source_stock": source_stock,
                            "source_reorder": source_reorder,
                            "target_wh": target_wh,
                            "target_stock": target_stock,
                            "target_reorder": target_reorder,
                            "target_demand": mat["avg_daily_demand"][target_wh],
                        }
                    )
    return imbalances


def enrich_with_shipping(imbalance, shipping_data):
    key = f"{imbalance['source_wh']}->{imbalance['target_wh']}"
    shipping = shipping_data["shipping"][key]
    imbalance["shipping_cost"] = shipping["cost_idr"]
    imbalance["lead_time_days"] = shipping["lead_time_days"]
    return imbalance


def apply_transfer_to_stock(stock_data, imbalance, quantity):
    """Setelah transfer 'dieksekusi', update angka stok supaya efeknya terlihat di run berikutnya."""
    mat = stock_data["materials"][imbalance["material_code"]]
    mat["stock"][imbalance["source_wh"]] = max(0, mat["stock"][imbalance["source_wh"]] - quantity)
    mat["stock"][imbalance["target_wh"]] = mat["stock"][imbalance["target_wh"]] + quantity

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/state", methods=["GET"])
def get_state():
    """INPUT: kirim data stok & ongkos kirim saat ini ke frontend."""
    stock_data = load_json(STOCK_PATH)
    shipping_data = load_json(SHIPPING_PATH)
    return jsonify({"stock_data": stock_data, "shipping_data": shipping_data})


@app.route("/api/state/stock", methods=["POST"])
def update_stock():
    """INPUT: simpan perubahan angka stok yang diedit user di tabel."""
    payload = request.get_json(force=True)
    stock_data = load_json(STOCK_PATH)
    for u in payload.get("updates", []):
        mat = stock_data["materials"].get(u["material_code"])
        if mat and u["warehouse"] in mat["stock"]:
            mat["stock"][u["warehouse"]] = int(u["quantity"])
    save_json(STOCK_PATH, stock_data)
    return jsonify({"stock_data": stock_data})


@app.route("/api/state/reset", methods=["POST"])
def reset_state():
    shutil.copyfile(STOCK_DEFAULT_PATH, STOCK_PATH)
    save_json(LEDGER_PATH, {"documents": []})
    return jsonify({"status": "ok"})


@app.route("/api/run", methods=["POST"])
def run_agent():
    stock_data = load_json(STOCK_PATH)
    shipping_data = load_json(SHIPPING_PATH)
    wh_names = stock_data["warehouse_names"]

    imbalances = detect_imbalances(stock_data)
    results = []

    for imbalance in imbalances:
        imbalance = enrich_with_shipping(imbalance, shipping_data)
        decision = reasoning_engine.get_decision(imbalance)

        action = None
        if decision["recommend_transfer"] and decision["suggested_quantity"] > 0:
            qty = decision["suggested_quantity"]
            doc = mock_sap_client.post_goods_movement(
                material=imbalance["material_code"],
                plant=imbalance["target_wh"],
                storage_location=imbalance["target_wh"],
                quantity=qty,
            )
            apply_transfer_to_stock(stock_data, imbalance, qty)
            action = doc["d"]

        results.append(
            {
                "material_code": imbalance["material_code"],
                "material_name": imbalance["material_name"],
                "source_wh": imbalance["source_wh"],
                "source_wh_name": wh_names[imbalance["source_wh"]],
                "target_wh": imbalance["target_wh"],
                "target_wh_name": wh_names[imbalance["target_wh"]],
                "source_stock": imbalance["source_stock"],
                "target_stock": imbalance["target_stock"],
                "shipping_cost": imbalance["shipping_cost"],
                "lead_time_days": imbalance["lead_time_days"],
                "decision": decision,
                "action": action,
            }
        )

    save_json(STOCK_PATH, stock_data)  # simpan efek transfer supaya kelihatan di run berikutnya

    return jsonify({"candidate_count": len(imbalances), "results": results})


@app.route("/api/simulate", methods=["POST"])
def simulate():
    """
    Uji reasoning engine langsung dengan angka manual (input bebas dari user),
    tanpa menyentuh data/stock_data.json atau ledger. Berguna untuk eksperimen cepat.
    """
    context = request.get_json(force=True)
    required = [
        "material_name", "source_wh", "source_stock", "source_reorder",
        "target_wh", "target_stock", "target_reorder", "target_demand",
        "margin_per_unit", "shipping_cost", "lead_time_days",
    ]
    missing = [k for k in required if k not in context]
    if missing:
        return jsonify({"error": f"Field wajib diisi: {', '.join(missing)}"}), 400

    decision = reasoning_engine.get_decision(context)
    return jsonify({"decision": decision})


@app.route("/api/ledger", methods=["GET"])
def get_ledger():
    """Riwayat semua dokumen SAP (mock) yang pernah dibuat agent."""
    if not os.path.exists(LEDGER_PATH):
        return jsonify({"documents": []})
    return jsonify(load_json(LEDGER_PATH))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
