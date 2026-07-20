"""Low-latency PCM preview transport for the SanWich SRT editor.

FFmpeg remains responsible for producing a seek-friendly mono PCM WAV proxy.
This module keeps one PortAudio stream alive and drives the UI from the audio
device clock instead of process launch time.
"""

from __future__ import annotations

import threading
import wave
from pathlib import Path

try:
    import sounddevice as _sd
except Exception:  # optional at import time; setup installs it for v2.5b
    _sd = None


class AudioPreviewError(RuntimeError):
    pass


class AudioPreviewPlayer:
    """Persistent, frame-addressable player for 16-bit PCM WAV files."""

    def __init__(self, latency: float = 0.03, blocksize: int = 256):
        self.latency = max(0.02, float(latency))
        self.blocksize = max(128, int(blocksize))
        self._lock = threading.RLock()
        self._wave: wave.Wave_read | None = None
        self._stream = None
        self._path = ""
        self._rate = 0
        self._channels = 0
        self._frame_width = 0
        self._total_frames = 0
        self._playing = False
        self._start_frame = 0
        self._position_frame = 0
        self._end_frame = 0
        self._dac_start_time: float | None = None
        self._finished_dac_time: float | None = None
        self._last_error = ""
        self._backend = "PortAudio"

    @staticmethod
    def available() -> bool:
        return _sd is not None

    @property
    def backend_name(self) -> str:
        return f"{self._backend}（sounddevice）" if self.available() else "不可用"

    @property
    def source_path(self) -> str:
        return self._path

    @property
    def last_error(self) -> str:
        return self._last_error

    def _audio_callback(self, outdata, frames, time_info, _status) -> None:
        silence = bytes(len(outdata))
        with self._lock:
            if not self._playing or self._wave is None:
                outdata[:] = silence
                return

            try:
                if self._dac_start_time is None:
                    self._dac_start_time = float(time_info.outputBufferDacTime)

                current_frame = self._wave.tell()
                remaining = max(0, self._end_frame - current_frame)
                wanted = min(frames, remaining)
                payload = self._wave.readframes(wanted) if wanted else b""
                actual_frames = len(payload) // max(1, self._frame_width)
                payload = payload[: actual_frames * self._frame_width]
                if len(payload) < len(outdata):
                    payload += bytes(len(outdata) - len(payload))
                outdata[:] = payload

                if current_frame + actual_frames >= self._end_frame and self._finished_dac_time is None:
                    self._finished_dac_time = (
                        float(time_info.outputBufferDacTime)
                        + (actual_frames / max(1, self._rate))
                    )
            except Exception as exc:
                self._last_error = str(exc)
                self._playing = False
                outdata[:] = silence

    def _open_stream(self) -> None:
        if _sd is None:
            raise AudioPreviewError("缺少 sounddevice，請重新執行 01_setup.bat。")
        if self._rate <= 0 or self._channels <= 0:
            raise AudioPreviewError("音訊格式尚未載入。")

        device_candidates = [(None, None, "PortAudio")]
        try:
            hostapis = _sd.query_hostapis()
            wasapi_index = next(
                index for index, host in enumerate(hostapis)
                if "wasapi" in str(host.get("name") or "").lower()
            )
            wasapi_device = int(hostapis[wasapi_index].get("default_output_device", -1))
            if wasapi_device >= 0:
                settings = _sd.WasapiSettings(exclusive=False, auto_convert=True)
                device_candidates.insert(0, (wasapi_device, settings, "Windows WASAPI"))
        except Exception:
            pass

        attempts = (self.latency, "low", None)
        errors: list[str] = []
        for device, extra_settings, backend in device_candidates:
            for latency in attempts:
                try:
                    kwargs = {
                        "samplerate": self._rate,
                        "channels": self._channels,
                        "dtype": "int16",
                        "blocksize": self.blocksize,
                        "callback": self._audio_callback,
                    }
                    if device is not None:
                        kwargs["device"] = device
                    if extra_settings is not None:
                        kwargs["extra_settings"] = extra_settings
                    if latency is not None:
                        kwargs["latency"] = latency
                    self._stream = _sd.RawOutputStream(**kwargs)
                    self._stream.start()
                    self._backend = backend
                    return
                except Exception as exc:
                    errors.append(str(exc))
                    try:
                        if self._stream is not None:
                            self._stream.close()
                    except Exception:
                        pass
                    self._stream = None
        raise AudioPreviewError("無法開啟 Windows 音訊輸出：" + "｜".join(errors[-2:]))

    def load(self, path: str) -> None:
        resolved = str(Path(path).resolve())
        with self._lock:
            if resolved == self._path and self._wave is not None and self._stream is not None:
                return
        self.close()
        with self._lock:
            try:
                wav = wave.open(resolved, "rb")
            except Exception as exc:
                raise AudioPreviewError(f"無法讀取預覽 WAV：{exc}") from exc

            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            compression = wav.getcomptype()
            if channels not in (1, 2) or sample_width != 2 or compression != "NONE":
                wav.close()
                raise AudioPreviewError("預覽音訊必須是單／雙聲道 16-bit PCM WAV。")

            self._wave = wav
            self._path = resolved
            self._rate = int(wav.getframerate())
            self._channels = channels
            self._frame_width = channels * sample_width
            self._total_frames = int(wav.getnframes())
            self._end_frame = self._total_frames
            try:
                self._open_stream()
            except Exception:
                wav.close()
                self._wave = None
                self._path = ""
                raise

    def play(self, path: str, start: float = 0.0, end: float | None = None) -> None:
        self.load(path)
        with self._lock:
            assert self._wave is not None
            start_frame = max(0, min(self._total_frames, int(round(float(start) * self._rate))))
            if end is None:
                end_frame = self._total_frames
            else:
                end_frame = max(start_frame + 1, int(round(float(end) * self._rate)))
                end_frame = min(self._total_frames, end_frame)
            self._wave.setpos(start_frame)
            self._start_frame = start_frame
            self._position_frame = start_frame
            self._end_frame = end_frame
            self._dac_start_time = None
            self._finished_dac_time = None
            self._last_error = ""
            self._playing = start_frame < end_frame

    def _refresh_position_locked(self) -> int:
        if not self._playing:
            return self._position_frame
        stream = self._stream
        if stream is None or self._dac_start_time is None:
            return self._start_frame
        try:
            stream_time = float(stream.time)
        except Exception:
            return self._position_frame
        elapsed = max(0.0, stream_time - self._dac_start_time)
        frame = min(self._end_frame, self._start_frame + int(elapsed * self._rate))
        self._position_frame = frame
        if self._finished_dac_time is not None and stream_time >= self._finished_dac_time:
            self._position_frame = self._end_frame
            self._playing = False
        return self._position_frame

    def current_time(self) -> float:
        with self._lock:
            frame = self._refresh_position_locked()
            return frame / max(1, self._rate)

    def is_playing(self) -> bool:
        with self._lock:
            self._refresh_position_locked()
            return bool(self._playing)

    def stop(self) -> None:
        with self._lock:
            self._refresh_position_locked()
            self._playing = False
            self._dac_start_time = None
            self._finished_dac_time = None

    pause = stop

    def close(self) -> None:
        with self._lock:
            self._playing = False
            stream, wav = self._stream, self._wave
            self._stream = None
            self._wave = None
            self._path = ""
            self._rate = 0
            self._total_frames = 0
        # PortAudio may wait for the callback during stop(); never hold the
        # callback lock while stopping the stream.
        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        if wav is not None:
            try:
                wav.close()
            except Exception:
                pass
