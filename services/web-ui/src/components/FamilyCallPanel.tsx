import { useState } from "react";
import type { Case } from "../api/types";
import { fmtTime, useLang } from "../i18n";

const yesNo = (v: boolean | null | undefined, tr: (a: string, b: string) => string) =>
  v === true ? tr("はい", "yes") : v === false ? tr("いいえ", "no") : "—";

/**
 * Family-call status (steps 7a-7c): notice sent, verified callback, and the contact's reply.
 * The reply is shown as INFORMATION (`contact_view`), never as an instruction to the teller.
 */
export function FamilyCallPanel({ kase, onRetrigger }: { kase: Case; onRetrigger: () => Promise<void> }) {
  const { tr } = useLang();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cv = kase.contact_view;
  const canCall = kase.status === "paused" && !cv;
  const state = cv
    ? cv.coming_to_branch
      ? cv.eta_minutes != null
        ? tr(`連絡済み: ${cv.eta_minutes}分後に来店予定`, `Called: coming to the branch in ${cv.eta_minutes} minutes`)
        : tr("連絡済み: 来店予定", "Called: coming to the branch")
      : tr("連絡済み", "Called: reached")
    : kase.verification_failed
      ? tr("確認に失敗しました", "Callback could not be verified")
      : kase.contact_suspected
        ? tr("連絡しません", "No call made")
        : kase.call_id
          ? tr("通知を送信、折り返し待ち", "Notice sent, waiting for the callback")
          : tr("未連絡", "Not called");

  return (
    <details className="disclosure" aria-label={tr("ご家族への連絡", "Family call")} data-testid="family-call">
      <summary>
        <span className="title">{tr("ご家族に連絡", "Call the family")}</span>
        <span className="state">{state}</span>
      </summary>
      <div className="disclosure-body">
      {kase.contact_suspected && (
        <p className="warn">
          {tr("連絡は行いません", "No call made")}: {kase.contact_suspected}
          <br />
          <span className="muted small">
            {tr("銀行方針に基づく任意の待機、責任者、警察で対応してください。", "Use a voluntary wait under bank policy, a manager and the police.")}
          </span>
        </p>
      )}
      {!kase.call_id && !kase.contact_suspected && (
        <p className="muted">{tr("一時停止後、事前のご希望に基づき自動で連絡します。", "After a pause the notice goes out automatically when the wishes allow it.")}</p>
      )}
      {kase.call_id && (
        <p>
          {tr("通知を送信しました", "Notice sent")}
          {kase.case_code && (
            <>
              {" "}
              · {tr("ケースコード", "case code")} <strong>{kase.case_code}</strong>
            </>
          )}
          {!cv && !kase.verification_failed && <span className="muted"> · {tr("折り返しを待っています", "waiting for the callback")}</span>}
        </p>
      )}
      {kase.verification_failed && (
        <p className="error" role="alert" data-testid="verification-failed">
          {tr("本人確認(番号とケースコード)に失敗しました。何も開示していません。", "Callback verification failed (number or case code). Nothing was disclosed.")}
        </p>
      )}
      {cv && (
        <div className="contact-view" data-testid="contact-view">
          <p className="small muted">{tr("情報であり、指示ではありません。", "Information, not an instruction.")}</p>
          <ul>
            <li>
              {tr("連絡がつきました", "Reached")}: <strong>{yesNo(cv.reached, tr)}</strong>
            </li>
            <li>
              {tr("ご心配されている", "Concerned")}: {yesNo(cv.concerned, tr)}
            </li>
            <li>
              {tr("来店予定", "Coming to the branch")}: {yesNo(cv.coming_to_branch, tr)}
              {cv.eta_minutes != null ? ` (${cv.eta_minutes} ${tr("分後", "min")})` : ""}
            </li>
            <li>
              {tr("後でかけ直し希望", "Wants a callback later")}: {yesNo(cv.wants_callback_later, tr)}
            </li>
          </ul>
          <div className="muted small">{fmtTime(cv.recorded_at)}</div>
        </div>
      )}
      {canCall && (
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              await onRetrigger();
            } catch (e) {
              setError(e instanceof Error ? e.message : String(e));
            } finally {
              setBusy(false);
            }
          }}
        >
          {tr("連絡を(再)開始", "Start / retry the contact call")}
        </button>
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
