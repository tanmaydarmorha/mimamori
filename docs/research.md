# Research brief: Mimamori open research items

**For:** a fresh research session. Read this file fully before starting. It's self-contained.
**Write findings into:** the `## Findings` section at the bottom of this file. Don't edit other files.
**Created:** 2026-10-12.

## Background (what Mimamori is)

Mimamori is a hackathon prototype (AI Builder Cup 2026, BFSI theme). It's a decision-support
layer for **Japanese banks** that helps branch tellers stop scams, mainly **fake-police scams
(ニセ警察詐欺)**, at the bank counter. A copilot reads what the customer says, spots coached
cover stories ("it's for the renovation"), and suggests questions. The teller decides whether to
pause the transaction. The bank may then:
- call a family member the customer nominated in advance
- notify the police
- freeze the scammer's receiving ("mule") account if it's held at the same bank

The design decisions are in [`decisions.md`](decisions.md). The deck edits that depend on this
research are in [`deck-changes.md`](deck-changes.md). You don't need to read the architecture docs.

## Rules for this research

1. **Never fabricate a source, article number, URL, quote or statistic.** If you can't find
   something, write "not found" and what you tried. A gap is fine; an invented citation is not.
2. **Prefer primary sources:**
   - e-Gov law database (laws.e-gov.go.jp)
   - National Police Agency (npa.go.jp)
   - prefectural police sites
   - Financial Services Agency (fsa.go.jp)
   - Personal Information Protection Commission (ppc.go.jp)
   - Japanese Bankers Association (zenginkyo.or.jp)
   - Deposit Insurance Corporation of Japan (dic.go.jp)

   Use news (NHK, Nikkei, Japan Times, Kyodo) for cases and secondary confirmation.
3. **Search in Japanese as well as English.** Most primary material is Japanese only. Suggested
   search terms are given for each item.
4. **For every source, record:**
   - URL
   - title (original language)
   - publisher
   - publication date, if shown
   - date accessed
   - the exact passage relied on: a short quote in the original language plus an English gloss
5. **Separate what the source says from your interpretation.** Mark interpretation as such.
6. **Give a confidence for each item:**
   - **confirmed:** a primary source says it directly
   - **likely:** secondary or indirect
   - **unresolved**

7. **Timebox:** about 30–45 minutes per item. Items R3 and R4 should be quick. Do them first.

## Items

Suggested order: **R3 → R4 → R1 → R2 → R5**.

### R1 · Published teller-check guidance (evaluation baseline "arm (a)")

**Why:** the evaluation compares Mimamori against *today's counter check*. That baseline must
come from published guidance, not something the team invented, or judges will call it a
strawman.

**Find:** one or more published checklists or guidance documents that tell bank tellers what to ask
or check when an older customer makes a large withdrawal or transfer. Concrete question items are
what we need. Likely publishers:
- prefectural police, often in joint programmes with local banks
- the Japanese Bankers Association
- the Financial Services Agency
- individual banks

**Search terms:**
- 声かけ チェックシート 金融機関 特殊詐欺
- 高額払戻し 声かけ 警察 通報
- 預貯金 払戻し 特殊詐欺 チェックリスト
- 全国銀行協会 特殊詐欺 対策
- 窓口 声掛け 例 ニセ警察

**Deliver:**
- The best source, with its question items listed (original Japanese plus English gloss).
- Any stated thresholds: amount, age, triggers for calling the police.
- A draft of the baseline as explicit rules, marked as a draft. Example: "transfer ≥ ¥X → ask Q1–Qn
  → pause and call police if any red-flag answer".
- Whether practice varies by prefecture or bank. If so, which source is most representative.

### R2 · Date T and the post-T held-out case set

**Why:** the evaluation's held-out test set is adapted from **publicly reported fake-police
cases**. Scam playbooks may only be built from alerts published **before date T**, and test cases
only from reports **after T**, so the test isn't contaminated.

**Find:**
1. **Public sources with case-level detail:**
   - NPA pages describing current scam methods
   - prefectural police pages describing current methods
   - published recordings of real scam calls, which some police forces host
   - news reports of individual cases, especially **cases stopped at a bank counter**
2. **For each case:**
   - publication date
   - who was impersonated
   - the contact channel
   - what the victim was told: secrecy, cover story, handover
   - payment method: cash, transfer, card, crypto, gold, e-money
   - amount, if stated
   - whether it happened or was stopped at a bank counter
3. **A count of usable cases** by month, so T can be chosen. The proposed T is **2026-04-01**. Check that there are at least 20 usable cases published after it. If not, propose an earlier T and say why.
4. Whether the NPA reports fake-police scams as their own category, and since when.

**Search terms:**
- ニセ警察詐欺 手口
- 警察官を名乗る 詐欺 事例 2026
- 特殊詐欺 窓口 阻止 銀行員 感謝状
- 犯人の音声 特殊詐欺 警視庁
- 警察庁 特殊詐欺 認知・検挙状況 2026

**Deliver:**
- A table of candidate cases: date, source URL, impersonation, instructions, payment method, counter (y/n), usable (y/n).
- Monthly counts.
- A recommended T with a reason.
- Don't write the adapted dialogues. Only collect the cases.

### R3 · Legal basis for freezing the mule account (Furikome Sagi Relief Act)

**Why:** in the demo, a fraud analyst approves freezing the scammer's receiving account at the
same bank. We believe the **Furikome Sagi Relief Act** (犯罪利用預金口座等に係る資金による被害回復分配金の支払等に関する法律,
2007/2008) allows a bank to suspend transactions on accounts suspected of fraud use. It then sets
out a forfeiture and victim-distribution process through the Deposit Insurance Corporation.

**Find and confirm:**
- The article that allows the bank to suspend transactions (取引の停止等), with its exact wording.
- What triggers it: whether it requires a police request or suspicion based on the bank's own information.
- The follow-on process: public notice by the Deposit Insurance Corporation, forfeiture, and distribution to victims.
- Any FSA or bankers' association guidance on how banks apply it.

**Search terms:**
- 振り込め詐欺救済法 第3条 取引の停止
- 犯罪利用預金口座等 取引の停止等の措置
- 預金保険機構 振り込め詐欺救済法 公告

**Deliver:**
- Article numbers.
- Quoted Japanese text with an English gloss.
- A one-paragraph plain-English summary of whether it supports "the bank freezes a suspected same-bank mule account after a human decision".

### R4 · APPI basis for giving the police an evidence summary

**Why:** the teller hands the police a printed evidence summary about the customer's case,
without the customer's consent at that moment. We believe Japan's privacy law (APPI, 個人情報保護法)
permits third-party provision without consent when:
- (a) it's based on laws, or
- (b) it's necessary to protect life, body or property and consent is difficult to obtain

We believe these are **Art. 27(1)(i)–(ii)** after the 2022 renumbering.

