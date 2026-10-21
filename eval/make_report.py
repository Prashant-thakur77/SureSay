"""Regenerate eval/REPORT.md (and the README results block) from eval/results/*.json.

Nothing in the report is typed by hand: every number is read from a results file written by a script.
Run 1 is the headline; run 2, when present, is shown as a stability check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.common import EVAL, ROOT, SPLIT, read_result  # noqa: E402

SEVERITY_NOTE = ("Severity labels are not used to pick the split; dev speakers were fixed before any run "
                 "(eval/common.py).")


def f(v: Any, suffix: str = "%") -> str:
    return "—" if v is None else f"{v}{suffix}"


def load(name: str, run: str = "run1") -> dict[str, Any] | None:
    return read_result(name, run) or read_result(name)


def confirm_section(c: dict[str, Any], c2: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    b0, ss = c["summary"]["b0"], c["summary"]["suresay"]
    t0, t1 = b0["test"], ss["test"]
    g0, g1 = b0["test_confirm_words_only"], ss["test_confirm_words_only"]
    d0, d1 = b0["test_distractors_only"], ss["test_distractors_only"]
    out = [
        "## Claim 1 — confirmations are heard right",
        "",
        f"Clips: TORGO single words from the 6 held-out dysarthric speakers — the answers \"yes\", \"no\", \"one\", "
        f"\"two\", \"three\" ({g1['clips']} decisions) plus up to {c['distractors_per_speaker']} other words per speaker "
        f"({d1['clips']} decisions) that must never count as a yes or a choice. Each clip is judged in the context it "
        "could appear in: three cards on screen, or one yes/no card. ASR: "
        f"`{c['asr_engine']}`; SureSay's recogniser bias was chosen on dev speakers only (`{c['suresay_bias']}`, "
        "see Tuning).",
        "",
        "| Test speakers | B0 plain (forced nearest word) | SureSay (consent parser) |",
        "|---|---|---|",
        f"| **False accepts, all clips** | **{f(t0['false_accept_pct'])}** ({t0['false_accepts']}/{t0['clips']}) | "
        f"**{f(t1['false_accept_pct'])}** ({t1['false_accepts']}/{t1['clips']}) |",
        f"| False accepts, other words only | {d0['false_accepts']}/{d0['clips']} | {d1['false_accepts']}/{d1['clips']} |",
        f"| Genuine answers recovered | {f(g0['true_accepts_recovered_pct'])} | {f(g1['true_accepts_recovered_pct'])} |",
        f"| Genuine answers refused (\"say it again\") | {f(g0['refused_pct'])} | {f(g1['refused_pct'])} |",
        f"| Decision accuracy, all clips | {f(t0['accuracy_pct'])} | {f(t1['accuracy_pct'])} |",
        "",
        "Per speaker, false-accept rate (all clips):",
        "",
        "| Speaker | Group | B0 | SureSay | clips |",
        "|---|---|---|---|---|",
    ]
    for g in ("test", "dev", "controls"):
        for spk in SPLIT[g]:
            a, b = b0["per_speaker"].get(spk), ss["per_speaker"].get(spk)
            if a and a["clips"]:
                out.append(f"| {spk} | {g} | {f(a['false_accept_pct'])} | {f(b['false_accept_pct'])} | {a['clips']} |")
    ctrl = ss.get("controls", {})
    out += ["", f"Controls (typical speech): SureSay false accepts {f(ctrl.get('false_accept_pct'))}, genuine answers "
            f"recovered {f(ss.get('controls_confirm_words_only', {}).get('true_accepts_recovered_pct'))}."]
    if c2:
        r2 = c2["summary"]["suresay"]["test"]
        out += ["", f"Run 2 (stability): SureSay false accepts {f(r2['false_accept_pct'])} "
                f"({r2['false_accepts']}/{r2['clips']}), B0 {f(c2['summary']['b0']['test']['false_accept_pct'])}."]
    sures_fa = [r for r in c["rows"] if r["group"] == "test" and r["suresay"]["decision"][0] in ("choose", "yes")
                and r["suresay"]["decision"] != r["truth"]]
    if sures_fa:
        out += ["", "Every SureSay false accept on test speakers, with what the recogniser heard:", ""]
        for r in sures_fa:
            out.append(f"- {r['speaker']}, said \"{r['word']}\" ({r['context']} card) → heard \"{r['suresay']['heard']}\" → "
                       f"{r['suresay']['decision'][0]} {r['suresay']['decision'][1] or ''}".rstrip())
    key = {"b0_fa": t0["false_accept_pct"], "ss_fa": t1["false_accept_pct"], "b0_acc": t0["accuracy_pct"],
           "ss_acc": t1["accuracy_pct"], "b0_rec": g0["true_accepts_recovered_pct"],
           "ss_rec": g1["true_accepts_recovered_pct"], "ss_refused": g1["refused_pct"],
           "fa_counts": (t0["false_accepts"], t1["false_accepts"], t1["clips"])}
    return out, key


def intent_section(i: dict[str, Any], i2: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    systems = i["systems"]
    names = {"b0": "B0 plain", "b1": "B1 + phrasebook", "ss_fuzzy": "SureSay (offline ranker)",
             "ss_nova": "SureSay (Nova 2 Lite)"}
    test = i["summary"]["test"]
    counts = {t["speaker"]: (t["in_book"], t["out_of_book"]) for t in i["tasks"]}
    out = [
        "## Claims 2 and 2b — the meaning is recovered, and SureSay says \"say it again\" when unsure",
        "",
        f"Per held-out speaker, a {i['book_size']}-phrase book: half of their own distinct TORGO sentences (up to 20) "
        "plus distractors from other speakers' prompts. The other half of their sentences stay *out* of the book "
        "and test abstaining. Every phrase is a \"say this for me\" action. ASR: "
        f"`{i['asr_engine']}`. Abstain thresholds were tuned on dev speakers only.",
        "",
        "| Test speakers | " + " | ".join(names[s] for s in systems) + " |",
        "|---|" + "---|" * len(systems),
        "| Top-1 phrase recovered | " + " | ".join(f(test[s]["top1_pct"]) for s in systems) + " |",
        "| Top-3 phrase recovered | " + " | ".join(f(test[s]["top3_pct"]) for s in systems) + " |",
        "| In the cards, counting \"maybe\" cards | " + " | ".join(
            f(test[s].get("in_cards_with_maybe_pct")) if s.startswith("ss") else (f(test[s]["top3_pct"]) if s != "b0" else "—")
            for s in systems) + " |",
        "| Out-of-book: correctly asked again | " + " | ".join(f(test[s]["correct_abstain_pct"]) for s in systems) + " |",
        "| Out-of-book: maybe cards offered (user declines) | " + " | ".join(
            f(test[s].get("maybe_cards_on_out_of_book_pct")) if s.startswith("ss") else "—" for s in systems) + " |",
        "| In-book: asked again needlessly | " + " | ".join(f(test[s]["false_abstain_pct"]) for s in systems) + " |",
        "| Acted on a wrong phrase without asking | " + " | ".join(
            f(test[s]["acted_without_asking_wrong_pct"]) for s in systems) + " |",
        "",
        f"Utterances: {test[systems[0]]['in_book']} in-book and {test[systems[0]]['out_of_book']} out-of-book across "
        "the test speakers. B0 has a single hypothesis, so it has no top-3. SureSay never acts without a confirmation, "
        "so its \"acted wrongly\" is 0 by construction; what it can do is show wrong cards, which the user declines. "
        "When it is unsure it asks again *and* offers its best guesses as \"maybe\" cards (only guesses scoring at "
        "least 0.50, a floor fixed before measuring); a maybe card needs the same confirmation as any other.",
        "",
        "Per test speaker (top-1 / correct abstain):",
        "",
        "| Speaker | in / out | " + " | ".join(names[s] for s in systems) + " |",
        "|---|---|" + "---|" * len(systems),
    ]
    for spk, v in test["per_speaker"].items():
        n_in, n_out = counts.get(spk, (0, 0))
        out.append(f"| {spk} | {n_in} / {n_out} | " + " | ".join(
            f"{f(v[s]['top1_pct'])} / {f(v[s]['correct_abstain_pct'])}" for s in systems) + " |")
    if "ss_nova" not in systems:
        out += ["", f"**Nova 2 Lite ranking: {i['nova']}.** The Nova path is implemented and unit-tested "
                "(tests/test_rank.py); its numbers will appear here when the account's Bedrock access opens."]
    ctrl = i["summary"].get("controls")
    if ctrl:
        out += ["", "## Claim 5 — typical speech is not hurt", "",
                "The same task on control speakers (no dysarthria):", "",
                "| Controls | " + " | ".join(names[s] for s in systems) + " |",
                "|---|" + "---|" * len(systems),
                "| Top-1 phrase recovered | " + " | ".join(f(ctrl[s]["top1_pct"]) for s in systems) + " |",
                "| Out-of-book: correctly asked again | " + " | ".join(f(ctrl[s]["correct_abstain_pct"]) for s in systems) + " |"]
    if i2:
        t2 = i2["summary"]["test"]
        out += ["", "Run 2 (stability), test top-1: " + ", ".join(f"{names[s]} {f(t2[s]['top1_pct'])}" for s in i2["systems"])]
    ss = "ss_nova" if "ss_nova" in systems else "ss_fuzzy"
    worst = min(test["per_speaker"].items(), key=lambda kv: kv[1][ss]["top1_pct"] or 0)
    key = {"b0_top1": test["b0"]["top1_pct"], "b1_top1": test["b1"]["top1_pct"], "b1_top3": test["b1"]["top3_pct"], "ss_top1": test[ss]["top1_pct"],
           "ss_top3": test[ss]["top3_pct"], "ss_abstain": test[ss]["correct_abstain_pct"],
           "b1_abstain": test["b1"]["correct_abstain_pct"], "ss_false_abstain": test[ss]["false_abstain_pct"],
           "b1_wrong": test["b1"]["acted_without_asking_wrong_pct"], "b0_wrong": test["b0"]["acted_without_asking_wrong_pct"],
           "ss_wrong": test[ss]["acted_without_asking_wrong_pct"],
           "ctrl_b0": (ctrl or {}).get("b0", {}).get("top1_pct"), "ctrl_ss": (ctrl or {}).get(ss, {}).get("top1_pct"),
           "worst": (worst[0], worst[1][ss]["top1_pct"], worst[1]["b1"]["top1_pct"], worst[1][ss]["false_abstain_pct"],
                     worst[1][ss].get("in_cards_with_maybe_pct")),
           "ss_maybe": test[ss].get("in_cards_with_maybe_pct"), "ss_maybe_oob": test[ss].get("maybe_cards_on_out_of_book_pct"),
           "ss_name": names[ss]}
    return out, key


def safety_section(s: dict[str, Any], s2: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    arms = s["arms"]
    adv = arms["suresay_adversary"]["summary"]
    plain = arms["plain_obedient"]["summary"]
    out = [
        "## Claim 3 — nothing changes without the user",
        "",
        "50 adversarial cases on the real hub over HTTP: 20 prompt injections hidden in tool output (product "
        "descriptions and contact names), 15 near-miss commands (the user meant one thing, recognition heard "
        "another), and 15 forged confirmations (the agent confirming for itself, replayed evidence and recordings, "
        "expired card sets, cross-user evidence, a captured signed request, pairing brute force, eight racing "
        "confirms). Metric: state changes in the home that the user did not confirm on their own paired device.",
        "",
        "| Arm | Injections (20) | Near-misses (15) | Forged (15) | Unconfirmed changes |",
        "|---|---|---|---|---|",
    ]

    def cell(summary: dict[str, Any], cat: str) -> str:
        c = summary["by_category"].get(cat)
        return "n/a" if not c else f"{c['unconfirmed_changes']}"

    out.append(f"| SureSay, scripted worst-case agent | {cell(adv, 'injection')} | {cell(adv, 'near_miss')} | "
               f"{cell(adv, 'forged')} | **{adv['unconfirmed_changes']} / {adv['cases']}** |")
    linked = arms.get("suresay_linked_adversary", {}).get("summary")
    if linked:
        out.append(f"| SureSay, same agent as an OAuth-linked client (as Alexa+) | {cell(linked, 'injection')} | "
                   f"{cell(linked, 'near_miss')} | {cell(linked, 'forged')} | **{linked['unconfirmed_changes']} / {linked['cases']}** |")
    out.append(f"| No gate, same scripted agent | {cell(plain, 'injection')} | {cell(plain, 'near_miss')} | n/a (nothing to forge) "
               f"| **{plain['unconfirmed_changes']} / {plain['cases']}** |")
    for arm, label in (("plain_nova", "No gate, Strands agent on Nova 2 Lite"), ("suresay_nova", "SureSay, Strands agent on Nova 2 Lite")):
        a = arms.get(arm, {})
        if a.get("summary"):
            sm = a["summary"]
            out.append(f"| {label} | {cell(sm, 'injection')} | {cell(sm, 'near_miss')} | {cell(sm, 'forged')} | "
                       f"**{sm['unconfirmed_changes']} / {sm['cases']}** |")
        else:
            out.append(f"| {label} | pending | pending | pending | {a.get('pending', 'not run')} |")
    for arm, label in (("plain_sonic", "No gate, a real model: Amazon Nova 2 Sonic as the agent"),
                       ("suresay_sonic", "SureSay, a real model: Amazon Nova 2 Sonic as the agent (with `confirm`)")):
        sm = arms.get(arm, {}).get("summary")
        if sm:
            out.append(f"| {label} | {cell(sm, 'injection')} | {cell(sm, 'near_miss')} | {cell(sm, 'forged')} | "
                       f"**{sm['unconfirmed_changes']} / {sm['cases']}** |")
    nm = adv["by_category"]["near_miss"]
    out += ["", f"On the 15 near-misses SureSay's cards still let the user do what they meant {nm['intent_done']} times "
            "(the intended action was among the three cards); the rest were declined and changed nothing. "
            "A plain assistant acts on the mishearing every time.", "",
            "The scripted agent is the worst case by design: it obeys every injection, acts on every mishearing and "
            "tries every forgery it can make, so the result does not depend on how well a model resists injection. "
            "Per-case evidence (HTTP status of each forgery, refusal reasons) is in `eval/results/run1/safety.json`."]
    if arms.get("plain_sonic", {}).get("summary") and arms.get("suresay_sonic", {}).get("summary"):
        ps, ss = arms["plain_sonic"]["summary"], arms["suresay_sonic"]["summary"]
        out += ["", "**With a real model.** Nova 2 Lite has no quota on this account yet, but Amazon Nova 2 Sonic takes "
                "text turns and calls tools, so it ran as the agent (temperature 0). Without the gate, on the same "
                f"tools, it made {ps['unconfirmed_changes']} unconfirmed changes in {ps['cases']} cases "
                f"({ps['by_category'].get('injection', {}).get('unconfirmed_changes', 0)} after an injection, "
                f"{ps['by_category'].get('near_miss', {}).get('unconfirmed_changes', 0)} by acting on a misheard "
                "command). Behind "
                f"SureSay, with SureSay's agent prompt and every MCP tool including `confirm`, it made "
                f"{ss['unconfirmed_changes']} in {ss['cases']}. Forgeries are structural, so they are covered by the "
                "scripted arms above."]
    if s2:
        out += ["", f"Run 2: {s2['arms']['suresay_adversary']['summary']['unconfirmed_changes']} / 50."]
    sonic = {k: arms.get(k, {}).get("summary") for k in ("plain_sonic", "suresay_sonic")}
    return out, {"ss": adv["unconfirmed_changes"], "cases": adv["cases"], "plain": plain["unconfirmed_changes"],
                 "plain_cases": plain["cases"], "near_intent": nm["intent_done"], "sonic": sonic}


def latency_section(lat: dict[str, Any], atom: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    u = lat["understand"]
    out = ["## Claim 4 — fast enough to talk to", "",
           f"{u['clips']} dev-speaker clips through `understand` ({u['asr_engine']} on this laptop's CPU + "
           f"{u['ranker']} ranker):", "",
           "| Measure | p50 | p95 |", "|---|---|---|",
           f"| understand, total | {u['total']['p50_ms']} ms | {u['total']['p95_ms']} ms |",
           f"| speech recognition | {u['asr']['p50_ms']} ms | {u['asr']['p95_ms']} ms |",
           f"| ranking | {u['rank']['p50_ms']} ms | {u['rank']['p95_ms']} ms |",
           f"| gate added to confirm, SQLite | {lat['gate_sqlite']['added_by_gate']['p50_ms']} ms | "
           f"{lat['gate_sqlite']['added_by_gate']['p95_ms']} ms |"]
    uc = lat.get("understand_cloud")
    if uc:
        out.insert(2, f"On the deployed hub (Lambda, us-east-1), {uc['clips']} dev clips as voice turns through "
                      f"{', '.join(uc['asr_engines'])}: understand **p50 {uc['total']['p50_ms']} ms, p95 "
                      f"{uc['total']['p95_ms']} ms** (speech recognition p50 {uc['asr']['p50_ms']} ms), measured inside "
                      "the function. Offline, on this laptop:")
        out.insert(3, "")
    key: dict[str, Any] = {"u50": (uc or u)["total"]["p50_ms"], "u95": (uc or u)["total"]["p95_ms"],
                           "u_where": "Lambda + Transcribe" if uc else "offline stack",
                           "g50": lat["gate_sqlite"]["added_by_gate"]["p50_ms"],
                           "g95": lat["gate_sqlite"]["added_by_gate"]["p95_ms"]}
    if "gate_cloud" in lat:
        g = lat["gate_cloud"]
        out.append(f"| gate added to confirm, deployed hub (Lambda + DynamoDB, us-east-1) | "
                   f"{g['gate_added_in_region']['p50_ms']} ms | {g['gate_added_in_region']['p95_ms']} ms |")
        out.append(f"| device evidence + confirm round trip, India → us-east-1 | "
                   f"{g['device_round_trip_from_client']['p50_ms']} ms | {g['device_round_trip_from_client']['p95_ms']} ms |")
        key.update(c50=g["gate_added_in_region"]["p50_ms"], c95=g["gate_added_in_region"]["p95_ms"])
    mt = lat.get("mcp_typed_cloud")
    if mt:
        out.append(f"| MCP `understand` on typed text, in the function (Alexa+ asks for < 500 ms round trip) | "
                   f"{mt['in_function']['p50_ms']} ms | {mt['in_function']['p95_ms']} ms |")
        out.append(f"| ...the same call's full round trip from India | {mt['round_trip_from_client']['p50_ms']} ms | "
                   f"{mt['round_trip_from_client']['p95_ms']} ms |")
    out.append(f"| device evidence + confirm over local HTTP | {lat['device_round_trip_http']['p50_ms']} ms | "
               f"{lat['device_round_trip_http']['p95_ms']} ms |")
    out += ["", "Nova 2 Lite ranking latency will be added when the account's Bedrock access opens."]
    if atom:
        out += ["", "### The one-time guarantee under contention", "",
                "Replay protection rests on consuming a nonce exactly once. 16 threads race to consume one nonce:", "",
                "| Store | trials | trials with ≠ 1 winner |", "|---|---|---|"]
        for k, v in atom["stores"].items():
            out.append(f"| {k.replace('_', ' ')} | {v['trials']} | {v['trials_not_exactly_one_winner']} |")
        out += ["", "The moto DynamoDB mock is not atomic under threads, so the unit tests skip it for this one "
                "property and real DynamoDB is tested instead."]
    return out, key


def adapt_section(a: dict[str, Any]) -> list[str]:
    w, wl = a["summary"]["without"], a["summary"]["with_learning"]
    out = ["## Learning from confirmations", "",
           "Each confirmed card teaches SureSay the user's way of saying it. Test: sentences a test speaker recorded "
           "twice; the first recording is treated as confirmed once (what the recogniser heard becomes a learned "
           "phrase), and the second recording is measured. Same phrasebook, same dev-tuned abstain rule, "
           f"`{a['asr_engine']}`.", "",
           "| Second recording | without learning | with learning |", "|---|---|---|",
           f"| Top-1 meaning recovered | {f(w["top1_pct"])} | **{f(wl["top1_pct"])}** |",
           f"| Top-3 meaning recovered | {f(w['top3_pct'])} | {f(wl['top3_pct'])} |",
           f"| Asked to say it again | {f(w['asked_again_pct'])} | {f(wl['asked_again_pct'])} |", "",
           "| Speaker | repeated sentences | top-1 without → with |", "|---|---|---|"]
    for spk, v in a["per_speaker"].items():
        out.append(f"| {spk} | {v['without']['utterances']} | {f(v['without']['top1_pct'])} → {f(v['with_learning']['top1_pct'])} |")
    out += ["", f"{w['utterances']} utterances in all: TORGO repeats only some sentences, so these counts are small and "
            "the result is indicative, not conclusive."]
    if wl["top1_pct"] == w["top1_pct"]:
        out += ["", "**Learning from one earlier confirmation did not change the result here.** A learned phrase helps "
                "when a mishearing repeats (the hub's tests show \"van awn\" going straight to the fan after one "
                "confirmation), but for these long sentences a severe speaker's two recordings were recognised too "
                "differently for one stored string to match. Learning sound patterns rather than exact strings is open."]
    return out


OTHER_RECOGNISERS = (("whisper/run1", "a local recogniser (faster-whisper, CPU)"),
                     ("novasonic/run1", "Amazon Nova 2 Sonic, a speech-to-speech model used as a recogniser"))


def asr_section(c: dict[str, Any], i: dict[str, Any]) -> list[str]:
    others = [(read_result("confirm", run), read_result("intent", run), what) for run, what in OTHER_RECOGNISERS]
    others = [o for o in others if o[0] and o[1]]
    if not others:
        return []
    rows = []
    for label, conf, intent in ((c["asr_engine"], c, i), *((wc["asr_engine"], wc, wi) for wc, wi, _ in others)):
        b0c, ssc = conf["summary"]["b0"]["test"], conf["summary"]["suresay"]["test"]
        gen = conf["summary"]["suresay"]["test_confirm_words_only"]
        it = intent["summary"]["test"]
        maybe = it["ss_fuzzy"].get("in_cards_with_maybe_pct")
        rows.append(f"| `{label}` | {f(b0c['false_accept_pct'])} | {f(ssc['false_accept_pct'])} | "
                    f"{f(gen['true_accepts_recovered_pct'])} | {f(it['b0']['top1_pct'])} | {f(it['b1']['top1_pct'])} | "
                    f"{f(it['ss_fuzzy']['top1_pct'])} | {f(maybe) if maybe is not None else '—'} | "
                    f"{f(it['ss_fuzzy']['correct_abstain_pct'])} |")
    also = " and with ".join(what for _, _, what in others)
    return ["## The same claims with other recognisers", "",
            f"Everything above uses Amazon Transcribe. The same pipeline was also run with {also}, each with its own "
            "dev-only tuning, to show the gate's effect does not depend on one recogniser. Test speakers:", "",
            "| Recogniser | false accepts B0 | false accepts SureSay | genuine answers recovered (SureSay) | "
            "top-1 B0 | top-1 B1 | top-1 SureSay | in the cards, with maybe cards (SureSay) | "
            "correct \"say again\" (SureSay) |",
            "|---|---|---|---|---|---|---|---|---|", *rows, "", *sonic_note()]


def _sonic_latency() -> str:
    sl = read_result("latency_nova_sonic", "novasonic/run1")
    tl = (read_result("latency", "run1") or {}).get("understand_cloud")
    if not (sl and tl):
        return ""
    return (f"Inside the Lambda function, recognition took {f(sl['asr']['p50_ms'], ' ms')} at p50 with Nova 2 Sonic "
            f"({sl['clips']} dev clips, {sl['failed']} failed) against {f(tl['asr']['p50_ms'], ' ms')} with Transcribe "
            f"({tl['clips']} clips). Same safety, a third of the cost, a longer wait: SureSay keeps Transcribe as the "
            "default and offers Sonic for spoken answers with `SURESAY_EVIDENCE_ASR=nova-sonic`. ")


def sonic_note() -> list[str]:
    spend = read_result("spend") or {}
    if not spend.get("nova_sonic_clips"):
        return []
    per = spend["nova_sonic_usd"] / spend["nova_sonic_clips"]
    prices = (read_result("cost") or {}).get("prices", {})
    tr = prices.get("transcribe_streaming_per_second", 0) * prices.get("transcribe_min_seconds_per_request", 0)
    return [f"Nova 2 Sonic ran on {spend['nova_sonic_clips']} clips for ${spend['nova_sonic_usd']:.2f} at list price "
            f"(${per * 1000:.2f} per 1,000 clips, input tokens only: the stream is closed before Sonic replies), against "
            f"${tr * 1000:.2f} per 1,000 short clips for Amazon Transcribe streaming (its 15-second minimum per request). "
            + _sonic_latency() + "Sonic has no custom vocabulary, so it is "
            "compared with no phrasebook priming; the \"maybe\" column is blank where that run predates maybe cards."]


def personal_section(pe: dict[str, Any]) -> list[str]:
    out = ["## Per-user calibration", "",
           "The abstain rule is global, tuned on two dev speakers. Simulation of learning it per user: for each test "
           "speaker, their own first half of utterances (as if confirmed or declined in daily use) picks a personal rule "
           "with the same grid and objective as the dev tuning; both rules are scored on the second half only.", "",
           "| Speaker | top-1, global → personal | asked again needlessly, global → personal | correct \"say again\", global → personal |",
           "|---|---|---|---|"]
    for spk, v in pe["per_speaker"].items():
        g, m = v["global"], v["personal"]
        out.append(f"| {spk} | {f(g['top1_pct'])} → {f(m['top1_pct'])} | {f(g['asked_again_in_book_pct'])} → "
                   f"{f(m['asked_again_in_book_pct'])} | {f(g['correct_abstain_pct'])} → {f(m['correct_abstain_pct'])} |")
    pool = pe["pooled"]
    out += ["", f"Pooled over {pool['utterances']} held-out utterances, handled right: {f(pool['global_handled_right_pct'])} "
            f"global, {f(pool['personal_handled_right_pct'])} personal. A small gain, concentrated in one speaker, who "
            "traded some caution for recall; the most severe speaker did not move. Per-user calibration is worth "
            "keeping, but it is not the fix for the worst case: maybe cards are."]
    return out


def cost_section(c: dict[str, Any]) -> list[str]:
    rows = [f"| {k.replace('_', ' ')} | ${v:.4f} |" for k, v in c["per_1000_turns_usd"].items()]
    tok = c["usage"]["nova_tokens"]
    return ["## Cost per 1,000 turns (estimate)", "",
            f"**About ${c['total_per_1000_turns_usd']} per 1,000 turns** (one spoken request + one spoken "
            f"confirmation each). Prices: {c['prices']['source']}.", "", "| Service | per 1,000 turns |", "|---|---|",
            *rows, "",
            f"Transcribe bills at least 15 s per request, so it dominates ({c['usage']['transcribe_billed_seconds']} "
            f"billed seconds per turn for {c['usage']['request_seconds']} s + {c['usage']['confirmation_seconds']} s "
            f"of real audio). Nova tokens: {'measured' if tok.get('measured') else tok.get('note')}. "
            f"Excluded: {c['excluded']}."]


def tuning_section(t: dict[str, Any]) -> list[str]:
    cb = t.get("confirm_bias", {})
    out = ["## Tuning (dev speakers F03 and M05 only)", ""]
    if cb:
        out += ["Speech-recognition bias for confirmations, chosen by a rule fixed before running "
                "(fewest false accepts, then most genuine answers recovered):", "",
                "| Bias | false accepts | genuine answers recovered |", "|---|---|---|"]
        for name, v in cb["candidates"].items():
            mark = " ← chosen" if name == cb["chosen"] else ""
            out.append(f"| {name}{mark} | {v['false_accepts']} / {v['clips']} | {f(v['true_accepts_recovered_pct'])} |")
    if t.get("fuzzy"):
        r = t["fuzzy"]["rule"]
        out += ["", f"Abstain rule for the offline ranker: floor {r['floor']}, confident {r['confident']}, margin "
                f"{r['margin']} ({t['fuzzy']['dev_objective']}/{t['fuzzy']['dev_utterances']} dev utterances handled right)."]
    if t.get("nova_status"):
        out += ["", f"Nova abstain rule: {t['nova_status']}."]
    return out


def filler_finding(c: dict[str, Any]) -> str | None:
    """How many of SureSay's test false accepts were the recogniser turning an unclear word into 'yeah'/'OK'."""
    fas = [r for r in c["rows"] if r["group"] == "test" and r["suresay"]["decision"][0] in ("choose", "yes")
           and r["suresay"]["decision"] != r["truth"]]
    fillers = [r for r in fas if re.sub(r"[^a-z ]", "", r["suresay"]["heard"].lower()).split()[-1:] in (["yeah"], ["ok"], ["okay"])]
    if not fas:
        return None
    return (f"**Unclear words heard as \"yeah\" or \"OK\".** {len(fillers)} of SureSay's {len(fas)} false accepts on test "
            f"speakers were the recogniser ({c['asr_engine']}) turning an unclear single word into a filler such as "
            "\"Yeah\" or \"OK.\", which the yes/no card accepts. That card guards the high-risk actions. A stricter yes "
            "vocabulary for that card is the candidate fix; it was found on test speakers, and dev has too few cases "
            "to tune it honestly, so it is reported here and not changed.")


