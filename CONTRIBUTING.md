# Contributing

```bash
make setup      # Python 3.13 venv (uv) + the web client's packages
make test       # the gate, the hub end to end, OAuth, the Alexa skill
make test-web   # the web client, including axe accessibility checks
make lint
```

## Rules every change keeps

1. **The agent can never confirm a write.** A change near the gate (`packages/confirm-gate-mcp`) starts with a failing test there.
2. **Every number comes from `eval/`.** Results are written by the eval scripts to `eval/results/`, `eval/make_report.py` turns them into `eval/REPORT.md`, and the README and write-up copy from there. Tuning uses the dev speakers (F03, M05) only.
3. **Accessibility is not optional.** New UI works from the keyboard and by single switch, announces itself to screen readers, and keeps WCAG 2.2 AA contrast in every theme.
4. **No dead ends.** Every screen offers *Say it again*, *Type it* and *None of these*.

## Pull requests

Keep them small, with tests. CI runs lint, both Python suites, the scripted safety suite, and the web client's typecheck, tests and build.
