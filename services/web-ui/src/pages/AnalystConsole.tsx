import { useCallback, useEffect, useState } from "react";
import * as api from "../api/client";
import { useCaseEvents } from "../api/sse";
import type { Case, Customer, FreezeRequest, OutreachItem, Playbook } from "../api/types";
import { useAuth } from "../auth/Auth";
import { RiskBand } from "../components/RiskBand";
import { Why } from "../components/Why";
import { fmtTime, useLang, yen } from "../i18n";

type Queue = "freezes" | "playbooks" | "outreach";

/**
 * Analyst console: three queues in the rail with their counts, the open queue on the right.
 * Analyst role only (see App). Data for the counts is loaded here; each queue shows its own rows.
 */
export function AnalystConsole() {
  const { tr } = useLang();
  const [queue, setQueue] = useState<Queue>("freezes");
  const [freezes, setFreezes] = useState<FreezeRequest[]>([]);
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [playbookError, setPlaybookError] = useState<string | null>(null);
  const [freezeError, setFreezeError] = useState<string | null>(null);
  // Outreach returned by a freeze decision made in this session (also learned via SSE `outreach_ready`).
  const [outreachByCase, setOutreachByCase] = useState<Record<string, OutreachItem[]>>({});
  const [outreachCounts, setOutreachCounts] = useState<Record<string, number>>({});

  const loadFreezes = useCallback(() => {
    api
      .listFreezeRequests()
      .then((r) => {
        setFreezes(r);
        setFreezeError(null);
      })
      .catch((e) => setFreezeError(String(e.message ?? e)));
  }, []);
  const loadPlaybooks = useCallback(() => {
    api
      .listPlaybooks("pending")
      .then((p) => {
        setPlaybooks(p);
        setPlaybookError(null);
      })
      .catch((e) => setPlaybookError(String(e.message ?? e)));
  }, []);
  useEffect(() => {
    loadFreezes();
    loadPlaybooks();
    const t = setInterval(loadFreezes, 3000);
    return () => clearInterval(t);
  }, [loadFreezes, loadPlaybooks]);

  const approved = freezes.filter((f) => f.status === "approved");
  const pending = freezes.filter((f) => f.status === "pending");
  const outreachTotal = approved.reduce((n, f) => n + (outreachCounts[f.case_id] ?? outreachByCase[f.case_id]?.length ?? 0), 0);
  const rows: [Queue, string, number][] = [
    ["freezes", tr("口座凍結の依頼", "Freeze requests"), pending.length],
    ["playbooks", tr("プレイブック", "Playbooks"), playbooks.length],
    ["outreach", tr("連絡対象", "Outreach"), outreachTotal],
  ];

  return (
    <div className="teller analyst" data-testid="analyst-console">
      <aside className="rail">
        <h2>{tr("確認待ち", "To review")}</h2>
        <ul className="queue-list" role="tablist" aria-label={tr("キュー", "Queues")}>
          {rows.map(([k, text, n]) => (
            <li key={k}>
              <button type="button" role="tab" aria-selected={queue === k} className={queue === k ? "on" : ""} onClick={() => setQueue(k)}>
                <span>{text}</span>
                <span className="count">{n}</span>
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main className="main">
        {queue === "freezes" && (
          <FreezeQueue
            pending={pending}
            decided={freezes.filter((f) => f.status !== "pending")}
            error={freezeError}
            onDone={loadFreezes}
            onOutreach={(caseId, items) => setOutreachByCase((m) => ({ ...m, [caseId]: items }))}
          />
        )}
        {queue === "playbooks" && <PlaybookQueue items={playbooks} error={playbookError} onDone={loadPlaybooks} />}
        {queue === "outreach" && (
          <OutreachList approved={approved} local={outreachByCase} onCount={(caseId, n) => setOutreachCounts((m) => (m[caseId] === n ? m : { ...m, [caseId]: n }))} />
        )}
      </main>
    </div>
  );
}

// ------------------------------------------------------------------ playbooks

function PlaybookQueue({ items, error, onDone }: { items: Playbook[]; error: string | null; onDone: () => void }) {
  const { tr } = useLang();
  const { identity } = useAuth();
  return (
    <section data-testid="playbook-queue">
      <h2>{tr("承認待ちのプレイブック", "Playbooks waiting for approval")}</h2>
      <p className="muted">{tr("承認されたプレイブックだけが窓口の副操縦に届きます。", "Only approved playbooks reach the counter copilot.")}</p>
      {error && (
        <p className="error">
          {tr("プレイブックを読み込めませんでした。", "Couldn't load the playbooks.")} {error}
        </p>
      )}
      {items.length === 0 && !error && <p className="muted">{tr("承認待ちはありません。", "Nothing is waiting.")}</p>}
      {items.map((p) => (
        <PlaybookRow key={p.id} pb={p} analystId={identity.user} onDone={onDone} />
      ))}
    </section>
  );
}

function PlaybookRow({ pb, analystId, onDone }: { pb: Playbook; analystId: string; onDone: () => void }) {
  const { tr } = useLang();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = async (status: "approved" | "rejected") => {
    setBusy(true);
    setError(null);
    try {
      await api.patchPlaybook(pb.id, { status, analyst_id: analystId, note: note.trim() || null });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <article className="case-cols playbook" data-testid={`playbook-${pb.id}`}>
      <div className="col-talk">
        <div>
          <h3>{pb.name}</h3>
          <p className="small muted">
            {pb.hypothesis} · v{pb.version}
            {(pb.contact_channels ?? []).length > 0 ? ` · ${(pb.contact_channels ?? []).join(", ")}` : ""}
          </p>
        </div>
        <div>
          <h4>{tr("出典", "Sources")}</h4>
          <ul className="plain">
            {pb.sources.map((s) => (
              <li key={s.url}>
                {s.publisher}, {tr("公表日", "published")} {s.published_at}
              </li>
            ))}
          </ul>
        </div>
        {(pb.script_phrases?.length ?? 0) > 0 && (
          <div>
            <h4>{tr("手口の文言", "Script phrases")}</h4>
            <p lang="ja">{pb.script_phrases!.join(" / ")}</p>
          </div>
        )}
        {(pb.question_bank?.questions?.length ?? 0) > 0 && (
          <div>
            <h4>{tr("質問バンク", "Question bank")}</h4>
            <ul className="plain">
              {pb.question_bank!.questions!.map((q) => (
                <li key={q.id}>
                  <span lang="ja">{q.ja}</span>
                  {q.en && <div className="gloss">EN: {q.en}</div>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div className="col-act">
        <section className="paper decision">
          <h3>{tr("あなたの判断", "Your decision")}</h3>
          <label className="field">
            {tr("メモ(任意)", "Note (optional)")}
            <input value={note} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="row">
            <button type="button" disabled={busy} onClick={() => act("approved")}>
              {tr("承認する", "Approve")}
            </button>
            <button type="button" className="quiet" disabled={busy} onClick={() => act("rejected")}>
              {tr("却下", "Reject")}
            </button>
          </div>
          {error && (
            <p className="error">
              {tr("保存できませんでした。もう一度お試しください。", "Couldn't save. Try again.")} {error}
            </p>
          )}
        </section>
      </div>
    </article>
  );
}

// ------------------------------------------------------------------ freeze requests

function FreezeQueue({
  pending,
  decided,
  error,
  onDone,
  onOutreach,
}: {
  pending: FreezeRequest[];
  decided: FreezeRequest[];
  error: string | null;
  onDone: () => void;
  onOutreach: (caseId: string, items: OutreachItem[]) => void;
}) {
  const { tr } = useLang();
  return (
    <section data-testid="freeze-queue">
      <h2>{tr("口座凍結の依頼", "Freeze requests")}</h2>
      {error && (
        <p className="error">
          {tr("依頼を読み込めませんでした。", "Couldn't load the requests.")} {error}
        </p>
      )}
      {pending.length === 0 && <p className="muted">{tr("判断待ちの依頼はありません。", "No requests are waiting.")}</p>}
      {pending.map((fr) => (
        <FreezeRow key={fr.freeze_id} fr={fr} onDone={onDone} onOutreach={onOutreach} />
      ))}
      {decided.length > 0 && (
        <div className="decided">
          <h3>{tr("判断済み", "Decided")}</h3>
          <ul className="plain">
            {decided.map((fr) => (
              <li key={fr.freeze_id}>
                <span className={`tag tag-${fr.status}`}>{fr.status === "approved" ? tr("承認", "approved") : tr("却下", "rejected")}</span> {fr.account_id} ·{" "}
                {fr.decided_by} · {fmtTime(fr.decided_at)}
                <div className="small muted">{fr.decision_rationale}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export function FreezeRow({
  fr,
  onDone,
  onOutreach,
}: {
  fr: FreezeRequest;
  onDone: () => void;
  onOutreach: (caseId: string, items: OutreachItem[]) => void;
}) {
  const { tr } = useLang();
  const { identity } = useAuth();
  const [kase, setKase] = useState<Case | null>(null);
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.getCase(fr.case_id).then(setKase).catch(() => {});
  }, [fr.case_id]);
  useEffect(() => {
    if (kase?.customer_ref) api.getCustomer(kase.customer_ref).then(setCustomer).catch(() => {});
  }, [kase?.customer_ref]);

  const decide = async (decision: "approve" | "reject") => {
    if (!rationale.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.postFreezeDecision(fr.case_id, { decision, analyst_id: identity.user, rationale: rationale.trim() });
      if (res.outreach.length) onOutreach(fr.case_id, res.outreach);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const others = kase?.card?.claims.find((c) => c.kind === "fact" && c.source.field === "distinct_other_payers_7d");
  const othersCount = others && others.kind === "fact" ? Number(others.source.value) : null;

  return (
    <article className="freeze-row" data-testid={`freeze-${fr.freeze_id}`}>
      {kase?.card && <RiskBand card={kase.card} language={kase.language ?? "ja"} name={customer?.display_name_ja ?? null} status={kase.status} showHoldLine={false} />}
      <div className="case-cols">
        <div className="col-talk">
          <div>
            <h3>{tr("送金先口座の凍結", "Freeze the payee account")}</h3>
            <p>
              {tr("対象の口座", "Account")}: <strong>{fr.account_id}</strong>
              {othersCount != null && (
                <>
                  {" "}
                  · {tr(`直近7日に他の${othersCount}人が送金`, `${othersCount} other customers paid it this week`)}
                </>
              )}
            </p>
            <p className="small muted">
              {tr("依頼者", "Requested by")} {fr.requested_by}, {fmtTime(fr.requested_at)}
            </p>
            <p>{fr.reason}</p>
          </div>
          {kase?.card && <Why card={kase.card} caseId={kase.case_id} />}
        </div>
        <div className="col-act">
          <section className="paper decision">
            <h3>{tr("あなたの判断", "Your decision")}</h3>
            <label className="field">
              {tr("判断の理由(必須、記録されます)", "Rationale (required, logged)")}
              <textarea rows={3} value={rationale} onChange={(e) => setRationale(e.target.value)} aria-label={tr("判断の理由", "Decision rationale")} />
            </label>
            <div className="row">
              <button type="button" className="danger" disabled={busy || !rationale.trim()} onClick={() => decide("approve")}>
                {tr("凍結を承認", "Approve freeze")}
              </button>
              <button type="button" className="quiet" disabled={busy || !rationale.trim()} onClick={() => decide("reject")}>
                {tr("却下", "Reject")}
              </button>
            </div>
            {!rationale.trim() && <p className="small muted">{tr("理由を入力すると判断できます。", "Write a rationale to decide.")}</p>}
            {error && (
              <p className="error">
                {tr("判断を保存できませんでした。もう一度お試しください。", "Couldn't save the decision. Try again.")} {error}
              </p>
            )}
          </section>
        </div>
      </div>
    </article>
  );
}

// ------------------------------------------------------------------ outreach

function OutreachList({
  approved,
  local,
  onCount,
}: {
  approved: FreezeRequest[];
  local: Record<string, OutreachItem[]>;
  onCount: (caseId: string, n: number) => void;
}) {
  const { tr } = useLang();
  return (
    <section data-testid="outreach">
      <h2>{tr("連絡対象", "Outreach")}</h2>
      <p className="muted">{tr("凍結した口座に振り込んだ、ほかのお客様です。", "Other customers who paid the frozen account.")}</p>
      {approved.length === 0 && Object.keys(local).length === 0 && <p className="muted">{tr("凍結が承認されると表示されます。", "They appear once a freeze is approved.")}</p>}
      {approved.map((fr) => (
        <OutreachForCase key={fr.freeze_id} fr={fr} local={local[fr.case_id]} onCount={onCount} />
      ))}
    </section>
  );
}

function OutreachForCase({ fr, local, onCount }: { fr: FreezeRequest; local?: OutreachItem[]; onCount: (caseId: string, n: number) => void }) {
  const { tr } = useLang();
  const [fetched, setFetched] = useState<OutreachItem[] | null>(null);
  // GET /cases/{id}/outreach is the source of truth; re-read when `outreach_ready` arrives.
  const refetch = useCallback(() => {
    api.getOutreach(fr.case_id).then(setFetched).catch(() => {});
  }, [fr.case_id]);
  useEffect(refetch, [refetch]);
  useCaseEvents(fr.case_id, (e) => e.type === "outreach_ready" && refetch());
  const items = fetched && fetched.length ? fetched : (local ?? fetched ?? []);
  useEffect(() => onCount(fr.case_id, items.length), [fr.case_id, items.length, onCount]);
  return (
    <article className="outreach-case">
      <h3>
        {fr.account_id}
      </h3>
      <p>
        <strong data-testid="outreach-count">{items.length}</strong> {tr("名のお客様", "other customers")}
      </p>
      <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>{tr("お客様", "Payer")}</th>
            <th className="num">{tr("合計金額", "Amount")}</th>
            <th>{tr("最終振込日", "Last paid")}</th>
            <th>{tr("状況", "Status")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((o) => (
            <tr key={o.customer_ref}>
              <td>
                <span lang="ja">{o.display_name_ja}</span>
                <div className="small muted">{o.account_id}</div>
              </td>
              <td className="num">{yen(o.total_jpy)}</td>
              <td>{fmtTime(o.last_paid_at)}</td>
              <td>{tr("未連絡", "Not contacted")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </article>
  );
}