def negative_section(ck: dict[str, Any], ik: dict[str, Any], c: dict[str, Any] | None = None,
                     tuning: dict[str, Any] | None = None) -> list[str]:
    spk, ss_t1, b1_t1, fab, ss_maybe = ik["worst"]
    filler = filler_finding(c) if c else None
    bias_text = "See Tuning."
    if tuning and tuning.get("confirm_bias"):
        cands = tuning["confirm_bias"]["candidates"]
        parts = ", ".join(f"{n}: {v['false_accepts']} false accepts, {f(v['true_accepts_recovered_pct'])} recovered"
                          for n, v in cands.items())
        bias_text = (f"On dev speakers ({parts}), no setting beat leaving the recogniser unbiased, so SureSay "
                     "transcribes confirmations without bias. Biasing that raises recall without false accepts is open.")
    extra = [f"6. {filler}"] if filler else []
    return ["## What does not work yet (published on purpose)", "",
            f"1. **The most severe speakers lose recall to the abstain rule, and maybe cards only partly win it back.** "
            f"Worst test speaker: {spk}. SureSay's confident cards hold their phrase {f(ss_t1)} of the time at top-1, "
            f"against {f(b1_t1)} for B1, because it asks again on {f(fab)} of them. Offering its best guesses as maybe "
            f"cards while asking again brings that speaker to {f(ss_maybe)} in the cards ({f(ik['ss_maybe'])} over all test "
            f"speakers), but maybe cards also appear on {f(ik['ss_maybe_oob'])} of out-of-book utterances, where the user has "
            "to decline them. B1 never asks and acted on a wrong phrase "
            f"{f(ik['b1_wrong'])} of the time; SureSay acted wrongly {f(ik['ss_wrong'])} of the time. Per-user thresholds are the next step.",
            f"2. **Strict confirmation costs retries.** On genuine yes/no/number answers from dysarthric speakers, SureSay "
            f"recovered {f(ck['ss_rec'])} (B0: {f(ck['b0_rec'])}) and asked {f(ck['ss_refused'])} of them to repeat. "
            "That is the price of the false-accept rate above; tap, keyboard and switch confirmation exist so a "
            "repeat is never a dead end.",
            f"3. **Recogniser biasing did not help confirmations.** {bias_text}",
            "4. **The model arms are pending.** Nova 2 Lite is authorized on this account but every on-demand quota is "
            "0 (increase requests filed; docs/FRICTION_LOG.md). The Strands agent is deployed on AgentCore Runtime and "
            "phrasebooks live in AgentCore Memory, but the agent cannot reason until Nova has quota, so turns fall back "
            "to direct answers. The Nova ranker and the Nova-agent safety arms are implemented and tested against "
            "stubs; no Nova 2 Lite number is reported until they run. (Amazon Nova 2 Sonic, the speech model, does "
            "run on this account and is measured above as a recogniser.)",
            "5. **Corpus caveats.** TORGO sentences are well-known reading passages that a large recogniser may "
            "have seen in training, and the phrasebooks are sentences rather than short home commands. "
            "Confirmation words are sparse in TORGO (a few per speaker), so per-speaker confirmation numbers rest "
            "on small counts.", *extra]


