"""The campaign worker script, run locally with a stand-in for WarpX."""
import argparse
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "warpx"))
import campaign

# Stands in for WarpX: runs to step 30 with a checkpoint every 10 steps, from the checkpoint named by amr.restart.
# A case given `stop_at=N` is stopped at step N as if its node had been taken away, unless it is restarting.
# A case given `hang=1` writes nothing and never ends. One given `slow_after=N` stops making progress at step N
# on its first try.
# It stops the worker's shells in one signal before itself (`timeout` gives it a process group of its own), so
# that no shell outlives it long enough to claim the case again.
STAND_IN = r"""#!/bin/bash
start=0; stop=0; crash=0; slow=0
for arg in "$@"; do case $arg in amr.restart=*) start=$((10#${arg##*chk}));; stop_at=*) stop=${arg#*=};; crash=*) crash=1;; hang=*) exec sleep 600;; slow_after=*) slow=${arg#*=};; esac; done
[ $crash -eq 1 ] && exit 134
mkdir -p diags/reducedfiles
[ $start -eq 0 ] && echo "#step" > diags/reducedfiles/number.txt
for step in $(seq $((start + 1)) 30); do
  echo "STEP $step ends"; echo "$step" >> diags/reducedfiles/number.txt
  [ $((step % 10)) -eq 0 ] && mkdir -p diags/chk$(printf %06d $step)
  [ $start -eq 0 ] && [ $step -eq $stop ] && { kill -9 -- -$(ps -o sid= -p $$ | tr -d ' '); kill -9 0; }
  [ $start -eq 0 ] && [ $slow -gt 0 ] && [ $step -eq $slow ] && exec sleep 600
done
exit 0
"""

# Stands in for mpirun: notes how many processes were asked for, then runs the program once.
MPIRUN = r"""#!/bin/bash
while [ "$1" != -np ]; do shift; done
echo "$2 processes on GPUs $CUDA_VISIBLE_DEVICES" > launched.txt; shift 2
exec "$@"
"""


class WorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.shared = Path(tempfile.mkdtemp())
        self.camp = self.shared / "campaigns/t"
        tools = self.shared / "bin"
        tools.mkdir()
        for name, text in (("warpx", STAND_IN), ("nvidia-smi", "#!/bin/sh\n"), ("mpirun", MPIRUN)):
            (tools / name).write_text(text)
            (tools / name).chmod(0o755)
        self.env = {**os.environ, "WARPX": str(tools / "warpx"), "PATH": f"{tools}:{os.environ['PATH']}"}
        campaign.SHARED = str(self.shared)

    def work(self, cases: str, gpus: int = 1, stall: int = 1800, timeout: int = 60, starts: int = 1) -> None:
        """Run one node's worker to the end on campaign t, adding `cases` to its queue. With `starts` above one the
        same job is started again after it ends, as the broker does with a job whose node it took."""
        _, template = campaign.job_spec("t", cases, timeout, gpus, stall, pause=1, look=1)
        for _ in range(starts):
            subprocess.run(["bash", "-c", shlex.split(template["spec"]["entrypoint"])[2]], env=self.env, check=False,
                           start_new_session=True)  # so that a stand-in stopping its node stops only this worker

    def rows(self, name: str) -> list[str]:
        return (self.camp / name / "diags/reducedfiles/number.txt").read_text().split()[1:]

    def test_every_case_runs_once_and_a_second_node_does_not_repeat_them(self) -> None:
        cases = "".join(f"c{index} deck\n" for index in range(19))
        self.work(cases)
        self.work(cases + "extra deck\n")
        for name in [f"c{index}" for index in range(19)] + ["extra"]:
            self.assertEqual((self.camp / name / "DONE").read_text().strip(), "complete")
            self.assertEqual((self.camp / name / "TRIES").read_text().strip(), "1")
        self.assertEqual(len({line.split()[2] for index in range(19) for line in (self.camp / f"c{index}/attempts.log").read_text().splitlines()}), 8)

    def test_cases_added_to_the_queue_are_run_by_a_node_the_campaign_already_has(self) -> None:
        self.work("a inputs_x\n")
        subprocess.run(["bash", "-c", campaign.queue_command("t", ["b inputs_x stop_at=0", "a inputs_x"])], check=True)
        self.assertEqual((self.camp / "queue.txt").read_text(), "b inputs_x stop_at=0\n")
        self.work("a inputs_x\n")
        self.assertEqual((self.camp / "b/DONE").read_text().strip(), "complete")
        self.assertEqual((self.camp / "a/TRIES").read_text().strip(), "1")

    def test_cases_given_four_gpus_each_run_two_at_a_time_with_one_process_per_gpu(self) -> None:
        self.work("".join(f"c{index} deck\n" for index in range(5)), gpus=4)
        launched = [(self.camp / f"c{index}/launched.txt").read_text().strip() for index in range(5)]
        self.assertEqual(set(launched), {"4 processes on GPUs 0,1,2,3", "4 processes on GPUs 4,5,6,7"})
        for index in range(5):
            self.assertEqual((self.camp / f"c{index}/DONE").read_text().strip(), "complete")

    def test_a_case_can_ask_for_fewer_processes_than_its_gpus(self) -> None:
        self.work("two deck np=2 some=setting\nall deck\n", gpus=8)
        self.assertEqual((self.camp / "two/launched.txt").read_text().strip(), "2 processes on GPUs 0,1,2,3,4,5,6,7")
        self.assertEqual((self.camp / "all/launched.txt").read_text().strip(), "8 processes on GPUs 0,1,2,3,4,5,6,7")

    def test_a_stopped_case_restarts_from_its_last_checkpoint_without_repeated_rows(self) -> None:
        self.work("stopped deck stop_at=25\n")
        self.assertFalse((self.camp / "stopped/DONE").exists())
        self.assertEqual(self.rows("stopped")[-1], "25")
        self.work("")  # its claim is fresh, so another node leaves it alone
        self.assertFalse((self.camp / "stopped/DONE").exists())
        old = time.time() - 600
        os.utime(self.camp / "stopped/CLAIM", (old, old))
        self.work("")
        self.assertEqual((self.camp / "stopped/DONE").read_text().strip(), "complete")
        self.assertIn("amr.restart=diags/chk000020", (self.camp / "stopped/attempts.log").read_text())
        self.assertEqual(self.rows("stopped"), [str(step) for step in range(1, 31)])

    def test_checkpoints_past_step_999999_are_ordered_by_step_and_not_as_text(self) -> None:
        diags = self.camp / "far_along/diags"
        for step in (999990, 1000000, 1000010):
            (diags / f"chk{step}").mkdir(parents=True)
        (self.camp / "far_along/run.log").write_text("STEP 999991 ends\nSTEP 1000001 ends\nSTEP 1000011 ends\n")
        self.work("far_along deck\n")
        self.assertIn("amr.restart=diags/chk1000010", (self.camp / "far_along/attempts.log").read_text())

        diags = self.camp / "pruned/diags"
        for step in (999990, 1000000, 1000010):
            (diags / f"chk{step}").mkdir(parents=True)
        self.work("pruned deck slow_after=5\n", stall=3)
        self.assertEqual(sorted(path.name for path in diags.glob("chk*")), ["chk1000000", "chk1000010"])

    def test_a_job_started_again_takes_back_the_cases_its_earlier_start_had_claimed(self) -> None:
        self.work("stopped deck stop_at=25\n", starts=2)  # the claim is seconds old when the job starts again
        self.assertEqual((self.camp / "stopped/DONE").read_text().strip(), "complete")
        self.assertIn("amr.restart=diags/chk000020", (self.camp / "stopped/attempts.log").read_text())

    def test_a_worker_whose_case_another_worker_has_claimed_stops_and_leaves_the_case_alone(self) -> None:
        worker = threading.Thread(target=self.work, args=("taken deck slow_after=5\n",), kwargs={"stall": 3})
        worker.start()
        time.sleep(1.5)
        (self.camp / "taken/CLAIM").write_text("another job\n")
        worker.join(timeout=30)
        self.assertFalse(worker.is_alive())
        self.assertFalse((self.camp / "taken/DONE").exists())
        self.assertFalse((self.camp / "taken/STALLED").exists())
        self.assertEqual((self.camp / "taken/CLAIM").read_text(), "another job\n")
        self.assertIn("lost its claim", (self.camp / "taken/attempts.log").read_text())

    def test_crashes_before_a_later_checkpoint_was_reached_do_not_count_towards_the_three(self) -> None:
        self.work("stopped deck stop_at=25\n")
        (self.camp / "stopped/CRASHES").write_text("3\n")  # as if it had crashed three times from checkpoint 10
        (self.camp / "stopped/attempts.log").write_text("job gpu 0 amr.restart=diags/chk000010\n")
        (self.camp / "stopped/CLAIM").unlink()
        self.work("")
        self.assertEqual((self.camp / "stopped/DONE").read_text().strip(), "complete")

    def test_a_case_whose_node_is_taken_away_again_and_again_at_the_same_point_is_not_failed(self) -> None:
        self.work("stopped deck stop_at=25\n")
        (self.camp / "stopped/TRIES").write_text("7\n")  # seven tries from checkpoint 20, none of them a crash
        (self.camp / "stopped/attempts.log").write_text("job gpu 0 amr.restart=diags/chk000020\n" * 7)
        (self.camp / "stopped/CLAIM").unlink()
        self.work("")
        self.assertEqual((self.camp / "stopped/DONE").read_text().strip(), "complete")

    def test_a_checkpoint_cut_short_is_not_used(self) -> None:
        self.work("stopped deck stop_at=20\n")  # stopped right after writing checkpoint 20: no step 21 in the log
        old = time.time() - 600
        os.utime(self.camp / "stopped/CLAIM", (old, old))
        self.work("")
        self.assertIn("amr.restart=diags/chk000010", (self.camp / "stopped/attempts.log").read_text())
        self.assertEqual(self.rows("stopped"), [str(step) for step in range(1, 31)])

    def test_a_case_that_keeps_crashing_fails_after_three_tries(self) -> None:
        self.work("bad deck crash=1\ngood deck\n")
        self.assertEqual((self.camp / "bad/DONE").read_text().strip(), "failed after 3 tries")
        self.assertEqual((self.camp / "good/DONE").read_text().strip(), "complete")

    def test_a_case_that_writes_nothing_is_stopped_and_failed_without_another_try(self) -> None:
        self.work("hung deck hang=1\ngood deck\n", stall=2)
        self.assertEqual((self.camp / "hung/DONE").read_text().strip(), "failed: no output for 2 seconds")
        self.assertEqual((self.camp / "hung/TRIES").read_text().strip(), "1")
        self.assertEqual((self.camp / "good/DONE").read_text().strip(), "complete")

    def test_a_case_out_of_time_carries_on_from_a_checkpoint_it_reached_and_fails_if_it_reached_none(self) -> None:
        self.work("far deck slow_after=15\nnowhere deck hang=1\n", timeout=2)
        self.assertEqual((self.camp / "far/DONE").read_text().strip(), "complete")
        self.assertIn("amr.restart=diags/chk000010", (self.camp / "far/attempts.log").read_text())
        self.assertEqual(self.rows("far"), [str(step) for step in range(1, 31)])
        self.assertEqual((self.camp / "nowhere/DONE").read_text().strip(), "failed: time limit")


