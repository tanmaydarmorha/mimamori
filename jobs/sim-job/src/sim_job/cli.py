"""Command line.

    sim-job seed --out ./sim-seed          write the extended synthetic seed the services start on
    sim-job run  --out ./sim-report.md     run the evaluation against live services, write the report
    sim-job run  --fake-services ...       pipeline check with in-package fakes (numbers are meaningless)

Exit 0 on success (a job); 2 if the services are not reachable; 3 if the date split is violated.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from mimamori_common.config import Settings
from mimamori_common.llm import FakeClient, get_general_client

from .arm_bc import ServiceArms
from .clients import CaseSvcClient, CoreBankClient
from .heldout import CutoffViolation, assert_playbooks_before_cutoff, load_heldout, to_scenarios
from .params import SimParams
from .personas import LlmRolePlayer, QuestionIndex, ScriptedRolePlayer
from .report import render
from .runner import RunResult, now_iso, run_scenarios, threshold_sweep
from .scenarios import synthetic_scenarios
from .seedgen import build_seed


def _canned_judge() -> FakeClient:
    canned = {"decision_reasonable": True, "missed_red_flags": [], "wording_problems": [], "notes": "canned response (fake judge)"}
    return FakeClient(json_handler=lambda system, user, schema: canned)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sim-job", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="write the extended synthetic seed directory")
    s.add_argument("--out", required=True, type=Path)
    r = sub.add_parser("run", help="run the three-way evaluation and write the Markdown report")
    r.add_argument("--out", type=Path, default=Path("sim-report.md"))
    r.add_argument("--fake-services", action="store_true", help="use in-package fake core-bank and case-svc (pipeline check only)")
    r.add_argument("--core-bank-url", default=None)
    r.add_argument("--case-svc-url", default=None)
    r.add_argument("--roleplay", choices=["scripted", "llm"], default="scripted")
    r.add_argument("--judge", choices=["general", "fake", "off"], default=None, help="default: general, or fake with --fake-services")
    r.add_argument("--threshold", type=int, default=SimParams.amount_threshold_jpy, help="arm (a) amount threshold in JPY")
    r.add_argument("--follow-p", type=float, default=SimParams.follow_p, help="chance the teller acts on a raised flag")
    r.add_argument("--max-turns", type=int, default=SimParams.max_turns)
    r.add_argument("--seed", type=int, default=SimParams.seed)
    r.add_argument("--sweep", default="500000,1000000,2000000,3000000", help="arm (a) thresholds to sweep, comma separated; empty to skip")
    r.add_argument("--no-heldout", action="store_true")
    r.add_argument("--heldout-file", default=None, help="alternative held-out cases JSON (same format)")
    return p


async def _run(args) -> int:
    settings = Settings.from_env()
    params = SimParams(amount_threshold_jpy=args.threshold, follow_p=args.follow_p, max_turns=args.max_turns, seed=args.seed)
    index = QuestionIndex.load()
    synthetic = synthetic_scenarios()
    hs = None if args.no_heldout else load_heldout(args.heldout_file)
    heldout = to_scenarios(hs) if hs else []

    world = None
    if args.fake_services:
        from .fakes import FakeWorld, make_clients

        world = FakeWorld()
        core, case = make_clients(world)
        core_url, case_url = "in-package fake", "in-package fake"
    else:
        core_url, case_url = args.core_bank_url or settings.core_bank_url, args.case_svc_url or settings.case_svc_url
        core, case = CoreBankClient(core_url), CaseSvcClient(case_url)
        down = [n for n, c in (("core-bank-mock", core), ("case-svc", case)) if not await c.healthy()]
        if down:
            print(f"sim-job: not reachable: {', '.join(down)} ({core_url}, {case_url}). Start the services on the sim seed "
                  "(see jobs/sim-job/README.md) or use --fake-services for a pipeline check.", file=sys.stderr)
            return 2
    try:
        # Date split guard: only playbooks published before T may be in use (CR 16, CR 28).
        approved = await case.approved_playbooks()
        playbook_rows = assert_playbooks_before_cutoff(approved, params.cutoff, hs)
    except CutoffViolation as err:
        print(f"sim-job: date split violated: {err}", file=sys.stderr)
        return 3

    judge_mode = args.judge or ("fake" if args.fake_services else "general")
    judge = get_general_client(settings) if judge_mode == "general" else _canned_judge() if judge_mode == "fake" else None
    role = LlmRolePlayer(get_general_client(settings)) if args.roleplay == "llm" else ScriptedRolePlayer()
    services = ServiceArms(core, case, index, params)

    res = RunResult(params=params)
    res.synthetic = await run_scenarios(synthetic, params, index, services, role, judge)
    if heldout:
        res.heldout = await run_scenarios(heldout, params, index, services, role, judge)
    if args.sweep.strip():
        res.sweep = await threshold_sweep(synthetic, params, index, [int(x) for x in args.sweep.split(",")])
    res.meta = {
        "generated_at": now_iso(), "mode": "fake services (pipeline check)" if world else "live services",
        "fake_services": bool(world), "fake_judge": judge_mode == "fake", "roleplay": args.roleplay,
        "judge": {"general": f"general model ({getattr(judge, 'name', 'n/a')}), prompt separate from the copilot's",
                  "fake": "canned (fake)", "off": "off"}[judge_mode],
        "core_bank_url": core_url, "case_svc_url": case_url,
        "seed_note": "extended synthetic seed from `sim-job seed` (services must be started on it)" if not world else "n/a (fake)",
    }
    text = render(res, hs, playbook_rows)
    if str(args.out) == "-":
        print(text)  # containers: the report goes to the job log
    else:
        args.out.write_text(text, encoding="utf-8")
        print(f"sim-job: report written to {args.out}")
    for c in (core, case):
        await c.aclose()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "seed":
        summary = build_seed(synthetic_scenarios() + (to_scenarios(load_heldout())), args.out)
        print(f"sim-job: seed written to {args.out} ({len(summary['added_customers'])} added customers). "
              f"Start the services with MIMAMORI_SEED_DIR={args.out}")
        return 0
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
