#!/usr/bin/env node
/**
 * Mock of the services the web UI talks to, built from docs/architecture/api-contracts.md.
 *
 * One process answers for core-bank-mock, case-svc and conversation-svc (scoring has no browser
 * endpoint). It accepts the paths as the services see them (`/cases/...`) and also with nginx's
 * `/api/{core,scoring,case,conversation}` prefix, so the Vite proxy, nginx and the tests can all
 * point at it. It replays the Tanaka flow (docs/architecture/c4-dynamic-tanaka.md):
 *
 *   POST /transfers (counter, 3,000,000) -> alert, case opened -> card with the first question
 *   -> customer turns (indicators found by keyword, risk-v1 computed here) -> pause recommended at c4
 *   -> POST decision (pause) -> hold + notice to Yuki -> WS /phone callback (number + case code)
 *   -> contact_view -> freeze request -> analyst approves -> six others
 *
 * The risk rule below is a small copy of risk-v1 (schemas/README.md) for the mock only. This is NOT the
 * real copilot: indicator detection is keyword matching so a typed demo behaves plausibly.
 *
 *   node mock-server/server.mjs            # PORT (default 8090), MOCK_DELAY_MS (default 1200)
 *   POST /__mock/reset                     # mock-only: back to the start of the demo
 */
import http from "node:http";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";

const DEMO_START = Date.parse("2026-10-13T11:42:00+09:00");
const PUBLISHED = "+81312345678";
const YUKI = "+819012345678";
const MULE = "acct-mule-0001";
const MENU_RETURN = "returning_a_call_about_a_case";

