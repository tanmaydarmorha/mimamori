"""Speech interfaces and implementations.

    SpeechToText   TypedInput (local, and the demo fallback) | CloudSttV2 (Chirp, ja-JP, streaming, two channels)
    TextToSpeech   TextOnly  (local, and the demo fallback) | CloudTts

Selection by config (`MIMAMORI_SPEECH=typed|cloud`). No Gemini Live API anywhere: voice is
STT -> text model -> templates -> rule check -> TTS. CloudSttV2 and CloudTts need the `cloud` extra
and have not been run against the real services yet (Chirp availability in asia-south1 is an open item).
"""

from __future__ import annotations

import asyncio
import queue
import threading
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Protocol

from .config import Settings

Channel = Literal["customer", "teller"]


@dataclass
class SpeechResult:
    text: str
    is_final: bool = True
    channel: Channel = "customer"
    confidence: float | None = None


class SpeechToText(Protocol):
    def transcribe_stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[SpeechResult]: ...


class TextToSpeech(Protocol):
    audio_format: str

    async def synthesize(self, text: str) -> bytes: ...


class TypedInput:
    """Stands in for STT: every incoming 'audio' chunk is one UTF-8 utterance, returned as a final
    result. Prefix a chunk with `teller:` for the teller channel (default is the customer)."""

    async def transcribe_stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[SpeechResult]:
        async for chunk in audio:
            text = chunk.decode("utf-8").strip()
            if not text:
                continue
            channel: Channel = "customer"
            if text.startswith("teller:"):
                channel, text = "teller", text[len("teller:"):].strip()
            elif text.startswith("customer:"):
                text = text[len("customer:"):].strip()
            yield SpeechResult(text=text, is_final=True, channel=channel)


@dataclass
class TextOnly:
    """Stands in for TTS: produces no audio and remembers what would have been spoken."""

    audio_format: str = "none"
    spoken: list[str] = field(default_factory=list)

    async def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return b""


class CloudSttV2:
    """Cloud Speech-to-Text V2, Chirp, streaming. Input is LINEAR16 PCM with `channels` interleaved
    channels, recognised separately per channel: channel 0 = customer microphone, 1 = teller."""

    def __init__(self, project: str, region: str, model: str = "chirp_2", language: str = "ja-JP",
                 channels: int = 2, sample_rate_hz: int = 16000) -> None:
        from google.api_core.client_options import ClientOptions
        from google.cloud.speech_v2 import SpeechClient

        self.recognizer = f"projects/{project}/locations/{region}/recognizers/_"
        self.model, self.language, self.channels, self.sample_rate_hz = model, language, channels, sample_rate_hz
        self.client = SpeechClient(client_options=ClientOptions(api_endpoint=f"{region}-speech.googleapis.com"))

    def _config(self):
        from google.cloud.speech_v2.types import cloud_speech as t

        return t.StreamingRecognitionConfig(
            config=t.RecognitionConfig(
                explicit_decoding_config=t.ExplicitDecodingConfig(
                    encoding=t.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=self.sample_rate_hz,
                    audio_channel_count=self.channels,
                ),
                features=t.RecognitionFeatures(
                    multi_channel_mode=t.RecognitionFeatures.MultiChannelMode.SEPARATE_RECOGNITION_PER_CHANNEL,
                ),
                model=self.model,
                language_codes=[self.language],
            ),
            streaming_features=t.StreamingRecognitionFeatures(interim_results=True),
        )

    async def transcribe_stream(self, audio: AsyncIterator[bytes]) -> AsyncIterator[SpeechResult]:
        from google.cloud.speech_v2.types import cloud_speech as t

        loop = asyncio.get_running_loop()
        inbound: queue.Queue[bytes | None] = queue.Queue()
        outbound: asyncio.Queue[SpeechResult | BaseException | None] = asyncio.Queue()

        def requests():
            yield t.StreamingRecognizeRequest(recognizer=self.recognizer, streaming_config=self._config())
            while (chunk := inbound.get()) is not None:
                yield t.StreamingRecognizeRequest(audio=chunk)

        def run() -> None:
            try:
                for response in self.client.streaming_recognize(requests=requests()):
                    for result in response.results:
                        if not result.alternatives:
                            continue
                        alt = result.alternatives[0]
                        item = SpeechResult(alt.transcript, result.is_final, "teller" if result.channel_tag == 1 else "customer",
                                            alt.confidence or None)
                        loop.call_soon_threadsafe(outbound.put_nowait, item)
            except BaseException as err:  # surfaced to the caller below
                loop.call_soon_threadsafe(outbound.put_nowait, err)
            finally:
                loop.call_soon_threadsafe(outbound.put_nowait, None)

        threading.Thread(target=run, daemon=True).start()

        async def pump() -> None:
            async for chunk in audio:
                inbound.put(chunk)
            inbound.put(None)

        pump_task = asyncio.create_task(pump())
        try:
            while (item := await outbound.get()) is not None:
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            pump_task.cancel()
            inbound.put(None)


class CloudTts:
    """Cloud Text-to-Speech, MP3. One instance per language (voice + locale)."""

    audio_format = "audio/mpeg"

    def __init__(self, voice: str = "ja-JP-Chirp3-HD-Aoede", language: str = "ja-JP") -> None:
        from google.cloud import texttospeech

        self._tts, self.voice, self.language = texttospeech, voice, language
        self.client = texttospeech.TextToSpeechClient()

    async def synthesize(self, text: str) -> bytes:
        tts = self._tts

        def call() -> bytes:
            response = self.client.synthesize_speech(
                input=tts.SynthesisInput(text=text),
                voice=tts.VoiceSelectionParams(language_code=self.language, name=self.voice),
                audio_config=tts.AudioConfig(audio_encoding=tts.AudioEncoding.MP3),
            )
            return response.audio_content

        return await asyncio.to_thread(call)


def for_language(settings: Settings, language: str) -> tuple[str, str]:
    """(STT locale, TTS voice) for a case language, `ja` or `en`."""
    if language == "ja":
        return settings.stt_language, settings.tts_voice
    if language == "en":
        return settings.stt_language_en, settings.tts_voice_en
    raise ValueError(f"unsupported language {language!r} (ja | en)")


def get_stt(settings: Settings | None = None, channels: int = 2, language: str = "ja") -> SpeechToText:
    """`channels=2` for counter audio (customer + teller), `channels=1` for phone audio."""
    settings = settings or Settings.from_env()
    if settings.speech_backend == "typed":
        return TypedInput()
    if settings.speech_backend == "cloud":
        if not settings.project_id:
            raise ValueError("MIMAMORI_PROJECT_ID is required for Cloud STT")
        return CloudSttV2(settings.project_id, settings.region, settings.stt_model, for_language(settings, language)[0], channels=channels)
    raise ValueError(f"unknown MIMAMORI_SPEECH {settings.speech_backend!r} (typed | cloud)")


def get_tts(settings: Settings | None = None, language: str = "ja") -> TextToSpeech:
    settings = settings or Settings.from_env()
    if settings.tts_backend == "typed":
        return TextOnly()
    if settings.tts_backend == "cloud":
        locale, voice = for_language(settings, language)
        return CloudTts(voice, locale)
    raise ValueError(f"unknown MIMAMORI_TTS {settings.tts_backend!r} (typed | cloud)")
