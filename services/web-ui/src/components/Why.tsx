import { useState } from "react";
import type { Claim, EvidenceCard as Card, FactClaim, InferenceClaim, QuoteClaim } from "../api/types";
import { CONDITION_LABEL, HYPOTHESIS_LABEL, INDICATOR_LABEL, label, useLang } from "../i18n";
import { Gloss } from "./SampleLines";

/**
 * Why the band says what it says: the verified facts and the customer's own words as plain sentences.
 * Everything a teller does not read aloud (claim IDs, rule codes, sources, hypotheses, dropped claims,
 * the dismiss action) sits under one native "Details". NO probability numbers: only the fields rendered
 * below can reach the screen, so a stray `confidence` on a claim (the model's own number) never shows.
 */
export function Why({
  card,
  caseId,
  onDismiss,
}: {
  card: Card;
  caseId?: string;
  onDismiss?: (claimId: string, reason: string) => Promise<void> | void;
}) {
  const { lang, tr } = useLang();
  const facts = card.claims.filter((c): c is FactClaim => c.kind === "fact");
  const quotes = card.claims.filter((c): c is QuoteClaim => c.kind === "quote");
  const inferences = card.claims.filter((c): c is InferenceClaim => c.kind === "inference");
  const byId = new Map<string, Claim>(card.claims.map((c) => [c.id, c]));

  const chip = (id: string) => {
    const c = byId.get(id);
    const hint = c?.kind === "quote" ? `「${c.source.text}」` : c && "statement_en" in c ? c.statement_en : undefined;
    return (
      <span key={id} className="chip" title={hint}>
        {id}
      </span>
    );
  };

  return (
    <section className="why" aria-label={tr("根拠", "Why")} data-testid="why">
      <h3>{tr("根拠", "Why")}</h3>
      <div className="grid2">
        <div>
          <h4>{tr("事実", "Facts")}</h4>
          {facts.length === 0 && <p className="muted">{tr("なし", "None")}</p>}
          <ul className="plain">
            {facts.map((f) => (
              <li key={f.id}>{f.statement_en}</li>
            ))}
          </ul>
        </div>
        <div>
          <h4>{tr("お客様の言葉", "Quotes")}</h4>
          {quotes.length === 0 && <p className="muted">{tr("なし", "None")}</p>}
          <ul className="plain">
            {quotes.map((q) => (
              <li key={q.id}>
                <p className="quote" lang="ja">
                  「{q.source.text}」
                </p>
                <Gloss text={q.source.text} />
              </li>
            ))}
          </ul>
        </div>
      </div>

      <details className="why-details">
        <summary className="muted">{tr("詳細", "Details")}</summary>
        <div className="details-body">
          {caseId && (
            <p className="small muted">
              {tr("ケース", "Case")} {caseId} · {tr("ルール", "rule")} {card.risk.rule_version}
            </p>
          )}
          {card.risk.fired.length > 0 && (
            <>
              <h4>{tr("該当した条件", "Conditions that fired")}</h4>
              <ul className="claims">
                {card.risk.fired.map((f, i) => (
                  <li key={i}>
                    {label(CONDITION_LABEL, f.condition, lang)} <span>{f.condition}</span> {f.claims.map(chip)}
                  </li>
                ))}
              </ul>
            </>
          )}
          <h4>{tr("事実の出典", "Fact sources")}</h4>
          <ul className="claims">
            {facts.map((f) => (
              <li key={f.id} data-claim={f.id}>
                {chip(f.id)} <span className="src">{f.source.tool}.{f.source.field} = {String(f.source.value)}</span>
              </li>
            ))}
          </ul>
          <h4>{tr("兆候", "Indicators")}</h4>
          <ul className="claims">
            {quotes.length === 0 && <li className="muted">{tr("なし", "None")}</li>}
            {quotes.map((q) => (
              <li key={q.id} data-claim={q.id}>
                {chip(q.id)} <span className="tag">{label(INDICATOR_LABEL, q.indicator, lang)}</span>{" "}
                <span className="src">
                  {q.source.turn_id}
                  {q.turn_id_corrected ? ` · ${tr("発言番号を補正", "turn corrected")}` : ""}
                </span>
                {onDismiss && <DismissButton claimId={q.id} onDismiss={onDismiss} />}
              </li>
            ))}
          </ul>
          <h4>{tr("仮説(推論。事実ではありません)", "Hypotheses (inferences, not facts)")}</h4>
          <ul className="claims" data-testid="inferences">
            {inferences.length === 0 && <li className="muted">{tr("なし", "None")}</li>}
            {inferences.map((i) => (
              <li key={i.id} data-claim={i.id}>
                {chip(i.id)} <span className="tag tag-hyp">{tr("仮説", "hypothesis")}</span> {i.statement_en}
                <div className="src">
                  {tr("根拠", "grounds")}: {i.grounds.map(chip)}
                </div>
              </li>
            ))}
          </ul>
          <h4>{tr("競合する説明", "Competing explanations")}</h4>
          <ul className="claims">
            {card.hypotheses.map((h) => (
              <li key={h.name}>
                <strong>{label(HYPOTHESIS_LABEL, h.name, lang)}</strong>{" "}
                {h.supporting_claims.length > 0 ? h.supporting_claims.map(chip) : <span className="muted">{tr("支持する根拠なし", "no supporting claims")}</span>}
              </li>
            ))}
          </ul>
          <details className="dropped" data-testid="dropped">
            <summary>
              {tr("除外された主張", "Dropped claims")} ({card.dropped.length})
            </summary>
            {card.dropped.length === 0 ? (
              <p className="muted">{tr("なし", "None")}</p>
            ) : (
              <ul>
                {card.dropped.map((d, i) => (
                  <li key={i}>
                    {d.reason} <span className="muted">{JSON.stringify(d.claim)}</span>
                  </li>
                ))}
              </ul>
            )}
          </details>
        </div>
      </details>
    </section>
  );
}

function DismissButton({
  claimId,
  onDismiss,
}: {
  claimId: string;
  onDismiss: (claimId: string, reason: string) => Promise<void> | void;
}) {
  const { tr } = useLang();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  if (!open)
    return (
      <button type="button" className="link" onClick={() => setOpen(true)}>
        {tr("この兆候を取り消す", "Dismiss this indicator")}
      </button>
    );
  return (
    <form
      className="inline-form"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          await onDismiss(claimId, reason.trim());
          setOpen(false);
        } finally {
          setBusy(false);
        }
      }}
    >
      <input
        aria-label={tr("取り消しの理由", "Dismissal reason")}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder={tr("理由(必須、記録されます)", "Reason (required, logged)")}
      />
      <button type="submit" disabled={busy || !reason.trim()}>
        {tr("取り消す", "Dismiss")}
      </button>
      <button type="button" className="link" onClick={() => setOpen(false)}>
        {tr("やめる", "Cancel")}
      </button>
    </form>
  );
}
