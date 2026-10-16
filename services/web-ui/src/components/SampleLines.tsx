import { DEMO_LINES, glossFor } from "../demoLines";
import { useLang } from "../i18n";

/** Quiet row of sample-line buttons. Clicking fills the input; it never sends. */
export function SampleLines({ who, language = "ja", onPick, disabled }: { who: "customer" | "contact"; language?: "ja" | "en"; onPick: (text: string) => void; disabled?: boolean }) {
  const { tr } = useLang();
  return (
    <div className="sample-lines" data-testid="sample-lines">
      <span className="muted small">{tr("例文", "Sample lines")}</span>
      {DEMO_LINES.filter((l) => l.who === who && l.language === language).map((l) => (
        <button key={l.id} type="button" className="sample" disabled={disabled} onClick={() => onPick(l.text)} title={l.text}>
          {tr(l.label_ja, l.label_en)}
        </button>
      ))}
    </div>
  );
}

/** "EN: ..." line under Japanese text, in English mode only, when the text is a known demo line. */
export function Gloss({ text, en }: { text?: string; en?: string }) {
  const { lang } = useLang();
  const g = en ?? (text ? glossFor(text) : undefined);
  if (lang !== "en" || !g) return null;
  return (
    <div className="gloss" data-testid="gloss">
      EN: {g}
    </div>
  );
}
