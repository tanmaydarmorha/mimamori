import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../src/auth/Auth";
import { LangProvider } from "../src/i18n";
import { Phone } from "../src/pages/Phone";

class FakeWS {
  static last: FakeWS;
  static OPEN = 1;
  readyState = 1;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  binaryType = "";
  constructor(public url: string) {
    FakeWS.last = this;
    setTimeout(() => this.onopen?.(), 0);
  }
  send(s: string) {
    this.sent.push(s);
  }
  close() {
    this.onclose?.();
  }
  push(o: object) {
    this.onmessage?.({ data: JSON.stringify(o) });
  }
}

const notice = { call_id: "call-0007-1", to_phone_e164: "+819012345678", sent_at: "2026-10-13T11:50:00+09:00", text: "サンプル銀行 駅前支店です。お母様の件でご連絡しました。公開番号 03-1234-5678 に折り返しください。番号 4821", language: "ja", gloss_en: "This is Sample Bank. We are contacting you about your mother.", published_phone_e164: "+81312345678", case_code: "4821" };

beforeEach(() => {
  vi.stubGlobal("WebSocket", FakeWS);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [notice] }));
});
afterEach(() => vi.unstubAllGlobals());

async function dialIn(code: string) {
  render(
    <LangProvider initial="ja">
      <AuthProvider initial={{ role: "teller", user: "t" }}>
        <Phone />
      </AuthProvider>
    </LangProvider>,
  );
  expect(await screen.findByTestId("notice")).toHaveTextContent("お母様の件");
  expect(screen.getByTestId("published-number")).toHaveTextContent("+81312345678");
  await userEvent.click(screen.getByRole("button", { name: /銀行に電話する/ }));
  await userEvent.click(screen.getByRole("button", { name: /ご連絡への折り返し/ }));
  for (const d of code) await userEvent.click(screen.getByRole("button", { name: d }));
  await userEvent.click(screen.getByRole("button", { name: "発信" }));
}