const pad = (n, w = 2) => String(n).padStart(w, "0");
function jst(ms) {
  const d = new Date(ms + 9 * 3600e3);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}+09:00`;
}
const jstParts = (ms) => {
  const d = new Date(ms + 9 * 3600e3);
  return { y: d.getUTCFullYear(), mo: d.getUTCMonth(), d: d.getUTCDate(), dow: d.getUTCDay() };
};
const atJst = (y, mo, d, h) => Date.UTC(y, mo, d, h) - 9 * 3600e3;

/** Hold window (api-contracts "Hold window"): max(placed+min, next business-day close) capped at placed+cap. */
export function holdWindow(placedMs, { minimum_hours = 4, extend = true, cap_hours = 24 } = {}) {
  const minEnds = placedMs + minimum_hours * 3600e3;
  let ends = minEnds;
  if (extend) {
    for (let i = 0; i < 10; i++) {
      const p = jstParts(minEnds + i * 86400e3);
      if (p.dow === 0 || p.dow === 6) continue;
      const close = atJst(p.y, p.mo, p.d, 15);
      if (close >= minEnds) {
        ends = Math.max(minEnds, close);
        break;
      }
    }
  }
  const cap = placedMs + cap_hours * 3600e3;
  return { minimum_ends_at: minEnds, ends_at: Math.min(ends, cap), cap_ends_at: cap };
}

// ------------------------------------------------------------------ static data (synthetic)

const CUSTOMERS = {
  "cust-tanaka-0001": { customer_ref: "cust-tanaka-0001", display_name_ja: "田中 圭子", display_name_kana: "タナカ ケイコ", tenure_years: 12, branch_name_ja: "サンプル銀行 駅前支店" },
};
const OTHER_PAYERS = [
  ["cust-0002", "acct-0002", "佐藤 花子", 1200000, "2026-10-09T10:12:00+09:00"],
  ["cust-0011", "acct-0011", "鈴木 一郎", 800000, "2026-10-09T13:40:00+09:00"],
  ["cust-0023", "acct-0023", "高橋 美咲", 2000000, "2026-10-09T15:05:00+09:00"],
  ["cust-0034", "acct-0034", "伊藤 健", 450000, "2026-10-12T09:50:00+09:00"],
  ["cust-0041", "acct-0041", "渡辺 久美子", 1500000, "2026-10-12T14:22:00+09:00"],
  ["cust-0052", "acct-0052", "山本 浩二", 600000, "2026-10-13T09:31:00+09:00"],
];

const QUESTIONS = [
  { id: "q.general.purpose", ja: "このお金は、どのようなご用途でしょうか。", en: "If you don't mind, may I ask what the money is for?" },
  { id: "q.fake_police.what_said", ja: "お電話の相手の方は、どのようなお話をされていましたか。", en: "What did the person on the phone say?" },
  { id: "q.fake_police.returned", ja: "そのお金は、後で戻ってくると言われていますか。", en: "Were you told the money would be returned later?" },
  { id: "q.fake_police.letters", ja: "警察や役所の名前で、書類や封筒が届いたりしていませんか。", en: "Have any documents or envelopes arrived in the name of the police or a government office?" },
];
const HOLD_LINE = {
  id: "h.fake_police.real_police",
  ja: "警察や金融庁が、お電話でお金の移動や、誰にも言わないことをお願いすることはございません。念のため、こちらから警察に確認させていただけますか。",
  en: "The police and the FSA never ask by phone for money to be moved or for secrecy. May we check with the police for you?",
  for_hypotheses: ["fake_police"],
};

const freshPlaybooks = () => [
  {
    id: "pb.fake_police.safe_account",
    version: 1,
    status: "approved",
    approved_by: "seed (team), pending analyst review",
    approved_at: "2026-10-13T00:00:00+09:00",
    regions: ["JP"],
    first_seen: null,
    sources: [{ publisher: "警察庁組織犯罪対策部 (特殊詐欺の手口と対策)", url: "https://www.npa.go.jp/bureau/criminal/souni/tokusyusagi/teguchi-taisaku.pdf", published_at: "2023-04-13" }],
    hypothesis: "fake_police",
    name: "Fake police: move money to a 'safe' account",
    contact_channels: ["phone", "video_call", "letter"],
    script_phrases: ["口座が犯罪に使われている", "安全な口座に移す", "捜査の秘密"],
    question_bank: { questions: QUESTIONS.slice(1), hold_lines: [HOLD_LINE] },
  },
  {
    id: "pb.other_scam.fee_sms",
    version: 1,
    status: "pending",
    approved_by: null,
    approved_at: null,
    regions: ["JP"],
    first_seen: null,
    sources: [{ publisher: "synthetic seed for the analyst-console demo (stands in for a public consumer-centre alert)", url: "https://example.invalid/alerts/fee-sms", published_at: "2025-11-20" }],
    hypothesis: "other_scam",
    name: "Unpaid-fee message: pay through a designated account",
    contact_channels: ["sms", "messaging_app"],
    script_phrases: ["未納料金", "本日中にお支払いください", "ご案内の口座へお振込みください"],
    question_bank: { questions: [{ id: "q.other_scam.how_notified", ja: "この件は、どのような方法でご連絡を受けましたか。", en: "" }], hold_lines: [] },
  },
];

// ------------------------------------------------------------------ indicator detection (mock only)

const PATTERNS = [
  ["impersonated_official", /警察|検察|金融庁|警視庁|刑事/],
  ["secrecy_instruction", /誰にも言|言うな|内緒|秘密|話すな|口外/],
  ["urgency", /今日中|急い|至急|すぐに払|早く/],
  ["cover_story", /リフォーム|改装|工事/],
  ["safe_account_transfer", /安全な口座|保全/],
  ["cash_or_card_handover", /現金を(渡|受け)|カードを(渡|預)|受け取りに/],
];
const CORE = { impersonated_official: "impersonation", impersonated_relative: "impersonation", secrecy_instruction: "secrecy", safe_account_transfer: "mechanism", cash_or_card_handover: "mechanism" };
const PRESSURE = new Set(["urgency", "third_party_pressure", "changed_contact_number"]);

function clauseWith(text, re) {
  const clauses = text.split(/[。、，,！!？?\n]/).map((s) => s.trim()).filter(Boolean);
  return clauses.find((c) => re.test(c)) ?? text.trim();
}

// ------------------------------------------------------------------ state

function freshState() {
  return {
    t0: Date.now(),
    caseSeq: 7,
    transferSeq: 1,
    cases: new Map(),
    transfers: new Map(),
    notices: [],
    calls: new Map(),
    playbooks: freshPlaybooks(),
    freezes: [],
    sseClients: new Map(), // caseId -> Set(res)
    audit: new Map(),
  };
}

export function startMock({ port = 8090, delayMs = Number(process.env.MOCK_DELAY_MS ?? 1200), host = "0.0.0.0" } = {}) {
  let S = freshState();
  const now = () => DEMO_START + (Date.now() - S.t0);
  const nowIso = () => jst(now());

  const json = (res, status, body) => {
    res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", ...cors });
    res.end(JSON.stringify(body));
  };
  const cors = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
  };
  const err = (res, status, error, detail) => json(res, status, { error, detail: detail ?? null });
  const readBody = (req) =>
    new Promise((resolve, reject) => {
      let s = "";
      req.on("data", (c) => (s += c));
      req.on("end", () => {
        if (!s) return resolve({});
        try {
          resolve(JSON.parse(s));
        } catch {
          reject(new Error("bad json"));
        }
      });
    });

  // ---- events / audit
  function emit(kase, type, data = {}) {
    const e = { seq: kase.events.length + 1, case_id: kase.case_id, type, at: nowIso(), data };
    kase.events.push(e);
    for (const res of S.sseClients.get(kase.case_id) ?? []) writeSse(res, e);
  }
  const writeSse = (res, e) => res.write(`id: ${e.seq}\nevent: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`);
  function audit(kase, who, what, why) {
    const list = S.audit.get(kase.case_id) ?? [];
    list.push({ at: nowIso(), who, what, why: why ?? null });
    S.audit.set(kase.case_id, list);
  }

  // ---- card (risk-v1, mock copy)
  function buildCard(kase) {
    const facts = [
      { id: "f1", kind: "fact", statement_en: "The payee account was opened 4 days ago.", source: { tool: "counterpart_graph", field: "account_age_days", value: 4 }, verified: true },
      { id: "f2", kind: "fact", statement_en: "7 different customers paid this account in the last 7 days.", source: { tool: "counterpart_graph", field: "distinct_payers_7d", value: 7 }, verified: true },
      { id: "f3", kind: "fact", statement_en: "No payments to contractors in 12 years.", source: { tool: "get_baseline", field: "contractor_payments_count_12y", value: 0 }, verified: true },
      { id: "f4", kind: "fact", statement_en: "Typical monthly withdrawals are ¥50,000.", source: { tool: "get_baseline", field: "median_monthly_withdrawal_jpy", value: 50000 }, verified: true },
    ];
    const quotes = kase.indicators.map((q) => ({
      id: q.id, kind: "quote", indicator: q.indicator, source: { turn_id: q.turn_id, text: q.text }, turn_id_corrected: false, verified: true,
    }));
    const inferences = [];
    const cover = quotes.find((q) => q.indicator === "cover_story");
    if (cover) inferences.push({ id: "i1", kind: "inference", statement_en: "The renovation reason doesn't match her history and is a known fake-police cover story.", grounds: [cover.id, "f3"], shown_as: "hypothesis" });
    inferences.push({ id: "i2", kind: "inference", statement_en: "The payee looks like a new account collecting from many people.", grounds: ["f1", "f2"], shown_as: "hypothesis" });

    const has = (t) => quotes.filter((q) => q.indicator === t);
    const coreGroups = new Set(quotes.filter((q) => CORE[q.indicator]).map((q) => CORE[q.indicator]));
    const pressure = quotes.some((q) => PRESSURE.has(q.indicator));
    const coverMismatch = has("cover_story").length > 0; // f3: no contractor payments in 12 years
    const risky = true; // f1 + f2: account 4 days old, 7 payers
    const coreQuotes = quotes.filter((q) => CORE[q.indicator]).map((q) => q.id);
    const fired = [];
    let level = "low";
    if (coreGroups.size >= 2) {
      level = "high";
      const imp = coreGroups.has("impersonation") && coreGroups.has("secrecy");
      fired.push({ condition: imp ? "H1:impersonation+secrecy" : "H1", claims: coreQuotes });
    } else if (coreGroups.size >= 1 && pressure && (coverMismatch || risky)) {
      level = "high";
      fired.push({ condition: "H2", claims: [...coreQuotes, ...quotes.filter((q) => PRESSURE.has(q.indicator)).map((q) => q.id)] });
    } else if (coreGroups.size >= 1 || coverMismatch || risky) {
      level = "elevated";
    }
    const asked = new Set(kase.suggested);
    const nextQ = QUESTIONS.find((q) => !asked.has(q.id)) ?? null;
    if (nextQ) kase.pendingQuestion = nextQ.id;
    const fakePolice = quotes.filter((q) => CORE[q.indicator]).map((q) => q.id);
    return {
      case_id: kase.case_id,
      customer_ref: kase.customer_ref,
      card_version: ++kase.cardVersion,
      updated_at: nowIso(),
      request: kase.request,
      claims: [...facts, ...quotes, ...inferences],
      hypotheses: [
        { name: "legitimate", playbook_id: null, supporting_claims: [] },
        { name: "fake_police", playbook_id: "pb.fake_police.safe_account", supporting_claims: [...fakePolice, ...inferences.map((i) => i.id)] },
      ],
      risk: { level, pause_recommended: level === "high", rule_version: "risk-v1", fired, hold_line_id: level === "high" ? HOLD_LINE.id : null },
      next_question: nextQ ? { question_id: nextQ.id, ja_filled: nextQ.ja, en_filled: nextQ.en } : null,
      dropped: kase.dropped,
    };
  }
  function setCard(kase) {
    kase.card = buildCard(kase);
    kase.risk_level = kase.card.risk.level;
    if (kase.card.next_question && !kase.suggested.includes(kase.card.next_question.question_id)) kase.suggested.push(kase.card.next_question.question_id);
  }

  function summary(k) {
    return { case_id: k.case_id, language: k.language ?? "ja", status: k.status, customer_ref: k.customer_ref, opened_at: k.opened_at, amount_jpy: k.request.amount_jpy, risk_level: k.risk_level ?? null };
  }
  function publicCase(k) {
    return {
      ...summary(k), account_id: k.account_id, transfer_id: k.transfer_id, request: k.request, signals: k.signals,
      card: k.card, transcript: k.transcript, decisions: k.decisions, hold: k.hold, call_id: k.call_id, case_code: k.case_code,
      hold_line: k.card?.risk.pause_recommended ? HOLD_LINE : null,
      contact_view: k.contact_view, verification_failed: k.verification_failed, contact_suspected: k.contact_suspected, freeze_request: k.freeze_request,
    };
  }

  // ---- domain actions
  function openCase(body) {
    const n = S.caseSeq++;
    const case_id = `case-2026-1013-${pad(n, 4)}`;
    const transfer_id = `tr-${pad(S.transferSeq++, 4)}`;
    const request = { channel: body.channel, kind: body.kind, amount_jpy: body.amount_jpy, payee: body.payee ? { name_kana: body.payee.name_kana, relation: body.payee.relation } : null };
    const kase = {
      case_id, transfer_id, customer_ref: body.customer_ref, account_id: body.account_id, status: "open", opened_at: nowIso(), request,
      signals: [
        { code: "amount_vs_baseline", statement_en: "The amount is 60 times her typical monthly withdrawal.", tool: "get_baseline", field: "amount_vs_median_ratio", value: 60 },
        { code: "new_payee", statement_en: "She has never paid this payee before.", tool: "get_baseline", field: "new_payee", value: true },
        { code: "payee_account_age", statement_en: "The payee account is 4 days old.", tool: "counterpart_graph", field: "account_age_days", value: 4 },
        { code: "payer_fan_in", statement_en: "7 different customers paid this account in the last 7 days.", tool: "counterpart_graph", field: "distinct_payers_7d", value: 7 },
      ],
      language: "ja", card: null, cardVersion: 0, risk_level: null, transcript: [], decisions: [], hold: null, call_id: null,
      case_code: null, contact_view: null, verification_failed: false, contact_suspected: null, freeze_request: null,
      events: [], indicators: [], dropped: [], suggested: [], cn: 0, tn: 0, qn: 0, createdMs: now(),
    };
    S.cases.set(case_id, kase);
    S.transfers.set(transfer_id, { transfer_id, status: "pending_alert", scoring: "alert", case_id, hold_id: null, request: body, created_at: nowIso() });
    emit(kase, "case_opened", { transfer_id });
    setTimeout(() => {
      // investigation finished: first card with the first approved question
      setCard(kase);
      emit(kase, "card_updated", { card_version: kase.card.card_version });
    }, delayMs);
    return { case_id, transfer_id };
  }

  function addTurn(kase, speaker, text) {
    const turn_id = speaker === "customer" ? `c${++kase.cn}` : `t${++kase.tn}`;
    kase.transcript.push({ turn_id, speaker, text, at: nowIso() });
    emit(kase, "transcript_turn", { turn_id, speaker });
    if (speaker === "customer") {
      for (const [indicator, re] of PATTERNS) {
        if (re.test(text) && !kase.indicators.some((q) => q.indicator === indicator)) {
          kase.indicators.push({ id: `q${++kase.qn}`, indicator, turn_id, text: clauseWith(text, re) });
        }
      }
      setCard(kase);
      emit(kase, "card_updated", { card_version: kase.card.card_version });
    }
    return { turn_id, card: speaker === "customer" ? kase.card : null };
  }

  function placeCall(kase) {
    const case_code = kase.case_code ?? (kase.case_id.endsWith("0007") ? "4821" : String(1000 + Math.floor(Math.random() * 9000)));
    const call_id = `call-${kase.case_id.slice(-4)}-1`;
    kase.call_id = call_id;
    kase.case_code = case_code;
    S.calls.set(call_id, { call_id, case_id: kase.case_id, case_code, locked: YUKI });
    const en = kase.language === "en";
    const text_en = `This is Sample Bank, Ekimae Branch. We are contacting you about your mother. To check that this message is from us, please call our published number 03-1234-5678, choose "Return a call about a message" from the voice menu, and give the confirmation number ${case_code}.`;
    const text = en ? text_en : `サンプル銀行 駅前支店です。お母様の件でご連絡しました。公開番号 03-1234-5678 に折り返しください。番号 ${case_code}`;
    S.notices.push({ call_id, to_phone_e164: YUKI, sent_at: nowIso(), text, language: kase.language ?? "ja", gloss_en: en ? null : text_en, published_phone_e164: PUBLISHED, case_code, audio_b64: null });
    emit(kase, "contact_notice_sent", { call_id });
  }

  function decide(kase, b) {
    if (b.action === "pause") {
      if (!b.basis) return { status: 422, error: "validation", detail: "pause needs a basis" };
      const w = holdWindow(now());
      const hold = {
        hold_id: `hold-${pad(S.transferSeq++, 4)}`, account_id: kase.account_id, transfer_id: kase.transfer_id, case_id: kase.case_id,
        placed_by: b.teller_id, placed_at: nowIso(), minimum_ends_at: jst(w.minimum_ends_at), ends_at: jst(w.ends_at), cap_ends_at: jst(w.cap_ends_at),
        status: "active", overrides: b.basis === "advance_wishes" ? ["after_contact_reached", "after_manager_review_and_second_confirmation"] : [], released_at: null, release_reason: null,
      };
      const warnings = kase.indicators.length === 0 ? ["single_source_pause"] : [];
      const rec = { decision_id: `dec-${pad(kase.decisions.length + 1, 4)}`, case_id: kase.case_id, action: "pause", basis: b.basis, release_reason: null, rationale: b.rationale, decided_by: b.teller_id, manager_id: null, decided_at: nowIso(), warnings };
      kase.decisions.push(rec);
      kase.hold = hold;
      kase.status = "paused";
      S.transfers.get(kase.transfer_id).status = "held";
      audit(kase, b.teller_id, `pause (${b.basis})`, b.rationale);
      emit(kase, "decision_logged", { decision_id: rec.decision_id, action: "pause" });
      emit(kase, "hold_placed", { hold_id: hold.hold_id, ends_at: hold.ends_at });
      if (b.basis === "advance_wishes") setTimeout(() => placeCall(kase), Math.min(delayMs, 800));
      return { body: { decision: rec, status: kase.status, hold, warnings } };
    }
    if (!b.release_reason) return { status: 422, error: "validation", detail: "release needs a release_reason" };
    if (b.release_reason === "manager_review_second_confirmation" && !(b.manager_id && b.second_confirmed_by && b.manager_id !== b.second_confirmed_by))
      return { status: 422, error: "validation", detail: "manager review needs manager_id and a different second_confirmed_by" };
    if (b.release_reason === "customer_override_after_contact_reached" && !kase.contact_view?.reached)
      return { status: 409, error: "conflict", detail: "contact has not been reached" };
    const rec = { decision_id: `dec-${pad(kase.decisions.length + 1, 4)}`, case_id: kase.case_id, action: "release", basis: null, release_reason: b.release_reason, rationale: b.rationale, decided_by: b.teller_id, manager_id: b.manager_id ?? null, decided_at: nowIso(), warnings: [] };
    kase.decisions.push(rec);
    kase.status = "released";
    if (kase.hold) Object.assign(kase.hold, { status: "released", released_at: nowIso(), release_reason: b.release_reason });
    S.transfers.get(kase.transfer_id).status = "released";
    audit(kase, b.teller_id, `release (${b.release_reason})`, b.rationale);
    emit(kase, "decision_logged", { decision_id: rec.decision_id, action: "release" });
    if (kase.hold) emit(kase, "hold_updated", { hold_id: kase.hold.hold_id, status: "released" });
    return { body: { decision: rec, status: kase.status, hold: kase.hold, warnings: [] } };
  }

  function policeSummary(kase, b) {
    const items = {};
    const lines = [`ケース ${kase.case_id} の情報(警察官のご要請に基づく)`];
    for (const it of b.requested_items) {
      if (it === "amount") { items.amount = kase.request.amount_jpy; lines.push(`金額: ${kase.request.amount_jpy.toLocaleString("ja-JP")}円`); }
      if (it === "payee") { items.payee = kase.request.payee; lines.push(`送金先: ${kase.request.payee?.name_kana ?? "なし"}`); }
      if (it === "customer_statements") { items.customer_statements = kase.transcript.filter((t) => t.speaker === "customer").map((t) => t.text); lines.push(...items.customer_statements.map((t) => `お客様の発言: ${t}`)); }
      if (it === "indicators") { items.indicators = kase.indicators.map((q) => q.indicator); lines.push(`不審な兆候: ${items.indicators.join(", ") || "なし"}`); }
      if (it === "timeline") { items.timeline = kase.events.map((e) => e.type); lines.push(`経過: ${items.timeline.join(" → ")}`); }
    }
    lines.push(`提供先: ${b.officer_name}(${b.officer_title})`);
    const out = { summary_id: `ps-${pad(kase.events.length + 1, 4)}`, issued_at: nowIso(), officer_name: b.officer_name, officer_title: b.officer_title, items, text_ja: lines.join("\n") };
    audit(kase, b.teller_id, `police summary to ${b.officer_name} (${b.officer_title}): ${b.requested_items.join(",")}`, "on officers' request");
    emit(kase, "police_summary_issued", { officer_name: b.officer_name, officer_title: b.officer_title, requested_items: b.requested_items });
    return out;
  }

  const outcome = (kase, cv) => {
    kase.contact_view = { case_id: kase.case_id, call_id: kase.call_id, nature: "information", reached: true, wants_callback_later: false, disclosed: ["transaction_paused", "reason_category", "customer_at_branch"], recorded_at: nowIso(), verification: { caller_number_match: true, case_code_match: true }, concerned: null, coming_to_branch: null, eta_minutes: null, ...cv };
    emit(kase, "contact_outcome", { reached: true });
  };

  // ---- HTTP routing
  const routes = [];
  const route = (method, pattern, fn) => routes.push([method, new RegExp(`^${pattern.replace(/:(\w+)/g, "(?<$1>[^/]+)")}$`), fn]);
  const needRole = (req, res, role) => {
    if ((req.headers["x-mimamori-role"] ?? "") !== role) {
      err(res, 403, "forbidden", `${role} role required`);
      return false;
    }
    return true;
  };
  const getCase = (res, id) => {
    const k = S.cases.get(id);
    if (!k) err(res, 404, "not_found", `no case ${id}`);
    return k;
  };

  route("GET", "/healthz", (_q, res) => json(res, 200, { status: "ok", service: "mock", version: "0.1.0" }));
  route("POST", "/__mock/reset", (_q, res) => {
    for (const set of S.sseClients.values()) for (const r of set) r.end();
    S = freshState();
    json(res, 200, { reset: true });
  });

  // core banking
  route("POST", "/transfers", async (req, res) => {
    const b = await readBody(req);
    if (!b.customer_ref || !b.account_id || !Number.isInteger(b.amount_jpy) || b.amount_jpy < 1) return err(res, 422, "validation", "customer_ref, account_id, amount_jpy required");
    if (b.channel === "counter" && b.amount_jpy >= 1_000_000) {
      const { case_id, transfer_id } = openCase(b);
      return json(res, 200, { transfer_id, status: "pending_alert", scoring: "alert", case_id, hold_id: null });
    }
    const transfer_id = `tr-${pad(S.transferSeq++, 4)}`;
    S.transfers.set(transfer_id, { transfer_id, status: "executed", scoring: b.channel === "counter" ? "allow" : "not_checked", case_id: null, hold_id: null, request: b, created_at: nowIso() });
    json(res, 200, { transfer_id, status: "executed", scoring: b.channel === "counter" ? "allow" : "not_checked", case_id: null, hold_id: null });
  });
  route("GET", "/transfers/:id", (_q, res, p) => {
    const t = S.transfers.get(p.id);
    t ? json(res, 200, t) : err(res, 404, "not_found");
  });
  route("GET", "/customers/:ref", (_q, res, p) => (CUSTOMERS[p.ref] ? json(res, 200, CUSTOMERS[p.ref]) : err(res, 404, "not_found")));
  route("GET", "/customers", (_q, res) => json(res, 200, Object.values(CUSTOMERS)));
  route("GET", "/accounts", (_q, res) => json(res, 200, [{ account_id: "acct-tanaka-0001", customer_ref: "cust-tanaka-0001", holder_name_kana: "タナカ ケイコ", branch_name_ja: "サンプル銀行 駅前支店", opened_on: "2014-04-01", balance_jpy: 0, status: "active" }]));

  // case service
  route("GET", "/cases", (req, res) => {
    const status = new URL(req.url, "http://x").searchParams.get("status");
    json(res, 200, [...S.cases.values()].filter((k) => !status || k.status === status).map(summary));
  });
  route("GET", "/cases/:id", (_q, res, p) => {
    const k = getCase(res, p.id);
    if (k) json(res, 200, publicCase(k));
  });
  route("GET", "/cases/:id/outreach", (req, res, p) => {
    if (!needRole(req, res, "analyst")) return;
    const k = getCase(res, p.id);
    if (k) json(res, 200, k.outreach ?? []);
  });
  route("GET", "/cases/:id/audit", (_q, res, p) => {
    const k = getCase(res, p.id);
    if (k) json(res, 200, S.audit.get(k.case_id) ?? []);
  });
  route("GET", "/cases/:id/events", (req, res, p) => {
    const k = getCase(res, p.id);
    if (!k) return;
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no", ...cors });
    const after = Number(new URL(req.url, "http://x").searchParams.get("after") ?? req.headers["last-event-id"] ?? 0) || 0;
    res.write(": connected\n\n");
    for (const e of k.events) if (e.seq > after) writeSse(res, e);
    const set = S.sseClients.get(k.case_id) ?? new Set();
    set.add(res);
    S.sseClients.set(k.case_id, set);
    const hb = setInterval(() => res.write(": hb\n\n"), 15000);
    req.on("close", () => {
      clearInterval(hb);
      set.delete(res);
    });
  });
  route("POST", "/cases/:id/turns", async (req, res, p) => {
    const k = getCase(res, p.id);
    if (!k) return;
    const b = await readBody(req);
    if (!b.text || typeof b.text !== "string" || !["customer", "teller"].includes(b.speaker ?? "customer")) return err(res, 422, "validation", "text required");
    json(res, 200, addTurn(k, b.speaker ?? "customer", b.text));
  });
  route("POST", "/cases/:id/decision", async (req, res, p) => {
    const k = getCase(res, p.id);
    if (!k) return;
    const b = await readBody(req);
    if (!b.rationale || !b.teller_id || !["pause", "release"].includes(b.action)) return err(res, 422, "validation", "action, rationale, teller_id required");
    if (k.status === "released" || k.status === "closed") return err(res, 409, "conflict", `case is ${k.status}`);
    const r = decide(k, b);
    r.body ? json(res, 200, r.body) : err(res, r.status, r.error, r.detail);
  });
  route("POST", "/cases/:id/claims/:cid/dismiss", async (req, res, p) => {
    const k = getCase(res, p.id);
    if (!k) return;
    const b = await readBody(req);
    if (!b.reason) return err(res, 422, "validation", "reason required");
    const before = k.indicators.length;
    k.indicators = k.indicators.filter((q) => q.id !== p.cid);
    if (k.indicators.length === before) return err(res, 404, "not_found", `no indicator ${p.cid}`);
    audit(k, b.teller_id, `dismiss ${p.cid}`, b.reason);
    setCard(k);
    emit(k, "card_updated", { card_version: k.card.card_version });
    json(res, 200, publicCase(k));
  });
  route("POST", "/cases/:id/police-summary", async (req, res, p) => {
    const k = getCase(res, p.id);
    if (!k) return;
    const b = await readBody(req);
    if (!b.officer_name?.trim() || !b.officer_title?.trim() || !Array.isArray(b.requested_items) || b.requested_items.length === 0) return err(res, 422, "validation", "officer_name, officer_title and requested_items are required");
    json(res, 200, policeSummary(k, b));
  });
  route("POST", "/cases/:id/contact-call", (_q, res, p) => {
    const k = getCase(res, p.id);
    if (!k) return;
    if (k.status !== "paused") return err(res, 409, "conflict", "case is not paused");
    placeCall(k);
    json(res, 200, publicCase(k));
  });
  route("PATCH", "/cases/:id/language", async (req, res, p) => {
    const k = getCase(res, p.id);
    if (!k) return;
    const b = await readBody(req);
    if (b.language !== "ja" && b.language !== "en") return err(res, 422, "validation_error", "language must be ja or en");
    if (k.transcript.length > 0) return err(res, 409, "language_locked", "the conversation language can't change once the case has a turn");
    k.language = b.language;
    audit(k, b.actor, "case.language_set", `language -> ${b.language}`);
    json(res, 200, publicCase(k));
  });
  route("POST", "/cases/:id/freeze-request", async (req, res, p) => {
    const k = getCase(res, p.id);
    if (!k) return;
    const b = await readBody(req);
    if (!b.reason?.trim()) return err(res, 422, "validation", "reason required");
    if (k.freeze_request) return err(res, 409, "conflict", "freeze already requested");
    k.freeze_request = { freeze_id: `frz-${pad(S.freezes.length + 1, 4)}`, case_id: k.case_id, account_id: MULE, requested_by: b.requested_by, reason: b.reason, requested_at: nowIso(), status: "pending", decided_by: null, decided_at: null, decision_rationale: null };
    S.freezes.push(k.freeze_request);
    audit(k, b.requested_by, "freeze requested", b.reason);
    emit(k, "freeze_requested", { freeze_id: k.freeze_request.freeze_id });
    json(res, 200, k.freeze_request);
  });
  route("GET", "/freeze-requests", (req, res) => {
    if (!needRole(req, res, "analyst")) return;
    const status = new URL(req.url, "http://x").searchParams.get("status");
    json(res, 200, S.freezes.filter((f) => !status || f.status === status));
  });
  route("POST", "/cases/:id/freeze-decision", async (req, res, p) => {
    if (!needRole(req, res, "analyst")) return;
    const k = getCase(res, p.id);
    if (!k) return;
    const b = await readBody(req);
    if (!["approve", "reject"].includes(b.decision) || !b.rationale?.trim()) return err(res, 422, "validation", "decision and rationale required");
    const fr = k.freeze_request;
    if (!fr || fr.status !== "pending") return err(res, 409, "conflict", "no pending freeze request");
    fr.status = b.decision === "approve" ? "approved" : "rejected";
    fr.decided_by = b.analyst_id;
    fr.decided_at = nowIso();
    fr.decision_rationale = b.rationale;
    audit(k, b.analyst_id, `freeze ${fr.status}`, b.rationale);
    emit(k, "freeze_decided", { decision: b.decision });
    let freeze = null;
    let outreach = [];
    if (b.decision === "approve") {
      freeze = { freeze_id: fr.freeze_id, account_id: fr.account_id, case_id: k.case_id, approved_by: b.analyst_id, frozen_at: nowIso(), status: "frozen" };
      outreach = OTHER_PAYERS.map(([customer_ref, account_id, display_name_ja, total_jpy, last_paid_at]) => ({ customer_ref, display_name_ja, account_id, last_paid_at, total_jpy }));
      k.outreach = outreach;
      emit(k, "outreach_ready", { outreach });
    }
    json(res, 200, { freeze_request: fr, freeze, outreach });
  });
  route("GET", "/playbooks", (req, res) => {
    const status = new URL(req.url, "http://x").searchParams.get("status");
    json(res, 200, S.playbooks.filter((p) => !status || p.status === status));
  });
  route("PATCH", "/playbooks/:id", async (req, res, p) => {
    if (!needRole(req, res, "analyst")) return;
    const b = await readBody(req);
    const pb = S.playbooks.find((x) => x.id === p.id);
    if (!pb) return err(res, 404, "not_found");
    if (!["approved", "rejected", "retired"].includes(b.status) || !b.analyst_id) return err(res, 422, "validation");
    pb.status = b.status;
    pb.approved_by = b.status === "approved" ? b.analyst_id : null;
    pb.approved_at = b.status === "approved" ? nowIso() : null;
    json(res, 200, pb);
  });

  // conversation service
  route("GET", "/notices", (req, res) => {
    const to = new URL(req.url, "http://x").searchParams.get("to");
    json(res, 200, S.notices.filter((n) => n.to_phone_e164 === to));
  });

  const server = http.createServer(async (req, res) => {
    if (req.method === "OPTIONS") {
      res.writeHead(204, cors);
      return res.end();
    }
    const url = new URL(req.url, "http://x");
    const path = url.pathname.replace(/^\/api\/(core|scoring|case|conversation)(?=\/|$)/, "") || "/";
    for (const [method, re, fn] of routes) {
      const m = method === req.method && re.exec(path);
      if (m) {
        try {
          return await fn(req, res, m.groups ?? {});
        } catch (e) {
          return err(res, 400, "bad_request", String(e.message ?? e));
        }
      }
    }
    err(res, 404, "not_found", `${req.method} ${path}`);
  });

  // ---- WebSockets: /phone and /cases/{id}/audio
  const wss = new WebSocketServer({ noServer: true });
  server.on("upgrade", (req, socket, head) => {
    const path = new URL(req.url, "http://x").pathname.replace(/^\/api\/(core|scoring|case|conversation)(?=\/|$)/, "");
    wss.handleUpgrade(req, socket, head, (ws) => {
      if (path === "/phone") return phoneSession(ws);
      const m = /^\/cases\/([^/]+)\/audio$/.exec(path);
      if (m && S.cases.has(m[1])) return audioSession(ws, S.cases.get(m[1]));
      ws.close(1008, "unknown socket");
    });
  });

  function audioSession(ws, kase) {
    ws.on("message", (data, isBinary) => {
      if (isBinary) return; // raw LINEAR16 frames: the mock has no STT
      let text = data.toString("utf8").trim();
      let speaker = "customer";
      if (text.startsWith("teller:")) {
        speaker = "teller";
        text = text.slice(7).trim();
      }
      if (!text) return;
      const { turn_id } = addTurn(kase, speaker, text);
      ws.send(JSON.stringify({ type: "transcript", turn_id, speaker, text, is_final: true }));
    });
  }

  const TEMPLATES = {
    what_happened: ["本日、お母様が当店でお手続きをされる際に、念のため一時的にお待ちいただいております。見知らぬ方から公的機関を名乗る電話があったようです。", "お知らせいたします。"],
    is_she_safe: ["お母様は、いま当店で職員と一緒にいらっしゃいますので、ご安心ください。", "ご心配ですよね。"],
    how_much: ["金額については、お電話ではお伝えできかねます。恐れ入ります。", "お気持ちはお察しします。"],
    account_details: ["口座の残高や番号は、お電話ではお伝えできません。ご了承ください。", "ご心配なお気持ち、お察しいたします。"],
    what_should_i_do: ["もし可能でしたら、当店までお越しいただけますと、お母様も心強いと存じます。", "ありがとうございます。"],
    coming_to_branch: ["ありがとうございます。担当者に伝え、お待ちしております。", "承知いたしました。"],
    other: ["申し訳ございません、その点については担当者から改めてご説明いたします。", "失礼いたしました。"],
  };
  const TEMPLATES_EN = {
    what_happened: ["We asked your mother to wait a short while today, as a precaution. We are checking as a precaution, because we were told of a call from someone claiming to be an official.", "I'm sorry for the worry. "],
    is_she_safe: ["Right now, your mother is here with our staff, so please be assured.", "I understand. "],
    how_much: ["I'm sorry, I'm unable to share the amount over the phone.", "I understand. "],
    account_details: ["I'm sorry, I'm unable to share account balances or numbers over the phone. Thank you for your understanding.", "I understand. "],
    what_should_i_do: ["If you are able to, it would be reassuring for your mother if you could come to our branch.", "Thank you. "],
    coming_to_branch: ["Thank you. I will let our staff know, and we look forward to seeing you.", ""],
    other: ["I'm sorry, our staff will follow up with you on that point.", ""],
  };
  function classifyEn(t) {
    if (/how much|amount|sum/i.test(t)) return "how_much";
    if (/account|balance|number|pin/i.test(t)) return "account_details";
    if (/coming|on my way|right away|be there/i.test(t)) return "coming_to_branch";
    if (/what should|what do i do/i.test(t)) return "what_should_i_do";
    if (/safe|ok(ay)?\b|where is/i.test(t)) return "is_she_safe";
    if (/what happened|why|what's going on/i.test(t)) return "what_happened";
    return "other";
  }
  function classify(t) {
    if (/いくら|金額|どのくらい|いくつ/.test(t)) return "how_much";
    if (/口座|残高|番号|暗証/.test(t)) return "account_details";
    if (/行きます|向かい|伺い|すぐ(に)?(行|向)/.test(t)) return "coming_to_branch";
    if (/どうすれば|どうしたら|どうしよう/.test(t)) return "what_should_i_do";
    if (/無事|大丈夫|安全|どこ(に)?い/.test(t)) return "is_she_safe";
    if (/何が|どうした|何があ|なぜ|どういう/.test(t)) return "what_happened";
    return "other";
  }

  function phoneSession(ws) {
    let state = "await_callback";
    let kase = null;
    let said = false;
    const finish = (reason) => {
      ws.send(JSON.stringify({ type: "ended", reason }));
      ws.close();
    };
    const closeOutcome = () => {
      if (kase && state === "verified" && !kase.contact_view) outcome(kase, { concerned: said ? true : null, coming_to_branch: null });
    };
    ws.on("close", closeOutcome);
    ws.on("message", (data, isBinary) => {
      if (isBinary) return; // audio frames are accepted and ignored: the mock has no STT
      let m;
      try {
        m = JSON.parse(data.toString("utf8"));
      } catch {
        return;
      }
      if (state === "await_callback") {
        const call = [...S.calls.values()].find((c) => c.case_code === m.case_code);
        const ok = m.type === "callback" && m.menu_choice === MENU_RETURN && call && m.caller_number === call.locked;
        ws.send(JSON.stringify({ type: "verification", ok: Boolean(ok) }));
        if (!ok) {
          if (call) {
            const k = S.cases.get(call.case_id);
            k.verification_failed = true;
            emit(k, "verification_failed", { call_id: call.call_id });
          }
          state = "failed";
          return finish("verification_failed");
        }
        kase = S.cases.get(call.case_id);
        state = "verified";
        const OPENING_EN = "This is an automated voice assistant. This call is recorded. Please tell me what you are calling about.";
        const enCall = kase.language === "en";
        ws.send(JSON.stringify({ type: "say", text: enCall ? OPENING_EN : "こちらは自動音声のアシスタントです。この通話は録音されます。", language: kase.language ?? "ja", gloss_en: enCall ? null : OPENING_EN, audio_b64: null, template_intent: "opening" }));
        return;
      }
      if (state !== "verified") return;
      if (m.type === "hangup") {
        closeOutcome();
        return finish("hangup");
      }
      if (m.type === "turn" && m.text) {
        const enCall = kase.language === "en";
        const intent = enCall ? classifyEn(m.text) : classify(m.text);
        const [tpl, connect] = (enCall ? TEMPLATES_EN : TEMPLATES)[intent];
        const [tplEn, connectEn] = TEMPLATES_EN[intent];
        if (intent !== "other") said = true;
        ws.send(JSON.stringify({ type: "say", text: `${connect}${tpl}`, language: kase.language ?? "ja", gloss_en: enCall ? null : `${tplEn}${connectEn ? " (+ a short lead-in, not translated)" : ""}`, audio_b64: null, template_intent: intent }));
        if (intent === "coming_to_branch") {
          outcome(kase, { concerned: true, coming_to_branch: true, eta_minutes: 30 });
          state = "done";
          setTimeout(() => finish("completed"), 100);
        }
      }
    });
  }

  return new Promise((resolve) => {
    server.listen(port, host, () => {
      const addr = server.address();
      resolve({
        port: addr.port,
        url: `http://127.0.0.1:${addr.port}`,
        reset: () => {
          S = freshState();
        },
        close: () =>
          new Promise((r) => {
            for (const set of S.sseClients.values()) for (const res of set) res.end();
            for (const c of wss.clients) c.terminate();
            server.closeAllConnections?.();
            server.close(() => r());
          }),
      });
    });
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT ?? 8090);
  startMock({ port }).then((m) => console.log(`mimamori mock server on ${m.url} (all four service prefixes)`));
}
