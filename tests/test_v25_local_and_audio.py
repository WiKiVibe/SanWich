from __future__ import annotations

import importlib.util
import threading
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


LOCAL = load_module("sanwich_local_llm_test", ROOT / "core" / "local_llm.py")
AUDIO = load_module("sanwich_audio_preview_test", ROOT / "core" / "audio_preview.py")
CORE = load_module("sanwich_core_v25_test", ROOT / "core" / "SanWich_legacy_core.py")
APP = load_module("sanwich_app_version_test", ROOT / "SanWich.py")


class LocalLLMTests(unittest.TestCase):
    def test_runtime_variant_respects_blackwell_driver_cuda_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = LOCAL.LocalLLMManager(Path(tmp))
            manager.gpu_info = lambda: {
                "name": "NVIDIA GeForce RTX 5070",
                "vram_mb": 12282,
                "driver_cuda": "13.1",
            }
            self.assertEqual(manager.runtime_variant(), "cuda-13.3")
            self.assertEqual(manager._engine_tuning(), {"context": 8192, "gpu_layers": 99})

            manager.gpu_info = lambda: {
                "name": "NVIDIA GeForce RTX 5070",
                "vram_mb": 12282,
                "driver_cuda": "12.9",
            }
            self.assertEqual(manager.runtime_variant(), "cuda-12.4")

            manager.gpu_info = lambda: {
                "name": "NVIDIA GeForce RTX 2060",
                "vram_mb": 6144,
                "driver_cuda": "13.1",
            }
            self.assertEqual(manager.runtime_variant(), "cuda-12.4")
            self.assertEqual(manager._engine_tuning(), {"context": 4096, "gpu_layers": 24})

    def test_release_assets_require_official_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = LOCAL.LocalLLMManager(Path(tmp))
            release = {
                "assets": [
                    {
                        "name": "llama-b1-bin-win-cuda-12.4-x64.zip",
                        "digest": "sha256:" + "a" * 64,
                    },
                    {
                        "name": "cudart-llama-bin-win-cuda-12.4-x64.zip",
                        "digest": "sha256:" + "b" * 64,
                    },
                ]
            }
            selected = manager._select_release_assets(release, "cuda-12.4")
            self.assertEqual(len(selected), 2)
            self.assertNotEqual(selected[0]["name"], selected[1]["name"])
            release["assets"][0]["digest"] = ""
            with self.assertRaises(LOCAL.LocalLLMError):
                manager._select_release_assets(release, "cuda-12.4")

    def test_model_ready_requires_size_and_verified_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = LOCAL.LocalLLMManager(Path(tmp))
            manager.model_dir.mkdir(parents=True)
            manager.model_path.write_bytes(b"tiny")
            self.assertFalse(manager.model_ready())

    def test_download_preflight_blocks_below_7gb_and_warns_below_10gb(self):
        original = LOCAL.shutil.disk_usage
        try:
            with tempfile.TemporaryDirectory() as tmp:
                manager = LOCAL.LocalLLMManager(Path(tmp))
                usage = lambda free: type("Usage", (), {"total": 20 * 1024**3, "used": 0, "free": free})()
                LOCAL.shutil.disk_usage = lambda _path: usage(6.9 * 1024**3)
                with self.assertRaisesRegex(LOCAL.LocalLLMError, "至少需要 7 GB"):
                    manager.preflight_disk_space()

                logs = []
                LOCAL.shutil.disk_usage = lambda _path: usage(8 * 1024**3)
                status = manager.preflight_disk_space(log_fn=logs.append)
                self.assertAlmostEqual(status["free_gb"], 8.0, places=1)
                self.assertTrue(any("建議保留 10 GB" in line for line in logs))
        finally:
            LOCAL.shutil.disk_usage = original


class _FakeStream:
    def __init__(self, *, callback, channels, **_kwargs):
        self.callback = callback
        self.channels = channels
        self.time = 10.0
        self.closed = False

    def start(self):
        return None

    def stop(self):
        return None

    def close(self):
        self.closed = True

    def pump(self, frames: int = 512):
        info = type("TimeInfo", (), {"outputBufferDacTime": self.time})()
        output = bytearray(frames * self.channels * 2)
        self.callback(output, frames, info, None)
        return output


class _FakeSoundDevice:
    RawOutputStream = _FakeStream


