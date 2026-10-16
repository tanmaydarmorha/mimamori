/**
 * Browser microphone -> LINEAR16 16 kHz binary frames on a WebSocket (only used when STT is on).
 *
 *  - `WS /cases/{id}/audio` wants 2 interleaved channels (0 = customer microphone, 1 = teller). One
 *    browser microphone feeds channel 0; channel 1 is silence.
 *  - `WS /phone` takes plain audio frames; mono.
 *
 * ScriptProcessorNode is deprecated but works everywhere and keeps this dependency-free; the
 * prototype streams a few seconds at a time, so the main-thread cost is irrelevant.
 */
export interface MicHandle {
  stop: () => void;
}

export function floatToInt16(f: Float32Array): Int16Array {
  const out = new Int16Array(f.length);
  for (let i = 0; i < f.length; i++) {
    const s = Math.max(-1, Math.min(1, f[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

/** Mono samples -> frame with `channels` interleaved channels; the signal is on channel 0. */
export function interleave(mono: Int16Array, channels: 1 | 2): Int16Array {
  if (channels === 1) return mono;
  const out = new Int16Array(mono.length * 2);
  for (let i = 0; i < mono.length; i++) out[i * 2] = mono[i];
  return out;
}

export async function startMic(ws: WebSocket, channels: 1 | 2): Promise<MicHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true } });
  const ctx = new AudioContext({ sampleRate: 16000 });
  const src = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  proc.onaudioprocess = (ev) => {
    if (ws.readyState !== WebSocket.OPEN) return;
    const frame = interleave(floatToInt16(ev.inputBuffer.getChannelData(0)), channels);
    ws.send(frame.buffer as ArrayBuffer);
  };
  src.connect(proc);
  proc.connect(ctx.destination);
  return {
    stop: () => {
      proc.disconnect();
      src.disconnect();
      stream.getTracks().forEach((t) => t.stop());
      void ctx.close();
    },
  };
}

/** Play `audio_b64` from a server `say` / notice. Format is not stated in the contract; the browser sniffs it. */
export function playBase64Audio(b64: string): void {
  try {
    const a = new Audio(`data:audio/mpeg;base64,${b64}`);
    void a.play();
  } catch {
    /* autoplay blocked or unsupported: the text is on screen anyway */
  }
}

/** Fallback voice for the typed demo: the browser's own ja-JP speech synthesis. */
export function speak(text: string, lang: "ja" | "en" = "ja"): void {
  if (typeof speechSynthesis === "undefined") return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang === "en" ? "en-US" : "ja-JP";
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}
export const speakJa = (text: string): void => speak(text, "ja");
