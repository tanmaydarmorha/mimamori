import type { ReactNode } from "react";
import type { EvidenceCard as Card, FactClaim, Language, PlaybookHoldLine } from "../api/types";
import { CASE_STATUS_LABEL, RISK_LABEL, label, useLang, yen } from "../i18n";

const factValue = (card: Card, tool: string, field: string): unknown =>
  (card.claims.find((c) => c.kind === "fact" && (c as FactClaim).source.tool === tool && (c as FactClaim).source.field === field) as FactClaim | undefined)?.source
    .value;

/**
 * The band: the one loud thing on the teller screen. Its field colour is the risk level, its first line
 * the state in words (never colour alone), then who and how much, the payee in words, and, when a pause
 * is recommended, the approved hold line to say to the customer. The level, pause recommendation and
 * hold line come from the card as computed in code; nothing is invented here.
 */
export function RiskBand({
  card,
  holdLine,
  language = "ja",
  name,
  status,
  control,
  showHoldLine = true,
}: {
  card: Card;
  holdLine?: PlaybookHoldLine | null;
  language?: Language;
  name?: string | null;
  /** Case status (open, paused, released), shown as a word at the top right. */
  status?: string;
  /** Top right, before the status: the language control. */
  control?: ReactNode;
  /** The teller reads the hold line to the customer; the analyst's screen leaves it out. */
  showHoldLine?: boolean;
}) {
  const { lang, tr } = useLang();
  const level = card.risk.level;
  const word = label(RISK_LABEL, level, lang);
  const paused = status === "paused";
  const state = paused && card.risk.pause_recommended
    ? tr(`${word}(一時停止中)`, `${word}: paused`)
    : card.risk.pause_recommended
      ? tr(`${word}(一時停止を推奨)`, `${word}: pause recommended`)
      : word;
  const req = card.request;
  const payee = req.payee;
  const age = factValue(card, "counterpart_graph", "account_age_days");
  const payers = factValue(card, "counterpart_graph", "distinct_payers_7d");
  const facts = [
    payee ? (payee.relation === "same_bank" ? tr("当行内の口座", "Same-bank account") : tr("他行の口座", "Other-bank account")) : null,
    typeof age === "number" ? tr(`開設から${age}日`, `${age} days old`) : null,
    typeof payers === "number" ? tr(`直近7日で${payers}人が送金`, `${payers} payers this week`) : null,
  ].filter(Boolean);

  return (
    <section className={`band band-${level}`} data-testid="risk-banner" data-level={level} aria-label={tr("リスク", "Risk")}>
      <div className="band-top">
        {control}
        {status && <span data-testid="case-status">{label(CASE_STATUS_LABEL, status, lang)}</span>}
      </div>
      <p className="band-state" role="status">
        <span key={`${level}-${card.risk.pause_recommended}`}>{state}</span>
      </p>
      <p className="band-who">
        {name ?? card.customer_ref} {yen(req.amount_jpy)}
        {payee && ` ${tr("→", "to")} ${payee.name_kana}`}
      </p>
      {facts.length > 0 && <p className="band-facts small muted">{facts.join(tr("、", ", "))}</p>}
      {showHoldLine && card.risk.pause_recommended && (
        <div className="band-hold" data-testid="hold-line">
          <p className="say small muted">{tr("お客様へのご案内", "Say to the customer")}</p>
          {holdLine ? (
            <>
              <p className="text" lang={language}>
                {language === "en" ? holdLine.en ?? holdLine.ja : holdLine.ja}
              </p>
              {holdLine.en && (
                <p className="small muted" lang={language === "en" ? "ja" : "en"}>
                  {language === "en" ? holdLine.ja : holdLine.en}
                </p>
              )}
            </>
          ) : (
            <p className="text">{card.risk.hold_line_id ?? ""}</p>
          )}
        </div>
      )}
    </section>
  );
}
