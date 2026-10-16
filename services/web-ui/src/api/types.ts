/**
 * Hand-written TypeScript types for the HTTP / SSE / WebSocket contracts the web UI calls.
 *
 * MIRRORS the Pydantic models in `libs/mimamori-common/src/mimamori_common/models/api.py` and the
 * data contracts in `schemas/` (evidence card, contact view, playbook, advance wishes). It is NOT
 * generated: when those change, update this file by hand. Do not add fields the contract lacks.
 *
 * There is deliberately no probability / likelihood / confidence field anywhere in these types:
 * risk is `low | elevated | high`, computed in code (`risk-v1`).
 */

export type Role = "teller" | "analyst" | "system";
export type Channel = "counter" | "atm" | "app";
export type TransferKind = "transfer" | "cash_withdrawal";
export type CaseStatus = "open" | "paused" | "released" | "closed";
export type RiskLevel = "low" | "elevated" | "high";
export type DisclosureField =
  | "transaction_paused"
  | "amount_band"
  | "reason_category"
  | "customer_at_branch"
  | "police_notified";

export const PHONE_MENU_RETURN_CALL = "returning_a_call_about_a_case";

export interface ApiErrorBody {
  error: string;
  detail?: string | null;
}

// ------------------------------------------------------------------ core banking (mock)

export interface Customer {
  customer_ref: string;
  display_name_ja: string;
  display_name_kana: string;
  tenure_years: number;
  branch_name_ja: string;
}

export interface Account {
  account_id: string;
  customer_ref: string;
  holder_name_kana: string;
  branch_name_ja: string;
  opened_on: string;
  /** Never shown in the teller UI beyond what the bank screen already shows; never copied into a brief. */
  balance_jpy: number;
  status: "active" | "frozen";
}

export interface PayeeRef {
  name_kana: string;
  relation: "same_bank" | "other_bank";
  account_id?: string | null;
}

export interface TransferRequest {
  customer_ref: string;
  account_id: string;
  channel: Channel;
  kind: TransferKind;
  amount_jpy: number;
  payee?: PayeeRef | null;
  memo?: string | null;
  teller_id?: string | null;
}

export type TransferStatus = "executed" | "pending_alert" | "held" | "released" | "cancelled";

export interface TransferResponse {
  transfer_id: string;
  status: TransferStatus;
  scoring: "allow" | "alert" | "unavailable" | "not_checked";
  case_id?: string | null;
  hold_id?: string | null;
}

export type HoldOverride = "after_contact_reached" | "after_manager_review_and_second_confirmation";

export interface Hold {
  hold_id: string;
  account_id: string;
  transfer_id: string;
  case_id: string;
  placed_by: string;
  placed_at: string;
  minimum_ends_at: string;
  ends_at: string;
  cap_ends_at: string;
  status: "active" | "released" | "expired";
  overrides: HoldOverride[];
  released_at?: string | null;
  release_reason?: string | null;
}

// ------------------------------------------------------------------ evidence card (schemas/evidence-card.json)

export type ToolName =
  | "get_baseline"
  | "recent_transactions"
  | "explain_payee"
  | "check_lists"
  | "counterpart_graph"
  | "search_playbooks"
  | "get_advance_wishes"
  | "teller_notes";

export type IndicatorType =
  | "impersonated_official"
  | "impersonated_relative"
  | "secrecy_instruction"
  | "urgency"
  | "cash_or_card_handover"
  | "cover_story"
  | "safe_account_transfer"
  | "changed_contact_number"
  | "third_party_pressure";

export type HypothesisName = "legitimate" | "fake_police" | "relative_in_trouble" | "gold_bullion" | "other_scam";

export interface FactClaim {
  id: string;
  kind: "fact";
  statement_en: string;
  source: { tool: ToolName; field: string; value: unknown };
  verified: true;
}

export interface QuoteClaim {
  id: string;
  kind: "quote";
  indicator: IndicatorType;
  source: { turn_id: string; text: string };
  turn_id_corrected?: boolean;
  verified: true;
}

export interface InferenceClaim {
  id: string;
  kind: "inference";
  statement_en: string;
  grounds: string[];
  shown_as: "hypothesis";
}

export type Claim = FactClaim | QuoteClaim | InferenceClaim;

export interface DroppedClaim {
  claim: Record<string, unknown>;
  reason: "no_citation" | "value_mismatch" | "quote_not_found" | "ungrounded_inference" | "unknown_question_id";
}

