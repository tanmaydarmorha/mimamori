import { useCallback, useEffect, useRef, useState } from "react";
import { listNotices, phoneSocketUrl } from "../api/client";
import { PHONE_MENU_RETURN_CALL, type Notice, type PhoneClientMessage, type PhoneServerMessage } from "../api/types";
import { useAuth } from "../auth/Auth";
import { playBase64Audio, speak, startMic, type MicHandle } from "../audio";
import { Gloss, SampleLines } from "../components/SampleLines";
import { useLang } from "../i18n";

/**
 * Simulated phone for the trusted contact (Yuki). Everything the contact reads or hears stays Japanese;
 * English appears beside it (labels via `tr`, "EN:" glosses for demo lines and fixed prompts). Flow: the notice arrives (it reveals nothing), she calls the PUBLISHED number
 * back, picks the menu item for returning a call about a case, keys the case code, and talks to the
 * automated assistant over `WS /phone` (typed, or voice when STT is on).
 */
const DEFAULT_NUMBER = "+819012345678"; // Yuki's number as locked in the (synthetic) wishes

type Stage = "home" | "menu" | "code" | "call";
interface Line {
  from: "agent" | "me" | "system";
  text: string;
  language?: "ja" | "en";
  gloss?: string | null;
}

export function Phone() {
  const { config } = useAuth();
  const { lang, setLang, tr } = useLang();
  const [stage, setStage] = useState<Stage>("home");
  const [myNumber, setMyNumber] = useState(DEFAULT_NUMBER);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [dialed, setDialed] = useState<string>("");
  const [callLang, setCallLang] = useState<"ja" | "en">("ja"); // the case language, from the notice and then each reply
  const [menu, setMenu] = useState<string>(PHONE_MENU_RETURN_CALL);
  const [code, setCode] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [ended, setEnded] = useState<string | null>(null);
  const [verified, setVerified] = useState<boolean | null>(null);
  const [text, setText] = useState("");
  const [voiceOut, setVoiceOut] = useState(true);
  const [micOn, setMicOn] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const mic = useRef<MicHandle | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    chatRef.current?.scrollTo?.({ top: chatRef.current.scrollHeight }); // keep the newest line in view
  }, [lines.length]);
  const voiceRef = useRef(voiceOut);
  voiceRef.current = voiceOut;

  // Notices for Yuki's number: poll while she is on the home screen.
  useEffect(() => {
    if (stage !== "home") return;
    let alive = true;
    const load = () =>
      listNotices(myNumber)
        .then((n) => alive && setNotices(n))
        .catch(() => {});
    void load();
    const t = setInterval(load, 2000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [stage, myNumber]);

  const stopMic = useCallback(() => {
    mic.current?.stop();
    mic.current = null;
    setMicOn(false);
  }, []);
  const hangup = useCallback(() => {
    stopMic();
    const s = ws.current;
    if (s && s.readyState === WebSocket.OPEN) s.send(JSON.stringify({ type: "hangup" } satisfies PhoneClientMessage));
    s?.close();
    ws.current = null;
  }, [stopMic]);
  useEffect(() => hangup, [hangup]);

  function connect() {
    setLines([]);
    setEnded(null);
    setVerified(null);
    const s = new WebSocket(phoneSocketUrl());
    s.binaryType = "arraybuffer";
    ws.current = s;
    s.onopen = () => {
      const cb: PhoneClientMessage = { type: "callback", caller_number: myNumber, menu_choice: menu, case_code: code };
      s.send(JSON.stringify(cb));
    };
    s.onmessage = (m) => {
      if (typeof m.data !== "string") return;
      let msg: PhoneServerMessage;
      try {
        msg = JSON.parse(m.data) as PhoneServerMessage;
      } catch {
        return;
      }
      if (msg.type === "verification") {
        setVerified(msg.ok);
      } else if (msg.type === "say") {
        setCallLang(msg.language);
        setLines((l) => [...l, { from: "agent", text: msg.text, language: msg.language, gloss: msg.gloss_en }]);
        if (msg.audio_b64) playBase64Audio(msg.audio_b64);
        else if (voiceRef.current) speak(msg.text, msg.language);
      } else if (msg.type === "ended") {
        setEnded(msg.reason);
        stopMic();
      }
    };
    s.onerror = () => setLines((l) => [...l, { from: "system", text: tr("接続できませんでした。サービスが起動しているか確認して、もう一度お試しください。", "Couldn't connect. Check that the services are running, then call again.") }]);
    s.onclose = () => setEnded((e) => e ?? "hangup");
    setStage("call");
  }

  function sendTurn(e: React.FormEvent) {
    e.preventDefault();
    const t = text.trim();
    const s = ws.current;
    if (!t || !s || s.readyState !== WebSocket.OPEN || ended) return;
    s.send(JSON.stringify({ type: "turn", text: t } satisfies PhoneClientMessage));
    setLines((l) => [...l, { from: "me", text: t }]);
    setText("");
  }

  async function toggleMic() {
    if (micOn) return stopMic();
    const s = ws.current;
    if (!s) return;
    try {
      mic.current = await startMic(s, 1);
      setMicOn(true);
    } catch (err) {
      setLines((l) => [...l, { from: "system", text: tr(`マイクを使えません(${err instanceof Error ? err.message : String(err)})。ブラウザのマイク許可を確認してください。`, `The microphone isn't available (${err instanceof Error ? err.message : String(err)}). Check the browser's microphone permission, or type instead.`) }]);
    }
  }

  const resetToHome = () => {
    hangup();
    setStage("home");
    setCode("");
  };

  return (
    <div className="phone-wrap">
      <aside className="phone-explain">
        <h2>{tr("娘さんの携帯電話", "The daughter's phone")}</h2>
        <p>
          {tr(
            "これは、事前に登録されたご連絡先(娘さん)の携帯電話の代わりです。銀行から届くメッセージには、折り返し先の番号と確認番号だけが書かれ、取引の内容は何も書かれていません。",
            "This stands in for the trusted contact's phone. The message from the bank holds only a number to call back and a code, and nothing about the transaction.",
          )}
        </p>
        <p>
          {tr(
            "銀行の公開番号に電話をかけ、「ご連絡への折り返し」を選び、確認番号を入力すると、自動音声のアシスタントにつながります。",
            "Call the bank's published number, choose \"return a call\", and enter the code to reach the automated assistant.",
          )}
        </p>
        <p>
          {tr(
            "アシスタントは承認済みの文言だけで答え、金額や口座番号は決して話しません。",
            "The assistant answers only in approved wording and never says an amount or an account number.",
          )}
        </p>
      </aside>
      <div className="phone" data-testid="phone" data-stage={stage}>
        <div className="phone-top">
          <span>{tr("電話", "Phone")}</span>
          <div className="seg small" role="group" aria-label="language">
            <button type="button" className={lang === "ja" ? "on" : ""} onClick={() => setLang("ja")}>
              日本語
            </button>
            <button type="button" className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>
              EN
            </button>
          </div>
          <span className="muted small" data-testid="my-number">
            {myNumber}
          </span>
        </div>

        {stage === "home" && (
          <div className="phone-body">
            <h2>{tr("メッセージ", "Messages")}</h2>
            {notices.length === 0 && <p className="muted">{tr("新しいお知らせはありません。", "No new messages.")}</p>}
            {notices.map((n) => (
              <article key={n.call_id} className="notice bubble bubble-agent" data-testid="notice">
                <div className="muted small">{new Date(n.sent_at).toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", hour12: false })}</div>
                <p lang={n.language}>{n.text}</p>
                <Gloss en={n.gloss_en ?? undefined} />
                <p className="small muted">
                  {tr("公開番号", "Published number")} <strong data-testid="published-number">{n.published_phone_e164}</strong>
                </p>
                <p className="code-line">
                  <span className="small muted">{tr("確認番号", "Code")}</span> <strong data-testid="notice-code">{n.case_code}</strong>
                </p>
                <div className="row">
                  <button type="button" className="quiet" onClick={() => (n.audio_b64 ? playBase64Audio(n.audio_b64) : speak(n.text, n.language))}>
                    {tr("再生", "Play")}
                  </button>
                  <button
                    type="button"
                    className="call"
                    onClick={() => {
                      setDialed(n.published_phone_e164);
                      setCallLang(n.language);
                      setStage("menu");
                    }}
                  >
                    {tr("銀行に電話する", "Call the bank")}
                  </button>
                </div>
              </article>
            ))}
            <details className="muted small">
              <summary>{tr("この端末の番号(テスト用)", "This phone's number (for testing)")}</summary>
              <label className="field">
                {tr("発信者番号", "Caller number")}
                <input value={myNumber} onChange={(e) => setMyNumber(e.target.value)} aria-label={tr("発信者番号", "Caller number")} />
              </label>
            </details>
          </div>
        )}

        {stage === "menu" && (
          <div className="phone-body">
            <h2>{lang === "ja" ? `${dialed} に発信中` : `Calling ${dialed}`}</h2>
            <p lang="ja">お電話ありがとうございます。ご用件の番号を押してください。</p>
            <Gloss en="Thank you for calling. Please press the number for your request." />
            <div className="menu">
              <button
                type="button"
                onClick={() => {
                  setMenu(PHONE_MENU_RETURN_CALL);
                  setStage("code");
                }}
              >
                1 · ご連絡への折り返し{lang === "en" ? " (Return a call about a message)" : ""}
              </button>
              <button
                type="button"
                onClick={() => {
                  setMenu("other");
                  setStage("code");
                }}
              >
                2 · その他のご用件{lang === "en" ? " (Something else)" : ""}
              </button>
            </div>
            <button type="button" className="quiet" onClick={resetToHome}>
              {tr("切る", "Hang up")}
            </button>
          </div>
        )}

        {stage === "code" && (
          <div className="phone-body">
            <h2>{tr("ケースコードを入力", "Enter the case code")}</h2>
            <p lang="ja">お知らせにあった番号を入力してください。</p>
            <Gloss en="Please enter the number from the message." />
            <input
              className="code-input"
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
              aria-label={tr("ケースコード", "Case code")}
            />
            <div className="keypad">
              {["1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "発信"].map((k) => (
                <button
                  key={k}
                  type="button"
                  disabled={k === "発信" && code.length === 0}
                  onClick={() => {
                    if (k === "⌫") setCode((c) => c.slice(0, -1));
                    else if (k === "発信") connect();
                    else setCode((c) => (c + k).slice(0, 8));
                  }}
                >
                  {k === "発信" ? tr("発信", "Call") : k}
                </button>
              ))}
            </div>
            <button type="button" className="quiet" onClick={resetToHome}>
              {tr("切る", "Hang up")}
            </button>
          </div>
        )}

        {stage === "call" && (
          <div className="phone-body call">
            {verified === false && (
              <p className="error" data-testid="phone-verify-failed">
                確認できませんでした。恐れ入りますが、通話を終了します。
                <Gloss en="We could not verify this. We are sorry, but we will end the call." />
              </p>
            )}
            <div className="chat" aria-live="polite" data-testid="phone-chat" ref={chatRef}>
              {lines.map((l, i) => (
                <div key={i} className={`bubble bubble-${l.from}`}>
                  <span lang={l.language ?? "ja"}>{l.text}</span>
                  {l.from === "me" ? <Gloss text={l.text} /> : <Gloss en={l.gloss ?? undefined} />}
                </div>
              ))}
              {lines.length === 0 && !ended && <p className="muted">{tr("接続しています…", "Connecting…")}</p>}
              {ended && (
                <p className="muted" data-testid="phone-ended">
                  {tr("通話が終了しました。", "The call has ended.")}
                </p>
              )}
            </div>
            {!ended && <SampleLines who="contact" language={callLang} disabled={verified !== true} onPick={setText} />}
            {!ended && (
              <form onSubmit={sendTurn} className="turn-form">
                <input lang={callLang} value={text} onChange={(e) => setText(e.target.value)} placeholder={tr("話す内容を入力", "Type what you say")} aria-label={tr("通話の発言", "Call speech")} />
                <button type="submit" disabled={!text.trim() || verified !== true}>
                  {tr("送信", "Send")}
                </button>
                {config.speech === "cloud" && (
                  <button type="button" onClick={toggleMic} aria-pressed={micOn} className={micOn ? "end" : ""}>
                    {micOn ? tr("マイク停止", "Stop mic") : tr("マイク", "Mic")}
                  </button>
                )}
              </form>
            )}
            <label className="check small">
              <input type="checkbox" checked={voiceOut} onChange={(e) => setVoiceOut(e.target.checked)} /> {tr("音声で読み上げる", "Read aloud")}
            </label>
            <div className="row">
              {!ended ? (
                <button type="button" className="end" onClick={() => { hangup(); setEnded("hangup"); }}>
                  {tr("通話を終了", "End call")}
                </button>
              ) : (
                <button type="button" onClick={resetToHome}>
                  {tr("戻る", "Back")}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
