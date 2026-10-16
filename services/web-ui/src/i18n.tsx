import { createContext, useContext, useState, type ReactNode } from "react";

export type Lang = "ja" | "en";
const KEY = "mimamori.lang";

interface LangState {
  lang: Lang;
  setLang: (l: Lang) => void;
  /** Pick the string for the current language: tr("日本語", "English"). */
  tr: (ja: string, en: string) => string;
}
const Ctx = createContext<LangState>({ lang: "ja", setLang: () => {}, tr: (ja) => ja });

export function LangProvider({ children, initial }: { children: ReactNode; initial?: Lang }) {
  const [lang, setLangState] = useState<Lang>(() => {
    if (initial) return initial;
    try {
      const v = localStorage.getItem(KEY);
      if (v === "en" || v === "ja") return v;
    } catch {
      /* ignore */
    }
    return "ja";
  });
  const setLang = (l: Lang) => {
    setLangState(l);
    try {
      localStorage.setItem(KEY, l);
    } catch {
      /* ignore */
    }
  };
  return <Ctx.Provider value={{ lang, setLang, tr: (ja, en) => (lang === "ja" ? ja : en) }}>{children}</Ctx.Provider>;
}
export const useLang = () => useContext(Ctx);

// ---- label tables (code value -> [ja, en]) -------------------------------------------------

export const INDICATOR_LABEL: Record<string, [string, string]> = {
  impersonated_official: ["公的機関なりすまし", "Impersonated official"],
  impersonated_relative: ["親族なりすまし", "Impersonated relative"],
  secrecy_instruction: ["口止め", "Secrecy instruction"],
  urgency: ["急かし", "Urgency"],
  cash_or_card_handover: ["現金・カードの受け渡し", "Cash or card handover"],
  cover_story: ["使途の説明", "Cover story"],
  safe_account_transfer: ["安全な口座への移動", "Safe-account transfer"],
  changed_contact_number: ["連絡先番号の変更", "Changed contact number"],
  third_party_pressure: ["第三者からの圧力", "Third-party pressure"],
};

export const RISK_LABEL: Record<string, [string, string]> = {
  low: ["低", "Low"],
  elevated: ["要注意", "Elevated"],
  high: ["高", "High"],
};

export const HYPOTHESIS_LABEL: Record<string, [string, string]> = {
  legitimate: ["正当な取引", "Legitimate"],
  fake_police: ["警察なりすまし", "Fake police"],
  relative_in_trouble: ["親族のトラブル", "Relative in trouble"],
  gold_bullion: ["金地金", "Gold bullion"],
  other_scam: ["その他の詐欺", "Other scam"],
};

export const CASE_STATUS_LABEL: Record<string, [string, string]> = {
  open: ["対応中", "Open"],
  paused: ["一時停止中", "Paused"],
  released: ["解除済み", "Released"],
  closed: ["終了", "Closed"],
};

export const CASE_EVENT_LABEL: Record<string, [string, string]> = {
  case_opened: ["ケースを開きました", "Case opened"],
  card_updated: ["根拠カードを更新", "Evidence card updated"],
  transcript_turn: ["会話を記録", "Conversation turn recorded"],
  decision_logged: ["判断を記録", "Decision logged"],
  hold_placed: ["一時停止を実行", "Hold placed"],
  hold_updated: ["一時停止を更新", "Hold updated"],
  police_summary_issued: ["警察向け要約を発行", "Police summary issued"],
  contact_notice_sent: ["家族へ通知を送信", "Family notice sent"],
  contact_outcome: ["家族への連絡結果", "Family contact outcome"],
  verification_failed: ["AIの提案を確認できず不採用", "AI suggestion rejected after checks"],
  freeze_requested: ["口座凍結を依頼", "Freeze requested"],
  freeze_decided: ["口座凍結を判断", "Freeze decided"],
  outreach_ready: ["他の顧客への連絡先を作成", "Outreach list ready"],
  wishes_frozen: ["本人の希望を確定", "Customer wishes frozen"],
};

export const POLICE_ITEM_LABEL: Record<string, [string, string]> = {
  amount: ["金額", "Amount"],
  payee: ["送金先", "Payee"],
  customer_statements: ["お客様の発言", "Customer statements"],
  indicators: ["不審な兆候", "Indicators"],
  timeline: ["経過", "Timeline"],
};

export const RELEASE_REASON_LABEL: Record<string, [string, string]> = {
  customer_override_after_contact_reached: ["連絡先に連絡がついたため、お客様の意思で解除", "Customer override, contact reached"],
  manager_review_second_confirmation: ["責任者の確認と第二確認の上で解除", "Manager review with second confirmation"],
  cleared_by_teller: ["窓口で問題なしと確認", "Cleared by teller"],
};

/** Plain-language names for the `risk-v1` conditions (the code stays visible next to it). */
export const CONDITION_LABEL: Record<string, [string, string]> = {
  "H1:impersonation+secrecy": ["なりすましと口止めの両方", "Impersonation and secrecy both present"],
  H1: ["中核の兆候が2グループ以上", "Two or more core indicator groups"],
  H2: ["中核の兆候1つ+圧力+使途の不一致または不審な送金先", "One core indicator + pressure + cover mismatch or risky counterpart"],
};

export function label(table: Record<string, [string, string]>, key: string, lang: Lang): string {
  const e = table[key];
  if (!e) return key;
  return lang === "ja" ? e[0] : e[1];
}

export const yen = (n: number) => `¥${n.toLocaleString("ja-JP")}`;
export const fmtTime = (iso?: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", hour12: false });
};

export const fmtClock = (iso?: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("ja-JP", { timeZone: "Asia/Tokyo", hour12: false, hour: "2-digit", minute: "2-digit" });
};
