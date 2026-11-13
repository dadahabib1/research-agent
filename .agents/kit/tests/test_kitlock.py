"""The kit's lock helper (`.agents/kit/bin/kitlock.py`, contract C7 section 3, C8 section 5), end to end: real
processes claim one lock file, a real holder is killed with `taskkill /F`, and every result is read from the
lock file on disk and from the operating system's process table, not from the helper's own report.

Run in a project with `python -I -m unittest discover -s .agents/kit/tests`, and by agent-kit's pytest.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent  # .agents/kit
BIN = KIT / "bin"
sys.path.insert(0, str(BIN))

import kitlock  # noqa: E402

WINDOWS = sys.platform == "win32"
# The interpreter itself, not a virtual environment's `python.exe`: that is a launcher running the interpreter
# as its child, and killing it ends the interpreter too, so `taskkill` of its pid would not test the helper (M86).
PYTHON = getattr(sys, "_base_executable", None) or sys.executable

# A claimant: waits for the shared start time, claims the lock, holds it, and on request starts a child under
# it: `python -c` that starts a grandchild, prints its pid, and sleeps 10 minutes, as the grandchild does (a
# Codex `.cmd` shim starting node). It prints one JSON line: held (with both pids) or busy.
CLAIMANT = r"""
import json, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
import kitlock
GRANDPARENT = sys.argv[7]
path, ident, start, hold, child = sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
while time.time() < start:
    pass
try:
    lock = kitlock.claim(path, {"format": "test-lock", "version": 1, "id": ident})
except kitlock.Busy as busy:
    print(json.dumps({"busy": busy.holder}), flush=True)
    sys.exit(3)
out = {"held": ident}
if child == "child":
    proc = lock.popen([sys.executable, "-I", "-c", GRANDPARENT], stdout=subprocess.PIPE, text=True)
    out["child"], out["grandchild"] = proc.pid, int(proc.stdout.readline())
print(json.dumps(out), flush=True)
time.sleep(hold)
lock.release()
"""


# A child that starts a grandchild, prints its pid, and sleeps 10 minutes, as the grandchild does.
GRANDPARENT = ("import subprocess, sys, time; "
               "g = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(600)']); "
               "print(g.pid, flush=True); time.sleep(600)")


def claimant(path: Path, ident: str, start: float, hold: float, child: bool = False) -> subprocess.Popen:
    return subprocess.Popen([PYTHON, "-I", "-c", CLAIMANT, str(BIN), str(path), ident, str(start),
                             str(hold), "child" if child else "-", GRANDPARENT], stdout=subprocess.PIPE,
                            text=True)


def on_disk(path: Path) -> dict:
    """The holder's JSON as any reader sees it: a plain read of the file, no lock taken."""
    return json.loads(path.read_text(encoding="utf-8"))


class Process:
    """A handle to a process by pid, opened before anything is killed so a reused pid cannot fool the wait."""

    def __init__(self, pid: int):
        import ctypes
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k32.OpenProcess.restype = ctypes.c_void_p
        self.k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.k32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.k32.CloseHandle.argtypes = [ctypes.c_void_p]
        # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE
        self.handle = self.k32.OpenProcess(0x00100000 | 0x1000 | 0x0001, False, pid)
        if not self.handle:
            raise OSError(f"cannot open process {pid}: error {ctypes.get_last_error()}")

    def ended_within(self, seconds: float) -> bool:
        return self.k32.WaitForSingleObject(self.handle, int(seconds * 1000)) == 0  # WAIT_OBJECT_0

    def close(self):
        self.k32.TerminateProcess(self.handle, 1)  # cleanup only: a child that survived the test
        self.k32.CloseHandle(self.handle)


