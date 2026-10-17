import { useEffect, useRef, useState } from "react";
import { audioSocketUrl } from "../api/client";
import type { AudioTranscriptFrame, Language, Transcript } from "../api/types";
import { startMic, type MicHandle } from "../audio";
import { useLang } from "../i18n";
import { Gloss, SampleLines } from "./SampleLines";

/**
 * Transcript plus the two ways turns get in:
 *  - typed turns (`POST /cases/{id}/turns`), the demo fallback, always available;
 *  - live microphone (`WS /cases/{id}/audio`), offered only when STT is on (`speech: cloud`).
 * Cards still arrive over SSE; the audio socket's JSON frames are only the live transcript.
 */
export function TurnPanel({
  caseId,
  transcript,
  speechOn,
  disabled,
  onSend,
  language = "ja",
  prefill,
}: {
  caseId: string;
  transcript: Transcript[];
  speechOn: boolean;
  disabled?: boolean;
  onSend: (speaker: "customer" | "teller", text: string) => Promise<void>;
  /** The case language: the sample-line buttons are the lines in this language. */
  language?: Language;
  /** "Say this": fills the input (never sends). `n` changes on every click. */
  prefill?: { speaker: "customer" | "teller"; text: string; n: number } | null;
}) {
  const { tr } = useLang();
  const [speaker, setSpeaker] = useState<"customer" | "teller">("customer");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<AudioTranscriptFrame[]>([]);
  const [micOn, setMicOn] = useState(false);
  const mic = useRef<{ ws: WebSocket; handle: MicHandle } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const initialCount = useRef(transcript.length); // turns present at first render do not animate

  useEffect(() => () => stopMic(), []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!prefill) return;
    setSpeaker(prefill.speaker);
    setText(prefill.text);
  }, [prefill?.n]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [transcript.length, live.length]);

  function stopMic() {
    mic.current?.handle.stop();
    mic.current?.ws.close();
    mic.current = null;
    setMicOn(false);
  }

  async function toggleMic() {
    if (micOn) return stopMic();
    setError(null);
    try {
      const ws = new WebSocket(audioSocketUrl(caseId));
      ws.binaryType = "arraybuffer";
      ws.onmessage = (m) => {
        if (typeof m.data !== "string") return;
        try {
          const f = JSON.parse(m.data) as AudioTranscriptFrame;
          if (f.type === "transcript") setLive((cur) => [...cur.filter((x) => x.turn_id !== f.turn_id || x.is_final), f].slice(-30));
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => setMicOn(false);
      await new Promise<void>((res, rej) => {
        ws.onopen = () => res();
        ws.onerror = () => rej(new Error("audio socket failed"));
      });
      // 2 channels: 0 = customer microphone, 1 = teller (silent from this single browser mic)
      const handle = await startMic(ws, 2);
      mic.current = { ws, handle };
      setMicOn(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      stopMic();
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onSend(speaker, t);
      setText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="conversation" aria-label={tr("会話", "Conversation")} data-testid="turn-panel">
      <h3>{tr("会話", "Conversation")}</h3>
      <div className="transcript" aria-live="polite">
        {transcript.length === 0 && <p className="muted">{tr("まだ発言がありません。", "No turns yet.")}</p>}
        {transcript.map((t, i) => (
          <div key={t.turn_id} className={`turn turn-${t.speaker}${i >= initialCount.current ? " fresh" : ""}`}>
            <span className="who">
              {t.speaker === "customer" ? tr("お客様", "Customer") : tr("窓口", "Teller")}
            </span>
            <span className="turn-text">
              <span lang={language}>{t.text}</span>
              {t.speaker === "customer" && <Gloss text={t.text} />}
            </span>
          </div>
        ))}
        {live
          .filter((f) => !f.is_final)
          .map((f) => (
            <div key={`live-${f.turn_id}`} className="turn turn-live">
              <span className="who">{f.speaker} …</span>
              <span lang="ja">{f.text}</span>
            </div>
          ))}
        <div ref={endRef} />
      </div>

      <SampleLines
        who="customer"
        language={language}
        disabled={disabled}
        onPick={(ja) => {
          setSpeaker("customer");
          setText(ja);
        }}
      />
      <form onSubmit={send} className="turn-form">
        <div className="seg" role="radiogroup" aria-label={tr("話者", "Speaker")}>
          <label className={speaker === "customer" ? "on" : ""}>
            <input type="radio" name="spk" checked={speaker === "customer"} onChange={() => setSpeaker("customer")} />
            {tr("お客様", "Customer")}
          </label>
          <label className={speaker === "teller" ? "on" : ""}>
            <input type="radio" name="spk" checked={speaker === "teller"} onChange={() => setSpeaker("teller")} />
            {tr("窓口", "Teller")}
          </label>
        </div>
        <input
          lang={language}
          value={text}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          placeholder={tr("発言を入力(例: リフォーム代なんです)", "Type what was said")}
          aria-label={tr("発言", "Turn text")}
        />
        <button type="submit" disabled={disabled || busy || !text.trim()}>
          {tr("送信", "Send")}
        </button>
        {speechOn && (
          <button type="button" onClick={toggleMic} className={micOn ? "danger" : ""} aria-pressed={micOn}>
            {micOn ? tr("マイク停止", "Stop mic") : tr("マイク開始", "Start mic")}
          </button>
        )}
      </form>
      {!speechOn && (
        <p className="muted small">{tr("窓口の音声認識は今後の機能です。このプロトタイプでは発言を文字で入力します。", "Speech-to-text at the counter is planned for a future release. In this prototype, type what was said.")}</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
