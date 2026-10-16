import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import * as api from "../api/client";
import type { CaseSummary } from "../api/types";
import { CaseView } from "../components/CaseView";
import { TransferForm } from "../components/TransferForm";
import { RISK_LABEL, label, useLang, yen } from "../i18n";

/**
 * Teller console: one list ("Today") on the left, newest first, and the open case on the right. A new
 * alert is simply a new row at the top, with its risk word and a 4px bar in the risk colour.
 * Names come from core banking, fetched once per customer and cached here (the open case fetches its own).
 */
export function TellerConsole() {
  const { caseId } = useParams();
  const nav = useNavigate();
  const { lang, tr } = useLang();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [announce, setAnnounce] = useState("");
  const known = useRef<Set<string> | null>(null);
  const asked = useRef<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const list = await api.listCases();
      list.sort((a, b) => b.opened_at.localeCompare(a.opened_at));
      setCases(list);
      if (known.current === null) {
        known.current = new Set(list.map((c) => c.case_id));
      } else {
        const added = list.filter((c) => !known.current!.has(c.case_id));
        list.forEach((c) => known.current!.add(c.case_id));
        if (added.length) {
          setFresh((cur) => new Set([...cur, ...added.map((c) => c.case_id)]));
          setAnnounce(`${tr("新しいアラート", "New alert")}: ${yen(added[0].amount_jpy)}`);
        }
      }
    } catch {
      /* the list retries on the next tick */
    }
  }, [tr]);

  useEffect(() => {
    void load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    for (const c of cases) {
      if (asked.current.has(c.customer_ref)) continue;
      asked.current.add(c.customer_ref);
      api
        .getCustomer(c.customer_ref)
        .then((cu) => setNames((n) => ({ ...n, [c.customer_ref]: cu.display_name_ja })))
        .catch(() => {});
    }
  }, [cases]);

  const nameOf = (c: CaseSummary) => names[c.customer_ref] ?? c.customer_ref;
  const word = (c: CaseSummary) => (c.risk_level ? label(RISK_LABEL, c.risk_level, lang) : tr("調査中", "Checking"));

  return (
    <div className="teller">
      <aside className="rail">
        <h2>{tr("本日", "Today")}</h2>
        <p className="sr-only" role="status">
          {announce}
        </p>
        <label className="rail-select field">
          <span className="sr-only">{tr("ケース", "Case")}</span>
          <select value={caseId ?? ""} onChange={(e) => e.target.value && nav(`/case/${e.target.value}`)} aria-label={tr("ケースを選ぶ", "Choose a case")}>
            <option value="">{tr("ケースを選ぶ", "Choose a case")}</option>
            {cases.map((c) => (
              <option key={c.case_id} value={c.case_id}>
                {nameOf(c)} {yen(c.amount_jpy)} {word(c)}
              </option>
            ))}
          </select>
        </label>
        <ul className="case-list" data-testid="case-list">
          {cases.length === 0 && <li className="muted small">{tr("ケースはありません", "No cases")}</li>}
          {cases.map((c) => (
            <li key={c.case_id} className={fresh.has(c.case_id) ? "fresh" : ""}>
              <NavLink
                to={`/case/${c.case_id}`}
                className={({ isActive }) => `risk-${c.risk_level ?? "low"}${isActive ? " active" : ""}`}
                onClick={() => setFresh((cur) => new Set([...cur].filter((x) => x !== c.case_id)))}
              >
                <span className="name">{nameOf(c)}</span>
                <span className="meta">
                  <span>{yen(c.amount_jpy)}</span>
                  <span className={c.risk_level ? `word-${c.risk_level}` : ""}>{word(c)}</span>
                </span>
              </NavLink>
            </li>
          ))}
        </ul>
        <TransferForm
          onCreated={(r) => {
            void load();
            if (r.case_id) nav(`/case/${r.case_id}`);
          }}
        />
      </aside>
      <main className="main">
        {caseId ? (
          <CaseView key={caseId} caseId={caseId} />
        ) : (
          <p className="empty">{tr("ケースは開かれていません。新しいアラートは左の一覧に表示されます。", "No case open. New alerts appear in the list on the left.")}</p>
        )}
      </main>
    </div>
  );
}