export interface Hypothesis {
  name: HypothesisName;
  playbook_id: string | null;
  supporting_claims: string[];
}

export interface RiskBlock {
  level: RiskLevel;
  pause_recommended: boolean;
  rule_version: string;
  fired: { condition: string; claims: string[] }[];
  hold_line_id?: string | null;
}

export interface EvidenceCard {
  case_id: string;
  customer_ref: string;
  card_version: number;
  updated_at: string;
  request: {
    channel: Channel;
    kind: TransferKind;
    amount_jpy: number;
    payee: { name_kana: string; relation: "same_bank" | "other_bank" } | null;
  };
  claims: Claim[];
  hypotheses: Hypothesis[];
  risk: RiskBlock;
  next_question: { question_id: string; ja_filled: string; en_filled?: string } | null;
  dropped: DroppedClaim[];
}

// ------------------------------------------------------------------ case service

export interface ScoreSignal {
  code: string;
  statement_en: string;
  tool: ToolName;
  field: string;
  value: unknown;
}

export interface Transcript {
  turn_id: string;
  speaker: "customer" | "teller";
  text: string;
  at: string;
}

export interface DecisionRecord {
  decision_id: string;
  case_id: string;
  action: "pause" | "release";
  basis?: "advance_wishes" | "bank_policy" | null;
  release_reason?: string | null;
  rationale: string;
  decided_by: string;
  manager_id?: string | null;
  decided_at: string;
  warnings: string[];
}

export interface ContactView {
  case_id: string;
  call_id: string;
  nature: "information";
  verification: { caller_number_match: boolean; case_code_match: boolean };
  reached: boolean;
  concerned?: boolean | null;
  coming_to_branch?: boolean | null;
  eta_minutes?: number | null;
  wants_callback_later?: boolean | null;
  disclosed: DisclosureField[];
  recorded_at: string;
}

export interface FreezeRequest {
  freeze_id: string;
  case_id: string;
  account_id: string;
  requested_by: string;
  reason: string;
  requested_at: string;
  status: "pending" | "approved" | "rejected";
  decided_by?: string | null;
  decided_at?: string | null;
  decision_rationale?: string | null;
}

export type Language = "ja" | "en";

export interface CaseSummary {
  case_id: string;
  language?: Language;
  status: CaseStatus;
  customer_ref: string;
  opened_at: string;
  amount_jpy: number;
  risk_level?: RiskLevel | null;
}

export interface Case extends CaseSummary {
  account_id: string;
  transfer_id: string;
  request: EvidenceCard["request"];
  signals: ScoreSignal[];
  card?: EvidenceCard | null;
  transcript: Transcript[];
  decisions: DecisionRecord[];
  hold?: Hold | null;
  call_id?: string | null;
  case_code?: string | null;
  contact_view?: ContactView | null;
  verification_failed: boolean;
  contact_suspected?: string | null;
  freeze_request?: FreezeRequest | null;
  /** Filled approved hold line for card.risk.hold_line_id, set while a pause is recommended. */
  hold_line?: { id: string; ja: string; en?: string | null } | null;
}

export type CaseEventType =
  | "case_opened"
  | "card_updated"
  | "transcript_turn"
  | "decision_logged"
  | "hold_placed"
  | "hold_updated"
  | "police_summary_issued"
  | "contact_notice_sent"
  | "contact_outcome"
  | "verification_failed"
  | "freeze_requested"
  | "freeze_decided"
  | "outreach_ready"
  | "wishes_frozen";

export const CASE_EVENT_TYPES: CaseEventType[] = [
  "case_opened",
  "card_updated",
  "transcript_turn",
  "decision_logged",
  "hold_placed",
  "hold_updated",
  "police_summary_issued",
  "contact_notice_sent",
  "contact_outcome",
  "verification_failed",
  "freeze_requested",
  "freeze_decided",
  "outreach_ready",
  "wishes_frozen",
];

export interface CaseEvent {
  seq: number;
  case_id: string;
  type: CaseEventType;
  at: string;
  data: Record<string, unknown>;
}

export interface TurnRequest {
  speaker: "customer" | "teller";
  text: string;
}
export interface TurnResponse {
  turn_id: string;
  card: EvidenceCard | null;
}

export type ReleaseReason =
  | "customer_override_after_contact_reached"
  | "manager_review_second_confirmation"
  | "cleared_by_teller";

