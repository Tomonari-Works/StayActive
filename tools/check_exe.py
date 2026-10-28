"""配布 EXE を別プロセスで起動し、制限時間内の正常終了を必須にする。"""

from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    executable = (root / sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "dist" / "StayActive.exe"
    if not executable.is_file():
        print("Missing executable:", executable)
        return 1
    process = subprocess.Popen([str(executable), "--smoke-test"], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    try:
        stdout, stderr = process.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        # 自分が起動した onefile の子プロセスまで終了し、検証をハングさせない。
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
        process.communicate(timeout=10)
        print("Packaged startup timed out.", file=sys.stderr)
        return 1
    if process.returncode != 0:
        print(stdout, end="")
        print(stderr, end="", file=sys.stderr)
        print(f"Packaged startup failed: exit {process.returncode}", file=sys.stderr)
        return 1
    print("Packaged startup, SVG loading, and clean shutdown: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