**Find and confirm:**
- The current article and paragraph numbers, with their wording.
- PPC guidelines or Q&A examples that cover giving information to the police in a fraud or scam situation, especially examples involving banks.
- Whether a police inquiry under Code of Criminal Procedure Art. 197(2) (捜査関係事項照会) counts as "based on laws".

**Search terms:**
- 個人情報保護法 第27条 第1項 第2号 財産の保護
- 個人情報保護委員会 ガイドライン 警察 提供 例
- 個人情報保護法 Q&A 振り込め詐欺 警察 提供

**Deliver:**
- Article references.
- Quoted wording with an English gloss.
- The most relevant PPC example.
- A short summary of whether the police handover in our design is covered, and under which basis.

### R5 · Enforceability of a non-cancellable, pre-agreed cooling-off pause

**Why:** in Mimamori, a customer can opt in, while well, to a protection agreement: *"if the
bank sees signs of a scam, pause the transaction for up to 24 hours and call my daughter, and
don't let me cancel the pause at the counter."* We need to know how defensible that is.

**Known tension:**
- **Against:** a deposit is a consumption deposit (消費寄託), repayable on demand. The **Consumer Contract Act Art. 10** (消費者契約法 第10条) can void clauses that unilaterally harm consumers' interests.
- **For:** it's opt-in, short, capped, and in the customer's own interest.

**Find:**
- Precedents or analogues:
  - opt-in withdrawal restrictions
  - agreements with a "trusted person" or proxy
  - the bankers' association guidance on financial transactions for customers with dementia or reduced cognitive ability (e.g. 金融取引の代理等に関する考え方, around 2021)
  - family trust products
  - age or inactivity ATM limits and the legal basis banks cite for them
- Any deposit-terms (預金規定) clauses that already let a bank suspend or refuse payment when fraud is suspected.
- Any commentary on the Consumer Contract Act and protective restrictions that customers choose themselves.

**Search terms:**
- 全国銀行協会 認知判断能力 低下 金融取引 考え方
- 預金規定 支払停止 不正利用 疑い
- ATM 振込制限 高齢者 法的根拠
- 消費者契約法 第10条 預金 引出し 制限
- 見守り 口座 引き出し制限 本人同意

**Deliver:**
- The closest precedents, with sources.
- The deposit-terms clauses found.
- An honest assessment: **supported / arguable / unlikely / unresolved**.
- A suggested one-sentence wording for the deck that doesn't overclaim. This item is expected to end "unresolved, needs legal review". The goal is the best available framing, not a legal opinion.

### R2b · Complete the held-out case set (follow-up, added 2026-10-12)

**Why:** R2 found about 10 detailed fake-police cases after T = 2026-04-01, mostly from Toyama.
The team decided to **keep T = 2026-04-01** and harvest more sources rather than move T.

**Do:**
- Harvest Tokyo Metropolitan Police (警視庁), Saitama, Osaka and Kanagawa police bulletins or
  case pages published after 2026-04-01. Also read the Tokyo MPD page on 警察官等をかたる詐欺
  (updated Apr 2026) that R2 found but didn't open.
- Target **≥ 20** narrative-rich ニセ警察 cases in total, including R2's ~10.
- Try to keep the payment-method mix near the NPA's H1 2026 split (transfer 65.6%, cash handover
  15.6%, crypto 13.9%). R2's set under-represents transfers. Report the actual mix.
- Same rules, table columns and confidence labels as R2. Add rows to R2's table rather than starting a new one.

**Search terms:** 警視庁 特殊詐欺 ニセ警察 事例 / 埼玉県警 特殊詐欺 発生状況 2026 /
大阪府警 特殊詐欺 手口 事例 / 神奈川県警 特殊詐欺 速報

**Deliver:** the extended R2 table, updated monthly counts, the payment-method mix, and whether
the 20-case target is met.

## Output format

Fill in this template under **Findings**, one block per item:

```markdown
### R<n> · <title>
**Status:** confirmed | likely | unresolved
**Answer (2–4 sentences):** …

**Sources**
| # | Title (original) | Publisher | Published | Accessed | URL |
|---|---|---|---|---|---|

**Key passages**
- [1] 「…」 — English gloss.

**Interpretation (ours, not the source's):** …
**Gaps / what I couldn't find:** …
**Suggested wording for the deck / decisions.md:** …
```

R2 also gets its case table and monthly counts. R1 also gets its question items and draft rules.

When done, add a short **Summary** at the top of Findings: one line per item with its status.

---

## Findings

**Researched:** 2026-10-12 (all "Accessed" dates below). Statute text was pulled verbatim from the e-Gov law API (`laws.e-gov.go.jp/api/1/lawdata/<law-id>`); PDFs were text-extracted locally. Where I only saw a search-engine or fetch-tool summary of a page (not the page text), it is flagged **[summary only]** and should be spot-checked before it goes on a slide.

## Summary

| Item | Status | One line |
|---|---|---|
| R3 | **confirmed** | Furikome Sagi Relief Act **Art. 3(1)**: a bank "shall appropriately take" suspension measures when it suspects an account is a crime-use account. Police info is one factor, **not required**. Art. 4–11 give the DIC notice → extinguishment → distribution process. Covers *transfer-induced* fraud only. |
| R4 | **confirmed** (basis), **arguable** (our exact handover) | APPI **Art. 27(1)(i)/(ii)** confirmed as you numbered them. PPC Q&A says a CCP **Art. 197(2)** inquiry = "based on laws" (i). A *teller-initiated* handover with no inquiry fits (ii) only weakly; **(iv)** is a better fit and wasn't in the brief. |
| R1 | **likely** | No published checklist with concrete teller *questions* found. Found: the NPA national request, prefectural "5-step" practice, the "ask what it's for, not 'are you being scammed?'" rule, Osaka's binding report duty. No national amount/age threshold is published. |
| R2 | **unresolved** | NPA made ニセ警察詐欺 its own category in **2026** (confirmed). Only **~15** post-2026-04-01 cases with usable narrative found, **not 20**. Counter-stopped cases with full dialogue are rare. T=2026-04-01 not yet shown feasible; see recommendation. |
| R5 | **unresolved** (lean *arguable* for opt-in pause, *unlikely* for "no counter override") | Every precedent found leaves an escape at the counter. A pause the customer cannot cancel at the counter has no precedent found. Needs legal review. |

---

### R3 · Legal basis for freezing the mule account (Furikome Sagi Relief Act)
**Status:** confirmed
**Answer (2–4 sentences):** The Act is 犯罪利用預金口座等に係る資金による被害回復分配金の支払等に関する法律 (平成十九年法律第百三十三号). **Art. 3(1)** says a financial institution "shall appropriately take" measures such as suspending transactions on its own account when, weighing factors including police information "and other circumstances", it recognises a suspicion of a crime-use account. A police request is therefore **not a precondition**; the bank's own information can count. **Art. 4(1)** raises the bar to "reasonable grounds to suspect" and then *obliges* the bank to suspend (if not already) and ask the Deposit Insurance Corporation (預金保険機構) to publish a notice. Art. 5, 7, 8–15 cover the 60-day claim period, extinguishment of the deposit claim, and distribution to victims.

