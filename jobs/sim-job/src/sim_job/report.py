"""Markdown report: per-arm synthetic results, the circularity note, and the held-out failure analysis."""

from __future__ import annotations

from .arm_a import LEXICON
from .heldout import VARIANTS, HeldOutSet
from .runner import ARM_LABELS, ARMS, RunResult, ScenarioResult, classify_miss, summarize
from .teller import ArmOutcome

CIRCULARITY_NOTE = """\
**Circularity: read this before the numbers.** The synthetic results below cannot show how well any
arm works against real fraud. The scenarios, the role-played customers, the ground-truth labels, the
playbooks and question banks the copilot draws on, the risk rule, and arm (a)'s red-flag lexicon were all
written by the same team, from the same sources, with the spike transcripts in front of them. The scam
customers say the phrases the playbooks list (安全な口座, 警察の人から電話…); the legitimate customers
include the traps the spike already exposed (a car for a grandchild, a genuine renovation, a secret
trip). A scripted customer also answers every arm identically, so arms differ only in what they ask and
when they flag. The label "scam" or "legit" is our own, not an independent finding, and the judge only
reviews process (decision reasonableness, wording), not truth. With n = 24 there are no rates to quote.
What this set can show: the pipeline runs end to end, where each arm's logic stops (an amount threshold, a
lexicon, an alert rule, a pause rule), and which of our own hard cases each arm fails. What it cannot
show: detection or false-positive rates in the world. The only part with outside content is the
held-out set, and even there the dialogue is our adaptation of a victim-side narrative."""

LIMITS = [
    "Role-play is scripted by default (deterministic, identical for every arm). A scripted customer answers by the *purpose* of the question and cannot react to wording; `--roleplay llm` removes that limit but makes a run non-repeatable.",
    "Arm (a) recognises red flags with a lexicon (sourced phrases, listed in section 5). A teller listens more flexibly than a regex; arm (a) as built is probably weaker than a trained teller at hearing paraphrase, and stronger than an untrained one. Its age trigger is not modelled and its amount threshold is a stated parameter.",
    "One shared teller assumption (acts on a raised flag with probability `follow_p`, same draw in every arm). It says nothing about real tellers' skill or fatigue.",
    "Wishes exist only for the hero customer (`advance_wishes` basis); everyone else is paused on `bank_policy`. Hold windows, overrides, the family call and freezes are not part of this evaluation.",
    "Each transfer is keyed once and each conversation is one pass; runs against live services are not repeatable unless the services are restarted on the same seed.",
]


def _cell(o: ArmOutcome | None, scenario) -> str:
    if o is None:
        return "n/a"
    if o.error:
        return "ERROR"
    if o.paused:
        return f"PAUSE (turn {o.paused_at_turn})" if o.paused_at_turn else "PAUSE (at alert)"
    if not o.engaged:
        txt = "not engaged"
    elif o.flag_ever:
        txt = "flag, not acted on"
    else:
        txt = "cleared"
    if scenario.ground_truth == "scam":
        txt += " - **LOST**"
    return txt


def _fmt_yen(n: int) -> str:
    return f"¥{n:,}"


def _summary_table(results: list[ScenarioResult], arms: list[str]) -> list[str]:
    lines = ["| | " + " | ".join(ARM_LABELS[a] for a in arms) + " |", "|---|" + "---|" * len(arms)]
    sums = {a: summarize(results, a) for a in arms}

    def row(label, fn):
        lines.append(f"| {label} | " + " | ".join(fn(sums[a]) for a in arms) + " |")

    row("Scams paused", lambda s: f"{s.scam_caught} of {s.scam_n}")
    row("Scams missed: arm never engaged", lambda s: str(s.missed_not_engaged))
    row("Scams missed: engaged, no flag", lambda s: str(s.missed_no_flag))
    row("Scams missed: flag raised, teller did not act", lambda s: str(s.missed_not_acted))
    row("Legitimate transactions paused (false pauses)", lambda s: f"{s.legit_false_pause} of {s.legit_n}")
    row("Scam yen that went through", lambda s: _fmt_yen(s.yen_lost))
    row("Legitimate yen paused", lambda s: _fmt_yen(s.yen_held_legit))
    row("Mean customer replies before a pause", lambda s: "n/a" if s.mean_turns_to_pause is None else f"{s.mean_turns_to_pause:.1f}")
    row("Errors (service failures)", lambda s: str(s.errors))
    row("Judge: decisions rated unreasonable", lambda s: f"{s.judge_unreasonable} of {s.judged}" if s.judged else "n/a")
    row("Judge: wording problems in teller's words", lambda s: str(s.wording_problems) if s.judged else "n/a")
    return lines