class AudioPreviewTests(unittest.TestCase):
    def test_player_uses_dac_clock_and_reuses_stream(self):
        original_sd = AUDIO._sd
        AUDIO._sd = _FakeSoundDevice()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                wav_path = Path(tmp) / "silence.wav"
                with wave.open(str(wav_path), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(bytes(16000 * 2 * 2))

                player = AUDIO.AudioPreviewPlayer()
                player.play(str(wav_path), 0.5, 1.5)
                stream = player._stream
                self.assertAlmostEqual(player.current_time(), 0.5, places=3)
                stream.pump()
                stream.time = 10.25
                self.assertAlmostEqual(player.current_time(), 0.75, places=2)
                player.play(str(wav_path), 1.0, 1.2)
                self.assertIs(player._stream, stream)
                player.close()
                self.assertTrue(stream.closed)
        finally:
            AUDIO._sd = original_sd


class LocalProviderValidationTests(unittest.TestCase):
    def test_cloud_model_lists_match_current_supported_choices(self):
        self.assertEqual(
            APP.OPENAI_MODELS,
            ["gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"],
        )
        self.assertEqual(
            APP.CLAUDE_MODELS,
            ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8", "claude-fable-5"],
        )
        self.assertEqual(APP.GEMINI_MODELS[0], "gemini-3.6-flash")
        self.assertNotIn("gemini-2.0-flash", APP.GEMINI_MODELS)

    def test_new_openai_models_use_gpt5_chat_parameters(self):
        captured = {}
        original = CORE._post_json
        try:
            def fake_post(url, headers, payload, timeout=120):
                captured.update({"url": url, "payload": payload})
                return {"choices": [{"message": {"content": "ok"}}]}

            CORE._post_json = fake_post
            result = CORE._llm_call_once(
                "system",
                "user",
                {"api_provider": "openai", "api_key": "test", "model": "gpt-5.6-luna"},
            )
        finally:
            CORE._post_json = original

        self.assertEqual(result, "ok")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(captured["payload"]["max_completion_tokens"], 8192)
        self.assertEqual(captured["payload"]["reasoning_effort"], "low")
        self.assertNotIn("temperature", captured["payload"])
        self.assertNotIn("max_tokens", captured["payload"])

    def test_gemini3_request_omits_deprecated_sampling_parameters(self):
        captured = {}
        original = CORE._post_json
        try:
            def fake_post(url, headers, payload, timeout=120):
                captured.update({"url": url, "payload": payload})
                return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

            CORE._post_json = fake_post
            result = CORE._llm_call_once(
                "system",
                "user",
                {"api_provider": "gemini", "api_key": "test", "model": "gemini-3.6-flash"},
            )
        finally:
            CORE._post_json = original

        self.assertEqual(result, "ok")
        self.assertIn("gemini-3.6-flash:generateContent", captured["url"])
        self.assertEqual(captured["payload"]["generationConfig"], {"maxOutputTokens": 4096})

    def test_provider_memory_keeps_keys_and_models_separate(self):
        cfg = APP.normalize_api_cfg(
            {
                "api_provider": "deepseek",
                "api_key": "sk-deepseek-demo",
                "model": "deepseek-v4-flash",
            }
        )
        cfg["api_keys_by_provider"]["gemini"] = "AIza-gemini-demo"
        cfg["models_by_provider"]["gemini"] = "gemini-2.5-flash"

        normalized = APP.normalize_api_cfg(cfg)

        self.assertEqual(normalized["api_keys_by_provider"]["deepseek"], "sk-deepseek-demo")
        self.assertEqual(normalized["api_keys_by_provider"]["gemini"], "AIza-gemini-demo")
        self.assertEqual(normalized["models_by_provider"]["deepseek"], "deepseek-v4-flash")
        self.assertEqual(normalized["models_by_provider"]["gemini"], "gemini-2.5-flash")

    def test_formal_v25_is_newer_than_v25b(self):
        self.assertTrue(APP.is_newer_version("v2.5", "2.5b"))
        self.assertFalse(APP.is_newer_version("v2.5b", "2.5"))
        self.assertTrue(APP.is_newer_version("v2.5.1", "2.5"))

    def test_local_provider_does_not_require_api_key(self):
        original = CORE._llm_call_once
        try:
            CORE._llm_call_once = lambda *_args, **_kwargs: (
                "1\n00:00:00,000 --> 00:00:01,000\n測試字幕\n"
            )
            lines, _plain = CORE.llm_merge(
                [{"timestamp": (0.0, 1.0), "text": "測試字幕"}],
                {"api_provider": "local", "api_key": "", "model": "breeze-local", "_llm_retry_delays": []},
                lambda *_args: None,
                use_text_fix=False,
            )
            self.assertEqual(lines, ["測試字幕"])
        finally:
            CORE._llm_call_once = original

    def test_local_batch_transcribes_all_then_releases_asr_before_llm(self):
        app = object.__new__(APP.App)
        app.cfg = {"api_provider": "local"}
        app.cancel_event = threading.Event()
        app.breeze_chip = object()
        app.ai_chip = object()
        app.run_btn = type("Button", (), {"configure": lambda self, **kwargs: None})()
        app.cancel_btn = type("Button", (), {"configure": lambda self, **kwargs: None})()
        app.set_progress = lambda *_args, **_kwargs: None
        app.set_chip = lambda *_args, **_kwargs: None
        app.log = lambda *_args, **_kwargs: None
        app.after = lambda *_args, **_kwargs: None

        events = []
        app.prepare_transcription = lambda inp, diarize=False: (
            events.append(f"asr:{inp}") or {"chunks": [], "breeze_text": inp, "speaker_turns": None}
        )
        app.release_breeze_pipeline = lambda: events.append("release")
        app.process_one = lambda inp, *_args, prepared=None, **_kwargs: (
            events.append(f"finish:{inp}") or True
        )

        manager = APP.LOCAL_LLM.MANAGER
        original_stop = manager.stop
        original_ensure = manager.ensure_running
        try:
            manager.stop = lambda: events.append("stop-local")
            manager.ensure_running = lambda **_kwargs: events.append("start-local") or "http://127.0.0.1:8080"
            app.batch_worker(
                [("a.wav", "a.srt", "a.txt"), ("b.wav", "b.srt", "b.txt")],
                True,
                "",
                False,
                False,
            )
        finally:
            manager.stop = original_stop
            manager.ensure_running = original_ensure

        self.assertEqual(
            events,
            ["stop-local", "asr:a.wav", "asr:b.wav", "release", "start-local", "finish:a.wav", "finish:b.wav"],
        )


if __name__ == "__main__":
    unittest.main()
