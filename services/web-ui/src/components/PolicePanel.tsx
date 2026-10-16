import { useState } from "react";
import { POLICE_ITEMS, type PoliceItem, type PoliceSummaryRequest, type PoliceSummaryResponse } from "../api/types";
import { POLICE_ITEM_LABEL, fmtTime, label, useLang } from "../i18n";

/**
 * Police-summary flow. The teller notifies the police; the evidence summary goes to attending
 * officers only ON REQUEST and only the sections they ask for. Officer name and title are required
 * and logged (APPI Art. 27(1)(i)). The form cannot submit without them.
 */
export function PolicePanel({
  tellerId,
  onIssue,
}: {
  tellerId: string;
  onIssue: (req: PoliceSummaryRequest) => Promise<PoliceSummaryResponse>;
}) {
  const { lang, tr } = useLang();
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [items, setItems] = useState<PoliceItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PoliceSummaryResponse | null>(null);

  const valid = name.trim() !== "" && title.trim() !== "" && items.length > 0;

  const toggle = (i: PoliceItem) => setItems((cur) => (cur.includes(i) ? cur.filter((x) => x !== i) : [...cur, i]));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      setResult(
        await onIssue({
          officer_name: name.trim(),
          officer_title: title.trim(),
          requested_items: POLICE_ITEMS.filter((i) => items.includes(i)),
          teller_id: tellerId,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="disclosure" aria-label={tr("警察への情報提供", "Police summary")} data-testid="police-panel">
      <summary>
        <span className="title">{tr("警察", "Police")}</span>
        <span className="state">
          {result ? tr(`${result.officer_name}さんに要約を提供済み`, `Summary given to ${result.officer_name}`) : tr("要請なし", "No request yet")}
        </span>
      </summary>
      <div className="disclosure-body">
      <p className="muted small">
        {tr(
          "警察官から要請があった場合のみ、要請された項目だけを提供します。氏名と職名は記録されます。",
          "Only on the officers' request, and only the sections they ask for. Their name and title are logged.",
        )}
      </p>
      <form onSubmit={submit}>
        <div className="row">
          <label className="field">
            {tr("警察官の氏名(必須)", "Officer name (required)")}
            <input value={name} onChange={(e) => setName(e.target.value)} aria-label={tr("警察官の氏名", "Officer name")} />
          </label>
          <label className="field">
            {tr("職名・階級(必須)", "Officer title (required)")}
            <input value={title} onChange={(e) => setTitle(e.target.value)} aria-label={tr("職名", "Officer title")} />
          </label>
        </div>
        <fieldset>
          <legend>{tr("要請された項目(1つ以上)", "Requested items (at least one)")}</legend>
          {POLICE_ITEMS.map((i) => (
            <label key={i} className="check">
              <input type="checkbox" checked={items.includes(i)} onChange={() => toggle(i)} />
              {label(POLICE_ITEM_LABEL, i, lang)}
            </label>
          ))}
        </fieldset>
        <button type="submit" disabled={!valid || busy}>
          {tr("要約を作成", "Issue summary")}
        </button>
        {!valid && (
          <p className="muted small" data-testid="police-hint">
            {tr("氏名、職名、項目を入力してください。", "Enter the officer's name and title and pick at least one item.")}
          </p>
        )}
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="summary" data-testid="police-result">
          <div className="muted small">
            {fmtTime(result.issued_at)} · {result.officer_name} ({result.officer_title})
          </div>
          <pre lang="ja">{result.text_ja}</pre>
          <button type="button" onClick={() => window.print()}>
            {tr("印刷", "Print")}
          </button>
        </div>
      )}
      </div>
    </details>
  );
}