def _matrix(results: list[ScenarioResult], arms: list[str]) -> list[str]:
    lines = ["| Scenario | Truth | Amount | " + " | ".join(ARM_LABELS[a] for a in arms) + " |",
             "|---|---|---|" + "---|" * len(arms)]
    for r in results:
        sc = r.scenario
        cells = " | ".join(_cell(r.arms.get(a), sc) for a in arms)
        lines.append(f"| {sc.id}: {sc.label} | {sc.ground_truth} | {_fmt_yen(sc.amount_jpy)} | {cells} |")
    return lines


# --------------------------------------------------------------------------- held-out explanation


def _why(arm: str, o: ArmOutcome | None, scenario, threshold: int) -> str:
    if o is None:
        return "not run"
    if o.error:
        return f"service error: {o.error[:120]}"
    if arm == "a_counter_check":
        if not o.engaged:
            return f"amount ¥{scenario.amount_jpy:,} is below the ¥{threshold:,} threshold, so no check is made"
        if o.paused or o.flag_ever:
            return "red flags heard: " + ", ".join(sorted({r.split(" ")[0] for r in o.reasons}))
        return ("the answers contained none of the published red flags (official instruction, secrecy order, script "
                "phrase, caller on the line, cannot explain, no documents)")
    if arm == "b_statistics":
        if o.scoring == "alert":
            return "Scoring alerted (signals: " + (", ".join(o.signals) or "not reported") + ")"
        return f"Scoring did not alert (scoring: {o.scoring}); a transfer that looks ordinary against the customer's baseline"
    if not o.engaged:
        return "no case was opened, so the copilot never ran (" + "; ".join(o.notes) + ")"
    if o.paused or o.flag_ever:
        return f"risk {o.risk_level}; rule fired: " + (", ".join(o.reasons) or "n/a")
    return f"copilot ran; risk stayed {o.risk_level} after {len(o.questions)} approved question(s)"


