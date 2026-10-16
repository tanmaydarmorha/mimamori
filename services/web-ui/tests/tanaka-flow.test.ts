// @vitest-environment node
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import WebSocket from "ws";
import * as api from "../src/api/client";
import { holdWindow, startMock } from "../mock-server/server.mjs";

/** The whole Tanaka flow through the web UI's API client against the mock server (docs/architecture/c4-dynamic-tanaka.md). */
let mock: Awaited<ReturnType<typeof startMock>>;
beforeAll(async () => {
  mock = await startMock({ port: 0, delayMs: 0, host: "127.0.0.1" });
  api.setApiBase(`${mock.url}/api`);
});
afterAll(() => mock.close());

const until = async <T>(fn: () => Promise<T | undefined | false>, ms = 3000): Promise<T> => {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error("timeout");
    await new Promise((r) => setTimeout(r, 20));
  }
};

function phone(messages: object[]): Promise<{ say: string[]; ok: boolean | null; ended: string | null }> {
  return new Promise((resolve) => {
    const ws = new WebSocket(`${mock.url.replace("http", "ws")}/api/conversation/phone`);
    const out = { say: [] as string[], ok: null as boolean | null, ended: null as string | null };
    let i = 0;
    ws.on("open", () => ws.send(JSON.stringify(messages[i++])));
    ws.on("message", (d) => {
      const m = JSON.parse(d.toString());
      if (m.type === "say") out.say.push(m.text);
      if (m.type === "verification") out.ok = m.ok;
      if (m.type === "ended") out.ended = m.reason;
      if (m.type !== "ended" && i < messages.length) ws.send(JSON.stringify(messages[i++]));
    });
    ws.on("close", () => resolve(out));
  });
}

describe("hold window", () => {
  const at = (s: string) => Date.parse(s);
  const ends = (s: string, o = {}) => new Date(holdWindow(at(s), o).ends_at).toISOString();
  it("matches the api-contracts test vectors", () => {
    expect(ends("2026-10-13T09:30:00+09:00")).toBe("2026-10-13T06:00:00.000Z"); // Tue 09:30 -> Tue 15:00 JST
    expect(ends("2026-10-13T11:50:00+09:00")).toBe("2026-10-14T02:50:00.000Z"); // -> Wed 11:50 (cap)
    expect(ends("2026-10-13T14:30:00+09:00")).toBe("2026-10-14T05:30:00.000Z"); // -> Wed 14:30 (cap)
    expect(ends("2026-10-16T14:30:00+09:00")).toBe("2026-10-17T05:30:00.000Z"); // Fri -> Sat 14:30 (cap)
    expect(ends("2026-10-13T14:30:00+09:00", { extend: false })).toBe("2026-10-13T09:30:00.000Z"); // Tue 18:30
  });
});

