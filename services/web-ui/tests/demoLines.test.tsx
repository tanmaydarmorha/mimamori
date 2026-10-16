import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TurnPanel } from "../src/components/TurnPanel";
import { EvidenceCard } from "../src/components/EvidenceCard";
import { glossFor } from "../src/demoLines";
import { LangProvider } from "../src/i18n";
import { tanakaCard } from "../src/test/fixtures";

const POLICE = "警察の人から電話があってね、誰にも言うなって言われてるの";
const transcript = [{ turn_id: "c1", speaker: "customer" as const, text: "リフォーム代なんです", at: "2026-10-13T11:42:00+09:00" }];
const panel = (lang: "ja" | "en", onSend = vi.fn()) =>
  render(
    <LangProvider initial={lang}>
      <TurnPanel caseId="case-1" transcript={transcript} speechOn={false} onSend={onSend} />
    </LangProvider>,
  );

describe("glossFor", () => {
  it("finds an exact line, a quote inside one line, and nothing for unknown text", () => {
    expect(glossFor("リフォーム代なんです")).toBe("It's for my renovation.");
    expect(glossFor("誰にも言うなって言われてるの")).toBe("The police called me and told me not to tell anyone.");
    expect(glossFor("今日はいい天気ですね")).toBeUndefined();
    expect(glossFor("")).toBeUndefined();
  });
  it("returns nothing when the text sits inside more than one line", () => {
    expect(glossFor("です")).toBeUndefined(); // in two customer lines
  });
});

describe("TurnPanel sample lines", () => {
  it("fills the input with the Japanese and does not send", async () => {
    const onSend = vi.fn();
    panel("en", onSend);
    await userEvent.click(screen.getByRole("button", { name: "Customer: police called, keep it secret" }));
    expect(screen.getByLabelText("Turn text")).toHaveValue(POLICE);
    expect(onSend).not.toHaveBeenCalled();
  });
  it("labels the buttons in Japanese in JA mode", () => {
    panel("ja");
    expect(screen.getByRole("button", { name: "お客様: リフォーム代" })).toBeInTheDocument();
  });
});

describe("English glosses", () => {
  it("shows the English under a known transcript turn in EN mode only", () => {
    const { unmount } = panel("en");
    expect(screen.getByTestId("gloss")).toHaveTextContent("EN: It's for my renovation.");
    expect(screen.getByText("リフォーム代なんです")).toBeInTheDocument(); // Japanese stays
    unmount();
    panel("ja");
    expect(screen.queryByTestId("gloss")).not.toBeInTheDocument();
    expect(screen.queryByText(/It's for my renovation/)).not.toBeInTheDocument();
  });
  it("glosses card quotes in EN mode", () => {
    render(
      <LangProvider initial="en">
        <EvidenceCard card={tanakaCard} />
      </LangProvider>,
    );
    expect(screen.getAllByTestId("gloss").length).toBeGreaterThan(0);
  });
});
