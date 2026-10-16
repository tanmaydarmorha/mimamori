import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import type { DecisionResponse, EvidenceCard as Card, PoliceSummaryResponse } from "../src/api/types";
import { AuthProvider } from "../src/auth/Auth";
import { DecisionPanel } from "../src/components/DecisionPanel";
import { EvidenceCard } from "../src/components/EvidenceCard";
import { PolicePanel } from "../src/components/PolicePanel";
import { LangProvider } from "../src/i18n";
import { tanakaCard, tanakaCase } from "../src/test/fixtures";

const wrap = (ui: React.ReactElement, lang: "ja" | "en" = "en") => render(<LangProvider initial={lang}>{ui}</LangProvider>);

describe("EvidenceCard", () => {
  it("shows facts, quotes, hypotheses, the question and the claims that fired, with no probability numbers", () => {
    const { container } = wrap(<EvidenceCard card={tanakaCard} holdLine={{ id: "h.fake_police.real_police", ja: "警察や金融庁が、お電話でお金の移動をお願いすることはございません。" }} />);
    expect(screen.getByTestId("risk-banner")).toHaveAttribute("data-level", "high");
    expect(screen.getByText(/pause recommended/i)).toBeInTheDocument();
    expect(screen.getByTestId("next-question")).toHaveTextContent("お電話の相手の方は、どのようなお話をされていましたか。");
    expect(screen.getByTestId("hold-line")).toHaveTextContent("警察や金融庁");
    expect(screen.getByText(/opened 4 days ago/)).toBeInTheDocument();
    expect(screen.getByText(/警察の人から電話があってね/)).toBeInTheDocument();
    // both hold-rule claims are shown as the reason it fired
    expect(screen.getByText("H1:impersonation+secrecy")).toBeInTheDocument();
    // inferences are labelled as hypotheses
    const inf = screen.getByTestId("inferences");
    expect(inf.querySelectorAll(".tag-hyp")).toHaveLength(2);

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/%|％/);
    expect(text).not.toMatch(/\b0\.\d+/);
    expect(text).not.toMatch(/probab|likelihood|confidence|確率|可能性/i);
  });

  it("never renders a model-supplied number even if one sneaks onto a claim", () => {
    const tainted = structuredClone(tanakaCard) as Card;
    for (const c of tainted.claims) Object.assign(c, { confidence: 0.93, probability: 0.87, likelihood: "87%" });
    Object.assign(tainted.risk, { probability: 0.91 });
    Object.assign(tainted.hypotheses[1], { likelihood: 0.66 });
    const { container } = wrap(<EvidenceCard card={tainted} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/0\.93|0\.87|0\.91|0\.66|87%/);
  });

  it("collapses dropped claims", async () => {
    const withDropped: Card = { ...tanakaCard, dropped: [{ claim: { id: "q9" }, reason: "quote_not_found" }] };
    wrap(<EvidenceCard card={withDropped} />);
    const details = screen.getByTestId("dropped") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details).toHaveTextContent("(1)");
    await userEvent.click(screen.getByText(/Dropped claims/));
    expect(details.open).toBe(true);
    expect(details).toHaveTextContent("quote_not_found");
  });
});