**Sources**
| # | Title (original) | Publisher | Published | Accessed | URL |
|---|---|---|---|---|---|
| 1 | 犯罪利用預金口座等に係る資金による被害回復分配金の支払等に関する法律 (e-Gov API, law id 419AC1000000133) | 総務省 e-Gov 法令検索 | Act of 2007-12-21 | 2026-10-12 | https://laws.e-gov.go.jp/api/1/lawdata/419AC1000000133 (human page: https://laws.e-gov.go.jp/law/419AC1000000133) |
| 2 | 同法 (Japanese Law Translation DB, shows last amendment 平成25年法律第45号) | 法務省 | – | 2026-10-12 | https://www.japaneselawtranslation.go.jp/ja/laws/view/3126/ja |
| 3 | 振り込め詐欺救済法に基づく公告の流れ | 金融庁 (出典: 預金保険機構) | 2022-12-28 (PDF metadata) | 2026-10-12 | https://www.fsa.go.jp/policy/kyuusai/furikome/nagare.pdf |

**Key passages**
- [1] Art. 3(1) 「金融機関は、当該金融機関の預金口座等について、捜査機関等から当該預金口座等の不正な利用に関する情報の提供があることその他の事情を勘案して犯罪利用預金口座等である疑いがあると認めるときは、当該預金口座等に係る取引の停止等の措置を適切に講ずるものとする。」 — A financial institution, for its own accounts, when it recognises a suspicion that an account is a crime-use account, taking into account things like information from investigative authorities *and other circumstances*, shall appropriately take measures such as suspending transactions.
- [1] Art. 3(2) 「…他の金融機関の預金口座等があると認めるときは、当該他の金融機関に対して必要な情報を提供するものとする。」 — If it finds accounts at *other* banks used to move the funds, it shall give them the necessary information.
- [1] Art. 4(1) 「…犯罪利用預金口座等であると疑うに足りる相当な理由があると認めるときは、速やかに、…取引の停止等の措置が講じられていない場合においては当該措置を講ずるとともに、…預金保険機構に対し、…当該債権の消滅手続の開始に係る公告をすることを求めなければならない。」 — With "reasonable grounds to suspect", the bank must promptly suspend (if not yet done) and request the DIC to publish notice starting extinguishment.
- [1] Art. 5(2) 「…公告があった日の翌日から起算して六十日以上でなければならない。」 — Claim-filing period is at least 60 days from the day after notice. Art. 7: if nobody files, 「当該対象預金等債権は、消滅する。」 — the deposit claim is extinguished.
- [1] Art. 8(1) 「金融機関は、…消滅預金等債権の額に相当する額の金銭を原資として、…被害回復分配金を支払わなければならない。」 — The bank must pay distributions to victims out of an amount equal to the extinguished claim. Art. 11(2): payment-application period at least 30 days.
- [3] FSA/DIC flow chart: 「債権消滅手続開始公告（権利行使の届出期間 60日以上）」→「債権消滅公告」→「分配金支払手続開始公告（支払申請期間 法定30日以上、運用90日）」 — statutory minimum 30 days, 90 days in practice.