def _heldout_section(res: RunResult, hs: HeldOutSet, playbook_rows: list[dict]) -> list[str]:
    p = res.params
    L = ["## 4. Held-out failure analysis (public fake-police cases published on or after "
         f"{hs.cutoff.isoformat()})", ""]
    L += [
        f"**Size of the set.** research.md R2 found {len(hs.cases)} narrative-rich fake-police cases after T "
        f"(target {hs.target_cases}); {len(hs.runnable)} can be replayed at a counter, "
        f"{len(hs.cases) - len(hs.runnable)} cannot (reasons below). **The 20-case target is not met**: R2b (Tokyo, "
        "Saitama, Osaka, Kanagawa bulletins) has not been done, so this set is what research.md has, and the "
        "counts below are counts of cases, not rates. Every replay is counterfactual: none of these victims was "
        "stopped at a bank counter in the source, so a result says what the method would have done on the case's "
        "recorded facts plus our stated assumptions, not what happened.",
        "",
        "**Date split (CR 16, CR 28).** Every approved playbook the copilot can use was checked before the run: "
        f"every source `published_at` is before T = {hs.cutoff.isoformat()}, and none cites a held-out case's URL.",
        "",
        "| Playbook | Status | Latest source published_at |", "|---|---|---|",
    ]
    L += [f"| `{r['id']}` | {r['status']} | {r['latest_source_published_at']} |" for r in playbook_rows]
    L += ["", "Each case becomes three replays of the same facts: **candid** (the victim says what the caller told them), "
          "**coached** (a generic cover story, no mention of calls, documents 'coming later') and **coached-papers** "
          "(the same, but the victim produces papers). The NPA itself says coaching defeats today's check (research "
          "R1 [6]). The cover story and the documents behaviour are assumptions (no source states them), so both "
          "document behaviours are run instead of picking one.", ""]
    by_case: dict[str, dict[str, ScenarioResult]] = {}
    for r in res.heldout:
        by_case.setdefault(r.scenario.source["case_id"], {})[r.scenario.source["variant"]] = r
    L += ["### Case by case", ""]
    for c in hs.cases:
        L += [f"#### {c['id']}: {c['impersonation']}", "",
              f"- Source: {c['publisher']}, published {c['published_at']} ({c['published_at_basis']}). <{c['source_url']}>"
              + (f" (`{c['source_file']}`)" if c.get("source_file") else ""),
              f"- Recorded: channel {c['channel']}; told: {c['told']}; payment {c['payment_method']}; "
              f"amount {'not stated' if not c['amount_jpy'] else _fmt_yen(c['amount_jpy'])}.",
              ]
        if not c["runnable"]:
            L += [f"- **Not replayed**: {c['not_runnable_reason']}.", ""]
            continue
        m = c["modelled"]
        L.append(f"- Modelled as: one counter {m['kind'].replace('_', ' ')} of {_fmt_yen(m['amount_jpy'])}"
                 + (" to a new payee at another bank" if m["payee_relation"] == "other_bank" else "") + ".")
        L += [f"- Assumption: {a}" for a in c["assumptions"]]
        L += ["", "| Variant | " + " | ".join(ARM_LABELS[a] for a in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
        for variant in VARIANTS:
            r = by_case.get(c["id"], {}).get(variant)
            if r:
                L.append(f"| {variant} | " + " | ".join(_cell(r.arms.get(a), r.scenario) for a in ARMS) + " |")
        L.append("")
        for variant in VARIANTS:
            r = by_case.get(c["id"], {}).get(variant)
            if not r:
                continue
            for a in ARMS:
                o = r.arms.get(a)
                if o is None:
                    continue
                verdict = "stopped" if o.paused else "**missed**"
                L.append(f"- {variant}, {ARM_LABELS[a]}: {verdict}. {_why(a, o, r.scenario, p.amount_threshold_jpy)}.")
        L.append("")
    L += ["### Failure patterns (counts of replays, not rates)", "",
          "| | " + " | ".join(ARM_LABELS[a] for a in ARMS) + " |", "|---|" + "---|" * len(ARMS)]
    labels = [("stopped", "Stopped (paused)"), ("not_engaged", "Missed: arm never engaged"),
              ("no_flag", "Missed: engaged, nothing raised"), ("not_acted", "Missed: flag raised, teller did not act"),
              ("error", "Service error")]
    counts = {a: dict.fromkeys([k for k, _ in labels], 0) for a in ARMS}
    for r in res.heldout:
        for a in ARMS:
            o = r.arms.get(a)
            if o is None:
                continue
            counts[a]["stopped" if o.paused else classify_miss(o)] += 1
    for k, label in labels:
        L.append(f"| {label} | " + " | ".join(str(counts[a][k]) for a in ARMS) + " |")
    L += ["", f"Replays: {len(res.heldout)} ({len(hs.runnable)} cases x {len(VARIANTS)} variants).", ""]
    if hs.excluded:
        L += ["### Considered and left out", "", "| research.md R2 row | Item | Why |", "|---|---|---|"]
        L += [f"| {e['research_row']} | {e['label']} | {e['reason']} |" for e in hs.excluded]
        L.append("")
    return L


# --------------------------------------------------------------------------- the report


def render(res: RunResult, hs: HeldOutSet | None, playbook_rows: list[dict]) -> str:
    p, meta = res.params, res.meta
    arms = [a for a in ARMS if any(r.arms.get(a) is not None for r in res.synthetic)] or ["a_counter_check"]
    L: list[str] = []
    if meta.get("fake_services"):
        L += ["> **FAKE SERVICES.** This run used the in-package fake core-bank and case-svc "
              "(`sim_job.fakes`): scoring is 'alert at or above ¥1M' and the 'copilot' is a keyword extractor. "
              "It checks the pipeline and the report layout only. **The numbers say nothing about Mimamori.**", ""]
    if meta.get("fake_judge"):
        L += ["> **FAKE JUDGE.** The judge model was a canned response; judge rows are layout only.", ""]
    L += ["# Mimamori simulation report: three-way evaluation", "",
          "Synthetic-only environment. All people, accounts and amounts are invented. "
          f"Generated {meta.get('generated_at', '')}.", "",
          "| | |", "|---|---|",
          f"| Mode | {meta.get('mode', 'n/a')} |",
          f"| Role-play | {meta.get('roleplay', 'scripted')} |",
          f"| Judge | {meta.get('judge', 'off')} |",
          f"| Services | core-bank `{meta.get('core_bank_url', 'n/a')}`, case-svc `{meta.get('case_svc_url', 'n/a')}` |",
          f"| Seed | {meta.get('seed_note', 'n/a')} |",
          f"| Held-out cut-off T | {p.cutoff.isoformat()} |", ""]
    L += ["## 1. The three arms and the shared teller assumption", "",
          "- **(a) Today's counter check**, built from published practice (research.md R1): the NPA request to speak to "
          "customers making high-value transfers or taking home high-value cash; Akita prefectural police's five-step "
          "routine (show the police request, questionnaire, suggest transfer over cash, suggest a bank cheque, report to "
          "police); Okayama practice (ask what the money is for, ask for the purchase papers, report if it cannot be "
          "explained). Escalation = pause and call the police. Asks four approved questions (purpose, who asked, on the "
          "phone now, documents). **The amount threshold is a stated parameter, not a sourced one.**",
          "- **(b) Statistics only**: Scoring alone. An alert is the flag; there are no questions.",
          "- **(c) Full Mimamori**: Scoring alert opens a case; the copilot (case-svc) reads each customer turn, code "
          "verifies quotes and computes risk (risk-v1); the teller asks the approved question it suggests. No alert, no "
          "case.", "",
          "**One teller-behaviour assumption for all three arms.** The teller asks the arm's questions, up to "
          f"{p.max_turns} per transaction. When the arm's flag is up, the teller pauses if they act on flags "
          f"(per-scenario draw, `follow_p` = {p.follow_p}, the same draw for every arm), otherwise carries on. "
          "With no pause after the last question the teller clears and releases. Nothing about the teller differs "
          "between arms. Every sim pause stands for a human decision and is posted with a rationale.", "",
          "| Parameter | Value |", "|---|---|",
          f"| Arm (a) amount threshold | ¥{p.amount_threshold_jpy:,} (stated parameter; swept in section 3) |",
          f"| Teller acts on a flag (`follow_p`) | {p.follow_p} |",
          f"| Questions per transaction | {p.max_turns} |",
          f"| Seed for the common random draw | {p.seed} |", ""]
    L += ["## 2. Synthetic results", "",
          f"{len(res.synthetic)} scenarios ({sum(r.scenario.ground_truth == 'scam' for r in res.synthetic)} scam, "
          f"{sum(r.scenario.ground_truth == 'legit' for r in res.synthetic)} legitimate). Counts, not rates.", "",
          CIRCULARITY_NOTE, ""]
    L += _summary_table(res.synthetic, arms) + [""]
    L += ["### Per scenario", ""] + _matrix(res.synthetic, arms) + [""]
    if res.sweep:
        L += ["## 3. Arm (a) sensitivity to the amount threshold", "",
              "Arm (a) only, scripted customers. The threshold is the one number the published practice leaves open.", "",
              "| Threshold | Scams paused | Scam yen through | Legitimate paused |", "|---|---|---|---|"]
        for t in sorted(res.sweep):
            s = summarize(res.sweep[t], "a_counter_check")
            L.append(f"| ¥{t:,} | {s.scam_caught} of {s.scam_n} | {_fmt_yen(s.yen_lost)} | {s.legit_false_pause} of {s.legit_n} |")
        L.append("")
    if hs is not None:
        L += _heldout_section(res, hs, playbook_rows)
    L += ["## 5. Arm (a) red-flag lexicon (the stated parameters of 'hearing' a flag)", "",
          "| Flag | Pattern | Applies to question purpose | Source |", "|---|---|---|---|"]
    for code, (rx, purpose, src) in LEXICON.items():
        L.append(f"| `{code}` | `{rx.replace('|', '\\|')}` | {purpose or 'any'} | {src} |")
    L += ["", "## 6. Limits of this evaluation", ""] + [f"- {x}" for x in LIMITS]
    return "\n".join(L) + "\n"
