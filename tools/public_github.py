"""公開用の本人確認を強制する。トークンはメモリー内だけで扱い、表示しない。"""

import json
import os
from pathlib import Path
import subprocess
import sys

APPROVED_LOGIN = "tomonariworks"
APPROVED_ID = 223291788
REPOSITORY = "Tomonari-Works/StayActive"
ROOT = Path(__file__).resolve().parents[1]


def public_environment():
    env = os.environ.copy()
    # 私用の環境変数や CLI プロファイルが認証を上書きしないようにする。
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        env.pop(name, None)
    result = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT,
        text=True, encoding="utf-8", capture_output=True, check=True)
    profile = Path(result.stdout.strip()) / "gh-public"
    profile.mkdir(parents=True, exist_ok=True)
    env["GH_CONFIG_DIR"] = str(profile)
    env["GH_HOST"] = "github.com"
    env["GH_PROMPT_DISABLED"] = "1"
    return env


def verify_identity(env):
    # GH_CONFIG_DIR だけでは OS keyring の既定トークンを分離できない。
    # 必ず公開アカウントを指定して取得し、子プロセスだけの環境変数で固定する。
    token = subprocess.run(["gh", "auth", "token", "--hostname", "github.com", "--user", APPROVED_LOGIN],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if token.returncode or not token.stdout.strip():
        raise RuntimeError("Public account authentication is missing. Run: python tools/public_github.py login (TomonariWorks only).")
    env["GH_TOKEN"] = token.stdout.strip()
    result = subprocess.run(["gh", "api", "user", "--hostname", "github.com", "--jq", "{login,id}"],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError("Public account authentication failed. No write operation was performed.")
    try:
        identity = json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Invalid GitHub identity response. Public operations are blocked.") from exc
    if identity.get("id") != APPROVED_ID or identity.get("login", "").casefold() != APPROVED_LOGIN:
        raise RuntimeError("The authenticated account is not approved. Public operations are blocked.")


def login_public_account(env):
    # gh の keyring にある「既定アカウント」はプロファイル間で共有される。
    # ログイン後に元のローカル選択を戻す。元アカウントで GitHub の書き込みは行わない。
    original_env = os.environ.copy()
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
        original_env.pop(name, None)
    previous = subprocess.run(["gh", "auth", "status", "--hostname", "github.com", "--json", "hosts",
        "--jq", '.hosts["github.com"][] | select(.active) | .login'], cwd=ROOT, env=original_env,
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    previous_login = previous.stdout.strip() if previous.returncode == 0 else ""
    login_env = env.copy()
    login_env.pop("GH_PROMPT_DISABLED", None)
    login_env.pop("GH_TOKEN", None)
    try:
        code = subprocess.run(["gh", "auth", "login", "--hostname", "github.com", "--git-protocol",
            "https", "--web", "--scopes", "repo,workflow"], cwd=ROOT, env=login_env).returncode
    finally:
        if previous_login:
            restored = subprocess.run(["gh", "auth", "switch", "--hostname", "github.com", "--user", previous_login],
                cwd=ROOT, env=original_env, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if restored.returncode:
                raise RuntimeError("Could not restore the original local CLI account selection. Public operations are blocked.")
    if code:
        return code
    verify_identity(env)
    print("Public GitHub identity verified: TomonariWorks")
    return 0


def verify_commit_identity():
    for key, expected in (("user.name", "TomonariWorks"),
                          ("user.email", "223291788+tomonariworks@users.noreply.github.com")):
        result = subprocess.run(["git", "config", "--get", key], cwd=ROOT,
            text=True, encoding="utf-8", capture_output=True, check=True)
        if result.stdout.strip() != expected:
            raise RuntimeError("Git のコミット名義が公開用設定と一致しません。push を中止します。")


def verify_outgoing_commits(branch):
    result = subprocess.run(["git", "log", "origin/main.." + branch, "--format=%an%x00%ae%x00%cn%x00%ce"],
        cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=True)
    approved_email = "223291788+tomonariworks@users.noreply.github.com"
    for line in result.stdout.splitlines():
        author, author_email, committer, committer_email = line.split("\0")
        if (author != "TomonariWorks" or committer != "TomonariWorks"
                or author_email != approved_email or committer_email != approved_email):
            raise RuntimeError("An outgoing commit has an unapproved author or committer. Push blocked.")


def main():
    args = sys.argv[1:]
    command = args.pop(0) if args else "check"
    env = public_environment()
    if command == "login":
        return login_public_account(env)
    verify_identity(env)
    if command == "check":
        print("Public GitHub identity verified: TomonariWorks")
        return 0
    if command == "gh":
        if not args:
            raise RuntimeError("gh コマンドの引数が必要です。")
        if args[0] == "auth" or "--show-token" in args:
            raise RuntimeError("Use the wrapper's login/check commands for authentication. Secret-output commands are blocked.")
        return subprocess.run(["gh", *args], cwd=ROOT, env=env).returncode
    if command == "fetch":
        return subprocess.run(["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential",
            "fetch", "https://github.com/" + REPOSITORY + ".git", "+refs/heads/*:refs/remotes/origin/*",
            "refs/tags/*:refs/tags/*"], cwd=ROOT, env=env).returncode
    if command == "push":
        if len(args) != 1 or args[0].startswith("-"):
            raise RuntimeError("push するブランチを 1 本指定してください。")
        verify_commit_identity()
        verify_outgoing_commits(args[0])
        env["STAYACTIVE_PUBLIC_IDENTITY_VERIFIED"] = str(APPROVED_ID)
        return subprocess.run(["git", "-c", "credential.helper=", "-c",
            "credential.helper=!gh auth git-credential", "push", "https://github.com/" + REPOSITORY + ".git",
            args[0]], cwd=ROOT, env=env).returncode
    raise RuntimeError("利用できる操作: check / login / gh / fetch / push")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
