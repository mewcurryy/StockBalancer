import os
import json

REASONING_MODE = os.environ.get("REASONING_MODE", "rule_based")


def build_prompt(context: dict) -> str:
    return f"""Kamu adalah reasoning engine untuk agent rebalancing stok gudang (StockBalancer).

Data ketimpangan stok yang terdeteksi:
- Material: {context['material_name']}
- Gudang sumber: {context['source_wh']} (stok saat ini: {context['source_stock']} unit, jauh di atas reorder point {context['source_reorder']})
- Gudang tujuan: {context['target_wh']} (stok saat ini: {context['target_stock']} unit, di bawah/mendekati reorder point {context['target_reorder']})
- Rata-rata demand harian di gudang tujuan: {context['target_demand']} unit/hari
- Margin keuntungan per unit: Rp{context['margin_per_unit']:,}
- Ongkos kirim sumber->tujuan: Rp{context['shipping_cost']:,}
- Estimasi lead time pengiriman: {context['lead_time_days']} hari

Tugasmu: putuskan apakah transfer stok ini layak secara ekonomis, dan berapa kuantitas
yang disarankan untuk ditransfer (jangan lebih dari stok berlebih di sumber).
Pertimbangkan trade-off antara ongkos kirim vs potensi kerugian akibat stockout
(lost sales) selama lead time di gudang tujuan.

Balas HANYA dalam format JSON persis seperti ini, tanpa teks lain:
{{
  "recommend_transfer": true atau false,
  "suggested_quantity": angka,
  "estimated_impact_idr": angka (estimasi penghematan/pencegahan kerugian, boleh negatif kalau tidak worth),
  "reasoning": "penjelasan singkat 2-3 kalimat dalam Bahasa Indonesia"
}}"""


def reason_with_claude(context: dict) -> dict:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": build_prompt(context)}],
    )
    text = response.content[0].text.strip()
    return _parse_json_response(text)


def reason_with_rules(context: dict) -> dict:
    """
    Default & fallback, 100% lokal, tanpa API.
    Ngecek 2 syarat terpisah, dan pesannya dibedakan sesuai alasan sebenarnya:
      1) Apakah worth secara untung-rugi (potensi rugi > ongkos kirim)?
      2) Apakah gudang sumber punya surplus stok yang cukup buat benar-benar dikirim?
    """
    kebutuhan_selama_kirim = context["target_demand"] * context["lead_time_days"]
    deficit_during_leadtime = max(0, kebutuhan_selama_kirim - context["target_stock"])
    potential_lost_sales_value = deficit_during_leadtime * context["margin_per_unit"]
    net_benefit = potential_lost_sales_value - context["shipping_cost"]
    worth_it = net_benefit > 0

    source_surplus = max(0, context["source_stock"] - context["source_reorder"])
    target_need = max(deficit_during_leadtime, context["target_reorder"] - context["target_stock"])
    suggested_qty = max(0, int(min(source_surplus, target_need)))

    recommend = worth_it and suggested_qty > 0

    if deficit_during_leadtime == 0:
        reasoning = (
            f"Stok gudang tujuan masih {context['target_stock']} unit, cukup untuk "
            f"{context['lead_time_days']} hari ke depan (butuh sekitar {kebutuhan_selama_kirim} unit). "
            f"Belum akan habis sebelum kiriman baru sampai, jadi transfer belum mendesak — "
            f"meski stoknya sudah di bawah batas aman (reorder point)."
        )
    elif not worth_it:
        reasoning = (
            f"Gudang tujuan memang akan kekurangan {deficit_during_leadtime} unit "
            f"(potensi rugi Rp{potential_lost_sales_value:,.0f}), tapi ongkos kirim "
            f"Rp{context['shipping_cost']:,.0f} lebih mahal dari potensi rugi itu, jadi belum sepadan."
        )
    elif suggested_qty == 0:
        reasoning = (
            f"Secara untung-rugi transfer ini sebenarnya layak (potensi rugi "
            f"Rp{potential_lost_sales_value:,.0f} lebih besar dari ongkos kirim Rp{context['shipping_cost']:,.0f}), "
            f"tapi gudang sumber tidak punya surplus stok yang cukup untuk dikirim tanpa membuat stoknya "
            f"sendiri jatuh di bawah batas aman. Transfer ditunda sampai stok sumber cukup."
        )
    else:
        reasoning = (
            f"Kalau tidak ditransfer, gudang tujuan diperkirakan kekurangan {deficit_during_leadtime} unit "
            f"sebelum kiriman sampai (potensi rugi Rp{potential_lost_sales_value:,.0f}). "
            f"Ongkos kirim cuma Rp{context['shipping_cost']:,.0f} — lebih murah dari potensi ruginya, "
            f"jadi transfer ini layak dilakukan."
        )

    return {
        "recommend_transfer": recommend,
        "suggested_quantity": suggested_qty,
        "estimated_impact_idr": round(net_benefit),
        "reasoning": reasoning,
    }


def _parse_json_response(text: str) -> dict:
    cleaned = text.replace("```json", "").replace("```", "").strip()
    return json.loads(cleaned)


def get_decision(context: dict) -> dict:
    """
    Entry point utama. Coba mode yang diminta, fallback otomatis ke rule_based
    kalau terjadi error (API down, kredit habis, key belum diisi, dsb), supaya
    demo tidak pernah gagal total.
    """
    try:
        if REASONING_MODE == "claude":
            return reason_with_claude(context)
        else:
            return reason_with_rules(context)
    except Exception as e:
        print(f"[WARNING] Reasoning engine '{REASONING_MODE}' gagal ({e}). Fallback ke rule-based.")
        return reason_with_rules(context)