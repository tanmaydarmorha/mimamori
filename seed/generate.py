"""Generate the synthetic core-banking seed data (deterministic: same output every run).

    python seed/generate.py          # rewrites seed/bank/*.json and seed/manifest.json

Synthetic only: invented names, invented account IDs, reserved-style phone numbers. Balances are
set per account and are not reconciled with the transaction history. The demo date is
2026-10-13 (Tuesday); the mule account opened four days earlier.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "bank"
JST = timezone(timedelta(hours=9))
DEMO_DATE = date(2026, 10, 13)
BRANCH = "サンプル銀行 駅前支店"
rng = random.Random(20261013)

SURNAMES = [("佐々木", "ササキ"), ("高橋", "タカハシ"), ("渡辺", "ワタナベ"), ("伊藤", "イトウ"), ("山本", "ヤマモト"), ("中村", "ナカムラ"),
            ("小林", "コバヤシ"), ("加藤", "カトウ"), ("吉田", "ヨシダ"), ("山田", "ヤマダ"), ("松本", "マツモト"), ("井上", "イノウエ"),
            ("木村", "キムラ"), ("林", "ハヤシ"), ("斎藤", "サイトウ"), ("清水", "シミズ"), ("山口", "ヤマグチ"), ("池田", "イケダ"),
            ("橋本", "ハシモト"), ("阿部", "アベ"), ("石川", "イシカワ"), ("前田", "マエダ"), ("藤田", "フジタ"), ("岡田", "オカダ")]
GIVEN = [("和子", "カズコ"), ("幸子", "サチコ"), ("正雄", "マサオ"), ("清", "キヨシ"), ("洋子", "ヨウコ"), ("博", "ヒロシ"), ("静江", "シズエ"),
         ("健一", "ケンイチ"), ("明美", "アケミ"), ("茂", "シゲル"), ("美代子", "ミヨコ"), ("勇", "イサム"), ("久美子", "クミコ"), ("実", "ミノル"),
         ("節子", "セツコ"), ("隆", "タカシ"), ("真理", "マリ"), ("拓也", "タクヤ"), ("由美", "ユミ"), ("大輔", "ダイスケ")]

customers, accounts, txns = [], [], []
txn_counter = 0


def add_customer(ref, ja, kana, tenure, account_id, opened_on, balance, holder_kana=None):
    customers.append({"customer_ref": ref, "display_name_ja": ja, "display_name_kana": kana, "tenure_years": tenure, "branch_name_ja": BRANCH})
    accounts.append({"account_id": account_id, "customer_ref": ref, "holder_name_kana": holder_kana or kana, "branch_name_ja": BRANCH,
                     "opened_on": opened_on.isoformat(), "balance_jpy": balance, "status": "active"})


def add_txn(account_id, when, kind, amount, channel, cp_account=None, cp_name=None, cp_cat=None, memo=None):
    global txn_counter
    txn_counter += 1
    txns.append({"txn_id": f"txn-{txn_counter:06d}", "account_id": account_id, "booked_at": when.isoformat(), "kind": kind,
                 "amount_jpy": amount, "channel": channel, "counterparty_account_id": cp_account, "counterparty_name_kana": cp_name,
                 "counterparty_category": cp_cat, "memo": memo})


def at(day: date, hour=None):
    return datetime(day.year, day.month, day.day, hour if hour is not None else rng.randint(9, 15), rng.randint(0, 59), tzinfo=JST)


def months(start: date, end: date):
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def clamp_day(y, m, d):
    return date(y, m, min(d, 28))


# ----------------------------------------------------------------------------- Tanaka Keiko (hero)
TANAKA, TANAKA_ACCT = "cust-tanaka-0001", "acct-tanaka-0001"
add_customer(TANAKA, "田中 圭子", "タナカ ケイコ", 12, TANAKA_ACCT, date(2014, 10, 1), 7_420_000)
for y, m in months(date(2014, 10, 1), date(2026, 10, 1)):
    if date(y, m, 1) > DEMO_DATE - timedelta(days=1):
        break
    if m in (2, 4, 6, 8, 10, 12) and clamp_day(y, m, 15) < DEMO_DATE:
        add_txn(TANAKA_ACCT, at(clamp_day(y, m, 15), 9), "deposit", 310_000, "system", cp_name="コウセイネンキン", cp_cat="pension")
    d = clamp_day(y, m, rng.randint(3, 25))
    if d < DEMO_DATE:
        add_txn(TANAKA_ACCT, at(d), "withdrawal", rng.choice([40_000, 50_000, 50_000, 50_000, 60_000]), rng.choice(["atm", "atm", "atm", "counter"]))
    d = clamp_day(y, m, 27)
    if d < DEMO_DATE:
        add_txn(TANAKA_ACCT, at(d, 9), "direct_debit", rng.randint(14, 22) * 1000, "system", cp_name="デンキ ガス スイドウ", cp_cat="utilities")
    if m == 4 and clamp_day(y, m, 10) < DEMO_DATE and y >= 2015:
        add_txn(TANAKA_ACCT, at(clamp_day(y, m, 10), 10), "withdrawal", 400_000, "counter")  # annual April school fee (seasonal)
    if m == 12 and y < 2026:
        add_txn(TANAKA_ACCT, at(clamp_day(y, m, 26)), "transfer_out", 50_000, "counter", cp_name="タナカ ユキ", cp_cat="individual", memo="お年玉")

# ----------------------------------------------------------------------------- company payees (older accounts)
COMPANIES = [("cust-co-0001", "株式会社サクラ工務店", "カ）サクラコウムテン", "acct-co-0001", date(2016, 4, 1), "contractor"),
             ("cust-co-0002", "株式会社ミドリモータース", "カ）ミドリモータース", "acct-co-0002", date(2012, 9, 1), "retailer"),
             ("cust-co-0003", "有限会社ヤマト食品", "ユ）ヤマトショクヒン", "acct-co-0003", date(2009, 6, 1), "retailer")]
for ref, ja, kana, acct, opened, _cat in COMPANIES:
    add_customer(ref, ja, kana, DEMO_DATE.year - opened.year, acct, opened, rng.randint(5, 40) * 1_000_000)

# ----------------------------------------------------------------------------- ordinary customers
ORDINARY = []
used = set()
while len(ORDINARY) < 56:
    s, g = rng.choice(SURNAMES), rng.choice(GIVEN)
    if (s[0], g[0]) in used or s[0] == "田中":
        continue
    used.add((s[0], g[0]))
    ORDINARY.append((f"cust-{len(ORDINARY) + 1:04d}", f"{s[0]} {g[0]}", f"{s[1]} {g[1]}"))

HISTORY_START = date(2023, 10, 1)
contractor_customers = {5, 12, 19, 26, 33, 40}  # a genuine contractor payment in their history
for i, (ref, ja, kana) in enumerate(ORDINARY, start=1):
    acct = f"acct-{i:04d}"
    tenure = rng.randint(4, 22)
    add_customer(ref, ja, kana, tenure, acct, date(DEMO_DATE.year - tenure, rng.randint(1, 12), 1), rng.randint(8, 150) * 100_000)
    monthly = rng.choice([30_000, 50_000, 80_000, 100_000, 150_000, 200_000])
    income = rng.choice([220_000, 260_000, 310_000, 380_000, 150_000])
    rent = rng.choice([0, 0, 62_000, 78_000, 95_000])
    insurance_month = rng.randint(1, 12)
    for y, m in months(HISTORY_START, DEMO_DATE):
        if clamp_day(y, m, 25) < DEMO_DATE:
            add_txn(acct, at(clamp_day(y, m, 25), 8), "deposit", income, "system", cp_name="カ）ホウジン キュウヨ", cp_cat="salary")
        d = clamp_day(y, m, rng.randint(3, 22))
        if d < DEMO_DATE:
            add_txn(acct, at(d), "withdrawal", int(monthly * rng.choice([0.8, 1.0, 1.0, 1.2])), rng.choice(["atm", "atm", "app", "counter"]))
        if clamp_day(y, m, 27) < DEMO_DATE:
            add_txn(acct, at(clamp_day(y, m, 27), 9), "direct_debit", rng.randint(9, 25) * 1000, "system", cp_name="デンキ ガス スイドウ", cp_cat="utilities")
        if rent and clamp_day(y, m, 1) < DEMO_DATE:
            add_txn(acct, at(clamp_day(y, m, 1), 9), "transfer_out", rent, "app", cp_name="ウチダ フドウサン", cp_cat="landlord", memo="家賃")
        if m == insurance_month and clamp_day(y, m, 15) < DEMO_DATE:
            add_txn(acct, at(clamp_day(y, m, 15), 9), "direct_debit", rng.choice([84_000, 120_000, 96_000]), "system", cp_name="セイメイホケン", cp_cat="insurance")
    if i in contractor_customers:
        add_txn(acct, at(date(2025, rng.randint(3, 9), rng.randint(2, 20))), "transfer_out", rng.choice([300_000, 450_000, 800_000]), "counter",
                "acct-co-0001", "カ）サクラコウムテン", "contractor", "工事代金")

# ----------------------------------------------------------------------------- the mule and its payers
MULE, MULE_ACCT = "cust-mule-0001", "acct-mule-0001"
MULE_OPENED = DEMO_DATE - timedelta(days=4)
add_customer(MULE, "株式会社ミライ建設", "カ）ミライケンセツ", 0, MULE_ACCT, MULE_OPENED, 0)
payer_rows = [(2, date(2026, 10, 9), 1_200_000), (11, date(2026, 10, 9), 800_000), (23, date(2026, 10, 9), 2_000_000),
              (34, date(2026, 10, 12), 450_000), (41, date(2026, 10, 12), 1_500_000), (52, date(2026, 10, 13), 600_000)]
mule_payers = []
for idx, day, amount in payer_rows:
    ref, acct = ORDINARY[idx - 1][0], f"acct-{idx:04d}"
    when = at(day, rng.randint(9, 14)) if day < DEMO_DATE else datetime(2026, 10, 13, 9, 12, tzinfo=JST)
    add_txn(acct, when, "transfer_out", amount, "app" if day.day == 12 else "counter", MULE_ACCT, "カ）ミライケンセツ", "company", "工事代金")
    add_txn(MULE_ACCT, when, "transfer_in", amount, "app" if day.day == 12 else "counter", acct, ORDINARY[idx - 1][2], "individual")
    mule_payers.append({"customer_ref": ref, "account_id": acct, "amount_jpy": amount, "paid_on": day.isoformat()})
for a in accounts:
    if a["account_id"] == MULE_ACCT:
        a["balance_jpy"] = sum(p["amount_jpy"] for p in mule_payers)

# ----------------------------------------------------------------------------- write
txns.sort(key=lambda t: (t["booked_at"], t["txn_id"]))
OUT.mkdir(exist_ok=True)
for name, data in [("customers", customers), ("accounts", accounts), ("transactions", txns)]:
    (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=0, separators=(",", ":")).replace("},{", "},\n{") + "\n")

manifest = {
    "note": "Synthetic. Index of the seeded scenarios for tests, the evaluation and the demo.",
    "demo_now": "2026-10-13T11:42:00+09:00",
    "demo_date": DEMO_DATE.isoformat(),
    "hero": {"customer_ref": TANAKA, "account_id": TANAKA_ACCT, "transfer": {"amount_jpy": 3_000_000, "payee_name_kana": "カ）ミライケンセツ",
             "payee_account_id": MULE_ACCT, "channel": "counter"}, "trusted_contact_phone_e164": "+819012345678"},
    "mule": {"customer_ref": MULE, "account_id": MULE_ACCT, "opened_on": MULE_OPENED.isoformat(),
             "prior_payers": mule_payers, "distinct_payers_7d_including_pending_tanaka": len(mule_payers) + 1},
    "school_fee_event": {"customer_ref": TANAKA, "account_id": TANAKA_ACCT, "date": "2026-04-10", "amount_jpy": 400_000,
                         "expect": "no case, matches seasonal baseline"},
    "legit_scenarios": [
        {"id": "genuine_renovation", "customer_ref": ORDINARY[4][0], "account_id": "acct-0005", "payee_account_id": "acct-co-0001",
         "amount_jpy": 2_400_000, "note": "earlier contractor payment to the same older account; spike conversation C"},
        {"id": "car_for_grandchild", "customer_ref": ORDINARY[7][0], "account_id": "acct-0008", "payee_account_id": "acct-co-0002",
         "amount_jpy": 1_800_000, "note": "dealer account is 14 years old; spike conversation B"},
    ],
    "counts": {"customers": len(customers), "accounts": len(accounts), "transactions": len(txns), "ordinary_customers": len(ORDINARY)},
    "normal_activity": "Replay an ordinary customer's last 14 days of transactions through POST /v1/events: none should alert, EXCEPT the six mule payers (mule.prior_payers), whose transfer to acct-mule-0001 is expected to alert.",
}
(HERE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(manifest["counts"])
