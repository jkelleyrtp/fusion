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
STAND_IN = r"""#!/bin/bash
start=0; stop=0; crash=0
for arg in "$@"; do case $arg in amr.restart=*) start=$((10#${arg##*chk}));; stop_at=*) stop=${arg#*=};; crash=*) crash=1;; esac; done
[ $crash -eq 1 ] && exit 134
mkdir -p diags/reducedfiles
[ $start -eq 0 ] && echo "#step" > diags/reducedfiles/number.txt
for step in $(seq $((start + 1)) 30); do
  echo "STEP $step ends"; echo "$step" >> diags/reducedfiles/number.txt
  [ $((step % 10)) -eq 0 ] && mkdir -p diags/chk$(printf %06d $step)
  [ $start -eq 0 ] && [ $step -eq $stop ] && pkill -9 -s $(ps -o sid= -p $$ | tr -d ' ')
done
exit 0
"""


class WorkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.shared = Path(tempfile.mkdtemp())
        self.camp = self.shared / "campaigns/t"
        tools = self.shared / "bin"
        tools.mkdir()
        for name, text in (("warpx", STAND_IN), ("nvidia-smi", "#!/bin/sh\n")):
            (tools / name).write_text(text)
            (tools / name).chmod(0o755)
        self.env = {**os.environ, "WARPX": str(tools / "warpx"), "PATH": f"{tools}:{os.environ['PATH']}"}
        campaign.SHARED = str(self.shared)

    def work(self, cases: str) -> None:
        """Run one node's worker to the end on campaign t, adding `cases` to its queue."""
        _, template = campaign.job_spec("t", cases, 60)
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


if __name__ == "__main__":
    unittest.main()