export interface DecisionRequest {
  action: "pause" | "release";
  basis?: "advance_wishes" | "bank_policy" | null;
  release_reason?: ReleaseReason | null;
  rationale: string;
  teller_id: string;
  manager_id?: string | null;
  second_confirmed_by?: string | null;
}
export interface DecisionResponse {
  decision: DecisionRecord;
  status: CaseStatus;
  hold?: Hold | null;
  warnings: string[];
}

export type PoliceItem = "amount" | "payee" | "customer_statements" | "indicators" | "timeline";
export const POLICE_ITEMS: PoliceItem[] = ["amount", "payee", "customer_statements", "indicators", "timeline"];

export interface PoliceSummaryRequest {
  officer_name: string;
  officer_title: string;
  requested_items: PoliceItem[];
  teller_id: string;
}
export interface PoliceSummaryResponse {
  summary_id: string;
  issued_at: string;
  officer_name: string;
  officer_title: string;
  items: Record<string, unknown>;
  text_ja: string;
}

export interface FreezeRequestBody {
  requested_by: string;
  reason: string;
}
export interface FreezeDecisionBody {
  decision: "approve" | "reject";
  analyst_id: string;
  rationale: string;
}
export interface OutreachItem {
  customer_ref: string;
  display_name_ja: string;
  account_id: string;
  last_paid_at: string;
  total_jpy: number;
}
export interface Freeze {
  freeze_id: string;
  account_id: string;
  case_id: string;
  approved_by: string;
  frozen_at: string;
  status: "frozen";
}
export interface FreezeDecisionResponse {
  freeze_request: FreezeRequest;
  freeze?: Freeze | null;
  outreach: OutreachItem[];
}

export interface DismissIndicatorBody {
  teller_id: string;
  reason: string;
}

export interface AuditEntry {
  [key: string]: unknown;
}

// ------------------------------------------------------------------ playbooks (schemas/playbook.json)

export interface PlaybookQuestion {
  id: string;
  ja: string;
  en?: string;
  purpose?: string;
}
export interface PlaybookHoldLine {
  id: string;
  ja: string;
  en?: string | null;
  for_hypotheses?: string[];
}
export interface Playbook {
  id: string;
  version: number;
  status: "pending" | "approved" | "rejected" | "retired";
  approved_by?: string | null;
  approved_at?: string | null;
  regions?: string[];
  first_seen?: string | null;
  sources: { publisher: string; url: string; published_at: string }[];
  hypothesis: HypothesisName;
  name: string;
  impersonates?: string[];
  contact_channels?: string[];
  script_phrases?: string[];
  victim_instructions?: string[];
  cover_stories?: { ja: string; en: string }[];
  payment_methods?: string[];
  targets?: string;
  question_bank?: { questions?: PlaybookQuestion[]; hold_lines?: PlaybookHoldLine[] };
}
export interface PlaybookPatch {
  status: "approved" | "rejected" | "retired";
  analyst_id: string;
  note?: string | null;
}

// ------------------------------------------------------------------ conversation service

export interface Notice {
  call_id: string;
  to_phone_e164: string;
  sent_at: string;
  text: string;
  language: Language;
  gloss_en?: string | null;
  published_phone_e164: string;
  case_code: string;
  audio_b64?: string | null;
}

export type PhoneClientMessage =
  | { type: "callback"; caller_number: string; menu_choice: string; case_code: string }
  | { type: "turn"; text?: string | null }
  | { type: "hangup" };

export type PhoneServerMessage =
  | { type: "say"; text: string; language: Language; gloss_en?: string | null; audio_b64?: string | null; template_intent?: string | null }
  | { type: "verification"; ok: boolean }
  | { type: "ended"; reason: "hangup" | "verification_failed" | "completed" };

/** `WS /cases/{id}/audio` server frames. */
export interface AudioTranscriptFrame {
  type: "transcript";
  turn_id: string;
  speaker: "customer" | "teller";
  text: string;
  is_final: boolean;
}

// ------------------------------------------------------------------ nginx-local (not a service contract)

/** `GET /config.json` and `GET /whoami` are answered by the web-ui's own nginx (like /healthz). */
export interface RuntimeConfig {
  env: "local" | "cloud";
  speech: "typed" | "cloud";
}
export interface WhoAmI {
  role: string;
  user: string;
}
