"""Transcribe eval clips once per (engine, bias) and cache the result on disk.

Bias settings:
* ``none``    — no biasing (B0)
* ``confirm`` — the confirmation vocabulary the hub uses for evidence
* ``book:<speaker>`` — that speaker's phrasebook words (B1 and SureSay)
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.common import CACHE, DATA  # noqa: E402

_ENGINE: Any = None
NO_VOCABULARY = {"nova-2-sonic"}  # engines with no custom vocabulary: one transcript per clip, whatever the bias
NOVA_SONIC_USD_PER_1K = {"speech": 0.003, "text": 0.00033}  # input tokens, us-east-1, from the AWS Price List API


def _cache_path(engine: str, bias: str, wav: str) -> Path:
    """Cached per engine and bias. SURESAY_EVAL_CACHE_NS gives a fresh namespace (run 2 re-transcribes)."""
    ns = os.environ.get("SURESAY_EVAL_CACHE_NS", "")
    tag = "none" if engine in NO_VOCABULARY else bias.replace(":", "-")  # the same audio heard the same way
    engine = f"{engine}@{ns}" if ns else engine
    key = hashlib.sha1(wav.encode()).hexdigest()[:16]
    return CACHE / "asr" / engine / tag / f"{Path(wav).stem}-{key}.json"


def _init(engine: str, threads: int) -> None:
    global _ENGINE
    if engine.startswith("whisper-"):
        from suresay.asr import WhisperAsr

        _ENGINE = WhisperAsr(engine.split("-", 1)[1], cpu_threads=threads)
    elif engine == "transcribe-streaming":
        import boto3

        from suresay.asr import TranscribeStreamingAsr, VocabularyManager

        _ENGINE = TranscribeStreamingAsr(vocab=VocabularyManager(boto3.client("transcribe", region_name="us-east-1")))
    elif engine == "nova-2-sonic":
        from suresay.asr import NovaSonicAsr

        _ENGINE = NovaSonicAsr()
    elif engine == "transcribe-batch":
        import boto3

        from suresay.asr import TranscribeBatchAsr, VocabularyManager

        bucket = os.environ["SURESAY_EVAL_BUCKET"]
        _ENGINE = TranscribeBatchAsr(bucket=bucket, vocab=VocabularyManager(boto3.client("transcribe")))
    else:
        raise ValueError(engine)


def _work(job: tuple[str, str, str, list[str]]) -> tuple[str, dict[str, Any]]:
    engine, bias, wav, vocab = job
    audio = (DATA / wav).read_bytes()
    heard = _ENGINE.transcribe(audio, vocabulary=vocab or None).as_dict()
    if getattr(_ENGINE, "last_usage", None):
        heard["usage"] = dict(_ENGINE.last_usage)
    return wav, heard


def transcribe_all(engine: str, bias: str, wavs: list[str], vocab: list[str], *, workers: int | None = None,
                   threads: int = 6) -> dict[str, dict[str, Any]]:
    """{wav: Heard-as-dict} for every clip, from cache where possible."""
    out: dict[str, dict[str, Any]] = {}
    todo = []
    for wav in wavs:
        p = _cache_path(engine, bias, wav)
        if p.exists():
            out[wav] = json.loads(p.read_text())
        else:
            todo.append((engine, bias, wav, vocab))
    if todo and engine.startswith("transcribe") and vocab:
        import boto3

        from suresay.asr import VocabularyManager

        name = VocabularyManager(boto3.client("transcribe", region_name="us-east-1")).wait_ready(vocab)
        if name is None:
            raise SystemExit(f"custom vocabulary for {bias} did not become READY")
        print(f"  custom vocabulary {name} READY", flush=True)
    if todo:
        print(f"  transcribing {len(todo)} clips with {engine} [{bias}]", flush=True)
        if engine.startswith("transcribe"):
            _count_spend(len(todo))
        n = workers or (8 if engine.startswith("transcribe") else 4 if engine in NO_VOCABULARY else 3)
        with concurrent.futures.ProcessPoolExecutor(n, initializer=_init, initargs=(engine, threads)) as pool:
            for i, (wav, heard) in enumerate(pool.map(_work, todo, chunksize=4), start=1):
                p = _cache_path(engine, bias, wav)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(heard))
                out[wav] = heard
                if "usage" in heard:
                    _count_nova_sonic(heard["usage"])
                if i % 50 == 0:
                    print(f"    {i}/{len(todo)}", flush=True)
    return out


def _count_spend(requests: int) -> None:
    """Running tally of billed Transcribe requests (15 s minimum each), so the spend cap is visible."""
    path = CACHE.parent / "results" / "spend.json"
    doc = json.loads(path.read_text()) if path.exists() else {"transcribe_requests": 0}
    doc["transcribe_requests"] += requests
    doc["transcribe_usd_at_15s_min"] = round(doc["transcribe_requests"] * 15 * 0.0001667, 2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1))


def _count_nova_sonic(usage: dict[str, int]) -> None:
    """Running tally of Nova 2 Sonic input tokens and their list price (output is never generated)."""
    path = CACHE.parent / "results" / "spend.json"
    doc = json.loads(path.read_text()) if path.exists() else {}
    doc["nova_sonic_clips"] = doc.get("nova_sonic_clips", 0) + 1
    doc["nova_sonic_speech_tokens"] = doc.get("nova_sonic_speech_tokens", 0) + int(usage.get("speech_tokens", 0))
    doc["nova_sonic_text_tokens"] = doc.get("nova_sonic_text_tokens", 0) + int(usage.get("text_tokens", 0))
    doc["nova_sonic_usd"] = round(doc["nova_sonic_speech_tokens"] / 1000 * NOVA_SONIC_USD_PER_1K["speech"]
                                  + doc["nova_sonic_text_tokens"] / 1000 * NOVA_SONIC_USD_PER_1K["text"], 4)
    path.write_text(json.dumps(doc, indent=1))


def prepare_vocabularies(engine: str, vocab_lists: list[list[str]]) -> None:
    """Start creating every custom vocabulary at once; Transcribe takes minutes per vocabulary."""
    if not engine.startswith("transcribe"):
        return
    import boto3

    from suresay.asr import VocabularyManager

    vm = VocabularyManager(boto3.client("transcribe", region_name="us-east-1"))
    for words in vocab_lists:
        if words:
            vm.name_for(words)
