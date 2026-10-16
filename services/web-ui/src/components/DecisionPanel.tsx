import { useEffect, useState } from "react";
import type { Case, DecisionRequest, DecisionResponse, ReleaseReason } from "../api/types";
import { RELEASE_REASON_LABEL, fmtClock, fmtTime, label, useLang } from "../i18n";

/**
 * Pause / release. A human decides every pause and release (DA 11): the recommendation never submits
 * itself, and the form will not submit without a basis (pause) or a reason (release) and a rationale.
 * The teller is never blocked on evidence strength; a single-source pause comes back as a warning.
 */
export function DecisionPanel({
  kase,
  tellerId,
  onDecide,
}: {
  kase: Case;
  tellerId: string;
  onDecide: (req: DecisionRequest) => Promise<DecisionResponse>;
}) {
  const { lang, tr } = useLang();
  const [mode, setMode] = useState<"pause" | "release">(kase.status === "paused" ? "release" : "pause");
  useEffect(() => {
    if (kase.status === "paused") setMode("release"); // the pause is placed: what is left to decide is the release
  }, [kase.status]);
  const [basis, setBasis] = useState<"" | "advance_wishes" | "bank_policy">("");
  const [reason, setReason] = useState<"" | ReleaseReason>("");
  const [rationale, setRationale] = useState("");
  const [managerId, setManagerId] = useState("");
  const [second, setSecond] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  const recommended = kase.card?.risk.pause_recommended ?? false;
  const contactReached = kase.contact_view?.reached === true;
  const decided = kase.status === "released" || kase.status === "closed";
  const needsManager = mode === "release" && reason === "manager_review_second_confirmation";
  const rationaleOk = rationale.trim().length > 0;
  const managerOk = !needsManager || (managerId.trim() !== "" && second.trim() !== "" && managerId.trim() !== second.trim());
  const valid =
    rationaleOk && managerOk && (mode === "pause" ? basis !== "" : reason !== "") && !(reason === "customer_override_after_contact_reached" && !contactReached);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    const req: DecisionRequest =
      mode === "pause"
        ? { action: "pause", basis: basis as "advance_wishes" | "bank_policy", rationale: rationale.trim(), teller_id: tellerId }
        : {
            action: "release",
            release_reason: reason as ReleaseReason,
            rationale: rationale.trim(),
            teller_id: tellerId,
            manager_id: needsManager ? managerId.trim() : null,
            second_confirmed_by: needsManager ? second.trim() : null,
          };
    try {
      const res = await onDecide(req);
      setWarnings(res.warnings);
      setRationale("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="paper decision" aria-label={tr("あなたの判断", "Your decision")} data-testid="decision-panel">
      <h3>{tr("あなたの判断", "Your decision")}</h3>

      {kase.hold && (
        <div className="hold-info" data-testid="hold-info">
          <p className="until">{tr(`${fmtClock(kase.hold.ends_at)}まで保留中`, `On hold until ${fmtClock(kase.hold.ends_at)}`)}</p>
          <p className="small muted">
            {tr("最短の解除", "Earliest release")} {fmtTime(kase.hold.minimum_ends_at)} · {tr("上限", "cap")} {fmtTime(kase.hold.cap_ends_at)}
          </p>
          {kase.hold.overrides.map((o) => (
            <p key={o} className="small">
              {o === "after_contact_reached"
                ? tr("連絡先に連絡がついた後に解除できます。", "Can be released after the contact is reached.")
                : tr("責任者の確認と第二確認の上で解除できます。", "Can be released after manager review and a second confirmation.")}
            </p>
          ))}
        </div>
      )}

      {decided ? (
        <p className="muted">{tr("このケースは判断済みです。", "This case has been decided.")}</p>
      ) : (
        <form onSubmit={submit}>
          <div className="seg" role="radiogroup" aria-label={tr("操作", "Action")}>
            <label className={mode === "pause" ? "on" : ""}>
              <input type="radio" name="mode" checked={mode === "pause"} onChange={() => setMode("pause")} />
              {tr("一時停止する", "Pause")}
            </label>
            <label className={mode === "release" ? "on" : ""}>
              <input type="radio" name="mode" checked={mode === "release"} onChange={() => setMode("release")} />
              {tr("解除・実行する", "Release")}
            </label>
          </div>

          {mode === "pause" ? (
            <label className="field">
              {tr("根拠(必須)", "Basis (required)")}
              <select value={basis} onChange={(e) => setBasis(e.target.value as typeof basis)} aria-label={tr("根拠", "Basis")}>
                <option value="">{tr("選択してください", "Select a basis")}</option>
                <option value="advance_wishes">{tr("事前のご希望(待機の取り決め)", "Advance wishes (cooling-off)")}</option>
                <option value="bank_policy">{tr("銀行の方針(任意の待機)", "Bank policy (voluntary wait)")}</option>
              </select>
            </label>
          ) : (
            <>
              <label className="field">
                {tr("解除の理由(必須)", "Release reason (required)")}
                <select value={reason} onChange={(e) => setReason(e.target.value as typeof reason)} aria-label={tr("解除の理由", "Release reason")}>
                  <option value="">{tr("選択してください", "Select a reason")}</option>
                  {(Object.keys(RELEASE_REASON_LABEL) as ReleaseReason[]).map((r) => (
                    <option key={r} value={r} disabled={r === "customer_override_after_contact_reached" && !contactReached}>
                      {label(RELEASE_REASON_LABEL, r, lang)}
                      {r === "customer_override_after_contact_reached" && !contactReached ? tr("(連絡先未確認)", " (contact not reached)") : ""}
                    </option>
                  ))}
                </select>
              </label>
              {needsManager && (
                <div className="row">
                  <label className="field">
                    {tr("責任者ID", "Manager ID")}
                    <input value={managerId} onChange={(e) => setManagerId(e.target.value)} />
                  </label>
                  <label className="field">
                    {tr("第二確認者ID(責任者と別の人)", "Second confirmer (not the manager)")}
                    <input value={second} onChange={(e) => setSecond(e.target.value)} />
                  </label>
                </div>
              )}
            </>
          )}

          <label className="field">
            {tr("理由・メモ(必須、記録されます)", "Rationale (required, logged)")}
            <textarea rows={3} value={rationale} onChange={(e) => setRationale(e.target.value)} aria-label={tr("理由", "Rationale")} />
          </label>

          <button type="submit" className={mode === "pause" && recommended ? "danger" : ""} disabled={!valid || busy}>
            {mode === "pause" ? tr("一時停止を実行", "Place pause") : tr("送金を解除する", "Release the transfer")}
          </button>
          {!valid && (
            <p className="muted small" data-testid="decision-hint">
              {mode === "pause"
                ? tr("根拠と理由を入力すると実行できます。", "Choose a basis and write a rationale to continue.")
                : tr("解除の理由と理由・メモを入力してください。", "Choose a release reason and write a rationale to continue.")}
            </p>
          )}
        </form>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {warnings.length > 0 && (
        <p className="warn" role="status" data-testid="decision-warnings">
          {warnings.includes("single_source_pause")
            ? tr("注意: 根拠が単一の情報源のため、警告付きで記録されました(停止は有効です)。", "Warning: single-source pause, logged. The pause stands.")
            : warnings.join(", ")}
        </p>
      )}

      {kase.decisions.length > 0 && (
        <ul className="log">
          {kase.decisions.map((d) => (
            <li key={d.decision_id}>
              <strong>{d.action === "pause" ? tr("一時停止", "Pause") : tr("解除", "Release")}</strong>{" "}
              {d.basis ?? d.release_reason} · {d.decided_by} · {fmtTime(d.decided_at)}
              <div className="muted small">{d.rationale}</div>
              {d.warnings.length > 0 && <div className="warn small">{d.warnings.join(", ")}</div>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
