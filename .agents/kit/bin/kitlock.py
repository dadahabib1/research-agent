"""The kit's lock helper (contract C7 section 3, C8 section 5): the one way kit code holds a named lock and runs
children under it. Standard library only; imported by `__file__` (C1 section 2).

    with kitlock.claim(path, {"format": "review-lock", "version": 1, "id": ...}) as lock:
        proc = lock.popen(["codex", ...])
        proc.communicate(timeout=...)  # every child has a timeout: the caller's (C7 section 6, C8 section 5)

On a timeout, let the exception leave the lock's `with` block: the release ends the child and its children,
and only then does the caller read or discard what is left of its output. Waiting on the child while still
holding the lock can hang: a `with subprocess.Popen` block of its own waits with no timeout, and after
`proc.kill()` a grandchild still holding the child's output pipe keeps `proc.communicate()` from returning.
A caller that needs the lock again after a timeout claims it again.

- **The lock** is an OS lock on one byte at offset 2**30 of the open lock file (`msvcrt.locking` on Windows,
  `fcntl.lockf` elsewhere). The OS frees it when the holding process ends, however it ends, so there is no
  expiry and no takeover: a file whose lock is free is free, whatever it says.
- **The holder's JSON** is written at the start of the file after the lock is taken (the caller's fields, plus
  `pid` and `acquired_at` when the caller leaves them out) and stays readable while the lock is held: the
  locked byte lies past it. A clean release empties the file; the file is never deleted, since a deleted
  file would let a second process lock a new file of the same name.
- **Children** started through `Lock.popen` join a Windows job object made with kill-on-job-close: they and
  the processes they start end when the holder releases the lock or its process ends, however it ends
  (M86). Each child starts suspended and runs only once it is in the job, so none of its own children can
  start outside it; one the caller kills on its timeout leaves none running past release. One gap: a holder
  killed between the child's creation and its assignment (microseconds) leaves that child suspended outside
  the job. It never runs, so it touches no checkout; it lingers until the machine restarts or someone ends it. Elsewhere there
  is no job object and children are not tied to the holder: not built, since C7 section 3 names the
  Windows job object only.
- **Busy:** `claim` raises `Busy`, carrying the holder's JSON as read from the file (`None` if it is still
  unreadable after a second: a holder that has just taken the lock writes it within milliseconds).

The lock is per open file on Windows; with `fcntl` it is per process, and closing any other descriptor of the
same file in the holding process drops it, so a holder never opens its own lock file a second time.
"""

from __future__ import annotations

import errno
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # C1 section 2: imports by __file__ under -I

import workfiles  # noqa: E402

OFFSET = 1 << 30  # the locked byte; the holder's JSON at the start of the file never reaches it
READ_TRIES, READ_PAUSE = 20, 0.05  # Busy: how long to wait for a new holder's JSON
BUSY_ERRNOS = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}  # msvcrt: EACCES (13, measured); fcntl: EAGAIN/EACCES

