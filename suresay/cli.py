"""Small admin commands, run by the operator (never reachable by the agent or a device).

``python -m suresay.cli pair [--user demo] [--transcriber alexa]`` prints a fresh pairing code; with
``--transcriber`` the device it pairs may send its own speech transcripts (a smart-speaker skill).
``python -m suresay.cli voice-device <device_id> alexa`` marks an already paired device that way.

With ``SURESAY_BACKEND=aws`` the code is written to the DynamoDB table the deployed hub reads,
so a browser can pair with the cloud hub. The code is shown here, never to the agent.
"""

from __future__ import annotations

import argparse

from confirm_gate import DeviceRegistry, DynamoStore, SqliteStore

from .config import settings


def main() -> None:
    ap = argparse.ArgumentParser(prog="suresay")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair", help="print a one-time pairing code")
    p.add_argument("--user", default=None)
    p.add_argument("--transcriber", default="", help="for a device that recognises speech itself, e.g. alexa")
    v = sub.add_parser("voice-device", help="mark a paired device as one that sends its own transcripts")
    v.add_argument("device_id")
    v.add_argument("transcriber")
    args = ap.parse_args()
    cfg = settings()
    store = DynamoStore(cfg.gate_table, region=cfg.region) if cfg.is_aws else SqliteStore(cfg.data_dir / "suresay.db")
    if args.cmd == "pair":
        user = args.user or cfg.default_user
        code = DeviceRegistry(store).start_pairing(user, transcriber=args.transcriber)
        print(code)
    elif args.cmd == "voice-device":
        if not DeviceRegistry(store).set_transcriber(args.device_id, args.transcriber):
            raise SystemExit(f"no active device {args.device_id}")
        print(f"{args.device_id} sends its own transcripts ({args.transcriber})")


if __name__ == "__main__":
    main()
