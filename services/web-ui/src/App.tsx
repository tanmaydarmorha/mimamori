import type { ReactNode } from "react";
import { Navigate, NavLink, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/Auth";
import { useLang } from "./i18n";
import { AnalystConsole } from "./pages/AnalystConsole";
import { Phone } from "./pages/Phone";
import { TellerConsole } from "./pages/TellerConsole";

/** Renders children only for `role`. Hiding the nav link is not enough: the route is guarded too. */
export function RequireRole({ role, children }: { role: "teller" | "analyst"; children: ReactNode }) {
  const { identity } = useAuth();
  const { tr } = useLang();
  if (identity.role !== role)
    return (
      <div className="forbidden" role="alert" data-testid="forbidden">
        <h2>{tr("権限がありません", "Not allowed")}</h2>
        <p className="muted">
          {tr(`この画面は ${role === "analyst" ? "分析担当" : "窓口担当"} 専用です。`, `This screen is for the ${role} role.`)}
        </p>
      </div>
    );
  return <>{children}</>;
}

function Shell() {
  const { identity, locked, setRole } = useAuth();
  const { lang, setLang, tr } = useLang();
  return (
    <div className="shell">
      <header className="topbar">
        <strong className="brand">見守り Mimamori</strong>
        <nav>
          {identity.role === "teller" && <NavLink to="/teller">{tr("窓口", "Counter")}</NavLink>}
          {identity.role === "analyst" && <NavLink to="/analyst">{tr("分析", "Analyst")}</NavLink>}
          <NavLink to="/phone" target="_blank">
            {tr("電話", "Phone")}
          </NavLink>
        </nav>
        <div className="spacer" />
        <div className="seg" role="group" aria-label="language">
          <button type="button" className={lang === "ja" ? "on" : ""} onClick={() => setLang("ja")}>
            日本語
          </button>
          <button type="button" className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>
            EN
          </button>
        </div>
        {locked ? (
          <span className="who" data-testid="identity">
            {identity.user} ({identity.role})
          </span>
        ) : (
          <div className="who">
            <span>{identity.user}</span>
            <details className="demo">
              <summary>{tr("デモ", "Demo")}</summary>
              <div className="demo-menu">
                <label className="field">
                  {tr("ロール(ローカル)", "Role (local)")}
                  <select value={identity.role} onChange={(e) => setRole(e.target.value as "teller" | "analyst")} aria-label={tr("ロール", "Role")}>
                    <option value="teller">teller</option>
                    <option value="analyst">analyst</option>
                  </select>
                </label>
              </div>
            </details>
          </div>
        )}
      </header>
      <Outlet />
    </div>
  );
}

function Home() {
  const { identity } = useAuth();
  return <Navigate to={identity.role === "analyst" ? "/analyst" : "/teller"} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/phone" element={<Phone />} />
      <Route element={<Shell />}>
        <Route index element={<Home />} />
        <Route
          path="/teller"
          element={
            <RequireRole role="teller">
              <TellerConsole />
            </RequireRole>
          }
        />
        <Route
          path="/case/:caseId"
          element={
            <RequireRole role="teller">
              <TellerConsole />
            </RequireRole>
          }
        />
        <Route
          path="/analyst"
          element={
            <RequireRole role="analyst">
              <AnalystConsole />
            </RequireRole>
          }
        />
        <Route path="*" element={<Home />} />
      </Route>
    </Routes>
  );
}
