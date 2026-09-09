import json
import os
from dotenv import load_dotenv

load_dotenv()  # baca file .env kalau ada (opsional, hanya dibutuhkan untuk mode claude)

import reasoning_engine
import mock_sap_client

OVERSTOCK_MULTIPLIER = 1.5  # dianggap overstock kalau stok > reorder_point x 1.5


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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


def print_header(text):
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def main():
    print_header("STOCKBALANCER AGENT — MULAI MONITORING (MODE MOCK, TANPA SAP/AWS ASLI)")
    print(f"Mode reasoning: {os.environ.get('REASONING_MODE', 'rule_based')}")

    stock_data = load_json("data/stock_data.json")
    shipping_data = load_json("data/shipping_cost.json")
    wh_names = stock_data["warehouse_names"]

    print_header("STEP 1-2: SCAN STOK & DETEKSI KETIMPANGAN")
    imbalances = detect_imbalances(stock_data)
    print(f"Ditemukan {len(imbalances)} kandidat ketimpangan stok.")

    for idx, imbalance in enumerate(imbalances, start=1):
        imbalance = enrich_with_shipping(imbalance, shipping_data)

        print_header(
            f"KANDIDAT #{idx}: {imbalance['material_name']} | "
            f"{wh_names[imbalance['source_wh']]} -> {wh_names[imbalance['target_wh']]}"
        )
        print(f"  Stok sumber   : {imbalance['source_stock']} (reorder point {imbalance['source_reorder']})")
        print(f"  Stok tujuan   : {imbalance['target_stock']} (reorder point {imbalance['target_reorder']})")
        print(f"  Ongkos kirim  : Rp{imbalance['shipping_cost']:,}")
        print(f"  Lead time     : {imbalance['lead_time_days']} hari")

        print("\n  >> Memanggil reasoning engine...")
        decision = reasoning_engine.get_decision(imbalance)

        print(f"\n  KEPUTUSAN AGENT: {'TRANSFER DIREKOMENDASIKAN' if decision['recommend_transfer'] else 'TRANSFER DITOLAK'}")
        print(f"  Kuantitas disarankan : {decision['suggested_quantity']} unit")
        print(f"  Estimasi dampak      : Rp{decision['estimated_impact_idr']:,}")
        print(f"  Penjelasan            : {decision['reasoning']}")

        if decision["recommend_transfer"] and decision["suggested_quantity"] > 0:
            print("\n  >> Mengeksekusi aksi (mock Create Material Document)...")
            result = mock_sap_client.post_goods_movement(
                material=imbalance["material_code"],
                plant=imbalance["target_wh"],
                storage_location=imbalance["target_wh"],
                quantity=decision["suggested_quantity"],
            )
            print("  BERHASIL (mock). Nomor dokumen simulasi:")
            print(json.dumps(result, indent=2)[:800])

    print_header("SELESAI — AUDIT TRAIL DI ATAS ADALAH LOG LENGKAP KEPUTUSAN AGENT")
    print("Semua transaksi mock tersimpan di data/mock_sap_ledger.json")


if __name__ == "__main__":
    main()