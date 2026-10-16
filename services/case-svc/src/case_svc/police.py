"""Police summary: issued to attending officers **on request**, limited to the sections they ask for; the
officer's name and title are logged (APPI Art. 27(1)(i) via CCP Art. 197(2), R4). A human triggers it."""

from __future__ import annotations

from mimamori_common.models import PoliceSummaryRequest, PoliceSummaryResponse

from .deps import Deps

SECTION_TITLES_JA = {"amount": "取引内容", "payee": "振込先", "customer_statements": "お客様の発言", "indicators": "確認された兆候",
                     "timeline": "経過"}
INDICATOR_JA = {
    "impersonated_official": "公的機関職員を名乗る連絡", "impersonated_relative": "親族を名乗る連絡", "secrecy_instruction": "口外禁止の指示",
    "urgency": "緊急性の強調", "cash_or_card_handover": "現金・カードの受け渡し", "cover_story": "資金使途の説明",
    "safe_account_transfer": "別口座への資金移動の指示", "changed_contact_number": "連絡先番号の変更", "third_party_pressure": "第三者からの催促",
}
EVENT_JA = {"case_opened": "アラート検知・案件作成", "decision_logged": "担当者の判断", "hold_placed": "お取引の保留", "hold_updated": "保留の更新",
            "contact_notice_sent": "ご家族への通知", "contact_outcome": "ご家族との通話結果"}


def _sections(case: dict, state: dict, events: list[dict], wanted: list[str]) -> dict:
    out: dict = {}
    req = case["request"]
    for item in wanted:
        if item == "amount":
            out[item] = {"amount_jpy": req["amount_jpy"], "kind": req["kind"], "channel": req["channel"]}
        elif item == "payee":
            out[item] = req.get("payee")
        elif item == "customer_statements":
            out[item] = [{"turn_id": i["turn_id"], "text": i["quote"]} for i in state["indicators"]]
        elif item == "indicators":
            out[item] = [{"claim_id": i["id"], "indicator": i["type"], "turn_id": i["turn_id"]} for i in state["indicators"]]
        elif item == "timeline":
            out[item] = [{"at": e["at"], "event": e["type"]} for e in events if e["type"] in EVENT_JA]
    return out


def _text_ja(case_id: str, items: dict) -> str:
    lines = [f"情報提供書（案件 {case_id}）", "※ご依頼のあった項目のみ記載しています。", ""]
    for key, value in items.items():
        lines.append(f"【{SECTION_TITLES_JA[key]}】")
        if key == "amount":
            lines.append(f"金額 {value['amount_jpy']:,}円（{'振込' if value['kind'] == 'transfer' else '現金引出し'}・窓口）")
        elif key == "payee":
            lines.append(f"{value['name_kana']}（{'当行' if value['relation'] == 'same_bank' else '他行'}）" if value else "なし")
        elif key == "customer_statements":
            lines += [f"{v['turn_id']}: 「{v['text']}」" for v in value] or ["なし"]
        elif key == "indicators":
            lines += [f"{v['claim_id']}: {INDICATOR_JA.get(v['indicator'], v['indicator'])}（{v['turn_id']}）" for v in value] or ["なし"]
        elif key == "timeline":
            lines += [f"{v['at']}  {EVENT_JA[v['event']]}" for v in value] or ["なし"]
        lines.append("")
    return "\n".join(lines).rstrip()


async def issue_summary(deps: Deps, case_id: str, body: PoliceSummaryRequest, via: str) -> PoliceSummaryResponse:
    store = deps.store
    async with store.lock(case_id):
        case, state = store.case(case_id), store.state(case_id)
        wanted = list(dict.fromkeys(body.requested_items))
        items = _sections(case, state, store.repo.list_events(case_id), wanted)
        now = store.now()
        n = len(state.setdefault("police_summaries", [])) + 1
        summary_id = f"ps-{case_id.split('case-')[1]}-{n}"
        state["police_summaries"].append(summary_id)
        state["police_notified"] = True
        store.save_state(case_id, state)
        store.audit(case_id, "police_summary.issued", body.teller_id,
                    f"on the request of {body.officer_name} ({body.officer_title}); sections: {', '.join(wanted)}",
                    via=via, summary_id=summary_id, officer_name=body.officer_name, officer_title=body.officer_title,
                    requested_items=wanted)
        store.emit(case_id, "police_summary_issued", {"summary_id": summary_id, "requested_items": wanted})
    return PoliceSummaryResponse(summary_id=summary_id, issued_at=now, officer_name=body.officer_name,
                                 officer_title=body.officer_title, items=items, text_ja=_text_ja(case_id, items))
