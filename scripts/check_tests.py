"""Bounded Git test checks with a live terminal stream and persistent logs."""

import argparse
import codecs
import math
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMOKE_TESTS = (
    "tests/test_auth_and_health.py",
    "tests/test_security_middleware.py",
    "tests/test_card_automation_schemas.py",
    "tests/test_question_matching.py",
)
EXTRA_MODULE_LIMIT = 3


def components(files: list[str]) -> set[str]:
    selected = set()
    for filename in files:
        if filename in {"Makefile", ".pre-commit-config.yaml"} or filename.startswith("scripts/"):
            selected.update({"backend", "frontend"})
        elif filename.startswith("backend/"):
            selected.add("backend")
        elif filename.startswith("frontend/") and not filename.startswith("frontend/.pnpm-store/"):
            selected.add("frontend")
    return selected


def backend_quick_tests(files: list[str], root: Path = ROOT) -> tuple[list[str], int]:
    candidates = set()
    for filename in files:
        path = Path(filename)
        if filename.startswith("backend/tests/test_") and path.suffix == ".py":
            candidates.add(str(path.relative_to("backend")))
        elif filename.startswith("backend/app/") and path.suffix == ".py":
            candidates.add(f"tests/test_{path.stem}.py")
            if len(path.parts) > 3:
                candidates.add(f"tests/test_{path.parts[2]}.py")
    extra = sorted(
        filename
        for filename in candidates
        if filename not in SMOKE_TESTS and (root / "backend" / filename).is_file()
    )
    return [*SMOKE_TESTS, *extra[:EXTRA_MODULE_LIMIT]], max(0, len(extra) - EXTRA_MODULE_LIMIT)


def stop_process(process: subprocess.Popen[bytes]) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        process.wait()
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def run_check(
    command: list[str], cwd: Path, log_path: Path, timeout: float, *, terminal_output: bool = True
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    output_lock = threading.Lock()
    try:
        terminal = os.open("/dev/tty", os.O_WRONLY | os.O_NONBLOCK) if terminal_output else None
    except OSError:
        terminal = None
    with log_path.open("w", encoding="utf-8") as log:

        def write(value: str) -> None:
            with output_lock:
                log.write(value)
                log.flush()
                sys.stdout.write(value)
                sys.stdout.flush()
                if terminal is not None:
                    try:
                        os.write(terminal, value.encode("utf-8"))
                    except OSError:
                        pass  # The complete output remains available in the log.

        write(f"\nRunning {' '.join(command)}\nLog: {log_path}\nTimeout: {timeout:.0f}s\n")
        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PATH"] = os.pathsep.join(
            [str(ROOT / ".local/node/bin"), str(ROOT / ".local/bin"), environment.get("PATH", "")]
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=os.name == "posix",
            )
        except OSError as error:
            write(f"Could not start tests: {error}\n")
            if terminal is not None:
                os.close(terminal)
            return 1
        assert process.stdout is not None

        def pump_output() -> None:
            decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            while chunk := os.read(process.stdout.fileno(), 4096):
                write(decoder.decode(chunk))
            write(decoder.decode(b"", final=True))

        reader = threading.Thread(target=pump_output, daemon=True)
        reader.start()
        result = 0
        try:
            while process.poll() is None:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    process.wait(timeout=min(15, remaining))
                except subprocess.TimeoutExpired:
                    write(f"\n[still running: {time.monotonic() - started:.0f}s; see {log_path}]\n")
            result = process.returncode
        except subprocess.TimeoutExpired:
            stop_process(process)
            write(f"\nTest check exceeded {timeout:.0f}s; stopping process group.\n")
            result = 124
        except KeyboardInterrupt:
            stop_process(process)
            result = 130
        finally:
            reader.join(timeout=5)
            process.stdout.close()
            if terminal is not None:
                os.close(terminal)
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("quick", "full"))
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()
    files = args.files
    if args.mode == "quick":
        staged = (
            subprocess.check_output(["git", "diff", "--cached", "--name-only", "-z"], cwd=ROOT)
            .decode()
            .split("\0")
        )
        # pre-commit does not pass deleted paths as filenames.
        files = sorted(set(files) | set(staged))
    selected = {"backend", "frontend"} if args.mode == "full" else components(files)
    if not selected:
        print("No backend/frontend changes; quick tests are not needed.")
        return 0
    limit = float(
        os.environ.get("CHECK_TEST_TIMEOUT_SECONDS", "300" if args.mode == "quick" else "1200")
    )
    if not math.isfinite(limit) or limit <= 0:
        parser.error("CHECK_TEST_TIMEOUT_SECONDS must be positive")
    deadline = time.monotonic() + limit
    for component in ("backend", "frontend"):
        if component not in selected:
            continue
        if component == "backend":
            command = [sys.executable, "-m", "pytest", "-v", "--durations=10"]
            if args.mode == "quick":
                modules, deferred = backend_quick_tests(files)
                command.extend(modules)
                print(
                    f"Backend smoke check: {len(modules)} modules; "
                    f"{deferred} deferred to full tests."
                )
        else:
            command = ["pnpm", "test"]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print("Test check exhausted its time budget.")
            return 124
        result = run_check(
            command,
            ROOT / component,
            ROOT / ".local/checks" / f"{args.mode}-{component}.log",
            remaining,
        )
        if result:
            return result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