**Interpretation (ours, not the source's):**
- The Act supports "bank suspends a suspected same-bank mule account", and it doesn't prescribe *who* inside the bank decides, so a human fraud-analyst approval is compatible. Art. 3 is phrased as a duty-to-act ("講ずるものとする") rather than a power, and the bank's deposit terms separately let it suspend (see R5, Shinkin clause 3(2)).
- **Scope limit that matters for the demo:** the Act is about 振込利用犯罪行為 (fraud using *transfers into* an account) per Art. 1 and Art. 8 (definitions in Art. 2, not re-quoted here). It does not obviously cover cash-handover (現金手交) cases; NPA's H1-2026 figures show handover was 15.6% of ニセ警察 cases by count (see R2). Freezing only helps where money went to a bank account.
- It also assumes the scammer's account is at the *same* bank. Art. 3(2) / Art. 4(3) route other-bank accounts via information-sharing, not a freeze by us.

**Gaps / what I couldn't find:** Art. 2(4) definition of 犯罪利用預金口座等 not re-quoted verbatim. No FSA supervisory-guideline (監督指針) text or 全銀協 handling procedure fetched. A secondary summary [summary only] says 全銀協 coordinated with FSA/NPA/DIC on operating procedures and that courts have upheld banks refusing withdrawal where suspicion was reasonable (a law-journal article); I did not open either primary document.
**Suggested wording for the deck / decisions.md:** 「振り込め詐欺救済法第3条により、金融機関は自行口座に犯罪利用の疑いがあると認めるとき、取引停止等の措置を講ずるものとされる（警察情報は考慮要素の一つで、必須ではない）。凍結の最終判断は人（不正対策担当者）が行う。」 English: "Under Art. 3 of the Furikome Sagi Relief Act a bank takes suspension measures on its own account when it suspects crime use; police information is one factor, not a precondition. A human analyst makes the call. Applies to transfer-based fraud only."

---

### R4 · APPI basis for giving the police an evidence summary
**Status:** confirmed (provisions and PPC position on 197(2)); handover as designed = **arguable**
**Answer (2–4 sentences):** Your numbering is right: APPI **Art. 27(1)(i)** is 「法令に基づく場合」 and **(ii)** is the life/body/property exception with "consent difficult to obtain". The PPC's own Q&A states that an investigative-authority inquiry under **CCP Art. 197(2)** (or 507) falls under 27(1)(i), so the customer's consent isn't needed. The brief's other route, (ii), requires that obtaining consent be *difficult*, which is hard to argue when the customer is standing at the counter. **27(1)(iv)** (cooperating with a state body's statutory duties where consent would impede them) is a closer fit for a teller's voluntary handover.

**Sources**
| # | Title (original) | Publisher | Published | Accessed | URL |
|---|---|---|---|---|---|
| 1 | 個人情報の保護に関する法律 (e-Gov API, 平成十五年法律第五十七号) | e-Gov 法令検索 | – (current text at access) | 2026-10-12 | https://laws.e-gov.go.jp/api/1/lawdata/415AC0000000057 |
| 2 | 刑事訴訟法 (e-Gov API, 昭和二十三年法律第百三十一号) Art. 197 | e-Gov 法令検索 | – | 2026-10-12 | https://laws.e-gov.go.jp/api/1/lawdata/323AC0000000131 |
| 3 | 「医療・介護関係事業者における個人情報の適切な取扱いのためのガイダンス」【各論】Q4-25 | 個人情報保護委員会 | not shown | 2026-10-12 | https://www.ppc.go.jp/all_faq_index/faq3-qb4-25 |
| 4 | 個人情報の保護に関する法律についてのガイドライン（通則編）3-6-1 / 3-1-5 | 個人情報保護委員会 | 平成28年11月、令和8年6月一部改正 (as shown on page) | 2026-10-12 | https://www.ppc.go.jp/personalinfo/legal/guidelines_tsusoku/ |
| 5 | 健保組合向け Q&A 問319 **[summary only; not opened]** | 個人情報保護委員会 | – | – | https://www.ppc.go.jp/all_faq_index/faq4-q319 |

**Key passages**
- [1] Art. 27(1) 「個人情報取扱事業者は、次に掲げる場合を除くほか、あらかじめ本人の同意を得ないで、個人データを第三者に提供してはならない。」 — Except in the listed cases, a business may not give personal data to a third party without prior consent.
- [1] (i) 「法令に基づく場合」 — Where based on laws.
- [1] (ii) 「人の生命、身体又は財産の保護のために必要がある場合であって、本人の同意を得ることが困難であるとき。」 — Where necessary to protect a person's life, body or property **and** obtaining consent is difficult.
- [1] (iv) 「国の機関若しくは地方公共団体又はその委託を受けた者が法令の定める事務を遂行することに対して協力する必要がある場合であって、本人の同意を得ることにより当該事務の遂行に支障を及ぼすおそれがあるとき。」 — Where cooperation with a national/local government body's statutory duties is needed **and** getting consent would risk impeding that task.
- [2] CCP Art. 197(2) 「捜査については、公務所又は公私の団体に照会して必要な事項の報告を求めることができる。」 — For an investigation, [police] may inquire of public offices or public/private bodies and ask for a report of necessary matters.
- [3] 「刑事訴訟法第１９７条第２項又は第５０７条に基づく警察や検察等の捜査機関からの照会や事情聴取は、個人情報保護法第２７条第１項第１号の「法令に基づく場合」に該当し、患者本人の同意を得ずに回答しても同法違反とはなりません。」 — An inquiry or interview by police/prosecutors under CCP 197(2) or 507 is "based on laws" under APPI 27(1)(i); answering without the patient's consent is not an APPI violation.
- [3] 「求められた情報以外の情報を提供した場合には、損害賠償を請求されるおそれも否定できません。」 — Providing information beyond what was asked may expose the provider to damages claims.
- [3] 「…求めに応じ提供したことを後日説明できるようにしておくことが必要と思われます。」 — Keep a record of the officer's title/name and what was provided so it can be explained later.
- [4] (as read via fetch tool, **[summary only]**) 3-6-1 gives no bank/police fraud example for (ii); it cross-refers to 3-1-5(2), whose examples are 「急病その他の事態が生じたときに、本人について、その血液型や家族の連絡先等を医師や看護師に提供する場合」 and 「大規模災害や事故等の緊急時に…被災者情報・負傷者情報等を家族、行政機関、地方自治体等に提供する場合」.

**Interpretation (ours, not the source's):**
- **Most relevant PPC example:** [3]. It is written for medical/care providers, but the reasoning (197(2) inquiry → (i)) is general. No PPC example about *banks and fraud* was found.
- Our design (teller hands over a printed summary, no inquiry yet): (i) does **not** apply unless police have issued a 197(2) inquiry; (ii) needs "consent difficult" — a present, reachable customer undermines that; **(iv) is the better hook**, but it also needs "consent would impede the task", which is arguable but plausible (a scam victim coached to refuse help). Also, APPI Art. 27 governs "個人データ" (data in a searchable database); a verbal summary of a conversation may be 個人情報 but not 個人データ at all. A lawyer should confirm that distinction.
- **Safer design:** have police issue a 197(2) inquiry (or take the summary on the spot as a response to officers on scene) and provide only what's asked; log officer name/title.

**Gaps / what I couldn't find:** No PPC or FSA example specifically on banks reporting suspected fraud to police. Q&A 4-25 has no publication date on the page. A secondary search summary mentioned a 2026-09 PPC proposal to relax consent for some third-party provision **[summary only, unverified; not relied on]**.
**Suggested wording for the deck / decisions.md:** 「警察への証拠要約の提供は、個人情報保護法第27条第1項第1号（法令に基づく場合：刑訴法197条2項の照会）を基本とし、同項第2号・第4号（財産の保護／国の事務への協力）を補完的根拠とする。提供範囲は照会・要請の範囲に限る。」 English: "Handover to police rests on APPI Art. 27(1)(i) (via a CCP 197(2) inquiry), with (ii)/(iv) as supporting grounds; scope limited to what police ask for. Needs legal confirmation for teller-initiated handovers."

---

### R1 · Published teller-check guidance (evaluation baseline "arm (a)")
**Status:** likely (practice and structure confirmed; **concrete question lists and numeric thresholds not found**)
**Answer (2–4 sentences):** Nationally, the NPA asks every bank to *speak to* customers making high-value transfers or taking home high-value cash, and to contact the nearest police station. Prefectural practice adds a staged routine and the explicit rule "ask what the money is for, don't just ask 'are you being scammed?'". No public document gave a numbered list of teller questions or a national amount/age threshold. The only legally binding example is Osaka's ordinance (report duty, Art. 21(3)).

**Sources**
| # | Title (original) | Publisher | Published | Accessed | URL |
|---|---|---|---|---|---|
| 1 | 警察庁・都道府県警察では、振り込め詐欺などの被害を防止する観点から､全国の金融機関に対し、・高額の振込をされるお客様 ・高額の現金をお持ち帰りになるお客様へのお声かけのほか、最寄りの警察署への連絡を求めています。 | 警察庁・都道府県警察 (hosted by 金融庁) | PDF created 2013-10-03 (metadata) | 2026-10-12 | https://www.fsa.go.jp/news/25/ginkou/2020140210-1/02.pdf |
| 2 | 金融機関に対し、声掛けと通報の強化を依頼 | 秋田県警察本部 | not shown | 2026-10-12 | https://www.police.pref.akita.lg.jp/uploads/contents/pages_0000000697_00/010_261209boukitaisakukyouka.pdf |
| 3 | 特殊詐欺被害防止のため、声かけへのご協力をお願いします | 広島市 市民安全推進課 | 2025-02-16 (last updated) | 2026-10-12 | https://www.city.hiroshima.lg.jp/living/1035962/1021171/1025678/1020476.html |
| 4 | 特殊詐欺被害防止(金融機関・コンビニでの声かけ) | 兵庫県警察 | not shown (cites agreement of 令和7年7月7日) | 2026-10-12 | https://www.police.pref.hyogo.lg.jp/tokusyusagi/koekake/index.htm |
| 5 | 大阪府安全なまちづくり条例の改正 (Art. 21(3), Art. 23) — police summary, **not the ordinance text** | 大阪府警察本部 | in force 2025-08-01 / 2025-10-01 | 2026-10-12 | https://www.police.pref.osaka.lg.jp/seikatsu/ammachijorei/2/20641.html |
| 6 | 特殊詐欺の手口と対策 | 警察庁組織犯罪対策部 | 令和5年4月13日 | 2026-10-12 | https://www.npa.go.jp/bureau/criminal/souni/tokusyusagi/teguchi-taisaku.pdf |
| 7 | コンプライアンス・マニュアル 預金業務「金融犯罪」(高知銀行 — bank name inferred from the document's pp. 13, 16, 20) | 高知銀行 (hosted by 消費者庁) | file dated 2021-05-27 | 2026-10-12 | https://www.cao.go.jp/consumer/history/06/kabusoshiki/winwin/doc/006_210527_shiryou2_2.pdf |
| 8 | 被害の未然防止事例紹介 (monthly cases, Sep 2025–Aug 2026) | 岡山県警察 生活安全企画課 | updated 2026-10-05 | 2026-10-12 | https://www.pref.okayama.jp/site/293/890484.html |

**Key passages**
- [1] 「高額の振込をされるお客様・高額の現金をお持ち帰りになるお客様へのお声かけのほか、最寄りの警察署への連絡を求めています」 — Banks are asked to speak to customers making high-value transfers / taking home high-value cash, and to contact the nearest police station.
- [2] Trigger 「金融機関の窓口で一定の年齢以上の方が一定の金額以上の現金を引き出そうとした場合」 (the age and amount are *not printed*), then steps ①「警察からのお願い」を提示 ②アンケートを実施 ③振込みによる支払を勧める ④預金小切手による取引を勧める ⑤警察に通報し、警察官が臨場 — i.e. show the police request; give a questionnaire; suggest transfer instead of cash; suggest a bank cheque; report and have officers attend. Plus 「このほか、被害のおそれがある場合は、すぐに警察に通報する。」
- [3][4] 「単に「だまされていませんか？」と伺っても、犯人にだまされている方は、自分がだまされているとは思っておらず、効果が認められないため、お金の使い途などを詳しく伺わせていただいています。」 (Hiroshima; Hyogo has near-identical logic) — Merely asking "are you being scammed?" doesn't work because victims don't think they are; staff ask in detail what the money is for.
- [5] Art. 21(3): 「特殊詐欺等の被害に遭っていたり、遭うおそれがある人を発見した場合、警察への通報等の措置を講じなければなりません。」 — Institutions must report to police etc. when they find someone who is or may be a victim. Art. 23(1): ATM transfer limit ≤ ¥100,000/day for accounts that are 70+, no ATM transfer in 3 years, Osaka resident (limit removable on customer request if no fraud risk; Art. 23(3)).
- [6] 「金融機関の職員のいる有人窓口等において、「特殊詐欺の被害に係る出金、送金等ではない」という一応の確認がされれば、出金、送金等はできる。ただし、被疑者から「銀行の窓口では、（出金、送金等の理由を）こう説明してください。」などと言われて、被害者が窓口で当該…説明をする場合等もあり、確認には、時間を要することもある。」 — At a staffed counter, withdrawal is allowed once a basic confirmation of "not scam-related" is obtained; but scammers coach victims on what to say, so confirmation can take time. **This is the baseline's known weakness, in NPA's own words.**
- [7] 「金融機関は、高額の振込や高額の出金をされるお客さまに声掛けをするよう警察庁から要請されています。お客さまに対して振込や出金の理由等を確認させていただき、聴取の結果、被害に遭われている疑いがある場合には、被害防止のために金融機関から警察に通報し、警察官が事情を伺うこととなっています。」 — Banks are asked by NPA to speak to high-value customers; staff confirm the reason; if scam is suspected they notify police and officers speak to the customer.
- [8] Real counter practice, Apr–Aug 2026 entries: (a) 「息子に頼まれた」としか言えず目的を説明できない → 通報 (Tomato Bank, Apr); (b) 「補助金がもらえる」→ 詳細確認 (post office, May); (c) 「息子の弁護士費用」→ 理由を聞き **息子に直接電話** (JA, Jun); (d) 車購入と説明 → **購入関係書類の提示を求め**、答えられず通報 (post office, Jul); (e) 「東京の警察」から送られた Letterpack、「守秘義務約定書」入り → 差出人と中身を一緒に確認 (post office, Aug).

**Draft baseline (arm a) — DRAFT, parameters in [ ] are placeholders, not sourced**
1. **Trigger:** customer aged ≥ [A] requests cash withdrawal ≥ ¥[X] or transfer ≥ ¥[X] *or* any other sign of risk (on the phone; first-time large transfer; sudden limit increase; unexplained purpose) [1][2][8].
2. **Step 1 – Show the police request / hand the questionnaire** [2].
3. **Step 2 – Ask the purpose in open form** ("What will the money be used for?", "Who asked you to do this?" "Are you talking to anyone by phone/LINE right now?"). *The last two are our wording, not found verbatim in any source;* [3][4] only give the "ask what it's for" principle.
4. **Step 3 – Verify the stated purpose**: ask for supporting documents (invoice/contract/purchase papers) or phone the named relative directly [8c, 8d].
5. **Step 4 – Offer safer alternatives** (bank transfer instead of cash, bank cheque) [2].
6. **Escalate:** if the purpose can't be explained, answers are inconsistent/evasive, or the customer says police/prosecutors/officials told them to do it → **pause and call police** (110 / local station); police attend [2][5][7].
7. **Release:** if the customer gives a plausible explanation and no red flag appears, pay out — which is exactly the NPA-acknowledged gap when the story was coached [6].

**Does practice vary?** Yes. The national request [1] is generic; thresholds and routines are set by each prefectural police and bank and mostly *not published*. Osaka is the only place found with a binding duty (Art. 21(3)) and ATM cap (Art. 23). **Most representative sources:** [1]+[6] for the national position, **[2] Akita for the staged routine**, [8] Okayama for realistic teller behaviour. A secondary news summary [summary only, 2019] said Urayasu (Chiba, age 60+) and Tondabayashi (Osaka, age 65+) ask banks to report withdrawals ≥ ¥1M; I did not open that article and the figures may be outdated.

**Interpretation (ours, not the source's):** Arm (a) should be defined as "[1]+[2]+[8] open-purpose questioning with documentary verification and police escalation", and its **expected weakness (coached cover stories) should be conceded** citing [6]. That is stronger than hiding it.
**Gaps / what I couldn't find:** No 全銀協 or FSA teller question list; no numeric thresholds in any national document; the Akita PDF has no visible date; Osaka ordinance text itself (only the police summary) not read; bank-internal manuals (e.g. a secondary note that a shinkin uses a "check sheet" [summary only]) not public. Tried: the five suggested search terms plus 声かけ 質問例 / 確認項目 / 通報基準 variants.
**Suggested wording for the deck / decisions.md:** 「比較対象（arm a）は、警察庁の要請に基づく現行の窓口声かけ（使途の確認→疑いがあれば警察通報）。警察庁自身が『犯人が窓口での説明を指示する場合がある』と認めている点が既存手法の限界である。」 English: "The baseline is today's counter practice requested by the NPA: ask the purpose, escalate to police if suspicious. The NPA itself notes scammers coach victims on what to say at the counter — the known gap."

---

### R2 · Date T and the post-T held-out case set
**Status:** unresolved (category question **confirmed**; the 20-case target is **not shown to be met**)
**Answer (2–4 sentences):** The NPA treats ニセ警察詐欺 as its own method **from 令和8年 (2026)**, with statistics starting then. I found about **15 post-2026-04-01 cases with narrative detail adequate for adaptation** (9 victim-side weekly reports from Toyama Police, 5 monthly counter cases from Okayama Police — only 1 of them fake-police — and 1 news report) plus ~6 thinner commendation reports. Cases *stopped at a bank counter* with the actual dialogue are the scarce part; most sources describe completed victimisations. **I could not confirm 20 from one pass, so the proposed T is not yet demonstrably feasible.**

**Sources**
| # | Title (original) | Publisher | Published | Accessed | URL |
|---|---|---|---|---|---|
| 1 | 令和８年上半期における特殊詐欺の認知・検挙状況等について（暫定値）/ ＜令和８年の特殊詐欺の手口についてのお知らせ＞ | 警察庁 | 2026-07-31 | 2026-10-12 | https://www.npa.go.jp/bureau/safetylife/sos47/assets/img/new-topics/detail/260731/01/01.pdf |
| 2 | 令和８年８月末における特殊詐欺の認知・検挙状況等について（暫定値） | 警察庁 | 2026-10-02 | 2026-10-12 | https://www.npa.go.jp/bureau/safetylife/sos47/new-topics/261002/01.html |
| 3 | 特殊詐欺情報（旧週間犯罪情報）— weekly PDFs 令和8年3月30日〜8月30日 | 富山県警察本部 生活安全企画課 | page updated 2026-09-10; "週間犯罪情報の更新を終了" after 2026-08 | 2026-10-12 | https://police.pref.toyama.jp/6108/syuukannhannzai.html (PDFs under /documents/3074/) |
| 4 | 被害の未然防止事例紹介 | 岡山県警察 | 2026-10-05 | 2026-10-12 | https://www.pref.okayama.jp/site/293/890484.html |
| 5 | 実際にあった「電話de詐欺」の犯人の電話音声 (real audio, incl. ニセ警察; newest recording Nov 2024) | 千葉県警察 | not shown | 2026-10-12 | https://www.police.pref.chiba.jp/seisoka/safe-life_fraud-audio.html |
| 6–15 | News/commendation items — URLs in the table below | various | various | 2026-10-12 | – |

**Key passages**
- [1] 「被害が急増している「ニセ警察詐欺」を独立した手口として位置付けました。」 — "The fast-rising ニセ警察詐欺 has been made an independent method." Also 「ニセ警察詐欺の検挙件数及び検挙人員は、令和８年から統計を開始している」 — arrest stats begin in 2026 (so no clean 2025 series; 2025 cases sit inside other categories).
- [1] H1 2026: ニセ警察 **4,466件 / 507.9億円**; 既遂1件当たり **1,163.9万円**; victims' 70s most common; by delivery: 振込型 2,930件 (**65.6%**), 現金手交型 695件 (**15.6%**), 暗号資産送信型 620件 (**13.9%**); initial contact by phone 98.2%.
- [2] To end-Aug 2026: **6,346件 / 728.6億円** (件数 −4.1%, 被害額 +27.0% y/y). (NPA page doesn't define the category or give delivery breakdown.)
- NPA's earlier public alert page 「ニセ警察詐欺に注意！」 carries the path `/new-topics/241218/` (i.e. **Dec 2024**) **[URL date only; page not opened]** — the *term* predates the 2026 statistical category.

**Candidate cases published after 2026-04-01** (counter = case was stopped/handled at a bank counter; "usable" = narrative detail sufficient to adapt later; "weekly bulletin" dates are the week the report covers)
| # | Date | Source (URL) | Impersonation | Channel / instructions | Payment | Amount | Counter | Usable |
|---|---|---|---|---|---|---|---|---|
| 1 | wk 4/6–4/12 | Toyama weekly 0406.pdf | 銀行員→八王子警察署 | +国際番号 auto-voice→phone; 口座の不正利用, 無実証明に紙幣シリアル調査; secrecy instruction present (partial) | transfer (method not captured) | ¥1.24M | n (not stated) | y |
| 2 | wk 4/6–4/12 | same | NTT職員→大阪府警 | phone+LINE; 警察手帳・守秘義務誓約書を提示; 預貯金の紙幣調査で無実証明 | ATM transfers ×4 | ¥8.0M | n (ATM); *bank flagged to police* | y |
| 3 | wk 5/11–5/17 | 0511.pdf | 総務省職員→静岡中央警察署→検察官 | phone→LINE video→Signal; マネロン, 出頭か逮捕; 逮捕状書類; **友人に話せば逮捕** | ATM (per text) | ¥3.97M | n | y |
| 4 | wk 5/11–5/17 | same | 警視庁警察官 | landline; 逮捕状; 通帳提出, **毎日出金して保管**, 現金を自宅敷地に置く | cash handover (after repeated withdrawals) | ¥6.9M | n (withdrawals at bank – counter opportunity) | y |
| 5 | wk 5/25–5/31 | 0525.pdf | 中国出入国管理局→警察官 | phone→chat app; **家族にも言ってはいけない**; 口座開設→入金→振込×3 | transfer | ¥4.0M | n | y |
| 6 | wk 6/15–6/21 | 0615.pdf | 東京中央南警察署→東京検察庁 | landline; **別の警察に通報してはいけない**; 預金確認, 現金237万円を自宅敷地に置く | cash handover | ¥2.37M | n | y |
| 7 | wk 7/13–7/19 | 0713.pdf | 金融機関職員→京都府警→検事 | phone; **逮捕前保釈保証金**; IB transfers | online banking | ¥23.27M | n | y |
| 8 | wk 7/27–8/2 | 0729.pdf | 警視庁警察官 | SMS→call centre; **家族にも話してはいけない**; 暗号資産で無実証明 | crypto ×3 | ¥1.30M | n | y |
| 9 | wk 7/27–8/2 | same | 通信事業者→東京中央警察署捜査二課→東京地検検事 | phone→messaging app; 定時連絡; 資金調査 | cash left at home ×2 (incl. ¥7M withdrawn) | ¥16.0M | n | y |
| 10 | 2026-08 (page updated 10/5) | Okayama [4] | "東京の警察" (Letterpack from sender; 守秘義務約定書 enclosed) | mail | – | n/s | **y** (post office) | y |
| 11 | 2026-04 | Okayama [4] (Tomato Bank) | not ニセ警察 (「息子に頼まれた」) | cash withdrawal | cash | n/s | **y** | y (generic) |
| 12 | 2026-05 | Okayama [4] (post office) | 「補助金」 | raising limit | – | n/s | **y** | y (generic) |
| 13 | 2026-06 | Okayama [4] (JA) | 息子の弁護士費用 | cash | cash | n/s | **y** | y (generic) |
| 14 | 2026-07 | Okayama [4] (post office) | 車購入と説明 | cash | cash | n/s | **y** | y (generic) |
| 15 | 2026-10-10 (year not in text) | 福島中央テレビ via Yahoo: https://news.yahoo.co.jp/articles/512b1a9948563d8f1f5b9b565cf2d21912d4473d | 空港職員→警察官→検察官 | landline→mobile→SNS video; マネロン; 全財産の紙幣確認 | cash left in home mailbox | ¥2.4M | n | y |
| 16 | 2026-06-29 | SunSun TV https://www.sunsuntv.co.jp/news/2026/06/2763450 | 警察官等 (Kochi) | n/s | cash **mailed**; Yamato intercept | ¥13.0M | n | partial |
| 17 | 2026-09-08 | 伊勢新聞 https://www.isenp.co.jp/2026/09/08/152714/ | ニセ警官 (customer said "警察から連絡") | n/s; customer "今は言えない" | n/s | n/s | y/home visit (33 Bank) | partial |
| 18 | 2026-09-15 | NHK Hiroshima https://news.web.nhk/newsweb/na/nb-4000035778 | 警察官 | n/s | **gold purchase** | n/s | y (Hiroshima Bank Miyauchi) | partial |
| 19 | 2026-10-01 | 京都中央信金 release https://www.kyoto-np.co.jp/articles/biz/1800403 | ニセ警察 + 息子騙り (2 cases) | n/s | n/s | n/s | y | n |
| 20 | 2026-10-09 | 北日本新聞 https://webun.jp/articles/-/1107751 (paywalled) | ニセ警察 | n/s | n/s | n/s | y (Hokuriku Bank Shinjo) | n |
| 21 | 2026-06-02 | 岐阜新聞 https://www.gifu-np.co.jp/articles/-/717456 (paywalled) | ニセ電話 | n/s | n/s | n/s | y (Gifu Shinkin) | n |
| – | 2026-07-29 | UHB https://www.uhb.jp/news/single.html?id=61053 | **not fake-police** (SNS investment) but rich counter dialogue: 「前の日まで指定されていた口座が今朝になって違う口座に変わった」 | SNS | counter transfer | ¥0.37M | **y** | y (as counter example) |

**Monthly counts, post-2026-04-01** (per row above; "usable" = column Usable y; "counter" = Counter y)
| Month | Fake-police, usable | Counter-stopped (any scam type), usable | Thin/other |
|---|---|---|---|
| 2026-04 | 2 (Toyama) | 1 (Okayama) | – |
| 2026-05 | 3 (Toyama ×3) | 1 | – |
| 2026-06 | 1 (Toyama) | 1 | 2 (SunSun, Gifu) |
| 2026-07 | 3 (Toyama ×3) | 2 (Okayama, UHB) | – |
| 2026-08 | 0 (Toyama, none found) | 1 (Okayama; fake-police-linked) | – |
| 2026-09 | 0 | 0 | 2 (Isenp, NHK Hiroshima) |
| 2026-10 (to 10/12) | 1 (FCT; year inferred) | 0 | 2 (Kyoto, Hokuriku) |
| **Total** | **~10 fake-police, narrative-rich** | **~6 counter, generic-scam** | **~6 thin** |

Toyama's weekly bulletin stopped after 2026-08, and my count is of **one prefecture** (Toyama's population is small) plus partial sampling elsewhere; Tokyo, Saitama, Kanagawa, Osaka weekly/monthly bulletins were **not** harvested, and they very likely hold many more. The 20-case target is plausible with them, but not shown here.

**Interpretation (ours, not the source's) — recommended T:**
- **Option A (preferred if you can spend one more hour):** keep **T = 2026-04-01** and harvest Tokyo MPD, Saitama and Osaka bulletins to reach ≥ 20 narrative-rich fake-police cases. Real counter *dialogues* will stay scarce regardless, so the held-out set should be mostly victim-side narratives that an annotator converts to counter dialogue, which is a larger adaptation step than "adapted from reported cases" implies. Say so in the deck.
- **Option B (if time-boxed):** move **T earlier to 2026-01-01**. Toyama's own page carries Jan–Mar 2026 bulletins in the same format (police-impersonation phrases appear in 7 of the 13 weekly sections from 1/5 to 3/29, e.g. 1/19–1/25 ×9 mentions), so this alone likely gives ≥ 20 — but those weeks predate the NPA's new category, so cases need manual tagging as ニセ警察. Playbook corpus before T stays large (NPA alerts date back to at least Dec 2024).
- The 2026 NPA statistics let us report the hold-out's representativeness: 振込 65.6% / 現金手交 15.6% / 暗号資産 13.9%. In my 9 Toyama cases, handover or crypto dominate, so the set may under-represent transfers.

**Gaps / what I couldn't find:** Case rows 16–21 rely on partial or paywalled articles; row 15's year is not printed in the article text (inferred from "October 10 (Saturday)" matching 2026). No published real-call audio dated after 2024-11 was found on the Chiba page (list is of recording dates, newest Nov 2024). NPA 2025 per-method figures weren't extracted. A Tokyo MPD page on 警察官等をかたる詐欺 exists (updated Apr 2026) but I did not read it.
**Suggested wording for the deck / decisions.md:** 「ニセ警察詐欺は警察庁が2026年から独立区分として統計化（2026年上半期: 4,466件・507.9億円）。評価用の保留事例は、2026年4月1日以降に公表された警察発表の事例から構成し、プレイブックは同日以前の注意喚起のみで構築する（T=2026-04-01、事例数は確認中）。」

---

### R5 · Enforceability of a non-cancellable, pre-agreed cooling-off pause
**Status:** unresolved (needs legal review). Lean: **arguable** for the opt-in pause itself; **unlikely/unproven** for "can't cancel at the counter".
**Answer (2–4 sentences):** No precedent found for a customer-chosen, bank-enforced payment pause that the customer cannot override at the counter. Every analogue found keeps a counter escape: ATM limits can be lifted at the window, and Osaka's ATM cap can be removed on request. Existing deposit-terms clauses let the bank suspend for money-laundering or unlawful-use suspicion, not to protect the depositor's own withdrawals. The Consumer Contract Act Art. 10 test (rights narrower than default rules *and* contrary to good faith) is the key risk, and I found no case law applying it to deposits.

**Sources**
| # | Title (original) | Publisher | Published | Accessed | URL |
|---|---|---|---|---|---|
| 1 | 消費者契約法 (e-Gov API, 平成十二年法律第六十一号) Art. 10 | e-Gov 法令検索 | – | 2026-10-12 | https://laws.e-gov.go.jp/api/1/lawdata/412AC0000000061 |
| 2 | 普通預金、納税準備預金共通規定 | 信用金庫 (shinkin.co.jp common rules) | PDF created 2020-03-04 | 2026-10-12 | https://www.shinkin.co.jp/torishin/kitei/pdf/futuu/futsuu_kyoutsuu.pdf |
| 3 | 金融取引の代理等に関する考え方および銀行と地方公共団体・社会福祉関係機関等との連携強化に関する考え方（公表版） | 全国銀行協会 | 2021-02-18 | 2026-10-12 | https://www.zenginkyo.or.jp/fileadmin/res/news/news330218.pdf (**body not read**; news page: https://www.zenginkyo.or.jp/news/2021/n021801/) |
| 4 | 特殊詐欺対策を目的とするATMでのキャッシュカードによるお引出しの一部制限について | 三菱UFJ信託銀行 (domain tr.mufg.jp; fetch tool labelled it MUFG Bank, **verify**) | 2026-07 (limit effective 2027-01-25) | 2026-10-12 | https://www.tr.mufg.jp/ippan/topics/20260717_tokusyusagi_atm_cashcard_seigen.html |
| 5 | 大阪府安全なまちづくり条例 Art. 23 (police summary) | 大阪府警察本部 | 2025-10-01 in force | 2026-10-12 | https://www.police.pref.osaka.lg.jp/seikatsu/ammachijorei/2/20641.html |

**Key passages**
- [1] Art. 10 「…消費者の権利を制限し又は消費者の義務を加重する消費者契約の条項であって、民法第一条第二項に規定する基本原則に反して消費者の利益を一方的に害するものは、無効とする。」 — A consumer-contract term that restricts the consumer's rights or increases their duties compared with default (non-mandatory) law, **and** unilaterally harms the consumer contrary to the good-faith principle of Civil Code Art. 1(2), is void.
- [2] 2(2) 「…マネー・ローンダリング、テロ資金供与、もしくは経済制裁関係法令等への抵触のおそれがあると判断した場合には、入金、払戻し等の本規定にもとづく取引の一部を制限する場合があります。」 — The bank may restrict part of deposits/withdrawals if it judges there is a risk of money-laundering / terror-financing / sanctions breach. 2(3): restriction is lifted once the risk is "合理的に解消された" on the depositor's explanation.
- [2] 3(2)④ 「この預金が法令や公序良俗に反する行為に利用され、またはそのおそれがあると認められる場合」 — If the deposit is used or likely to be used for unlawful/immoral acts, the bank may suspend transactions or terminate.
- [4] The limit applies to customers 70+ with no ATM transfer in 3 years; the notice offers an **opt-out** route; per the fetch tool, counter withdrawals appear unaffected **[summary only; text partly garbled]**.
- [5] Art. 23: 10万円/day ATM cap for 70+/3-year no-transfer/Osaka residents; removable on the customer's request "if the institution judges there is no risk of special fraud".
- [3 — via search summary, **[summary only]**] The 2021 全銀協 paper says proxies' withdrawals can be accommodated where *clearly in the depositor's interest* and says adult guardianship is the basic route; the 2022 全銀協 document on 不測の事態における預金の払出し (https://www.zenginkyo.or.jp/fileadmin/res/news/news340516.pdf) is a follow-on. Not read in full.

**Interpretation (ours, not the source's):**
- **For you:** opt-in, short (≤ 24 h), capped, customer-initiated, and aimed at the customer's own interest; the customer can set it up while well. Art. 10 requires the term to *unilaterally harm* the consumer; a protection the consumer chose is less likely to be seen that way. Bank-offered ATM limits with a customer opt-out [4] show the sector already limits consumers' default right to withdraw at will.
- **Against you:** a deposit is repayable on demand (consumption deposit). A term that stops the customer withdrawing at the counter **even when they, with capacity, demand it** restricts a default right with no escape. Contemporary precedents all keep a counter or request route [4][5]. Existing clauses [2] protect the bank/public from misuse, not the depositor from themselves.
- **Cheapest risk reduction (design, not legal advice):** keep the pause, but give the customer a defined override path — e.g. after the nominated person has been called and confirms, or after the 24 h expires, or with a second identity check — so it is a *delay* rather than a *prohibition*. That puts it much nearer the sector analogues.

**Gaps / what I couldn't find:** No case law applying 消契法10条 to deposit withdrawal limits; no bank terms with a customer-selected, non-cancellable pause; no 全銀協 text on pre-agreed "trusted person" arrangements (only a shinkin pre-registered-agent service surfaced **[summary only]**); the full 全銀協 2021 paper not read; no FSA/CAA commentary. Searches tried: all five suggested terms plus 取引の制限 / 預金規定 / ATM限度額 / 見守り variants.
**Suggested wording for the deck / decisions.md:** 「お客様ご自身が事前に選択する、最大24時間の一時保留（家族への連絡付き）。保留を窓口で取り消せない設計の法的有効性（消費者契約法10条等）は未確認であり、法務レビュー要。」 English: "A customer-chosen pause of up to 24 hours with a call to a nominated family member; the enforceability of a pause that cannot be cancelled at the counter (Consumer Contract Act Art. 10 etc.) is unresolved and needs legal review."

---

### Method notes / caveats
- Statutes (APPI, CCP, Furikome Act, Consumer Contract Act) were read directly from e-Gov's XML API, so those quotes are verbatim. e-Gov returns the current consolidated text; I did not check amendment dates beyond the law numbers.
- PDFs (NPA, Akita, Kochi Bank manual, Shinkin rules, FSA flow, Toyama weeklies) were text-extracted locally. The Osaka PDF `2025_12_355_02_03.pdf` extracted as garbled text, so I relied on the Osaka Prefectural Police summary page instead.
- Quotes marked **[summary only]** came from a search-engine or fetch-tool summary. The fetch tool also truncates and paraphrases; short quotes from web pages (PPC Q&A 4-25, Hiroshima, Hyogo, Okayama, Osaka police) should be spot-checked against the live page before publication.
- I did not read: the Osaka ordinance text, 全銀協 2021 paper body, PPC Q&A 問319, Tokyo MPD / Saitama / Chiba bulletins, or any FSA 監督指針.
