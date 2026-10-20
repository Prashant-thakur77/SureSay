"""Where utterance and evidence audio lives: S3 on AWS, a folder locally. Keys are content-addressed."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol


class Media(Protocol):
    def put(self, kind: str, data: bytes, *, suffix: str = ".wav") -> str: ...
    def get(self, ref: str) -> bytes: ...


_REF = re.compile(r"^(utterance|evidence)/[0-9a-f]{32}\.[a-z0-9]{2,4}$")


def _key(kind: str, data: bytes, suffix: str) -> str:
    if kind not in ("utterance", "evidence"):
        raise ValueError("kind must be utterance or evidence")
    return f"{kind}/{hashlib.sha256(data).hexdigest()[:32]}{suffix}"


def check_ref(ref: str) -> str:
    if not isinstance(ref, str) or not _REF.match(ref):
        raise ValueError("not an audio reference SureSay issued")
    return ref


class LocalMedia:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, kind: str, data: bytes, *, suffix: str = ".wav") -> str:
        key = _key(kind, data, suffix)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return key

    def get(self, ref: str) -> bytes:
        return (self.root / check_ref(ref)).read_bytes()


class S3Media:
    def __init__(self, bucket: str, *, region: str = "us-east-1", client: object | None = None) -> None:
        if client is None:
            import boto3

            client = boto3.client("s3", region_name=region)
        self.s3 = client
        self.bucket = bucket

    def put(self, kind: str, data: bytes, *, suffix: str = ".wav") -> str:
        key = _key(kind, data, suffix)
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType="audio/wav",  # type: ignore[attr-defined]
                           ServerSideEncryption="AES256")
        return key

    def get(self, ref: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=check_ref(ref))["Body"].read()  # type: ignore[attr-defined]
