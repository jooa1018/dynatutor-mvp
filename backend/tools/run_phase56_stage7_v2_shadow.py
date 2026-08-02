"""Run the whole v2 shadow evaluation: prepare, then verify, then run, then score.

This is a thin orchestrator over four commands that each do one job, and it
invokes them as **separate processes** rather than calling into them.  That is
the point of the file, so it is worth saying why.

The shadow result is only evidence if the runtime phase could not have seen the
answer.  When all three jobs ran in one process, that claim rested on where the
comments were: the process loaded `PublicCorpusCaseV1` objects — which contain
`gold` — before it ran anything, held them across the whole pipeline, and read
the expected answers at the end.  A test could show that the runtime callback
did not reach for one.  Nothing could show that it could not.

Split into processes, the claim becomes a property of what each one opens:

* ``run_phase56_stage7_v2_shadow_prepare`` reads the corpus and the manifest,
  migrates them, and publishes the candidate archive, a gold-free runtime
  input bundle, and an attestation of what it prepared — together, as one
  immutable generation under ``--publication-root``, made authoritative by a
  single ``CURRENT.json`` pointer replace.  It runs no pipeline and compares
  no answer.
* ``run_phase56_stage7_v2_shadow_verify_prepare`` rebuilds the preparation from
  the corpus and the manifest and compares its own result against those files.
  It exists because the other checks in this chain are all comparisons *between
  artifacts Phase M wrote* — and a runtime input and an attestation forged
  together agree with each other perfectly.  Going back to the frozen corpus is
  the only comparison a forger cannot satisfy.  It solves nothing, runs no
  pipeline, scores nothing, and writes only its own report.
* ``run_phase56_stage7_v2_shadow_runtime`` reads *only* the published bundle —
  a type with no field an expectation could be written into — checks it against
  the attestation, runs the pipeline, and freezes the full restricted snapshot
  and the public redacted view.  It never opens the corpus.
* ``run_phase56_stage7_v2_shadow_score`` reads the frozen snapshot back **from
  disk** and the corpus, checks the snapshot is bound to the attested
  preparation, and compares.  It holds no compiler, solver or projection, so it
  cannot re-run anything having seen the gold.

**One pipeline, one generation.**  Phase M prints
``STAGE7_V2_PREPARE_PUBLICATION_ID=<generation-id>`` on success; this
orchestrator captures that id exactly once and passes the same value to Phase
V, Phase R and Phase G.  Each of them resolves the pinned generation directly
and never re-reads ``CURRENT.json``, so a second writer that publishes — and
re-points the authority — while this pipeline is mid-flight cannot make two of
its phases observe two different preparations.  A Phase M that exits 0 without
printing the id is refused here, before Phase V, for the same reason a failed
Phase M is: nothing downstream may run unpinned.

The order is load-bearing: Phase V runs **between** preparation and runtime, so
a preparation that fails verification reaches the pipeline zero times.

Each step's exit status is the step's own disposition, and this orchestrator
returns the first non-zero one it sees.  A failed acceptance exits 2; it does
not print FAIL and return 0.

All artifacts stay outside the repository.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent

PREPARE = TOOLS / "run_phase56_stage7_v2_shadow_prepare.py"
VERIFY_PREPARE = TOOLS / "run_phase56_stage7_v2_shadow_verify_prepare.py"
RUNTIME = TOOLS / "run_phase56_stage7_v2_shadow_runtime.py"
SCORE = TOOLS / "run_phase56_stage7_v2_shadow_score.py"

PUBLICATION_ID_KEY = "STAGE7_V2_PREPARE_PUBLICATION_ID="
PUBLICATION_FAILURE_EXIT = 2


def _run(step: str, command: list[str]) -> int:
    print(f"--- {step}: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, check=False)
    print(f"--- {step} exit={completed.returncode}", flush=True)
    return completed.returncode


def _run_prepare(step: str, command: list[str]) -> tuple[int, str | None]:
    """Run Phase M, echoing its output while capturing the publication id.

    Captured rather than re-derived: the id names the exact generation Phase M
    made authoritative, and re-resolving ``CURRENT.json`` here instead would
    re-introduce the race this pipeline is pinned against.  The last
    occurrence wins if the key were ever printed twice, but Phase M prints it
    exactly once, immediately before its acceptance line.
    """

    print(f"--- {step}: {' '.join(command)}", flush=True)
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    sys.stdout.write(completed.stdout)
    sys.stdout.flush()
    sys.stderr.write(completed.stderr)
    sys.stderr.flush()
    print(f"--- {step} exit={completed.returncode}", flush=True)
    publication_id = None
    for line in completed.stdout.splitlines():
        if line.startswith(PUBLICATION_ID_KEY):
            publication_id = line[len(PUBLICATION_ID_KEY) :].strip()
    return completed.returncode, publication_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--publication-root",
        type=Path,
        required=True,
        help=(
            "where Phase M publishes the generation the whole pipeline is "
            "pinned to. Replaces the three per-artifact paths: the artifacts "
            "of one preparation are never published separately."
        ),
    )
    parser.add_argument("--verification-report", type=Path, required=True)
    parser.add_argument("--runtime-snapshot", type=Path, required=True)
    parser.add_argument("--redacted-view", type=Path, required=True)
    parser.add_argument("--shadow-report", type=Path, required=True)
    parser.add_argument("--scorecard", type=Path, required=True)
    parser.add_argument("--exact-code-head", type=str, required=True)
    parser.add_argument("--campaign-seal", type=str, default=None)
    parser.add_argument("--record-regressions", action="store_true")
    args = parser.parse_args()

    prepare_command = [
        sys.executable,
        str(PREPARE),
        "--corpus-archive",
        str(args.corpus_archive),
        "--manifest",
        str(args.manifest),
        "--publication-root",
        str(args.publication_root),
        "--exact-code-head",
        args.exact_code_head,
    ]
    if args.campaign_seal:
        prepare_command += ["--campaign-seal", args.campaign_seal]
    status, publication_id = _run_prepare("PHASE_M_PREPARE", prepare_command)
    if status:
        return status
    if publication_id is None:
        print(
            "STAGE7_V2_SHADOW_ORCHESTRATOR=FAIL:prepare_publication_id_missing",
            file=sys.stderr,
        )
        return PUBLICATION_FAILURE_EXIT

    # The one pin, spelled once.  Every downstream phase receives this exact
    # pair and resolves the generation directly, so none of them re-interprets
    # whatever CURRENT.json says by the time it starts.
    pinned = [
        "--publication-root",
        str(args.publication_root),
        "--publication-id",
        publication_id,
    ]

    verify_command = [
        sys.executable,
        str(VERIFY_PREPARE),
        "--corpus-archive",
        str(args.corpus_archive),
        "--manifest",
        str(args.manifest),
        *pinned,
        "--verification-report",
        str(args.verification_report),
        "--exact-code-head",
        args.exact_code_head,
    ]
    if args.campaign_seal:
        verify_command += ["--campaign-seal", args.campaign_seal]
    status = _run("PHASE_V_VERIFY_PREPARE", verify_command)
    if status:
        return status

    runtime_command = [
        sys.executable,
        str(RUNTIME),
        *pinned,
        "--runtime-snapshot",
        str(args.runtime_snapshot),
        "--redacted-view",
        str(args.redacted_view),
        "--exact-code-head",
        args.exact_code_head,
    ]
    if args.record_regressions:
        runtime_command.append("--record-regressions")
    status = _run("PHASE_R_RUNTIME", runtime_command)
    if status:
        return status

    score_command = [
        sys.executable,
        str(SCORE),
        "--corpus-archive",
        str(args.corpus_archive),
        "--runtime-snapshot",
        str(args.runtime_snapshot),
        *pinned,
        "--shadow-report",
        str(args.shadow_report),
        "--scorecard",
        str(args.scorecard),
        "--expected-code-head",
        args.exact_code_head,
    ]
    if args.campaign_seal:
        score_command += ["--campaign-seal", args.campaign_seal]
    return _run("PHASE_G_SCORE", score_command)


if __name__ == "__main__":
    raise SystemExit(main())
