import type { Case, EvidenceCard } from "../api/types";
import raw from "./card-tanaka.json"; // copy of schemas/examples/evidence-card-tanaka.json

export const tanakaCard = raw as unknown as EvidenceCard;

export const tanakaCase: Case = {
  case_id: tanakaCard.case_id,
  status: "open",
  customer_ref: tanakaCard.customer_ref,
  opened_at: "2026-10-13T11:42:00+09:00",
  amount_jpy: 3000000,
  risk_level: "high",
  account_id: "acct-tanaka-0001",
  transfer_id: "tr-0001",
  request: tanakaCard.request,
  signals: [],
  card: tanakaCard,
  transcript: [],
  decisions: [],
  hold: null,
  call_id: null,
  case_code: null,
  contact_view: null,
  verification_failed: false,
  contact_suspected: null,
  freeze_request: null,
};
