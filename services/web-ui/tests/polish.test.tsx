import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import * as api from "../src/api/client";
import type { FreezeRequest, TransferResponse } from "../src/api/types";
import { CASE_EVENT_TYPES } from "../src/api/types";
import { AuthProvider } from "../src/auth/Auth";
import { TransferForm } from "../src/components/TransferForm";
import { CASE_EVENT_LABEL, LangProvider, label } from "../src/i18n";
import { FreezeRow } from "../src/pages/AnalystConsole";
import { tanakaCase } from "../src/test/fixtures";

vi.mock("../src/api/client", async (orig) => ({
  ...(await orig<typeof import("../src/api/client")>()),
  getCase: vi.fn(),
  getCustomer: vi.fn().mockResolvedValue({ display_name_ja: "田中 花子" }),
  postTransfer: vi.fn(),
}));

const fr: FreezeRequest = {
  freeze_id: "fz-1",
  case_id: tanakaCase.case_id,
  account_id: "acct-mule-0001",
  requested_by: "teller-01",
  requested_at: "2026-10-16T02:00:00Z",
  reason: "7 payers in 7 days",
  status: "pending",
};

describe("WI-010 polish", () => {
  it.each([
    ["en", /paused/i],
    ["ja", /一時停止中/],
  ] as const)("freeze row for a paused case shows the paused wording (%s)", async (lang, re) => {
    vi.mocked(api.getCase).mockResolvedValue({ ...tanakaCase, status: "paused" });
    render(
      <LangProvider initial={lang}>
        <AuthProvider>
          <FreezeRow fr={fr} onDone={() => {}} onOutreach={() => {}} />
        </AuthProvider>
      </LangProvider>,
    );
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(re));
    expect(screen.getByRole("status")).not.toHaveTextContent(/recommended|を推奨/);
  });

  it.each([
    ["en", { transfer_id: "tr-1", status: "pending_alert", scoring: "alert", case_id: "case-1" }, "Alert raised. The case is open."],
    ["ja", { transfer_id: "tr-1", status: "pending_alert", scoring: "alert", case_id: "case-1" }, "アラートが出ました。ケースを開きました。"],
    ["en", { transfer_id: "tr-2", status: "executed", scoring: "allow" }, "Nothing unusual. The transfer was accepted."],
    ["ja", { transfer_id: "tr-2", status: "executed", scoring: "allow" }, "問題は見つかりませんでした。振込を受け付けました。"],
    ["en", { transfer_id: "tr-3", status: "executed", scoring: "unavailable" }, "The check was unavailable, so the transfer went ahead under existing controls."],
    ["ja", { transfer_id: "tr-3", status: "executed", scoring: "unavailable" }, "確認ができなかったため、通常の手続きで受け付けました。"],
  ] as const)("transfer form closes after submit and says one plain sentence (%s)", async (lang, resp, text) => {
    vi.mocked(api.postTransfer).mockResolvedValue(resp as unknown as TransferResponse);
    const onCreated = vi.fn();
    render(
      <LangProvider initial={lang}>
        <AuthProvider>
          <TransferForm onCreated={onCreated} />
        </AuthProvider>
      </LangProvider>,
    );
    const details = screen.getByTestId("transfer-form") as HTMLDetailsElement;
    await userEvent.click(details.querySelector("summary")!);
    await waitFor(() => expect(details.open).toBe(true));
    await userEvent.click(details.querySelector("button[type=submit]")!);
    await waitFor(() => expect(screen.getByTestId("transfer-result")).toHaveTextContent(text));
    expect(screen.getByTestId("transfer-result").textContent).toBe(text);
    expect(details.open).toBe(false);
    expect(onCreated).toHaveBeenCalledWith(resp);
  });

  it("every case event type has a ja and an en label; unknown types fall back to the code", () => {
    for (const t of CASE_EVENT_TYPES) {
      expect(CASE_EVENT_LABEL[t]?.[0], t).toBeTruthy();
      expect(CASE_EVENT_LABEL[t]?.[1], t).toBeTruthy();
      expect(label(CASE_EVENT_LABEL, t, "en")).not.toBe(t);
    }
    expect(label(CASE_EVENT_LABEL, "something_new", "ja")).toBe("something_new");
  });
});