class LocalTest(unittest.TestCase):
    """`campaign.py local`, with the stand-in in place of the CPU builds of WarpX."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())
        stand_in = self.root / "warpx"
        stand_in.write_text(STAND_IN)
        stand_in.chmod(0o755)
        patched = mock.patch.multiple(campaign, LOCAL={"inputs_rz_": stand_in}, RESULTS=self.root / "results",
                                      REGISTRY=self.root / "registry.json", PATCHES=[])
        patched.start()
        self.addCleanup(patched.stop)
        self.cases = self.root / "cases.txt"

    def run_local(self, cases: str, only: str = "") -> None:
        self.cases.write_text(cases)
        campaign.local(argparse.Namespace(name="t", cases=self.cases, question="q", only=only, threads=1))

    def test_cases_run_to_the_end_are_complete_and_others_failed_and_none_runs_twice(self) -> None:
        self.run_local("good inputs_rz_x\nbad inputs_rz_x crash=1\nlater inputs_rz_x\n", only="g")
        self.run_local("good inputs_rz_x\nbad inputs_rz_x crash=1\nlater inputs_rz_x\n")
        folder = campaign.RESULTS / "t"
        self.assertEqual((folder / "good/DONE").read_text().strip(), "complete")
        self.assertEqual((folder / "later/DONE").read_text().strip(), "complete")
        self.assertEqual((folder / "bad/DONE").read_text().strip(), "failed: exit code 134")
        self.assertEqual((folder / "good/run.log").read_text().count("STEP 1 ends"), 1)
        self.assertEqual(list((folder / "good/diags").glob("chk*")), [])
        self.assertEqual(len(campaign.registry()["t"]["cases"]), 3)

    def test_a_case_given_again_with_other_settings_is_refused(self) -> None:
        self.run_local("good inputs_rz_x\n")
        with self.assertRaises(AssertionError):
            self.run_local("good inputs_rz_x crash=1\n")

    def test_a_complete_case_that_was_never_reduced_is_named_rather_than_silently_left_out_of_the_table(self) -> None:
        campaign.REGISTRY.write_text(json.dumps({"t": {"question": "q", "jobs": [], "cases": [
            "reduced inputs_rz_spindle_fed", "bare inputs_rz_spindle_fed", "stopped inputs_rz_spindle_fed"]}}))
        for case, state in (("reduced", "complete"), ("bare", "complete"), ("stopped", "failed: time limit")):
            (campaign.RESULTS / "t" / case).mkdir(parents=True)
            (campaign.RESULTS / "t" / case / "DONE").write_text(state + "\n")
        (campaign.RESULTS / "t/reduced/measured.json").write_text('{"width": 1}')
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            campaign.table("t")
        self.assertEqual((campaign.RESULTS / "t/table.jsonl").read_text(), '{"case": "reduced", "width": 1}\n')
        self.assertIn("complete but not reduced", said.getvalue())
        self.assertTrue(said.getvalue().strip().endswith(": bare"))

    def test_launchers_are_counted_only_on_nodes_without_taints_and_by_the_cpu_not_yet_asked_for(self) -> None:
        def node(name: str, taints: list) -> dict:
            return {"metadata": {"name": name}, "spec": {"taints": taints}, "status": {"allocatable": {"cpu": "15890m"}}}

        def described(asked: str) -> str:
            return f"Allocated resources:\n  Resource  Requests  Limits\n  --------  --------  ------\n  cpu  {asked} (97%)  31 (195%)\n"

        nodes = {"items": [node("full", []), node("open", []), node("gpu", [{"key": "nvidia.com/gpu"}])]}
        # 15.89 - 15.51 leaves no half core; 15.89 - 14.6 leaves two; the GPU node's free CPU is not for launchers.
        about = {"full": described("15510m"), "open": described("14600m"), "gpu": described("1")}
        self.assertEqual(campaign.launcher_room(nodes, about), 2)


if __name__ == "__main__":
    unittest.main()
