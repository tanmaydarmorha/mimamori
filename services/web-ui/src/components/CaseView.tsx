import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api/client";
import { useCaseEvents } from "../api/sse";
import type { Case, CaseEvent, Customer, DecisionRequest, PoliceSummaryRequest } from "../api/types";
import { useAuth } from "../auth/Auth";
import { CASE_EVENT_LABEL, CASE_STATUS_LABEL, fmtTime, label, useLang, yen } from "../i18n";
import { DecisionPanel } from "./DecisionPanel";
import { AskNext } from "./AskNext";
import { RiskBand } from "./RiskBand";
import { Why } from "./Why";
import { FamilyCallPanel } from "./FamilyCallPanel";
import { FreezeRequestPanel } from "./FreezeRequestPanel";
import { PolicePanel } from "./PolicePanel";
import { TurnPanel } from "./TurnPanel";
import type { Language } from "../api/types";

/** One open case: the band, then talk (ask next, conversation, why) on the left and act (decision and the three disclosures) on the right. */
export function CaseView({ caseId }: { caseId: string }) {
  const { lang, tr } = useLang();
  const { identity, config } = useAuth();
  const [kase, setKase] = useState<Case | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [prefill, setPrefill] = useState<{ speaker: "customer" | "teller"; text: string; n: number } | null>(null);
  const alive = useRef(true);
  const act = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    try {
      const c = await api.getCase(caseId);
      if (alive.current) {
        setKase(c);
        setError(null);
      }
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : String(e));
    }
  }, [caseId]);

  useEffect(() => {
    alive.current = true;
    setKase(null);
    void refresh();
    return () => {
      alive.current = false;
    };
  }, [refresh]);

  useEffect(() => {
    act.current?.scrollTo?.({ top: 0 }); // a new status starts at the top of the decision column
  }, [kase?.status]);

  const events = useCaseEvents(caseId, (_e: CaseEvent) => void refresh());

  // Bank-side display name (core banking), best effort. The evidence card itself carries no name.
  useEffect(() => {
    setCustomer(null);
    if (!kase?.customer_ref) return;
    api.getCustomer(kase.customer_ref).then(setCustomer).catch(() => {});
  }, [kase?.customer_ref]);


  if (error && !kase) return <p className="error">{error}</p>;
  if (!kase) return <p className="muted">{tr("読み込み中…", "Loading…")}</p>;

  const decide = async (req: DecisionRequest) => {
    const res = await api.postDecision(caseId, req);
    await refresh();
    return res;
  };
  const issuePolice = async (req: PoliceSummaryRequest) => {
    const res = await api.postPoliceSummary(caseId, req);
    await refresh();
    return res;
  };

  const language = kase.language ?? "ja";
  const control = (
    <LanguageControl
      language={language}
      locked={kase.transcript.length > 0}
      onChange={async (l) => {
        await api.patchLanguage(caseId, l, identity.user);
        await refresh();
      }}
    />
  );
  const name = customer?.display_name_ja ?? null;

  return (
    <div className="case-view" data-testid="case-view">
      {kase.card ? (
        <RiskBand card={kase.card} holdLine={kase.hold_line} language={language} name={name} status={kase.status} control={control} />
      ) : (
        <section className="band" data-testid="investigating">
          <div className="band-top">
            {control}
            <span>{label(CASE_STATUS_LABEL, kase.status, lang)}</span>
          </div>
          <p className="band-state">
            <span>{tr("調査中…", "Checking…")}</span>
          </p>
          <p className="band-who">
            {name ?? kase.customer_ref} {yen(kase.amount_jpy)}
          </p>
          <ul className="plain small muted">
            {kase.signals.map((s) => (
              <li key={s.code}>{s.statement_en}</li>
            ))}
          </ul>
        </section>
      )}

      <div className="case-cols">
        <div className="col-talk">
          {kase.card && <AskNext card={kase.card} language={language} onSay={(text) => setPrefill({ speaker: "teller", text, n: (prefill?.n ?? 0) + 1 })} />}
          <TurnPanel
            caseId={caseId}
            transcript={kase.transcript}
            language={language}
            prefill={prefill}
            speechOn={config.speech === "cloud"}
            disabled={kase.status === "released" || kase.status === "closed"}
            onSend={async (speaker, text) => {
              await api.postTurn(caseId, { speaker, text });
              await refresh();
            }}
          />
          {kase.card && (
            <Why
              card={kase.card}
              caseId={kase.case_id}
              onDismiss={async (claimId, reason) => {
                await api.dismissClaim(caseId, claimId, { teller_id: identity.user, reason });
                await refresh();
              }}
            />
          )}
          <details className="timeline-row">
            <summary className="muted">{tr("経過", "Timeline")}</summary>
            <ol className="timeline" data-testid="timeline">
              {/* verification_failed can arrive up to 3 times per call: show it once */}
              {events
                .filter((e, i, all) => e.type !== "verification_failed" || all.findIndex((x) => x.type === e.type) === i)
                .map((e) => (
                  <li key={e.seq}>
                    {label(CASE_EVENT_LABEL, e.type, lang)} <span className="muted small">{fmtTime(e.at)}</span>
                  </li>
                ))}
            </ol>
          </details>
        </div>

        <div className="col-act" ref={act}>
          <DecisionPanel kase={kase} tellerId={identity.user} onDecide={decide} />
          <FamilyCallPanel
            kase={kase}
            onRetrigger={async () => {
              await api.postContactCall(caseId);
              await refresh();
            }}
          />
          <PolicePanel tellerId={identity.user} onIssue={issuePolice} />
          <FreezeRequestPanel
            kase={kase}
            onRequest={async (reason) => {
              await api.postFreezeRequest(caseId, { requested_by: identity.user, reason });
              await refresh();
            }}
          />
        </div>
      </div>
    </div>
  );
}

function LanguageControl({ language, locked, onChange }: { language: Language; locked: boolean; onChange: (l: Language) => Promise<void> }) {
  const { tr } = useLang();
  const [err, setErr] = useState<string | null>(null);
  const name = (l: Language) => (l === "ja" ? "日本語" : "English");
  if (locked)
    return (
      <span className="language-badge" data-testid="language-badge">
        {tr("会話の言語", "Conversation language")}: <span className="tag">{name(language)}</span>
      </span>
    );
  return (
    <span className="language-select" data-testid="language-select">
      <label>
        {tr("会話の言語", "Conversation language")}:{" "}
        <select
          value={language}
          aria-label={tr("会話の言語", "Conversation language")}
          onChange={(e) => onChange(e.target.value as Language).then(() => setErr(null), (x) => setErr(x instanceof Error ? x.message : String(x)))}
        >
          <option value="ja">日本語</option>
          <option value="en">English</option>
        </select>
      </label>
      {err && <span className="error"> {err}</span>}
    </span>
  );
}
