import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Case } from "../src/api/types";
import { AuthProvider } from "../src/auth/Auth";
import { CaseView } from "../src/components/CaseView";
import { LangProvider } from "../src/i18n";
import { tanakaCase } from "../src/test/fixtures";

afterEach(() => vi.unstubAllGlobals());

function renderCase(initial: Case) {
  let current = initial;
  const calls: { method: string; url: string; body?: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, url, body });
      if (method === "PATCH" && url.endsWith("/language")) current = { ...current, language: body.language };
      const payload = url.includes("/customers/") ? { customer_ref: "cust-tanaka-0001", display_name_ja: "田中 圭子", display_name_kana: "", tenure_years: 12, branch_name_ja: "" } : current;
      return { ok: true, status: 200, json: async () => payload };
    }),
  );
  render(
    <LangProvider initial="en">
      <AuthProvider initial={{ role: "teller", user: "teller-01" }}>
        <CaseView caseId={initial.case_id} />
      </AuthProvider>
    </LangProvider>,
  );
  return calls;
}

describe("conversation language on the case view", () => {
  it("offers the selector before the first turn and PATCHes the choice", async () => {
    const calls = renderCase({ ...tanakaCase, transcript: [], language: "ja" });
    const select = await screen.findByLabelText("Conversation language");
    await userEvent.selectOptions(select, "en");
    await waitFor(() => expect(calls.find((c) => c.method === "PATCH")).toBeTruthy());
    expect(calls.find((c) => c.method === "PATCH")).toMatchObject({ body: { language: "en", actor: "teller-01" } });
    expect(calls.find((c) => c.method === "PATCH")!.url).toContain(`/cases/${tanakaCase.case_id}/language`);
  });

  it("replaces the selector with a read-only badge once there is a turn", async () => {
    renderCase({ ...tanakaCase, language: "en", transcript: [{ turn_id: "c1", speaker: "customer", text: "リフォーム代なんです", at: "2026-10-13T11:42:00+09:00" }] });
    const badge = await screen.findByTestId("language-badge");
    expect(badge).toHaveTextContent("English");
    expect(screen.queryByTestId("language-select")).not.toBeInTheDocument();
  });
});

describe("counter in an English case (WI-006)", () => {
  const withQuestion: Case = {
    ...tanakaCase,
    language: "en",
    transcript: [],
    card: { ...tanakaCase.card!, next_question: { question_id: "q.fake_police.what_said", ja_filled: "お電話の相手の方は、どのようなお話をされていましたか。", en_filled: "What did the person on the phone say?" } },
  };

  it("offers the English customer lines, not the Japanese ones", async () => {
    renderCase(withQuestion);
    expect(await screen.findByRole("button", { name: "Customer: home renovation" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Customer: it's for renovation" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Customer: police called, keep it secret" }));
    expect(screen.getByLabelText("Turn text")).toHaveValue("The police called me and told me not to tell anyone, not even my family.");
  });

  it("shows the English question first, and Say this fills the teller input without sending", async () => {
    const calls = renderCase(withQuestion);
    const q = await screen.findByTestId("next-question");
    const [first, second] = Array.from(q.querySelectorAll("p"));
    expect(first).toHaveTextContent("What did the person on the phone say?");
    expect(first).toHaveAttribute("lang", "en");
    expect(second).toHaveTextContent("お電話の相手の方");
    await userEvent.click(screen.getByRole("button", { name: "Say this" }));
    expect(screen.getByLabelText("Turn text")).toHaveValue("What did the person on the phone say?");
    expect(screen.getByRole("radio", { name: "Teller" })).toBeChecked();
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("a Japanese case shows the Japanese question first and the Japanese lines", async () => {
    renderCase({ ...withQuestion, language: "ja" });
    const q = await screen.findByTestId("next-question");
    expect(q.querySelector("p")).toHaveTextContent("お電話の相手の方");
    expect(screen.getByRole("button", { name: "Customer: it's for renovation" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Say this" }));
    expect(screen.getByLabelText("Turn text")).toHaveValue("お電話の相手の方は、どのようなお話をされていましたか。");
  });
});
