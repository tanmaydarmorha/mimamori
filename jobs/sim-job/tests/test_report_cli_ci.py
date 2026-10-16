import re
from pathlib import Path

from sim_job import cli, fakes
from sim_job.report import CIRCULARITY_NOTE

REPO = Path(__file__).resolve().parents[3]
JOB = REPO / "jobs" / "sim-job"


def fake_run(tmp_path, *extra):
    out = tmp_path / "report.md"
    code = cli.main(["run", "--fake-services", "--out", str(out), *extra])
    return code, out


def test_one_command_writes_the_report_with_every_required_section(tmp_path, capsys):
    code, out = fake_run(tmp_path)
    assert code == 0
    md = out.read_text()
    assert "FAKE SERVICES" in md.splitlines()[0]  # a pipeline-check run says so before anything else
    assert "Circularity: read this before the numbers" in md and CIRCULARITY_NOTE.splitlines()[0] in md
    for arm in ("(a) today's counter check", "(b) statistics only", "(c) full Mimamori"):
        assert arm in md
    assert "stated parameter" in md and "One teller-behaviour assumption" in md
    assert "Held-out failure analysis" in md and "The 20-case target is not met" in md
    assert "counts of cases, not rates" in md
    assert md.count("#### HO-") == 11  # every case in the research set appears, replayed or with the reason it was not
    assert "Not replayed" in md and "crypto-asset payment" in md
    assert "Arm (a) sensitivity to the amount threshold" in md
    assert "published_at" in md and "2023-04-13" in md
    assert "Considered and left out" in md


def test_report_has_no_rate_claims_in_the_held_out_section(tmp_path):
    _, out = fake_run(tmp_path)
    held = out.read_text().split("## 4. Held-out failure analysis")[1].split("## 5.")[0]
    assert "%" not in held


def test_report_to_stdout_and_flags(tmp_path, capsys):
    assert cli.main(["run", "--fake-services", "--out", "-", "--no-heldout", "--judge", "off", "--sweep", ""]) == 0
    text = capsys.readouterr().out
    assert "Mimamori simulation report" in text and "Held-out failure analysis" not in text
    assert "Arm (a) sensitivity" not in text


def test_threshold_and_follow_p_are_reported_as_parameters(tmp_path):
    _, out = fake_run(tmp_path, "--threshold", "2500000", "--follow-p", "0.8")
    md = out.read_text()
    assert "¥2,500,000 (stated parameter" in md and "(`follow_p`) | 0.8" in md


def test_unreachable_services_exit_2(tmp_path, capsys):
    code = cli.main(["run", "--core-bank-url", "http://127.0.0.1:9", "--case-svc-url", "http://127.0.0.1:9",
                     "--out", str(tmp_path / "r.md")])
    assert code == 2
    assert "not reachable" in capsys.readouterr().err


def test_a_playbook_published_on_or_after_T_stops_the_run_with_exit_3(tmp_path, monkeypatch, capsys):
    real = fakes.load_example

    def tampered(name):
        data = real(name)
        if name == "playbooks.json":
            data[0]["sources"][0]["published_at"] = "2026-05-01"
        return data

    monkeypatch.setattr(fakes, "load_example", tampered)
    code, out = fake_run(tmp_path)
    assert code == 3 and not out.exists()
    assert "date split violated" in capsys.readouterr().err


def test_seed_subcommand_writes_the_extended_seed(tmp_path, capsys):
    out = tmp_path / "sim-seed"
    assert cli.main(["seed", "--out", str(out)]) == 0
    assert (out / "bank" / "transactions.json").exists()
    assert f"MIMAMORI_SEED_DIR={out}" in capsys.readouterr().out


# ----------------------------------------------------------------------- CI and Dockerfile conventions


def _copies(dockerfile: str) -> set[str]:
    return {line.split()[1].rstrip("/") for line in dockerfile.splitlines() if line.startswith("COPY ")}


def test_ci_paths_match_the_dockerfile_copies_exactly():
    copies = _copies((JOB / "Dockerfile").read_text())
    assert copies == {"libs/mimamori-common", "schemas", "seed", "jobs/sim-job"}
    wf = (REPO / ".github" / "workflows" / "ci-sim-job.yml").read_text()
    expected = {f"{c}/**" for c in copies} | {".github/workflows/ci-sim-job.yml", ".github/workflows/_build-deploy.yml"}
    for key in ("push", "pull_request"):
        m = re.search(rf"{key}:\n(?:    branches: \[main\]\n)?    paths: \[(.*)\]", wf)
        assert m, key
        assert {p.strip() for p in m.group(1).split(",")} == expected


def test_workflow_uses_block_style_and_the_job_kind():
    wf = (REPO / ".github" / "workflows" / "ci-sim-job.yml").read_text()
    assert "concurrency:\n  group: ci-sim-job-${{ github.ref }}\n  cancel-in-progress: true" in wf
    assert "    with:\n      name: sim-job\n      path: jobs/sim-job\n      kind: job\n" in wf
    assert not re.search(r"(concurrency|with):\s*\{", wf)


def test_dockerfile_conventions():
    df = (JOB / "Dockerfile").read_text()
    assert df.startswith("#") and "FROM python:3.12-slim" in df
    assert 'CMD ["python", "-m", "sim_job", "run"' in df
    assert "asia-" not in df  # no hard-coded region anywhere