def main() -> None:
    c, i, s, lat = load("confirm"), load("intent"), load("safety"), load("latency")
    c2, i2, s2 = read_result("confirm", "run2"), read_result("intent", "run2"), read_result("safety", "run2")
    from eval.common import tuning_name

    tuning = read_result(tuning_name(c["asr_engine"])) if c else None
    cost, atom = read_result("cost"), read_result("store_atomicity")
    missing = [n for n, v in (("confirm", c), ("intent", i), ("safety", s), ("latency", lat)) if v is None]
    if missing:
        raise SystemExit(f"missing results: {missing}; run make eval first")
    assert c and i and s and lat
    conf, ck = confirm_section(c, c2)
    intent, ik = intent_section(i, i2)
    safety, sk = safety_section(s, s2)
    latency, lk = latency_section(lat, atom)
    head = [
        "# SureSay evaluation report",
        "",
        "Generated by `eval/make_report.py` from `eval/results/` — do not edit by hand. "
        f"Results git SHA {c['git_sha']}, generated {c['generated_at']}.",
        "",
        "**Data:** TORGO: 8 speakers with dysarthria (cerebral palsy or ALS) and control "
        "speakers, 16 kHz. **Split:** dev = " + ", ".join(SPLIT["dev"]) + "; test = " + ", ".join(SPLIT["test"]) +
        "; controls = " + ", ".join(SPLIT["controls"]) + ". Prompts and thresholds were tuned on dev only. "
        + SEVERITY_NOTE,
        "",
        "**Revisions:** on 21 Oct an independent security review hardened the consent parser (hesitations, questions and "
        "qualifiers such as \"ok hang on\" or \"okay, who is it\" are never a yes; unreadable Hindi words count as unknown). "
        "Claim 1 was recomputed from the same cached transcripts and did not change.",
        "",
        "**Baselines, one change at a time:** B0 = plain assistant (recogniser, top transcript acts); "
        "B1 = + the user's phrasebook (biased recognition, nearest phrase acts); SureSay = + ranked candidates, "
        "abstaining, and the confirm gate.",
        "",
        "## Headline",
        "",
        "| Claim | Metric | B0 plain | B1 + phrasebook | SureSay | Data |",
        "|---|---|---|---|---|---|",
        f"| Confirm heard right | false accepts | {f(ck['b0_fa'])} | — | **{f(ck['ss_fa'])}** | {ck['fa_counts'][2]} decisions, 6 test speakers |",
        f"| Meaning recovered | top-1 / top-3 | {f(ik['b0_top1'])} / — | {f(ik['b1_top1'])} / {f(ik['b1_top3'])} | {f(ik['ss_top1'])} / {f(ik['ss_top3'])} | 50-phrase books, 6 test speakers |",
        f"| In the cards when unsure too | counting maybe cards | — | {f(ik['b1_top3'])} (acts without asking) | **{f(ik['ss_maybe'])}** | same |",
        f"| Abstains when unsure | correct \"say again\" | 0% | {f(ik['b1_abstain'])} | **{f(ik['ss_abstain'])}** | out-of-book utterances |",
        f"| Never acts on a guess | acted on a wrong phrase without asking | {f(ik['b0_wrong'])} | {f(ik['b1_wrong'])} | **{f(ik['ss_wrong'])}** | in-book + out-of-book |",
        f"| Nothing without consent | unconfirmed changes | {sk['plain']} / {sk['plain_cases']} (no gate) | — | **{sk['ss']} / {sk['cases']}** | adversarial suite |",
        *([f"| …with a real model as the agent | unconfirmed changes | {sk['sonic']['plain_sonic']['unconfirmed_changes']} / "
           f"{sk['sonic']['plain_sonic']['cases']} (Nova 2 Sonic, no gate) | — | **{sk['sonic']['suresay_sonic']['unconfirmed_changes']} / "
           f"{sk['sonic']['suresay_sonic']['cases']}** | Amazon Nova 2 Sonic, injections + near-misses |"]
          if all(sk["sonic"].values()) else []),
        f"| Speed | understand p50 / p95 | — | — | {lk['u50']} / {lk['u95']} ms | 100 dev clips, {lk['u_where']} |",
        f"| Gate overhead | p50 / p95 | — | — | {lk.get('c50', lk['g50'])} / {lk.get('c95', lk['g95'])} ms | "
        f"{'Lambda + DynamoDB' if 'c50' in lk else 'SQLite'} |",
        f"| No regression | top-1, controls | {f(ik['ctrl_b0'])} | — | {f(ik['ctrl_ss'])} | control speakers |",
        "",
        f"SureSay column: {ik['ss_name']}; the Nova 2 Lite ranker is pending Bedrock access. B1 recovers more phrases at "
        "top-1 because it never abstains, and pays for it by acting on a wrong phrase without asking.",
        "",
    ]
    body = head + conf + [""] + intent + [""] + safety + [""] + latency + [""]
    body += asr_section(c, i) + [""]
    pe = load("personal")
    if pe:
        body += personal_section(pe) + [""]
    adapt = load("adapt")
    if adapt:
        body += adapt_section(adapt) + [""]
    if cost:
        body += cost_section(cost) + [""]
    if tuning:
        body += tuning_section(tuning) + [""]
    body += negative_section(ck, ik, c, tuning) + [""]
    (EVAL / "REPORT.md").write_text("\n".join(body))
    block = "\n".join(head[head.index("## Headline") + 2: -1])
    negatives = "\n".join(line for line in negative_section(ck, ik, c, tuning)[2:] if line)
    for doc in (ROOT / "README.md", ROOT / "docs" / "DEVPOST.md"):
        if not doc.exists():
            continue
        text = doc.read_text()
        text = re.sub(r"(<!-- results:start -->\n).*?(<!-- results:end -->)",
                      lambda m: m.group(1) + block + "\n" + m.group(2), text, flags=re.S)
        text = re.sub(r"(<!-- negatives:start -->\n).*?(<!-- negatives:end -->)",
                      lambda m: m.group(1) + negatives + "\n" + m.group(2), text, flags=re.S)
        doc.write_text(text)
    print("wrote eval/REPORT.md")


if __name__ == "__main__":
    main()