describe("Tanaka flow", () => {
  it("runs alert -> card -> pause recommendation -> decision -> notice -> verified callback -> freeze -> six others", async () => {
    // an ordinary transfer is not alerted
    const small = await api.postTransfer({ customer_ref: "cust-tanaka-0001", account_id: "acct-tanaka-0001", channel: "counter", kind: "transfer", amount_jpy: 50000, payee: { name_kana: "テスト", relation: "other_bank" } });
    expect(small.status).toBe("executed");
    expect(small.case_id).toBeNull();

    // step 3: counter transfer -> alert
    const t = await api.postTransfer({ customer_ref: "cust-tanaka-0001", account_id: "acct-tanaka-0001", channel: "counter", kind: "transfer", amount_jpy: 3_000_000, payee: { name_kana: "カ）ミライケンセツ", relation: "same_bank", account_id: "acct-mule-0001" } });
    expect(t.status).toBe("pending_alert");
    const id = t.case_id!;
    expect((await api.listCases()).map((c) => c.case_id)).toContain(id);

    // step 4: card with the first approved question
    const first = (await until(async () => (await api.getCase(id)).card))!;
    expect(first.risk.level).toBe("elevated");
    expect(first.risk.pause_recommended).toBe(false);
    expect(first.next_question?.ja_filled).toBeTruthy();

    // step 5: turns
    const c1 = await api.postTurn(id, { speaker: "customer", text: "リフォーム代なんです" });
    expect(c1.card!.claims.some((c) => c.kind === "quote" && c.indicator === "cover_story")).toBe(true);
    await api.postTurn(id, { speaker: "teller", text: "どのような工事ですか" });
    const c2 = await api.postTurn(id, { speaker: "customer", text: "警察の人から電話があってね、誰にも言うなって言われてるの" });
    expect(c2.turn_id).toBe("c2");
    expect(c2.card!.risk.level).toBe("high");
    expect(c2.card!.risk.pause_recommended).toBe(true);
    expect((await api.getCase(id)).hold_line?.ja).toContain("警察や金融庁");
    expect(c2.card!.risk.fired[0].condition).toBe("H1:impersonation+secrecy");
    expect(JSON.stringify(c2.card)).not.toMatch(/probab|likelihood|confidence/i);

    // quotes are verbatim substrings of the customer's turn
    for (const q of c2.card!.claims) if (q.kind === "quote" && q.source.turn_id === "c2") expect("警察の人から電話があってね、誰にも言うなって言われてるの").toContain(q.source.text);

    // step 6: pause needs a basis (contract: 422); then a pause places the hold
    api.setIdentity({ role: "teller", user: "teller-01" });
    await expect(api.postDecision(id, { action: "pause", rationale: "x", teller_id: "teller-01" })).rejects.toMatchObject({ status: 422 });
    const dec = await api.postDecision(id, { action: "pause", basis: "advance_wishes", rationale: "impersonation + secrecy", teller_id: "teller-01" });
    expect(dec.status).toBe("paused");
    expect(dec.hold!.overrides).toContain("after_contact_reached");
    expect(dec.warnings).toEqual([]);

    // police summary: name and title required
    await expect(api.postPoliceSummary(id, { officer_name: "", officer_title: "", requested_items: ["amount"], teller_id: "teller-01" })).rejects.toMatchObject({ status: 422 });
    const ps = await api.postPoliceSummary(id, { officer_name: "山田 太郎", officer_title: "巡査部長", requested_items: ["amount", "indicators"], teller_id: "teller-01" });
    expect(ps.text_ja).toContain("山田 太郎");
    expect(Object.keys(ps.items).sort()).toEqual(["amount", "indicators"]);

    // step 7: notice reveals nothing; wrong number / wrong code never verify
    const [notice] = await until(async () => {
      const n = await api.listNotices("+819012345678");
      return n.length ? n : false;
    });
    expect(notice.text).not.toMatch(/3,?000,?000|三百万|300万|acct-/);
    expect(notice.published_phone_e164).toBe("+81312345678");

    const wrongCode = await phone([{ type: "callback", caller_number: "+819012345678", menu_choice: "returning_a_call_about_a_case", case_code: "0000" }]);
    expect(wrongCode).toMatchObject({ ok: false, ended: "verification_failed" });
    const wrongNumber = await phone([{ type: "callback", caller_number: "+819099999999", menu_choice: "returning_a_call_about_a_case", case_code: notice.case_code }]);
    expect(wrongNumber).toMatchObject({ ok: false, ended: "verification_failed" });
    expect((await api.getCase(id)).verification_failed).toBe(true);

    const call = await phone([
      { type: "callback", caller_number: "+819012345678", menu_choice: "returning_a_call_about_a_case", case_code: notice.case_code },
      { type: "turn", text: "母は今いくら持っていますか" },
      { type: "turn", text: "すぐ支店に行きます" },
    ]);
    expect(call.ok).toBe(true);
    expect(call.say[0]).toContain("自動音声");
    expect(call.say[1]).toContain("お伝えできかねます");
    expect(call.say.join("")).not.toMatch(/円|万/);
    expect(call.ended).toBe("completed");

    const after = await api.getCase(id);
    expect(after.contact_view).toMatchObject({ nature: "information", reached: true, concerned: true, coming_to_branch: true });

    // step 8: freeze request, analyst role only
    const fr = await api.postFreezeRequest(id, { requested_by: "teller-01", reason: "7 payers in 7 days, account 4 days old" });
    expect(fr.status).toBe("pending");
    await expect(api.listFreezeRequests()).rejects.toMatchObject({ status: 403 }); // teller
    api.setIdentity({ role: "analyst", user: "analyst-01" });
    expect((await api.listFreezeRequests("pending")).map((f) => f.freeze_id)).toContain(fr.freeze_id);
    await expect(api.postFreezeDecision(id, { decision: "approve", analyst_id: "analyst-01", rationale: "" })).rejects.toMatchObject({ status: 422 });
    const fd = await api.postFreezeDecision(id, { decision: "approve", analyst_id: "analyst-01", rationale: "evidence card reviewed" });
    expect(fd.freeze?.status).toBe("frozen");
    expect(fd.outreach).toHaveLength(6);
    expect(await api.getOutreach(id)).toHaveLength(6);

    // playbooks: analyst approves the pending one
    const [pb] = await api.listPlaybooks("pending");
    const patched = await api.patchPlaybook(pb.id, { status: "approved", analyst_id: "analyst-01" });
    expect(patched.status).toBe("approved");
    api.setIdentity({ role: "teller", user: "teller-01" });
    await expect(api.patchPlaybook(pb.id, { status: "rejected", analyst_id: "x" })).rejects.toMatchObject({ status: 403 });
  });

  it("the SSE stream replays and then streams events", async () => {
    const { EventSource } = await import("eventsource");
    const t = await api.postTransfer({ customer_ref: "cust-tanaka-0001", account_id: "acct-tanaka-0001", channel: "counter", kind: "transfer", amount_jpy: 2_000_000, payee: { name_kana: "カ）ミライケンセツ", relation: "same_bank" } });
    const id = t.case_id!;
    const types: string[] = [];
    const es = new EventSource(`${mock.url}/api/case/cases/${id}/events`);
    for (const ty of ["case_opened", "card_updated", "transcript_turn"]) es.addEventListener(ty, (e) => types.push(JSON.parse((e as MessageEvent).data).type));
    await until(async () => types.includes("card_updated"));
    await api.postTurn(id, { speaker: "customer", text: "こんにちは" });
    await until(async () => types.includes("transcript_turn"));
    es.close();
    expect(types[0]).toBe("case_opened");
  });
});