describe("simulated phone", () => {
  it("calls back with the number, menu choice and case code, then converses and ends on completed", async () => {
    await dialIn("4821");
    const ws = FakeWS.last;
    await waitFor(() => expect(ws.sent).toHaveLength(1));
    expect(JSON.parse(ws.sent[0])).toEqual({ type: "callback", caller_number: "+819012345678", menu_choice: "returning_a_call_about_a_case", case_code: "4821" });

    ws.push({ type: "verification", ok: true });
    ws.push({ type: "say", language: "ja", text: "こちらは自動音声のアシスタントです。この通話は録音されます。" });
    expect(await screen.findByText(/自動音声のアシスタント/)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("通話の発言"), "すぐ支店に行きます");
    await userEvent.click(screen.getByRole("button", { name: "送信" }));
    expect(JSON.parse(ws.sent[1])).toEqual({ type: "turn", text: "すぐ支店に行きます" });

    ws.push({ type: "say", language: "ja", text: "ありがとうございます。担当者に伝え、お待ちしております。" });
    ws.push({ type: "ended", reason: "completed" });
    expect(await screen.findByTestId("phone-ended")).toBeInTheDocument();
    expect(screen.queryByLabelText("通話の発言")).not.toBeInTheDocument();
  });

  it("shows nothing but a failure line when verification fails", async () => {
    await dialIn("0000");
    const ws = FakeWS.last;
    ws.push({ type: "verification", ok: false });
    ws.push({ type: "ended", reason: "verification_failed" });
    expect(await screen.findByTestId("phone-verify-failed")).toBeInTheDocument();
    expect(screen.getByTestId("phone-ended")).toBeInTheDocument();
  });

  it("has a language toggle, and a contact sample line fills the input without sending", async () => {
    await dialIn("4821");
    const ws = FakeWS.last;
    ws.push({ type: "verification", ok: true });
    ws.push({ type: "say", language: "ja", text: "こちらは自動音声のアシスタントです。" });
    await screen.findByText(/自動音声のアシスタント/);
    expect(screen.getByRole("group", { name: "language" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "娘: 母は大丈夫?" }));
    expect(screen.getByLabelText("通話の発言")).toHaveValue("母は大丈夫ですか？");
    expect(ws.sent).toHaveLength(1); // only the callback
    await userEvent.click(screen.getByRole("button", { name: "EN" }));
    expect(screen.getByRole("button", { name: "Daughter: is my mother safe?" })).toBeInTheDocument();
  });

  it("shows the notice text and, in English mode, its gloss; an English call shows no gloss", async () => {
    const { unmount } = render(
      <LangProvider initial="en">
        <AuthProvider initial={{ role: "teller", user: "t" }}>
          <Phone />
        </AuthProvider>
      </LangProvider>,
    );
    expect(await screen.findByTestId("notice")).toHaveTextContent("お母様の件");
    expect(screen.getByTestId("gloss")).toHaveTextContent("EN: This is Sample Bank.");
    unmount();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [{ ...notice, text: "This is Sample Bank. Please call us.", language: "en", gloss_en: null }] }));
    render(
      <LangProvider initial="en">
        <AuthProvider initial={{ role: "teller", user: "t" }}>
          <Phone />
        </AuthProvider>
      </LangProvider>,
    );
    const n = await screen.findByTestId("notice");
    expect(n).toHaveTextContent("Please call us.");
    expect(n.querySelector("p")).toHaveAttribute("lang", "en");
    expect(screen.queryByTestId("gloss")).not.toBeInTheDocument();
  });

  it("renders say text with its lang and, in EN mode, the gloss", async () => {
    render(
      <LangProvider initial="en">
        <AuthProvider initial={{ role: "teller", user: "t" }}>
          <Phone />
        </AuthProvider>
      </LangProvider>,
    );
    await screen.findByTestId("notice");
    await userEvent.click(screen.getByRole("button", { name: /Call the bank/ }));
    await userEvent.click(screen.getByRole("button", { name: /ご連絡への折り返し/ }));
    for (const d of "4821") await userEvent.click(screen.getByRole("button", { name: d }));
    await userEvent.click(screen.getByRole("button", { name: "Call" }));
    const ws = FakeWS.last;
    await waitFor(() => expect(ws.sent).toHaveLength(1));
    ws.push({ type: "verification", ok: true });
    ws.push({ type: "say", language: "ja", text: "こちらは自動音声のアシスタントです。", gloss_en: "This is an automated voice assistant." });
    ws.push({ type: "say", language: "en", text: "Thank you. I will let our staff know." });
    expect(await screen.findByText("Thank you. I will let our staff know.")).toHaveAttribute("lang", "en");
    expect(screen.getByText("EN: This is an automated voice assistant.")).toBeInTheDocument();
    expect(screen.getAllByTestId("gloss")).toHaveLength(1);
  });

  it("offers the English contact lines on an English call", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [{ ...notice, text: "This is Sample Bank.", language: "en", gloss_en: null }] }));
    render(
      <LangProvider initial="en">
        <AuthProvider initial={{ role: "teller", user: "t" }}>
          <Phone />
        </AuthProvider>
      </LangProvider>,
    );
    await screen.findByTestId("notice");
    await userEvent.click(screen.getByRole("button", { name: /Call the bank/ }));
    await userEvent.click(screen.getByRole("button", { name: /ご連絡への折り返し/ }));
    for (const d of "4821") await userEvent.click(screen.getByRole("button", { name: d }));
    await userEvent.click(screen.getByRole("button", { name: "Call" }));
    const ws = FakeWS.last;
    await waitFor(() => expect(ws.sent).toHaveLength(1));
    ws.push({ type: "verification", ok: true });
    ws.push({ type: "say", language: "en", text: "This is an automated voice assistant." });
    await screen.findByText("This is an automated voice assistant.");
    await userEvent.click(screen.getByRole("button", { name: "Daughter: how much?" }));
    expect(screen.getByLabelText("Call speech")).toHaveValue("How much is the transfer?");
    expect(screen.queryByRole("button", { name: "Daughter: what happened?" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Daughter: is my mother safe?" })).toBeInTheDocument();
  });
});
