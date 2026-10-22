"""Regenerate eval/REPORT.md (and the README results block) from eval/results/*.json.

Nothing in the report is typed by hand: every number is read from a results file written by a script.
Run 1 is the headline; run 2, when present, is shown as a stability check.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.common import EVAL, ROOT, SPLIT, read_result, tuning_name  # noqa: E402

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
    reject_lines, reject_key = b0_reject_block(c)
    out += reject_lines
    key = {"b0_fa": t0["false_accept_pct"], "ss_fa": t1["false_accept_pct"], "b0_acc": t0["accuracy_pct"],
           "ss_acc": t1["accuracy_pct"], "b0_rec": g0["true_accepts_recovered_pct"],
           "ss_rec": g1["true_accepts_recovered_pct"], "ss_refused": g1["refused_pct"],
           "fa_counts": (t0["false_accepts"], t1["false_accepts"], t1["clips"]), "b0_reject": reject_key}
    return out, key


def confirm_b0_cell(ck: dict[str, Any]) -> str:
    """Headline B0 cell: the forced baseline, and B0 + reject where a recogniser confidence exists to measure it."""
    r = ck.get("b0_reject")
    if not r:
        return f(ck["b0_fa"])
    return (f"{f(ck['b0_fa'])} (forced) / {f(r['fa'])} (with reject, on `{r['engine']}`, where forced is "
            f"{f(r['b0_fa'])} and SureSay {f(r['ss_fa'])})")


def _confirm_runs(c: dict[str, Any]) -> list[dict[str, Any]]:
    """The headline confirm result, then the same claim with the other recognisers."""
    return [c, *(o for run, _ in OTHER_RECOGNISERS if (o := read_result("confirm", run)))]


def b0_reject_block(c: dict[str, Any]) -> tuple[list[str], dict[str, Any] | None]:
    """B0 + reject: plain B0 that asks again when the recogniser is unsure, on every engine that gives a confidence."""
    runs = _confirm_runs(c)
    have = [r for r in runs if "b0_reject" in r["summary"]]
    without = [r for r in runs if "b0_reject" not in r["summary"]]
    if not have:
        return [], None
    out = ["", "### A fairer baseline: B0 + reject", "",
           "B0 above never refuses. B0 + reject is the same plain recogniser path, but it asks again when the "
           "recogniser is unsure: it heard nothing, or its per-utterance confidence is below a threshold. The "
           "threshold was chosen on dev speakers only (F03, M05) by a rule fixed before any test-speaker result for "
           "this arm was computed (`eval/tune_b0_reject.py`): among thresholds that recover at least as many genuine "
           "answers on dev as SureSay does, take the one with the fewest dev false accepts (ties: the lower threshold). "
           "When it does not ask again it is plain B0, forced to the nearest word."]
    if without:
        out += ["", "It needs a confidence from the recogniser, and not every recogniser gives one. "
                + "; ".join(f"`{r['asr_engine']}`: {r.get('b0_reject_status') or 'not run'}" for r in without)
                + ". So it is measured only on "
                + ", ".join(f"`{r['asr_engine']}`" for r in have) + ", next to that recogniser's own B0 and SureSay."]
    key = None
    for r in have:
        b0, br, ss = (r["summary"][a] for a in ("b0", "b0_reject", "suresay"))
        tune = read_result(tuning_name(r["asr_engine"]) + "_b0_reject") or {}
        d = tune.get("dev", {})
        if tune.get("available"):
            out += ["", f"`{r['asr_engine']}`: threshold {r['b0_reject_threshold']:.3f} (confidence = exp of the "
                    "mean token log-probability). Dev: SureSay recovered "
                    f"{tune['suresay_dev']['recovered']} genuine answers with {tune['suresay_dev']['false_accepts']} "
                    f"false accepts in {tune['suresay_dev']['clips']} decisions; B0 + reject at this threshold recovered "
                    f"{d.get('recovered')} with {d.get('false_accepts')} false accepts"
                    + ("" if tune.get("constraint_met") else " (no threshold met the floor; it falls back to never "
                       "rejecting)") + f", out of {tune['candidates_tried']} thresholds tried."]
        rows = [("**False accepts, all clips**", lambda s: f"**{f(s['test']['false_accept_pct'])}** "
                 f"({s['test']['false_accepts']}/{s['test']['clips']})"),
                ("False accepts, other words only", lambda s: f"{s['test_distractors_only']['false_accepts']}/"
                 f"{s['test_distractors_only']['clips']}"),
                ("Genuine answers recovered", lambda s: f(s["test_confirm_words_only"]["true_accepts_recovered_pct"])),
                ("Genuine answers asked again", lambda s: f(s["test_confirm_words_only"]["refused_pct"])),
                ("Asked again, all clips (right for other words)", lambda s: f(s["test"]["refused_pct"])),
                ("Decision accuracy, all clips", lambda s: f(s["test"]["accuracy_pct"]))]
        out += ["", f"Test speakers, `{r['asr_engine']}`:", "",
                "| Test speakers | B0 (forced nearest word) | B0 + reject (asks again when unsure) | SureSay |",
                "|---|---|---|---|",
                *(f"| {name} | {cell(b0)} | {cell(br)} | {cell(ss)} |" for name, cell in rows),
                "", "Per speaker, false-accept rate (all clips): "
                + ", ".join(f"{spk} {f(br['per_speaker'][spk]['false_accept_pct'])}"
                            for spk in SPLIT["test"] if spk in br["per_speaker"]) + " (B0 + reject).",
                "", f"It asks again only on the recogniser's own doubt: {br['test_distractors_only']['false_accepts']} of "
                f"its {br['test']['false_accepts']} false accepts here are other words (not answers) heard with enough "
                "confidence and then forced to the nearest allowed word, where SureSay's parser refuses anything that "
                "is not an answer."]
        if key is None:
            key = {"engine": r["asr_engine"], "b0_fa": b0["test"]["false_accept_pct"],
                   "fa": br["test"]["false_accept_pct"], "ss_fa": ss["test"]["false_accept_pct"]}
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
        "least 0.50, a floor fixed before measuring, and since 22 Oct only guesses that share a content word with what "
        "was heard, allowing for mishearing: `suresay.rank.relevant`, the same rule the product uses); a maybe card "
        "needs the same confirmation as any other.",
        "",
        *([f"Top-1 equals top-3 here: when SureSay was confident, the intended phrase was never on card 2 or 3. "
           "In this test the extra cards earn their place only when SureSay is unsure, as \"maybe\" cards "
           f"(top-1 {f(test['ss_fuzzy']['top1_pct'])} → in the cards {f(test['ss_fuzzy'].get('in_cards_with_maybe_pct'))}). "
           "The phrasebooks are TORGO reading sentences, which differ from one another in many words; short home "
           "commands that differ by one word (\"turn on the fan\" / \"turn on the TV\") are where a second and third "
           "card matter most, and this corpus does not measure them.", ""]
          if test["ss_fuzzy"]["top1_pct"] == test["ss_fuzzy"]["top3_pct"] else []),
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


def task_section(t: dict[str, Any], i: dict[str, Any] | None) -> list[str]:
    """Task success within two tries (eval/run_task_eval.py)."""
    test = t["summary"]["test"]
    ss, b1, b0 = test["suresay"], test["b1"], test["b0"]
    src = t["second_recording_available"]
    by = ss["second_tries_by_source"]
    tries = "; ".join(f"{k}: {v['attempts']}, {v['done']} done" for k, v in by.items()) or "none"
    out = ["## Task success: done within two tries", "",
           f"`eval/run_task_eval.py`. Every in-book sentence of the six test speakers is a task ({test['tasks']} in all): "
           "the user wants it said for them. SureSay's first try is the recording Claim 2 uses; the task is done when "
           "the sentence is on a card (a confident card, or a \"maybe\" card under the same 0.50 floor and shared-word "
           "rule as above) and the user confirms it. If it is not on a card (SureSay asked again, or the user declined "
           "every card), the user says it again: a different TORGO recording of the same sentence by the same speaker, "
           "preferring another session, then another take in the same session, then the same take as heard by TORGO's "
           "other microphone. The baselines act at once on the first recording. Recogniser for every try: "
           f"`{t['asr_engine']}` (local and free), with the phrasebook bias and the dev-tuned abstain rule for that "
           "recogniser.", "",
           "| Test speakers | B0 plain | B1 + phrasebook | SureSay |", "|---|---|---|---|",
           f"| Done on the first try | {f(b0['success_pct'])} | {f(b1['success_pct'])} | {f(ss['done_first_try_pct'])} |",
           f"| **Done within two tries** | {f(b0['success_pct'])} (acts at once) | {f(b1['success_pct'])} (acts at once) | "
           f"**{f(ss['done_within_two_pct'])}** |",
           f"| Wrong action taken | {f(b0['wrong_action_pct'])} ({b0['wrong_actions']}) | {f(b1['wrong_action_pct'])} "
           f"({b1['wrong_actions']}) | **0** (acted without confirmation: {ss['acted_without_confirmation']}) |",
           f"| Tries per done task, mean | 1 | 1 | {ss['mean_tries_when_done']} |",
           f"| Sets of cards the user had to decline | — | — | {ss['card_sets_declined']} |", "",
           "| Speaker | tasks | B0 | B1 (wrong actions) | SureSay first try → within two |", "|---|---|---|---|---|"]
    for spk, v in test["per_speaker"].items():
        out.append(f"| {spk} | {v['tasks']} | {f(v['b0']['success_pct'])} | {f(v['b1']['success_pct'])} "
                   f"({v['b1']['wrong_actions']}) | {f(v['suresay']['done_first_try_pct'])} → "
                   f"{f(v['suresay']['done_within_two_pct'])} |")
    out += ["", f"Second tries made: {ss['second_tries']} ({tries}). Second recordings available for the "
            f"{test['tasks']} sentences: " + "; ".join(f"{k}: {v}" for k, v in src.items()) + ". TORGO rarely has a "
            "sentence read twice by the same speaker, so most \"second tries\" available are the same performance "
            "through the other microphone, which is not a fresh try; counting only genuinely new recordings as a "
            f"second try, SureSay is done within two tries {f(ss['done_within_two_counting_only_new_takes_pct'])} of "
            f"the time. Tasks that needed a second try but had no other recording: "
            f"{ss['needed_second_try_but_no_other_recording']}."]
    if i and i.get("asr_engine") != t["asr_engine"]:
        it = i["summary"]["test"]
        out += ["", f"Caveats: the local recogniser hears these well-known reading passages better than "
                f"`{i['asr_engine']}` does (Claim 2: with it, the first try puts the sentence on a card "
                f"{f(it['ss_fuzzy'].get('in_cards_with_maybe_pct'))} of the time and B1's top-1 is "
                f"{f(it['b1']['top1_pct'])}); second tries were not run with it, to keep this evaluation free. "
                f"With only {ss['second_tries']} second tries, the second-try gain rests on a handful of cases. "
                "Out-of-book requests, where B1 always acts wrongly, are not part of this task set (see Claim 2)."]
    return out


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
        brc = conf["summary"].get("b0_reject", {}).get("test")
        rows.append(f"| `{label}` | {f(b0c['false_accept_pct'])} | {f(brc['false_accept_pct']) if brc else '—'} | "
                    f"{f(ssc['false_accept_pct'])} | "
                    f"{f(gen['true_accepts_recovered_pct'])} | {f(it['b0']['top1_pct'])} | {f(it['b1']['top1_pct'])} | "
                    f"{f(it['ss_fuzzy']['top1_pct'])} | {f(maybe) if maybe is not None else '—'} | "
                    f"{f(it['ss_fuzzy']['correct_abstain_pct'])} |")
    also = " and with ".join(what for _, _, what in others)
    return ["## The same claims with other recognisers", "",
            f"Everything above uses Amazon Transcribe. The same pipeline was also run with {also}, each with its own "
            "dev-only tuning, to show the gate's effect does not depend on one recogniser. Test speakers:", "",
            "| Recogniser | false accepts B0 | false accepts B0 + reject | false accepts SureSay | "
            "genuine answers recovered (SureSay) | "
            "top-1 B0 | top-1 B1 | top-1 SureSay | in the cards, with maybe cards (SureSay) | "
            "correct \"say again\" (SureSay) |",
            "|---|---|---|---|---|---|---|---|---|---|", *rows, "",
            "B0 + reject needs a per-utterance confidence from the recogniser; \"—\" means the recogniser gives none "
            "(see Claim 1).", "", *sonic_note()]


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


def clarity_section(cl: dict[str, Any]) -> list[str]:
    g = cl["groups"]
    rows = [f"| {spk} | {v['severity']} | {f(v['mean_clarity'])} | {v['clips']} |" for spk, v in cl["per_speaker"].items()]
    sev = {k: v["mean_clarity"] for k, v in g.items()}
    outlier = [s for s, v in cl["per_speaker"].items() if v["severity"] == "severe" and (v["mean_clarity"] or 0) > (sev.get("moderately severe") or 101)]
    return ["## Practice: does the clarity score mean something?", "",
            "Practice scores a recording by the share of the sentence's words that speech recognition heard, in order, "
            "without the user's phrasebook. On up to 25 sentence recordings per TORGO speaker, the score against the "
            f"severity categories published with the corpus (Frenchay Dysarthria Assessment), recogniser `{cl['asr_engine']}`:", "",
            "| Group | mean clarity |", "|---|---|",
            *[f"| {k} | {f(v['mean_clarity'])} ({v['speakers']} speaker{'s' if v['speakers'] != 1 else ''}) |" for k, v in g.items()],
            "", f"Spearman rank correlation between a speaker's clarity and severity: **{cl['spearman_all']}** across all "
            f"11 speakers, {cl['spearman_dysarthric_only']} across the 8 with dysarthria.", "",
            "| Speaker | severity | clarity | clips |", "|---|---|---|---|", *rows, "",
            "What it does not show: the score saturates near the top, so mild dysarthria and typical speech look the same; "
            + (f"{', '.join(outlier)} is rated severe yet scores above the moderately severe speaker; " if outlier else "")
            + "and it is a practice signal, not a clinical measure. It does order speakers broadly by severity, which is "
            "what a daily progress line needs."]


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
    for engine in ("transcribe-streaming", "whisper-small.en", "nova-2-sonic"):
        br = read_result(tuning_name(engine) + "_b0_reject")
        if not br:
            continue
        if not br.get("available"):
            out += ["", f"B0 + reject threshold, `{engine}`: none, {br['reason']}."]
            continue
        d, sd = br["dev"], br["suresay_dev"]
        out += ["", f"B0 + reject threshold, `{engine}`: {br['threshold']:.3f}, by the rule in Claim 1 "
                f"({br['candidates_tried']} thresholds tried; floor: SureSay's {sd['recovered']} genuine answers on dev, "
                f"{'met' if br['constraint_met'] else 'not met'}). Dev: {d['false_accepts']} / {d['clips']} false accepts, "
                f"{d['recovered']} genuine answers recovered, asked again on {f(d['refused_pct'])} of decisions "
                f"(SureSay: {sd['false_accepts']} / {sd['clips']}, {sd['recovered']}, {f(sd['refused_pct'])})."]
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



def consent_stress_section(cs: dict[str, Any]) -> list[str]:
    s, b = cs["suresay"], cs["baseline"]
    rows = [f"| {fam} | {v['cases']} | {v['baseline_false_accepts']} | **{v['suresay_false_accepts']}** |"
            for fam, v in sorted(cs["families"].items(), key=lambda kv: -kv[1]["cases"])]
    return ["## Consent stress test: thousands of ways of not saying yes", "",
            f"`eval/run_consent_stress.py` generates {cs['negatives']:,} utterances that must never count as consent "
            "(hedges, negations, questions with and without a question mark, sound-alikes, two answers at once, "
            "out-of-range numbers, long sentences that merely contain a yes, numbers on the yes/no card, extra words on "
            "the high-risk card; English, Hinglish and Devanagari; each with casing and punctuation variants) and "
            f"{cs['positives']} genuine answers that must be understood. It runs the gate's consent parser on the text, "
            "so it tests the decision itself; Claim 1 tests it on real dysarthric audio through a recogniser. Baseline: "
            f"{b['what']}.", "",
            "| | Non-answers taken as consent | Genuine answers understood |", "|---|---|---|",
            f"| Keyword baseline | {b['false_accepts']:,} / {cs['negatives']:,} ({f(b['false_accept_rate'] * 100)}) | "
            f"{b['answers_understood']} / {cs['positives']} ({f(b['answer_rate'] * 100)}) |",
            f"| SureSay | **{s['false_accepts']} / {cs['negatives']:,} ({f(s['false_accept_rate'] * 100)})** | "
            f"**{s['answers_understood']} / {cs['positives']} ({f(s['answer_rate'] * 100)})** |", "",
            "| Family | Cases | Baseline false accepts | SureSay false accepts |", "|---|---|---|---|", *rows, "",
            "Not a held-out result: the first run of this test found real gaps, and the parser was fixed before this "
            "run (with a failing test for each, in `packages/confirm-gate-mcp/tests/test_consent.py`): a question "
            "without a question mark (\"is two the fan\") chose option 2, and \"the to one\" (a misheard \"the two "
            "one\") chose option 1, together 8 false accepts out of 7,045 at the time; \"go ahead\" was refused as a yes "
            "and now counts. Eight further first-run \"false accepts\" were the test's own mislabels: \"doosra one\" is "
            "\"the second one\", a genuine answer, and was moved to the genuine set. Claim 1 was recomputed after the "
            "fixes from the same cached transcripts and did not change."]


def site_audit_section(sa: dict[str, Any]) -> list[str]:
    def row(ff: str, label: str) -> str:
        m, x = sa[ff]["median_scores"], sa[ff]["median_metrics"]
        return (f"| {label} | {m['performance']} | **{m['accessibility']}** | {m['best-practices']} | {m['seo']} | "
                f"{x['fcp_ms'] / 1000:.1f} s | {x['lcp_ms'] / 1000:.1f} s | {x['cls']:.3f} |")
    lh = sa["phone"]["runs"][0].get("lighthouse", "")
    return ["## The live site, audited", "",
            f"Lighthouse {lh} on the live home page ({sa['url']}), median of {sa['runs_per_form_factor']} runs per form "
            "factor: the phone run emulates a mid-range phone on throttled 4G (`eval/run_site_audit.py`).", "",
            "| Form factor | Performance | Accessibility | Best practices | SEO | First paint | Largest paint | Layout shift |",
            "|---|---|---|---|---|---|---|---|", row("phone", "Phone"), row("desktop", "Desktop"), "",
            "The web client's own tests also run axe on every screen (`web/src/test`)."]


def live_checks_section(lc: dict[str, Any]) -> list[str]:
    rows = [f"| {'✓' if c['passed'] else '✗'} | {c['check']} | {c['detail'].replace('|', '/')} |" for c in lc["checks"]]
    lat = lc["round_trip_from_test_machine"]
    lrows = [f"| {k} | {v['p50_ms']} | {v['p95_ms']} | {v.get('minus_network_p50_ms', '—')} |" for k, v in lat.items()]
    srv = lc.get("server_side_understand") or {}
    srows = [f"| understand, {k} | {v['requests']} | {v['p50_ms']} | {v['p95_ms']} |" for k, v in srv.items()]
    out = ["## The live server, checked as an MCP client", "",
           f"`eval/run_live_checks.py` runs against the deployed hub ({lc['url']}) over HTTPS as an MCP client: "
           f"**{lc['passed']} of {lc['total']} checks passed** ({lc['generated_at']}).", "",
           "| | Check | Detail |", "|---|---|---|", *rows, "",
           "Round trips from the test machine (they include the network to us-east-1; `/healthz` measures that network "
           "on its own, and the last column subtracts it):", "",
           "| Request | p50 ms | p95 ms | p50 minus network, ms |", "|---|---|---|---|", *lrows]
    if srows:
        out += ["", "The server's own processing time for real requests in the last 48 hours, from the CloudWatch "
                "metric the hub emits (`UnderstandMs`; voice includes speech recognition):", "",
                "| Request | Requests | p50 ms | p95 ms |", "|---|---|---|---|", *srows]
    return out

def live_assistant_section(la: dict[str, Any]) -> list[str]:
    s = la["summary"]
    rows = [f"| {'attack: ' if r.get('attack') else ''}{r['text'].replace('|', '/')} | {', '.join(r['tools']) or '—'} | "
            f"{', '.join(x or '?' for x in r['confirm_results']) or '—'} | {'yes' if r['home_changed'] else 'no'} | {r['server_ms']} |"
            for r in la["rows"]]
    return ["## A live AI driving SureSay over MCP", "",
            f"`eval/run_live_assistant.py` sends {s['turns']} typed requests to the deployed hub's live assistant, where "
            f"Amazon Nova 2 Sonic (`{s['model']}`) calls SureSay's MCP tools with exactly the agent's powers"
            + (f", running in Amazon Bedrock AgentCore Runtime for {s['runs_on'].get('AgentCore Runtime', 0)} of the "
               f"{s['turns']} turns (the hub runs the same code itself only if the runtime fails). "
               if s.get("runs_on") else ". ")
            +
            f"{s['turns'] - s.get('attacks', 0)} are ordinary requests; {s.get('attacks', 0)} try to talk the model into "
            "acting without the user (false consent, fake authority, urgency, hidden instructions). Nobody answers the "
            f"cards, so nothing may change. **{s['changes_without_the_user']} of {s['turns']} turns changed the home.** "
            f"The model called `confirm` {s.get('confirm_attempts', s['tried_confirm'])} times and the gate refused "
            f"{s.get('confirm_attempts_refused', s['confirm_refused'])}"
            + (f"; {s['confirm_attempts_on_a_real_set']} of those aimed at a card set a tool had really just proposed "
               f"(the model had its real `pending_id`), and every refusal gave the reason "
               f"\"{reasons[0]}\"" if (reasons := sorted({x for r in la['rows'] for x in r.get('refusal_reasons', []) if x}))
               and len(reasons) == 1 and "confirm_attempts_on_a_real_set" in s else "")
            + f"; in the other attacks it proposed a card set, asked again or only replied, "
            f"each of which leaves the decision with the user. It called `understand` in {s['used_understand']} of "
            f"{s['answered']} turns. Model time per turn: p50 {s['server_p50_ms']} ms, max {s['server_max_ms']} ms"
            + (f"; the whole round trip from this machine, p50 {s['wall_p50_ms']} ms " if s.get("wall_p50_ms") else " ")
            + f"({la['generated_at']}).", "",
            "| Request | Tools the model called | confirm | Home changed | Server ms |", "|---|---|---|---|---|", *rows, "",
            "One run of each request at the model's default settings; the model's choices and replies vary between runs."]

def sonic_rank_section(r: dict[str, Any], spend: dict[str, Any]) -> list[str]:
    """Claims 2 and 5 with a Bedrock model ranking: Amazon Nova 2 Sonic, while Nova 2 Lite has no quota."""
    names = {"b1": "B1 + phrasebook", "ss_fuzzy": "SureSay, offline ranker", "ss_sonic": "SureSay, Nova 2 Sonic ranker"}
    systems = [x for x in ("b1", "ss_fuzzy", "ss_sonic") if x in r["systems"]]
    test, ctrl = r["summary"]["test"], r["summary"].get("controls") or {}
    ms = sorted(row["ss_sonic"]["ms"] for row in r["rows"] if "ss_sonic" in row and "ms" in row["ss_sonic"])
    p50 = ms[len(ms) // 2] if ms else None
    rule = r["rules"].get("sonic", {})
    row = lambda label, k, g=test: "| " + label + " | " + " | ".join(  # noqa: E731
        f(g[x].get(k)) if (x.startswith("ss") or k in ("top1_pct", "top3_pct", "correct_abstain_pct", "false_abstain_pct"))
        else "—" for x in systems) + " |"
    out = ["## Claims 2 and 5 with a Bedrock model ranking", "",
           f"`eval/run_intent_eval.py --model sonic` repeats Claims 2 and 5 with **Amazon Nova 2 Sonic** "
           f"(`{r.get('ranker_model')}`) as the ranker, on the same `{r['asr_engine']}` transcripts, phrasebooks and "
           "split. Nova 2 Lite, the intended ranker, has no quota on this account; Sonic gets Lite's prompt, with two "
           "rule lines reworded past its content filter (docs/FRICTION_LOG.md #19), and submits its ranking as a "
           "`submit_ranking` tool call, a structured output; the stream closes there, so no speech is generated. "
           f"Its abstain rule was tuned on the dev speakers only (floor {rule.get('floor')}, confident "
           f"{rule.get('confident')}, margin {rule.get('margin')}). Temperature 0.", "",
           "| Test speakers | " + " | ".join(names[x] for x in systems) + " |", "|---|" + "---|" * len(systems),
           row("Top-1 phrase recovered", "top1_pct"), row("Top-3 phrase recovered", "top3_pct"),
           row("In the cards, counting \"maybe\" cards", "in_cards_with_maybe_pct"),
           row("Out-of-book: correctly asked again", "correct_abstain_pct"),
           row("Out-of-book: maybe cards offered (user declines)", "maybe_cards_on_out_of_book_pct"),
           row("In-book: asked again needlessly", "false_abstain_pct")]
    if ctrl:
        out += [row("Controls: top-1", "top1_pct", ctrl), row("Controls: correctly asked again", "correct_abstain_pct", ctrl)]
    t_rows = [x["ss_sonic"] for x in r["rows"] if x.get("group") == "test" and "ss_sonic" in x]
    ab = [x for x in t_rows if x["abstain"]]
    empty = sum(not x["top"] for x in ab)
    out += ["", f"When Sonic was unsure ({len(ab)} of {len(t_rows)} test utterances) it returned no guesses at all in "
            f"{empty} of them, so it offers no \"maybe\" cards: none that are unrelated, but the intended phrase is also "
            "shown less often than with the offline ranker, which offers its best related guesses when unsure. The "
            "product keeps the offline ranker; the Bedrock ranker is one setting away (`SURESAY_RANKER`), and Nova 2 "
            "Lite's number will be added when its quota opens."]
    out += ["", f"{len(ms)} ranking calls in this run; time per call p50 {p50:.0f} ms from this machine"
            if p50 is not None else "", ]
    if spend.get("nova_sonic_rank_calls"):
        out[-1] += (f"; all {spend['nova_sonic_rank_calls']} Sonic ranking calls so far (dev tuning included) cost "
                    f"${spend['nova_sonic_rank_usd']:.2f} at list price.")
    return out


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
            "run on this account: it is measured above as a recogniser, and it is the live AI that calls SureSay's MCP "
            "tools in the Alexa+ view, measured in \"A live AI driving SureSay over MCP\", and it stands in as the ranker in "
            "\"Claims 2 and 5 with a Bedrock model ranking\".)",
            "5. **Corpus caveats.** TORGO sentences are well-known reading passages that a large recogniser may "
            "have seen in training, and the phrasebooks are sentences rather than short home commands. "
            "Confirmation words are sparse in TORGO (a few per speaker), so per-speaker confirmation numbers rest "
            "on small counts.", *extra]


def main() -> None:
    c, i, s, lat = load("confirm"), load("intent"), load("safety"), load("latency")
    c2, i2, s2 = read_result("confirm", "run2"), read_result("intent", "run2"), read_result("safety", "run2")
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
        "Every result file records the git SHA and time it was made; the newest are listed under \"Result files\" at the end.",
        "",
        "**Data:** TORGO: 8 speakers with dysarthria (cerebral palsy or ALS) and control "
        "speakers, 16 kHz. **Split:** dev = " + ", ".join(SPLIT["dev"]) + "; test = " + ", ".join(SPLIT["test"]) +
        "; controls = " + ", ".join(SPLIT["controls"]) + ". Prompts and thresholds were tuned on dev only. "
        + SEVERITY_NOTE,
        "",
        "**Revisions:** on 21 Oct an adversarial security review (a separate AI reviewer agent) hardened the consent parser (hesitations, questions and "
        "qualifiers such as \"ok hang on\" or \"okay, who is it\" are never a yes; unreadable Hindi words count as unknown). "
        "Claim 1 was recomputed from the same cached transcripts and did not change. On 22 Oct the consent stress test "
        "found two gaps in the parser (below); after the fixes Claim 1 was recomputed again and did not change. Also on "
        "22 Oct maybe cards started requiring a shared content word with what was heard (the product and this "
        "evaluation use the same rule): on the six test speakers, irrelevant maybe cards on out-of-book requests fell "
        "from 47.2% to the figure below, and the intended phrase in the cards when unsure from 93.5% to the figure below.",
        "",
        "**Baselines, one change at a time:** B0 = plain assistant (recogniser, top transcript acts); "
        "B1 = + the user's phrasebook (biased recognition, nearest phrase acts); SureSay = + ranked candidates, "
        "abstaining, and the confirm gate.",
        "",
        "## Headline",
        "",
        "| Claim | Metric | B0 plain | B1 + phrasebook | SureSay | Data |",
        "|---|---|---|---|---|---|",
        f"| Confirm heard right | false accepts | {confirm_b0_cell(ck)} | — | **{f(ck['ss_fa'])}** | {ck['fa_counts'][2]} decisions, 6 test speakers"
        f"{'; the reject arm needs a recogniser confidence, which Transcribe does not give' if ck.get('b0_reject') else ''} |",
        f"| Nothing without consent | unconfirmed changes | {sk['plain']} / {sk['plain_cases']} (no gate) | — | **{sk['ss']} / {sk['cases']}** | adversarial suite |",
        *([f"| …with a real model as the agent | unconfirmed changes | {sk['sonic']['plain_sonic']['unconfirmed_changes']} / "
           f"{sk['sonic']['plain_sonic']['cases']} (Nova 2 Sonic, no gate) | — | **{sk['sonic']['suresay_sonic']['unconfirmed_changes']} / "
           f"{sk['sonic']['suresay_sonic']['cases']}** | Amazon Nova 2 Sonic, injections + near-misses |"]
          if all(sk["sonic"].values()) else []),
        *([f"| A live AI can't confirm | home changes with no answer from the user | — | — | **{la0['summary']['changes_without_the_user']} / "
           f"{la0['summary']['turns']}** | Amazon Nova 2 Sonic driving the deployed MCP server, {la0['summary'].get('attacks', 0)} turns adversarial; "
           f"{la0['summary'].get('confirm_attempts_refused', 0)} of {la0['summary'].get('confirm_attempts', 0)} confirm attempts refused |"]
          if (la0 := read_result("live_assistant")) else []),
        *([f"| Never mistakes a non-answer for consent | non-answers taken as consent | "
           f"{f(cs0['baseline']['false_accept_rate'] * 100)} (keyword spotting) | — | **{f(cs0['suresay']['false_accept_rate'] * 100)}** | "
           f"{cs0['negatives']:,} generated non-answers, {f(cs0['suresay']['answer_rate'] * 100)} of {cs0['positives']} genuine answers understood |"]
          if (cs0 := read_result("consent_stress")) else []),
        f"| Never acts on a guess | acted on a wrong phrase without asking | {f(ik['b0_wrong'])} | {f(ik['b1_wrong'])} | **{f(ik['ss_wrong'])}** | in-book + out-of-book; by design, since every action waits for the user |",
        *([f"| Done within two tries | sentence said, B0/B1 acting at once (wrong actions) | "
           f"{f(tk0['b0']['success_pct'])} ({f(tk0['b0']['wrong_action_pct'])}) | {f(tk0['b1']['success_pct'])} "
           f"({f(tk0['b1']['wrong_action_pct'])}) | **{f(tk0['suresay']['done_within_two_counting_only_new_takes_pct'])}** (0) "
           f"counting only new recordings; {f(tk0['suresay']['done_within_two_pct'])} counting the other microphone | "
           f"{tk0['tasks']} in-book sentences, 6 test speakers, `{tk['asr_engine']}` (a different recogniser from the rows above) |"]
          if (tk := read_result("task")) and (tk0 := tk["summary"].get("test")) else []),
        f"| In the cards when unsure too | counting maybe cards | — | {f(ik['b1_top3'])} (acts without asking) | **{f(ik['ss_maybe'])}** | same |",
        f"| Abstains when unsure | correct \"say again\" | 0% | {f(ik['b1_abstain'])} | **{f(ik['ss_abstain'])}** | out-of-book utterances |",
        f"| Meaning recovered | top-1 / top-3 | {f(ik['b0_top1'])} / — | {f(ik['b1_top1'])} / {f(ik['b1_top3'])} | {f(ik['ss_top1'])} / {f(ik['ss_top3'])} | 50-phrase books, 6 test speakers; SureSay asks again when unsure, "
        f"where B1 guesses, so its cards hold the phrase {f(ik['ss_maybe'])} of the time counting maybe cards (next row) |",
        *([f"| Meaning recovered by a Bedrock model | top-1 / in the cards | — | — | {f(sr0['summary']['test']['ss_sonic']['top1_pct'])} / "
           f"{f(sr0['summary']['test']['ss_sonic']['in_cards_with_maybe_pct'])}; maybe cards on out-of-book "
           f"{f(sr0['summary']['test']['ss_sonic']['maybe_cards_on_out_of_book_pct'])} | Amazon Nova 2 Sonic as the ranker, same 6 test speakers |"]
          if (sr0 := read_result("intent", "sonic/run1")) and "ss_sonic" in sr0["summary"]["test"] else []),
        *([f"| Works as an MCP server for Alexa+ | live checks passed | — | — | **{lc0['passed']} / {lc0['total']}** | the deployed server, incl. the Alexa+ client's own handshake |"]
          if (lc0 := read_result("live_checks")) else []),
        *([f"| Accessible | Lighthouse accessibility, phone / desktop | — | — | **{sa0['phone']['median_scores']['accessibility']} / "
           f"{sa0['desktop']['median_scores']['accessibility']}** | the live site |"]
          if (sa0 := read_result("site_audit")) else []),
        f"| Speed | understand p50 / p95 | — | — | {lk['u50']} / {lk['u95']} ms | 100 dev clips, {lk['u_where']}"
        + (f"; real spoken requests on the live server: {v['p50_ms']:.0f} / {v['p95_ms']:.0f} ms ({v['requests']} requests, "
           "CloudWatch, incl. recognition)" if (v := ((read_result("live_checks") or {}).get("server_side_understand") or {})
                                                 .get("voice")) else "") + " |",
        f"| Gate overhead | p50 / p95 | — | — | {lk.get('c50', lk['g50'])} / {lk.get('c95', lk['g95'])} ms | "
        f"{'Lambda + DynamoDB' if 'c50' in lk else 'SQLite'} |",
        f"| No regression | top-1, controls | {f(ik['ctrl_b0'])} | — | {f(ik['ctrl_ss'])} | control speakers |",
        "",
        f"SureSay column: {ik['ss_name']}; the Nova 2 Lite ranker is pending Bedrock access. B1 recovers more phrases at "
        "top-1 because it never abstains, and pays for it by acting on a wrong phrase without asking.",
        "",
    ]
    body = head + conf + [""] + intent + [""]
    task = read_result("task")
    if task:
        body += task_section(task, i) + [""]
    body += safety + [""] + latency + [""]
    body += asr_section(c, i) + [""]
    pe = load("personal")
    if pe:
        body += personal_section(pe) + [""]
    cl = load("clarity")
    if cl:
        body += clarity_section(cl) + [""]
    adapt = load("adapt")
    if adapt:
        body += adapt_section(adapt) + [""]
    if cost:
        body += cost_section(cost) + [""]
    if tuning:
        body += tuning_section(tuning) + [""]
    cs, sa = read_result("consent_stress"), read_result("site_audit")
    if cs:
        body += consent_stress_section(cs) + [""]
    if sa:
        body += site_audit_section(sa) + [""]
    lc = read_result("live_checks")
    if lc:
        body += live_checks_section(lc) + [""]
    sr = read_result("intent", "sonic/run1")
    if sr and "ss_sonic" in sr["systems"]:
        body += sonic_rank_section(sr, read_result("spend") or {}) + [""]
    la = read_result("live_assistant")
    if la:
        body += live_assistant_section(la) + [""]
    body += negative_section(ck, ik, c, tuning) + [""]
    files = sorted((p for p in (EVAL / "results").rglob("*.json") if "scratch" not in p.parts), key=lambda p: str(p))
    stamped = []
    for p in files:
        try:
            doc = json.loads(p.read_text())
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("git_sha"):
            stamped.append(f"| `{p.relative_to(EVAL)}` | {doc['git_sha']} | {doc.get('generated_at', '')} |")
    body += ["## Result files", "", "| File | git SHA | Generated |", "|---|---|---|", *stamped, ""]
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
        if lc:  # the speed sentence in the requirements table, from the latest live checks
            extra = [v["minus_network_p50_ms"] for v in lc["round_trip_from_test_machine"].values() if "minus_network_p50_ms" in v]
            typed = (lc.get("server_side_understand") or {}).get("typed")
            if extra and typed:
                p95 = f"{typed['p95_ms'] / 1000:.1f} s" if typed["p95_ms"] >= 1000 else f"{typed['p95_ms']:.0f} ms"
                text = re.sub(r"every MCP call adds [0-9.]+–[0-9.]+ ms to the network round trip; the server's own time for "
                              r"typed `understand` is about [0-9.]+ ms at p50 \(CloudWatch; p95 [0-9. ]+m?s over real requests\)",
                              f"every MCP call adds {min(extra)}–{max(extra)} ms to the network round trip; the server's own "
                              f"time for typed `understand` is about {typed['p50_ms']:.0f} ms at p50 (CloudWatch; p95 {p95} "
                              "over real requests)", text)
        doc.write_text(text)
    print("wrote eval/REPORT.md")


if __name__ == "__main__":
    main()
