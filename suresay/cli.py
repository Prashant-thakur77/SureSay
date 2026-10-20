"""Small admin commands: ``python -m suresay.cli pair [--user demo]`` prints a fresh pairing code.

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
    args = ap.parse_args()
    cfg = settings()
    store = DynamoStore(cfg.gate_table, region=cfg.region) if cfg.is_aws else SqliteStore(cfg.data_dir / "suresay.db")
    if args.cmd == "pair":
        user = args.user or cfg.default_user
        code = DeviceRegistry(store).start_pairing(user)
        print(code)


if __name__ == "__main__":
    main()
