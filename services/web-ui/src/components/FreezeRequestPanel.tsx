import { useState } from "react";
import type { Case } from "../api/types";
import { useLang } from "../i18n";

/** Teller asks the analyst to freeze the payee (mule) account. The analyst decides (CR 21). */
export function FreezeRequestPanel({
  kase,
  onRequest,
}: {
  kase: Case;
  onRequest: (reason: string) => Promise<void>;
}) {
  const { tr } = useLang();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fr = kase.freeze_request;
  const state = !fr
    ? tr("未依頼", "Not requested")
    : fr.status === "pending"
      ? tr("依頼済み、分析担当の判断待ち", "Requested, waiting for the analyst")
      : fr.status === "approved"
        ? tr("承認されました", "Approved")
        : tr("却下されました", "Rejected");

  return (
    <details className="disclosure" aria-label={tr("口座凍結の依頼", "Freeze request")} data-testid="freeze-request">
      <summary>
        <span className="title">{tr("送金先口座の凍結", "Freeze the payee account")}</span>
        <span className="state">{state}</span>
      </summary>
      <div className="disclosure-body">
      <p className="muted small">{tr("凍結の判断は分析担当が行います。", "The analyst decides.")}</p>
      {fr ? (
        <p>
          <span className={`tag tag-${fr.status}`}>{fr.status}</span> {fr.reason}
          {fr.decision_rationale && <span className="muted small"> · {fr.decision_rationale}</span>}
        </p>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (!reason.trim()) return;
            setBusy(true);
            setError(null);
            try {
              await onRequest(reason.trim());
              setReason("");
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="field">
            {tr("依頼理由(必須)", "Reason (required)")}
            <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} aria-label={tr("凍結の依頼理由", "Freeze reason")} />
          </label>
          <button type="submit" disabled={busy || !reason.trim()}>
            {tr("凍結を依頼", "Request freeze")}
          </button>
        </form>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      </div>
    </details>
  );
}
