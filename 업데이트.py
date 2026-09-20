#!/usr/bin/env python3
"""실습자료 복구 도우미.

평소에는 `git pull` 로 새 자료를 받으세요.
`git pull` 이 아래 같은 메시지로 막혔을 때만 이 파일을 실행하면 됩니다.

    error: Your local changes would be overwritten by merge
    CONFLICT (content): Merge conflict in ...

배포된 원본 파일을 되돌려 충돌을 없애고 최신 자료를 받아옵니다.
'내작업/' 폴더와 여러분이 만든 파일은 건드리지 않습니다.
되돌리기 전에 바뀐 내용은 '.백업/날짜_시각/' 에 그대로 보관합니다.

    uv run 업데이트.py
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKUP_ROOT = Path(".백업")


def git(*args: str) -> subprocess.CompletedProcess:
    """git 명령을 실행하고 결과를 돌려준다."""
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def fail(message: str, hint: str = "") -> None:
    print(f"\n❌ {message}")
    if hint:
        print(f"   {hint}")
    print("\n해결되지 않으면 이 화면을 그대로 강사님께 보여주세요.")
    sys.exit(1)


def main() -> None:
    print("실습자료 복구 도우미")
    print("─" * 46)

    # 저장소 폴더 안에서 실행됐는지 확인 (더블클릭 실행 대비)
    here = Path(__file__).resolve().parent
    os.chdir(here)

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        fail(
            "여기는 git 저장소가 아닙니다.",
            "git clone 으로 내려받은 'enkoa-practice' 폴더 안에서 실행하세요.",
        )

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() or "main"

    print("최신 정보를 확인하는 중...")
    fetched = git("fetch", "origin")
    if fetched.returncode != 0:
        fail("서버에서 자료를 가져오지 못했습니다.", "인터넷 연결을 확인해 주세요.")

    remote = f"origin/{branch}"
    if git("rev-parse", "--verify", remote).returncode != 0:
        fail(f"서버에 '{branch}' 브랜치가 없습니다.")

    # 원격과 다른 배포 파일을 모두 찾는다 (수정·staged·직접 커밋한 것까지 포함)
    # -z 로 받아야 한글 파일명이 "\353\263\200" 처럼 escape 되지 않는다
    diff = git("diff", "--name-only", "-z", remote)
    changed = [name for name in diff.stdout.split("\0") if name.strip()]

    if changed:
        stamp = datetime.now().strftime("%m%d_%H%M")
        dest = BACKUP_ROOT / stamp
        print(f"\n배포 원본이 바뀐 파일 {len(changed)}개를 '{dest}' 에 보관합니다:")
        saved, missing = 0, []
        for rel in changed:
            src = Path(rel)
            if not src.is_file():
                # 서버에서 지워진 파일 등 — 되돌려도 잃을 내용이 없다
                missing.append(rel)
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            saved += 1
            print(f"   - {rel}")

        if saved:
            print("   (여기서 필요한 내용을 꺼내 '내작업/' 으로 옮기세요)")
        if missing:
            print(f"   ※ 보관할 실물이 없는 항목 {len(missing)}개는 건너뛰었습니다.")
        if saved == 0 and not missing:
            fail(
                "바뀐 파일을 보관하지 못했습니다.",
                "되돌리면 작업 내용이 사라질 수 있어 중단합니다.",
            )
    else:
        print("되돌릴 파일이 없습니다.")

    print("\n배포 원본을 되돌리고 새 자료를 받는 중...")
    reset = git("reset", "--hard", remote)
    if reset.returncode != 0:
        fail("자료를 되돌리지 못했습니다.", reset.stderr.strip())

    print("─" * 46)
    print("✅ 업데이트 완료!")
    print("   '내작업/' 폴더와 직접 만든 파일은 그대로 있습니다.")
    if changed:
        print("   앞으로는 자료를 '내작업/' 에 복사한 뒤 실습해 주세요.")


if __name__ == "__main__":
    main()
