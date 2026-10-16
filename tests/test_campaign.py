"""The campaign worker script, run locally with a stand-in for WarpX."""
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "warpx"))
import campaign

# Stands in for WarpX: runs to step 30 with a checkpoint every 10 steps, from the checkpoint named by amr.restart.
# A case given `stop_at=N` is stopped at step N as if its node had been taken away, unless it is restarting.
# A case given `hang=1` writes nothing and never ends.
# It stops the worker's shells in one signal before itself (`timeout` gives it a process group of its own), so
# that no shell outlives it long enough to claim the case again.
STAND_IN = r"""#!/bin/bash
start=0; stop=0; crash=0
for arg in "$@"; do case $arg in amr.restart=*) start=$((10#${arg##*chk}));; stop_at=*) stop=${arg#*=};; crash=*) crash=1;; hang=*) exec sleep 600;; esac; done
[ $crash -eq 1 ] && exit 134
mkdir -p diags/reducedfiles
[ $start -eq 0 ] && echo "#step" > diags/reducedfiles/number.txt
for step in $(seq $((start + 1)) 30); do
  echo "STEP $step ends"; echo "$step" >> diags/reducedfiles/number.txt
  [ $((step % 10)) -eq 0 ] && mkdir -p diags/chk$(printf %06d $step)
  [ $start -eq 0 ] && [ $step -eq $stop ] && { kill -9 -- -$(ps -o sid= -p $$ | tr -d ' '); kill -9 0; }
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

    def work(self, cases: str, gpus: int = 1, stall: int = 1800) -> None:
        """Run one node's worker to the end on campaign t, adding `cases` to its queue."""
        _, template = campaign.job_spec("t", cases, 60, gpus, stall)
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


if __name__ == "__main__":
    unittest.main()
