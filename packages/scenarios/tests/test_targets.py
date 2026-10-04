import subprocess
from pathlib import Path

from debugassist.scenarios.targets import TargetRepo

PATCH = """From 0000000000000000000000000000000000000000 Mon Sep 17 00:00:00 2001
From: Maya Chen <maya.chen@miniride.dev>
Date: Sun, 4 Oct 2026 10:00:00 +0000
Subject: [PATCH] feat: greet loudly

---
 hello.txt | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)

diff --git a/hello.txt b/hello.txt
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-hello
+HELLO
--
2.50.0
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_release_branch_and_natural_commit(tmp_path: Path) -> None:
    repo_dir = tmp_path / "demo"
    repo_dir.mkdir()
    git(repo_dir, "init", "-q", "-b", "main")
    git(repo_dir, "config", "user.email", "release@miniride.dev")
    git(repo_dir, "config", "user.name", "Release Bot")
    (repo_dir / "hello.txt").write_text("hello\n")
    git(repo_dir, "add", ".")
    git(repo_dir, "commit", "-qm", "init")
    git(repo_dir, "tag", "v1.0.0")
    patch = tmp_path / "0001.patch"
    patch.write_text(PATCH)

    repo = TargetRepo("demo", base_dir=tmp_path)
    assert repo.is_clean()
    assert repo.checkout_release("v1.0.0", "1.1.0") == "release/1.1.0"
    repo.apply_patch(patch)
    assert (repo_dir / "hello.txt").read_text() == "HELLO\n"
    log = git(repo_dir, "log", "-1", "--format=%an <%ae>|%cn <%ce>|%s")
    assert log == "Maya Chen <maya.chen@miniride.dev>|Maya Chen <maya.chen@miniride.dev>|feat: greet loudly"
    assert repo.head() == "release/1.1.0"
    repo.checkout_main()
    assert (repo_dir / "hello.txt").read_text() == "hello\n"
