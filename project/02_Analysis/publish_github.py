"""Nature clock - publish the website on GitHub.

Double-click 4_Publish_to_GitHub.bat. For every repository in github_targets.csv:
copies ../03_Outputs/website/index.html, then commits, pushes, prints the site address.
A target at the top level (folder ".") also gets README.md plus the project
itself (scripts, word lists, raw data) in a folder called "project".

github_targets.csv (semicolon separated):
  name    short label, also the local folder name under ../05_Publish
  repo    the repository's web address, e.g. https://github.com/datamat/nature-clock.git
          (empty = target switched off)
  folder  where index.html goes inside the repository: "." for the top level,
          or a subfolder such as "clock" (for demo.datascientist.ch/clock)

Needs Git for Windows (https://git-scm.com/download/win, default settings).
The first push opens a GitHub sign-in in the browser. After that, no password.
"""
import csv
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SITE = ROOT / "03_Outputs" / "website" / "index.html"
WORK = ROOT / "05_Publish"
# what goes into the "project" folder of the repository
PROJECT_PARTS = ["01_Data_raw", "02_Analysis"]
SKIP = {"__pycache__"}

_mail = None


def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return r.stdout.strip()


def identity(repo):
    """Commits need a name plus e-mail. Ask once, store it in each repository folder."""
    global _mail
    if git("config", "user.email", cwd=repo, check=False):
        return
    name = git("config", "--global", "user.name", check=False) or "Matthias Häni"
    if _mail is None:
        _mail = git("config", "--global", "user.email", check=False) or input(
            "E-mail of your GitHub account (only used to label the update): ").strip()
    git("config", "user.name", name, cwd=repo)
    git("config", "user.email", _mail or "nature-clock@users.noreply.github.com", cwd=repo)


def site_url(repo_url, folder):
    """https://github.com/owner/repo(.git) -> https://owner.github.io/repo/ (plus subfolder)."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_url)
    if not m:
        return None
    owner, name = m.group(1), m.group(2)
    base = f"https://{owner}.github.io/" if name.lower() == f"{owner.lower()}.github.io" else f"https://{owner}.github.io/{name}/"
    return base if folder == "." else base + folder.strip("/") + "/"


def copy_project(repo):
    """Mirror README plus the project folders into the repository."""
    readme = ROOT / "README.md"
    if readme.exists():
        shutil.copyfile(readme, repo / "README.md")
    dest = repo / "project"
    if dest.exists():
        shutil.rmtree(dest)
    for part in PROJECT_PARTS:
        src = ROOT / part
        if src.exists():
            shutil.copytree(src, dest / part, ignore=shutil.ignore_patterns(*SKIP))
    for bat in ROOT.glob("*.bat"):
        shutil.copyfile(bat, dest / bat.name)


def publish(name, repo_url, folder):
    repo = WORK / name
    if not (repo / ".git").exists():
        print(f"  first time: downloading {repo_url}")
        WORK.mkdir(exist_ok=True)
        git("clone", repo_url, str(repo))
    else:
        git("pull", "--rebase", "--quiet", cwd=repo, check=False)
    identity(repo)
    target = repo / folder / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SITE, target)
    if folder == ".":
        copy_project(repo)
    git("add", "-A", cwd=repo)
    if not git("status", "--porcelain", cwd=repo):
        print("  already up to date")
    else:
        git("commit", "-m", f"Update nature clock {date.today().isoformat()}", cwd=repo)
        git("push", "-u", "origin", "HEAD:main", cwd=repo)
        print("  published")
    url = site_url(repo_url, folder)
    if url:
        print(f"  website: {url}")


def main():
    try:
        git("--version")
    except Exception:
        print("Git is not installed. Install Git for Windows from https://git-scm.com/download/win")
        print("(default settings), then double-click again.")
        return
    if not SITE.exists():
        print("No website yet. Run 3_Build_website.bat first.")
        return
    with open(HERE / "github_targets.csv", encoding="utf-8-sig") as f:
        targets = [t for t in csv.DictReader(f, delimiter=";") if (t.get("repo") or "").strip()]
    if not targets:
        print("No target in github_targets.csv has a repository address yet.")
        return
    for t in targets:
        print(f"{t['name']}:")
        try:
            publish(t["name"].strip(), t["repo"].strip(), (t.get("folder") or ".").strip() or ".")
        except Exception as e:
            print("  failed:", e)
    print("\nGitHub Pages needs about a minute to show the new version.")


if __name__ == "__main__":
    try:
        main()
    finally:
        input("Press Enter to close.")