describe("DecisionPanel", () => {
  const response: DecisionResponse = { decision: { decision_id: "dec-1" }, status: "paused", warnings: [] } as unknown as DecisionResponse;

  it("will not pause without a basis and a rationale", async () => {
    const onDecide = vi.fn().mockResolvedValue(response);
    wrap(<DecisionPanel kase={tanakaCase} tellerId="teller-01" onDecide={onDecide} />);
    const go = screen.getByRole("button", { name: "Place pause" });
    expect(go).toBeDisabled();

    await userEvent.type(screen.getByLabelText("Rationale"), "Impersonation and secrecy in c4");
    expect(go).toBeDisabled(); // still no basis
    await userEvent.selectOptions(screen.getByLabelText("Basis"), "advance_wishes");
    expect(go).toBeEnabled();
    await userEvent.click(go);

    expect(onDecide).toHaveBeenCalledWith({
      action: "pause",
      basis: "advance_wishes",
      rationale: "Impersonation and secrecy in c4",
      teller_id: "teller-01",
    });
  });

  it("a whitespace-only rationale does not count", async () => {
    wrap(<DecisionPanel kase={tanakaCase} tellerId="teller-01" onDecide={vi.fn()} />);
    await userEvent.selectOptions(screen.getByLabelText("Basis"), "bank_policy");
    await userEvent.type(screen.getByLabelText("Rationale"), "   ");
    expect(screen.getByRole("button", { name: "Place pause" })).toBeDisabled();
  });

  it("shows the single-source warning but still lets the pause through", async () => {
    const onDecide = vi.fn().mockResolvedValue({ ...response, warnings: ["single_source_pause"] });
    wrap(<DecisionPanel kase={tanakaCase} tellerId="t" onDecide={onDecide} />);
    await userEvent.selectOptions(screen.getByLabelText("Basis"), "bank_policy");
    await userEvent.type(screen.getByLabelText("Rationale"), "worried");
    await userEvent.click(screen.getByRole("button", { name: "Place pause" }));
    expect(await screen.findByTestId("decision-warnings")).toHaveTextContent(/single-source pause/);
  });

  it("release needs a reason; the contact-reached override is locked until the contact is reached", async () => {
    wrap(<DecisionPanel kase={{ ...tanakaCase, status: "paused" }} tellerId="t" onDecide={vi.fn()} />);
    await userEvent.click(screen.getByLabelText("Release"));
    const opt = screen.getByRole("option", { name: /Customer override, contact reached/ });
    expect(opt).toBeDisabled();
    expect(screen.getByRole("button", { name: "Release the transfer" })).toBeDisabled();
  });

  it("manager review needs a manager and a different second confirmer", async () => {
    const onDecide = vi.fn().mockResolvedValue(response);
    wrap(<DecisionPanel kase={{ ...tanakaCase, status: "paused" }} tellerId="t" onDecide={onDecide} />);
    await userEvent.click(screen.getByLabelText("Release"));
    await userEvent.selectOptions(screen.getByLabelText("Release reason"), "manager_review_second_confirmation");
    await userEvent.type(screen.getByLabelText("Rationale"), "reviewed");
    const btn = screen.getByRole("button", { name: "Release the transfer" });
    expect(btn).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Manager ID"), "mgr-1");
    await userEvent.type(screen.getByLabelText(/Second confirmer/), "mgr-1");
    expect(btn).toBeDisabled(); // same person
    await userEvent.clear(screen.getByLabelText(/Second confirmer/));
    await userEvent.type(screen.getByLabelText(/Second confirmer/), "mgr-2");
    expect(btn).toBeEnabled();
  });
});

describe("PolicePanel", () => {
  const result: PoliceSummaryResponse = { summary_id: "ps-1", issued_at: "2026-10-13T12:00:00+09:00", officer_name: "山田", officer_title: "巡査部長", items: {}, text_ja: "要約テキスト" };

  it("requires officer name, title and at least one item", async () => {
    const onIssue = vi.fn().mockResolvedValue(result);
    wrap(<PolicePanel tellerId="teller-01" onIssue={onIssue} />);
    const go = screen.getByRole("button", { name: "Issue summary" });
    expect(go).toBeDisabled();

    await userEvent.click(screen.getByLabelText("Amount"));
    await userEvent.type(screen.getByLabelText("Officer name"), "山田 太郎");
    expect(go).toBeDisabled(); // no title yet
    await userEvent.type(screen.getByLabelText("Officer title"), "   ");
    expect(go).toBeDisabled(); // blank title
    await userEvent.clear(screen.getByLabelText("Officer title"));
    await userEvent.type(screen.getByLabelText("Officer title"), "巡査部長");
    expect(go).toBeEnabled();

    await userEvent.click(go);
    expect(onIssue).toHaveBeenCalledWith({
      officer_name: "山田 太郎",
      officer_title: "巡査部長",
      requested_items: ["amount"],
      teller_id: "teller-01",
    });
    expect(await screen.findByTestId("police-result")).toHaveTextContent("要約テキスト");
  });

  it("requires at least one requested item", async () => {
    wrap(<PolicePanel tellerId="t" onIssue={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Officer name"), "山田");
    await userEvent.type(screen.getByLabelText("Officer title"), "巡査");
    expect(screen.getByRole("button", { name: "Issue summary" })).toBeDisabled();
  });
});

describe("roles", () => {
  const renderApp = (role: "teller" | "analyst", path: string) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }));
    return render(
      <MemoryRouter initialEntries={[path]}>
        <LangProvider initial="en">
          <AuthProvider initial={{ role, user: `${role}-01` }}>
            <App />
          </AuthProvider>
        </LangProvider>
      </MemoryRouter>,
    );
  };

  it("hides the analyst console from a teller, in the nav and by route", async () => {
    renderApp("teller", "/analyst");
    expect(await screen.findByTestId("forbidden")).toBeInTheDocument();
    expect(screen.queryByTestId("analyst-console")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Analyst" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Counter" })).toBeInTheDocument();
  });

  it("shows the analyst console to an analyst and hides the teller console", async () => {
    renderApp("analyst", "/analyst");
    expect(await screen.findByTestId("analyst-console")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analyst" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Counter" })).not.toBeInTheDocument();
  });

  it("an analyst cannot open the teller console by URL", async () => {
    renderApp("analyst", "/teller");
    await waitFor(() => expect(screen.getByTestId("forbidden")).toBeInTheDocument());
  });

  it("the role switcher changes what is visible", async () => {
    renderApp("teller", "/teller");
    await userEvent.selectOptions(screen.getByLabelText("Role"), "analyst");
    expect(screen.queryByRole("link", { name: "Analyst" })).toBeInTheDocument();
  });
});
