import type { EvidenceCard as Card, Language } from "../api/types";
import { useLang } from "../i18n";

/** The paper cue card: the approved question to ask next, in the case language first. "Say this" fills the counter input; it never sends. */
export function AskNext({ card, language = "ja", onSay }: { card: Card; language?: Language; onSay?: (text: string) => void }) {
  const { tr } = useLang();
  const q = card.next_question;
  if (!q) return null;
  const primary = language === "en" ? q.en_filled ?? q.ja_filled : q.ja_filled;
  const secondary = language === "en" ? q.ja_filled : q.en_filled;
  return (
    <section className="paper next-q ask-next" data-testid="next-question" aria-label={tr("次に伺うこと", "Ask next")}>
      <h4>{tr("次に伺うこと", "Ask next")}</h4>
      <p lang={language} className="q-ja">
        {primary}
      </p>
      {secondary && (
        <p lang={language === "en" ? "ja" : "en"} className="small muted">
          {secondary}
        </p>
      )}
      {onSay && (
        <button type="button" onClick={() => onSay(primary)}>
          {tr("この質問を入力", "Say this")}
        </button>
      )}
    </section>
  );
}
