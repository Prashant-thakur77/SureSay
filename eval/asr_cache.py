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


def _cache_path(engine: str, bias: str, wav: str) -> Path:
    tag = bias.replace(":", "-")
    key = hashlib.sha1(wav.encode()).hexdigest()[:16]
    return CACHE / "asr" / engine / tag / f"{Path(wav).stem}-{key}.json"


def _init(engine: str, threads: int) -> None:
    global _ENGINE
    if engine.startswith("whisper-"):
        from suresay.asr import WhisperAsr

        _ENGINE = WhisperAsr(engine.split("-", 1)[1], cpu_threads=threads)
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
    heard = _ENGINE.transcribe(audio, vocabulary=vocab or None)
    return wav, heard.as_dict()


def transcribe_all(engine: str, bias: str, wavs: list[str], vocab: list[str], *, workers: int = 3,
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
    if todo:
        print(f"  transcribing {len(todo)} clips with {engine} [{bias}]", flush=True)
        with concurrent.futures.ProcessPoolExecutor(workers, initializer=_init, initargs=(engine, threads)) as pool:
            for i, (wav, heard) in enumerate(pool.map(_work, todo, chunksize=4), start=1):
                p = _cache_path(engine, bias, wav)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(heard))
                out[wav] = heard
                if i % 50 == 0:
                    print(f"    {i}/{len(todo)}", flush=True)
    return out
