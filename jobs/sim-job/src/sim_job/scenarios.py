"""The synthetic scenario set: 12 scam and 12 legitimate counter transactions.

Every person, company and account is invented. Ground truth is the scenario's own label (we wrote the
scenario), which is exactly why results on this set are circular: see report.CIRCULARITY_NOTE.

Customers that exist in `seed/` (Tanaka, cust-0005, cust-0008, the mule, company accounts) are reused;
the rest are described by a `CustomerSpec` that `seedgen.build_seed` turns into 36 months of ordinary
history in an extended copy of the seed directory, which core-bank-mock is started against
(`MIMAMORI_SEED_DIR`). The sim never writes into a running core-bank-mock: its API has no seeding call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .personas import Persona, candid_persona, coached_persona, legit_persona

GroundTruth = Literal["scam", "legit"]


@dataclass(frozen=True)
class CustomerSpec:
    """A synthetic ordinary customer to generate (36 months of history ending at the demo date)."""

    ref: str
    name_ja: str
    name_kana: str
    tenure_years: int = 15
    income_jpy: int = 220_000  # monthly pension / salary deposit
    median_withdrawal_jpy: int = 60_000
    largest_prior_jpy: int = 0  # one earlier counter payment of about this size to a known payee, if > 0


@dataclass(frozen=True)
class PayeeSpec:
    """Where the money goes.

    kind:
      existing   an account already in seed/ (account_id given)
      new_mule   a same-bank account opened `age_days` ago with `fan_in` distinct payers this week
      company    a same-bank company account opened `age_days` ago (default 8 years), `prior_payments`
                 earlier payments from this customer
      other_bank another bank: nothing visible to Scoring about the account
    """

    kind: Literal["existing", "new_mule", "company", "other_bank"]
    name_kana: str
    account_id: str | None = None
    age_days: int | None = None
    fan_in: int = 0
    prior_payments: int = 0

    @property
    def relation(self) -> str:
        return "other_bank" if self.kind == "other_bank" else "same_bank"


@dataclass
class Scenario:
    id: str
    label: str
    ground_truth: GroundTruth
    set: Literal["synthetic", "heldout"]
    customer_ref: str
    account_id: str
    kind: Literal["transfer", "cash_withdrawal"]
    amount_jpy: int
    persona: Persona
    payee: PayeeSpec | None = None
    new_customer: CustomerSpec | None = None
    has_wishes: bool = False
    source: dict | None = None  # held-out: provenance and assumptions
    channel: str = "counter"

    @property
    def basis(self) -> str:
        return "advance_wishes" if self.has_wishes else "bank_policy"

    def payee_account_id(self) -> str | None:
        """Account ID of a same-bank payee: given, or deterministic for the ones seedgen creates."""
        if not self.payee or self.payee.relation == "other_bank":
            return None
        return self.payee.account_id or f"acct-sim-{self.payee.kind}-{self.id}"

    def transfer_body(self, teller_id: str) -> dict:
        body = {"customer_ref": self.customer_ref, "account_id": self.account_id, "channel": self.channel,
                "kind": self.kind, "amount_jpy": self.amount_jpy, "teller_id": teller_id}
        if self.payee:
            body["payee"] = {"name_kana": self.payee.name_kana, "relation": self.payee.relation,
                             **({"account_id": self.payee_account_id()} if self.payee_account_id() else {})}
        return body


def _cust(ref: str, ja: str, kana: str, **kw) -> CustomerSpec:
    return CustomerSpec(ref=ref, name_ja=ja, name_kana=kana, **kw)


# --------------------------------------------------------------------------- personas from the spike

# Spike conversations A, B, C, D (spikes/gemma-copilot/conversations.json), customer lines only, keyed by
# question purpose so they answer whichever approved question is asked.
PERSONA_A = Persona(
    "persona-A-fake-police-renovation",
    description="Fake-police victim, renovation cover story, secrecy line appears when asked about calls (spike A)",
    replies={
        "ask_purpose": ("ええ、あの、リフォーム代なんです。家の、お風呂のね。",),
        "verify_purpose": ("えっと…それは、知り合いの紹介で。今日中に払わないといけないって言われてて。",
                           "見積もり…いや、それは後で送るって。とにかく急いでるのよ。"),
        "check_contact": ("…警察の人から電話があってね。誰にも言うなって言われてるの。あなたにも言っちゃいけないのよ、本当は。",
                          "娘には言わないでって。心配かけたくないし…警察の人もそう言ってたから。"),
        "check_instructions": ("私の口座が犯罪に使われてるから、お金を安全な口座に移さないといけないって。終わったら戻してくれるって。",
                               "言われた通りにするだけよ。"),
        "confirm_details": ("ええ、言われた通りの口座です。",),
        "offer_alternative": ("いえ、今日中に振り込まないといけないのよ。",),
    },
)
PERSONA_B = Persona(
    "persona-B-car-for-grandchild",
    description="Legitimate: car for a grandchild; says 内緒 about the past surprise (spike B)",
    replies={
        "ask_purpose": ("孫がね、就職したもんで、車を買ってやろうと思って。",),
        "verify_purpose": ("この前、孫と一緒に店に行って話してきたんですよ。これが注文書。",),
        "check_contact": ("いや、そんなの来てないよ。車のことは孫には内緒にしてたけど、もう本人も知ってるしね。",
                          "孫も知っていますよ。"),
        "check_instructions": ("いえ、自分で決めたことよ。",),
        "confirm_details": ("振込先は販売店の名前で合ってると思うけど、確認してもらえる？",),
        "offer_alternative": ("いえ、このままでお願いします。",),
    },
)
PERSONA_C = Persona(
    "persona-C-genuine-renovation",
    description="Legitimate: balance of a renovation already under way (spike C)",
    replies={
        "ask_purpose": ("リフォーム代の残りです。先月、手付金を払ったところの。",),
        "verify_purpose": ("息子と一緒に業者さんと会ってね、見積もりもここにありますよ。",),
        "check_contact": ("いえ、特にありません。", "息子も知っていますよ。"),
        "check_instructions": ("急いではないんだけど、月末までに払う約束だから。",),
        "confirm_details": ("ええ、見積書の通りです。",),
        "offer_alternative": ("いえ、このままでお願いします。",),
    },
)
PERSONA_D = Persona(
    "persona-D-son-in-trouble-cash",
    description="Relative-in-trouble victim withdrawing cash for a handover at the station (spike D)",
    replies={
        "ask_purpose": ("息子がね、会社のお金をなくしちゃって、今日中に返さないとクビになるって。",),
        "check_instructions": ("息子から電話があって、今日中に必要だって言うのよ。",),
        "check_contact": ("声？ちょっと風邪ひいてて声が変だったけど、息子ですよ。番号も変わったって言ってたし。",
                          "嫁には言うなって言われたの。恥ずかしいからって。"),
        "check_handover": ("会社の上司の人が取りに来てくれるっていうから、駅で渡すことになってて。",),
        "verify_purpose": ("書類なんてないですよ。",),
        "offer_alternative": ("いえ、現金で渡さないといけないのよ。",),
    },
)
PERSONA_GOLD = Persona(
    "persona-gold-bullion",
    description="Gold-bullion scam victim: a caller recommended buying gold, a courier will collect it",
    replies={
        "ask_purpose": ("金を買うことにしたんです。",),
        "check_instructions": ("電話の人が、今のうちに買った方がいいって勧めてくれて。",),
        "check_handover": ("買った金は、あとで担当の人が取りに来るって言ってました。",),
        "check_contact": ("ええ、その人とは何度か電話でお話ししました。", "家族には、驚かせたいので話していません。"),
        "verify_purpose": ("書類は、その人が後で送ると言っていました。",),
        "confirm_details": ("教えてもらった通りの口座です。",),
    },
)

_MULE_PAYEE_KANA = "カ）ミライケンセツ"


def synthetic_scenarios() -> list[Scenario]:
    """12 scam + 12 legitimate scenarios. Order is stable (ids are used in the report and the seed)."""
    S: list[Scenario] = []

    def scam(n, label, ref, ja, kana, kind, amount, persona, payee=None, **kw):
        sid = f"syn-scam-{n:02d}"
        spec = None if ref.startswith(("cust-tanaka",)) else _cust(ref, ja, kana, **kw.pop("spec", {}))
        S.append(Scenario(sid, label, "scam", "synthetic", ref, "acct-" + ref.removeprefix("cust-"), kind, amount,
                          persona, payee, spec, **kw))

    def legit(n, label, ref, ja, kana, kind, amount, persona, payee=None, existing=False, **kw):
        sid = f"syn-legit-{n:02d}"
        spec = None if existing else _cust(ref, ja, kana, **kw.pop("spec", {}))
        S.append(Scenario(sid, label, "legit", "synthetic", ref, "acct-" + ref.removeprefix("cust-"), kind, amount,
                          persona, payee, spec, **kw))

    # ---- scam
    scam(1, "Hero: fake police, renovation cover story, ¥3M to the fan-in mule (Tanaka)", "cust-tanaka-0001", "", "",
         "transfer", 3_000_000, PERSONA_A, PayeeSpec("existing", _MULE_PAYEE_KANA, "acct-mule-0001"), has_wishes=True)
    scam(2, "Fake police, renovation story, young same-bank account, 2 payers", "cust-sim-s02", "浅井 トミ", "アサイ トミ",
         "transfer", 1_800_000, PERSONA_A, PayeeSpec("new_mule", "カ）ホクトリフォーム", age_days=3, fan_in=2))
    scam(3, "Coached: renovation story, documents 'coming later', fan-in mule",
         "cust-sim-s03", "石渡 清", "イシワタ キヨシ", "transfer", 2_200_000,
         coached_persona("coached-reno-later", cover="リフォーム代なんです。お風呂の工事で。", cash=False,
                         secrecy_leak=True, docs="later"),
         PayeeSpec("new_mule", "カ）アサヒケンソウ", age_days=5, fan_in=6))
    scam(4, "Coached: repair story, invoice produced, other-bank payee",
         "cust-sim-s04", "海野 ふみ", "ウンノ フミ", "transfer", 2_000_000,
         coached_persona("coached-repair-docs", cover="屋根の修理代なんです。", cash=False, secrecy_leak=False, docs="provided"),
         PayeeSpec("other_bank", "カ）ミナトシゴト"))
    scam(5, "Candid: told by police and prosecutor, threatened with arrest, ¥5M other-bank",
         "cust-sim-s05", "大久保 勇", "オオクボ イサム", "transfer", 5_000_000,
         candid_persona("candid-threat", claimed="警察や検察の方", cash=False, secrecy=True, threat=True, live_contact=True),
         PayeeSpec("other_bank", "ホアンシキン カンリ"))
    scam(6, "Candid: told by police to move money, young same-bank account",
         "cust-sim-s06", "川端 澄子", "カワバタ スミコ", "transfer", 1_500_000,
         candid_persona("candid-plain", claimed="警察の方", cash=False, secrecy=False, threat=False, live_contact=False),
         PayeeSpec("new_mule", "カ）ヒカリトウシ", age_days=2, fan_in=1))
    scam(7, "Son in trouble: ¥2M cash for a handover at the station", "cust-sim-s07", "小暮 洋子", "コグレ ヨウコ",
         "cash_withdrawal", 2_000_000, PERSONA_D)
    scam(8, "Son in trouble: ¥0.9M cash (below the ¥1M threshold)", "cust-sim-s08", "平野 実", "ヒラノ ミノル",
         "cash_withdrawal", 900_000, PERSONA_D)
    scam(9, "Gold-bullion scam: ¥2.8M transfer to a precious-metals firm", "cust-sim-s09", "須藤 一郎", "スドウ イチロウ",
         "transfer", 2_800_000, PERSONA_GOLD, PayeeSpec("other_bank", "カ）ゴールドトレード"))
    scam(10, "Coached: cash for 'house repairs', invoice produced", "cust-sim-s10", "樋口 照子", "ヒグチ テルコ",
         "cash_withdrawal", 1_400_000,
         coached_persona("coached-cash-docs", cover="家の修理にお金が要るんです。", cash=True, secrecy_leak=False, docs="provided"))
    scam(11, "Candid: told by police to hand over cash, arrest threatened", "cust-sim-s11", "三浦 昭", "ミウラ アキラ",
         "cash_withdrawal", 3_000_000,
         candid_persona("candid-cash-threat", claimed="警視庁の警察官", cash=True, secrecy=True, threat=True, live_contact=True))
    scam(12, "Coached: ¥0.8M to a 2-day-old same-bank account (below threshold)", "cust-sim-s12", "古川 トシ", "フルカワ トシ",
         "transfer", 800_000,
         coached_persona("coached-small-docs", cover="リフォームの手付金なんです。", cash=False, secrecy_leak=True, docs="provided"),
         PayeeSpec("new_mule", "カ）サクラハウジング", age_days=2, fan_in=2))

    # ---- legitimate
    legit(1, "Genuine renovation balance, earlier deposit to the same payee (spike C)", "cust-0005", "", "",
          "transfer", 2_400_000, PERSONA_C, PayeeSpec("existing", "カ）サクラコウムテン", "acct-co-0001"), existing=True)
    legit(2, "Car for a grandchild, long-standing dealer account (spike B)", "cust-0008", "", "",
          "transfer", 1_800_000, PERSONA_B, PayeeSpec("existing", "カ）ミドリモータース", "acct-co-0002"), existing=True)
    legit(3, "House purchase deposit to a developer at another bank", "cust-sim-l03", "岡本 孝", "オカモト タカシ",
          "transfer", 3_000_000,
          legit_persona("legit-house", purpose="家の購入の手付金です。", documents="売買契約書があります。これです。",
                        family="はい、妻と一緒に決めました。"),
          PayeeSpec("other_bank", "カ）ミナミハウジング"))
    legit(4, "Wedding gift to a grandchild, individual at another bank, no documents", "cust-sim-l04", "安藤 栄子", "アンドウ エイコ",
          "transfer", 1_500_000,
          legit_persona("legit-gift", purpose="孫の結婚のお祝いです。", documents="お祝いなので、書類は特にありません。",
                        family="はい、娘も知っています。"),
          PayeeSpec("other_bank", "ナカタ ユウキ"))
    legit(5, "Nursing-home entrance fee, contract in hand", "cust-sim-l05", "村田 邦夫", "ムラタ クニオ",
          "transfer", 2_000_000,
          legit_persona("legit-care", purpose="母の施設の入居金です。", documents="入居契約書があります。",
                        family="はい、兄弟みんな知っています。"),
          PayeeSpec("other_bank", "シャカイフクシホウジン ヒカリノ"))
    legit(6, "Second instalment to a contractor paid twice before", "cust-sim-l06", "森田 和子", "モリタ カズコ",
          "transfer", 1_600_000,
          legit_persona("legit-instalment", purpose="外壁工事の中間金です。", documents="見積書と請求書です。"),
          PayeeSpec("company", "カ）ミドリガイヘキ", age_days=2900, prior_payments=2), spec={"largest_prior_jpy": 800_000})
    legit(7, "Funeral costs in cash, invoice in hand", "cust-sim-l07", "杉本 義男", "スギモト ヨシオ",
          "cash_withdrawal", 1_200_000,
          legit_persona("legit-funeral", purpose="主人の葬儀の費用です。", documents="葬儀社の請求書です。これです。"))
    legit(8, "Anniversary trip booked as a surprise, travel-agency quote in hand", "cust-sim-l08", "柴田 弘", "シバタ ヒロシ",
          "transfer", 1_500_000,
          legit_persona("legit-trip", purpose="結婚記念日の旅行代金です。妻には内緒で予約したんです。",
                        documents="旅行会社の見積書です。", family="いえ、妻にはサプライズなので話していません。"),
          PayeeSpec("other_bank", "カ）サンライズツアー"))
    legit(9, "Routine small cash withdrawal", "cust-sim-l09", "田代 澄", "タシロ スミ",
          "cash_withdrawal", 80_000, legit_persona("legit-routine", purpose="生活費です。", documents="いえ、特にありません。"))
    legit(10, "Help for a daughter's home purchase, family transfer, no documents", "cust-sim-l10", "原田 道子", "ハラダ ミチコ",
          "transfer", 4_000_000,
          legit_persona("legit-family", purpose="娘の家の購入を援助するんです。",
                        documents="家族のことなので、書類はありません。", instructions="いえ、私から申し出たことです。",
                        family="はい、娘も婿も知っています。"),
          PayeeSpec("other_bank", "ハラダ ユカリ"))
    legit(11, "Hospital bill, invoice in hand", "cust-sim-l11", "竹内 政子", "タケウチ マサコ",
          "transfer", 1_100_000,
          legit_persona("legit-hospital", purpose="入院費用のお支払いです。", documents="病院の請求書です。"),
          PayeeSpec("other_bank", "イリョウホウジン セイワカイ"))
    legit(12, "Replacement car for self, dealer order form in hand", "cust-sim-l12", "金井 修", "カナイ オサム",
          "transfer", 2_600_000,
          legit_persona("legit-own-car", purpose="車の買い替えです。", documents="注文書です。",
                        contact="ディーラーの方から、納車日の確認のお電話はありました。"),
          PayeeSpec("other_bank", "カ）ノースモータース"))
    return S


def by_id(scenarios: list[Scenario]) -> dict[str, Scenario]:
    return {s.id: s for s in scenarios}