class Lock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "locks" / "review-codex.lock"

    def test_ac1_two_processes_claim_at_once_one_holds_and_the_other_names_it(self):
        """Two reviews in one checkout, or two merges at once (C7 section 3, C8 section 5, T19)."""
        for round_ in range(5):
            with self.subTest(round=round_):
                start = time.time() + 1.5  # both are running and spinning before it
                procs = [claimant(self.path, f"r{round_}-{n}", start, 2.0) for n in ("a", "b")]
                lines = [json.loads(p.stdout.readline()) for p in procs]
                held = [line["held"] for line in lines if "held" in line]
                self.assertEqual(len(held), 1, lines)
                holder = procs[[("held" in line) for line in lines].index(True)]
                file_json = on_disk(self.path)  # readable while held (the locked byte lies past it)
                self.assertEqual((file_json["id"], file_json["pid"]), (held[0], holder.pid))
                busy = next(line["busy"] for line in lines if "busy" in line)
                self.assertEqual((busy["id"], busy["pid"]), (held[0], holder.pid), "busy must name the holder")
                for p in procs:
                    p.stdout.read()
                    p.wait(timeout=30)
                    p.stdout.close()
                self.assertEqual(sorted(p.returncode for p in procs), [0, 3])
                self.assertTrue(self.path.is_file(), "the lock file is never deleted")

    @unittest.skipUnless(WINDOWS, "the job object is Windows only")
    def test_ac2_a_killed_holder_frees_the_lock_at_once_and_its_child_is_gone(self):
        """A crashed review's checkout freed for the next at once, and no Codex or test process left using it
        (C7 section 3, M86)."""
        holder = claimant(self.path, "killed", time.time(), 600, child=True)
        line = json.loads(holder.stdout.readline())
        child, grandchild = Process(line["child"]), Process(line["grandchild"])
        self.addCleanup(child.close)
        self.addCleanup(grandchild.close)
        self.assertFalse(child.ended_within(0.5), "the child must be running before the holder is killed")
        self.assertFalse(grandchild.ended_within(0), "the grandchild must be running before the holder is killed")
        with self.assertRaises(kitlock.Busy):
            kitlock.claim(self.path, {"format": "test-lock", "version": 1, "id": "too-early"})
        holder.kill()  # TerminateProcess, as taskkill /F; through our own handle, so the reviewer's sandbox allows it (M119)
        holder.wait(timeout=30)
        holder.stdout.close()
        lock = kitlock.claim(self.path, {"format": "test-lock", "version": 1, "id": "next"})  # one try: at once
        self.addCleanup(lock.release)
        self.assertEqual(on_disk(self.path)["id"], "next")
        self.assertTrue(child.ended_within(10), "the killed holder's child is still running")
        self.assertTrue(grandchild.ended_within(10), "the killed holder's child's child is still running")

    @unittest.skipUnless(WINDOWS, "the job object is Windows only")
    def test_a_child_past_its_timeout_ends_when_the_lock_is_released(self):
        """A hung Codex or test run: the caller's timeout leaves the `with` block, and the release must end the
        child and its children before the next review resets the checkout (C7 section 3, the docstring's
        pattern)."""
        with self.assertRaises(subprocess.TimeoutExpired):
            with kitlock.claim(self.path, {"format": "test-lock", "version": 1, "id": "hung"}) as lock:
                proc = lock.popen([PYTHON, "-I", "-c", GRANDPARENT], stdout=subprocess.PIPE, text=True)
                grandchild = int(proc.stdout.readline())
                child, grand = Process(proc.pid), Process(grandchild)
                self.addCleanup(child.close)
                self.addCleanup(grand.close)
                proc.communicate(timeout=0.5)
        self.assertEqual(self.path.read_bytes(), b"", "a clean release empties the file")
        self.assertTrue(child.ended_within(10), "the timed-out child is still running after release")
        self.assertTrue(grand.ended_within(10), "the timed-out child's child is still running after release")
        proc.stdout.close()
        proc.wait(timeout=10)

    def test_ac3_a_file_with_stale_json_and_no_holder_is_free(self):
        """A crashed holder's file says who held it; the lock is free all the same (no expiry, no takeover)."""
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"format": "test-lock", "version": 1, "id": "crashed", "pid": 4,
                                         "acquired_at": "2026-10-01T00:00:00Z"}), encoding="utf-8")
        lock = kitlock.claim(self.path, {"format": "test-lock", "version": 1, "id": "fresh"})
        try:
            self.assertEqual((on_disk(self.path)["id"], on_disk(self.path)["pid"]), ("fresh", os.getpid()))
        finally:
            lock.release()
        self.assertTrue(self.path.is_file(), "the lock file is never deleted")


# AC4: the helper is the only kit code that takes an OS lock on a file.
LOCK_CALLS = re.compile(r"msvcrt\s*\.\s*locking|\bLK_[A-Z]+\b|fcntl\s*\.\s*(lockf|flock)|\bLockFile(Ex)?\b")
LOCK_EXEMPT = ("bin/kitlock.py", "tests/test_kitlock.py")


def lock_openers(kit: Path) -> list[str]:
    """`path:line: text` for each OS file-lock call in the kit's Python files outside the helper."""
    found = []
    for path in sorted(kit.rglob("*.py")):
        rel = path.relative_to(kit).as_posix()
        if rel in LOCK_EXEMPT:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if LOCK_CALLS.search(line):
                found.append(f"{rel}:{number}: {line.strip()[:120]}")
    return found


class OnlyTheHelper(unittest.TestCase):
    def test_ac4_no_other_kit_code_locks_a_file(self):
        """A script with its own lock would not be released with its process, or would block the helper's."""
        self.assertEqual(lock_openers(KIT), [])

    def test_ac4_a_planted_lock_call_is_found(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        planted = {"bin/review.py": "msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)\n",
                   "hooks/x.py": "fcntl.lockf(fd, fcntl.LOCK_EX)\n",
                   "bin/kitlock.py": "msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)\n",  # the helper itself: allowed
                   "bin/ok.py": "blocking = True  # a lookalike word\n"}
        for rel, text in planted.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_text(text, encoding="utf-8")
        self.assertEqual([f.split(":")[0] for f in lock_openers(tmp)], ["bin/review.py", "hooks/x.py"])


if __name__ == "__main__":
    unittest.main()