if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for _name, _res, _args in (
            ("CreateJobObjectW", wintypes.HANDLE, [wintypes.LPVOID, wintypes.LPCWSTR]),
            ("SetInformationJobObject", wintypes.BOOL, [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                                         wintypes.DWORD]),
            ("AssignProcessToJobObject", wintypes.BOOL, [wintypes.HANDLE, wintypes.HANDLE]),
            ("OpenProcess", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            ("OpenThread", wintypes.HANDLE, [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]),
            ("ResumeThread", wintypes.DWORD, [wintypes.HANDLE]),
            ("CreateToolhelp32Snapshot", wintypes.HANDLE, [wintypes.DWORD, wintypes.DWORD]),
            ("Thread32First", wintypes.BOOL, [wintypes.HANDLE, wintypes.LPVOID]),
            ("Thread32Next", wintypes.BOOL, [wintypes.HANDLE, wintypes.LPVOID]),
            ("CloseHandle", wintypes.BOOL, [wintypes.HANDLE])):
        getattr(_k32, _name).restype, getattr(_k32, _name).argtypes = _res, _args

    class _BasicLimits(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _ExtendedLimits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class _ThreadEntry(ctypes.Structure):  # THREADENTRY32
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                    ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]

    _EXTENDED_LIMIT_INFORMATION = 9  # JobObjectExtendedLimitInformation
    _KILL_ON_JOB_CLOSE = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    _CREATE_SUSPENDED = 0x4
    _PROCESS_SET_QUOTA, _PROCESS_TERMINATE, _THREAD_SUSPEND_RESUME = 0x0100, 0x0001, 0x0002
    _SNAPTHREAD, _INVALID = 0x4, wintypes.HANDLE(-1).value
else:
    import fcntl


class Busy(Exception):
    """The lock is held by another process; `holder` is its JSON from the file, or None if unreadable."""

    def __init__(self, path: Path, holder: dict | None):
        self.path, self.holder = Path(path), holder
        super().__init__(f"{self.path} is held by {json.dumps(holder) if holder else 'an unknown holder'}")


def read_holder(path: Path) -> dict | None:
    """The JSON at the start of a lock file, or None (missing, empty, half-written or not an object). It says
    who holds the lock only while the lock is held: `claim` is the only test of that. Never call it in the
    holding process on a POSIX system (see the module's note)."""
    try:
        with open(path, "rb") as f:
            data = json.loads(f.read(OFFSET // 1024).decode("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _job() -> int | None:
    """A new job object whose processes end when its last handle closes (the holder's, never inherited)."""
    if sys.platform != "win32":
        return None
    job = _k32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = _ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
    if not _k32.SetInformationJobObject(job, _EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits),
                                        ctypes.sizeof(limits)):
        error = ctypes.get_last_error()
        _k32.CloseHandle(job)
        raise ctypes.WinError(error)
    return job


def _resume(pid: int) -> None:
    """Resume the threads of a process started suspended (Popen keeps no thread handle)."""
    snap = _k32.CreateToolhelp32Snapshot(_SNAPTHREAD, 0)
    if snap == _INVALID:
        raise ctypes.WinError(ctypes.get_last_error())
    resumed = 0
    try:
        entry = _ThreadEntry(dwSize=ctypes.sizeof(_ThreadEntry))
        more = _k32.Thread32First(snap, ctypes.byref(entry))
        while more:
            if entry.th32OwnerProcessID == pid:
                thread = _k32.OpenThread(_THREAD_SUSPEND_RESUME, False, entry.th32ThreadID)
                if thread:
                    if _k32.ResumeThread(thread) != 0xFFFFFFFF:
                        resumed += 1
                    _k32.CloseHandle(thread)
            more = _k32.Thread32Next(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    if not resumed:
        raise OSError(f"could not resume process {pid}")


class Lock:
    """A held lock. Release it with `release()` or by leaving its `with` block; ending the process frees it."""

    def __init__(self, path: Path, fd: int, job: int | None):
        self.path, self._fd, self._job = path, fd, job

    def popen(self, args, **kwargs) -> subprocess.Popen:
        """`subprocess.Popen`, the child inside this lock's job object (Windows). It is killed if it cannot be
        put there: no child runs outside the job."""
        if self._fd is None:
            raise RuntimeError(f"{self.path} is not held")
        if self._job is None:
            return subprocess.Popen(args, **kwargs)
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | _CREATE_SUSPENDED
        proc = subprocess.Popen(args, **kwargs)
        try:
            handle = _k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, proc.pid)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not _k32.AssignProcessToJobObject(self._job, handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                _k32.CloseHandle(handle)
            _resume(proc.pid)
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        return proc

    def release(self) -> None:
        """End every child still running (close the job), empty the file, then free the lock. Idempotent."""
        if self._job is not None:
            _k32.CloseHandle(self._job)
            self._job = None
        if self._fd is not None:
            fd, self._fd = self._fd, None
            try:
                os.ftruncate(fd, 0)
            finally:
                os.close(fd)  # the OS frees the lock with the file

    def __enter__(self) -> Lock:
        return self

    def __exit__(self, *exc) -> None:
        self.release()


def claim(path: Path, fields: dict) -> Lock:
    """Take the lock at `path` (made, with its folder, if missing) and write `fields` as the holder's JSON, or
    raise `Busy` at once; no waiting (a caller that waits polls)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0))  # not inherited (PEP 446)
    try:
        if sys.platform == "win32":
            os.lseek(fd, OFFSET, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, OFFSET, os.SEEK_SET)
    except OSError as e:
        os.close(fd)
        if e.errno not in BUSY_ERRNOS:
            raise
        holder = None
        for _ in range(READ_TRIES):
            holder = read_holder(path)
            if holder is not None:
                break
            time.sleep(READ_PAUSE)
        raise Busy(path, holder) from None
    try:
        holder = {**fields}
        holder.setdefault("pid", os.getpid())
        holder.setdefault("acquired_at", workfiles.utc_iso())
        data = json.dumps(holder).encode("utf-8")
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        while data:
            data = data[os.write(fd, data):]
        os.fsync(fd)
        return Lock(path, fd, _job())
    except BaseException:
        os.close(fd)
        raise
