"""Update the existing checkout without discarding local work."""
import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True,
                          capture_output=True, text=True, encoding='utf-8', errors='replace').stdout


def requirements_hash():
    return hashlib.sha256((ROOT / 'requirements.txt').read_bytes()).digest()


def main():
    try:
        changes = git('status', '--porcelain')
        if changes:
            print('Chua cap nhat: thu muc co thay doi hoac tep chua duoc Git quan ly.')
            print(changes)
            print('Hay giu nguyen cac tep va gui ket qua nay de kiem tra. Khong tu reset/xoa.')
            return 1
        branch = git('branch', '--show-current').strip()
        if branch not in ('feat/bot-team-dashboard','main'):
            print('Dang o nhanh ' + (branch or 'detached HEAD') + '. Chi cap nhat main hoac feat/bot-team-dashboard.')
            return 1
        previous = requirements_hash()
        print('Dang tai cap nhat...', flush=True)
        git('fetch', '--prune', 'origin')
        remotes = git('for-each-ref', '--format=%(refname)', 'refs/remotes/origin').splitlines()
        if 'refs/remotes/origin/'+branch not in remotes:
            if branch != 'feat/bot-team-dashboard' or 'refs/remotes/origin/main' not in remotes:
                print('Khong tim thay nhanh tuong ung tren origin. Khong thay doi tep.')
                return 1
            try:
                git('merge-base', '--is-ancestor', 'HEAD', 'origin/main')
            except subprocess.CalledProcessError:
                print('Nhanh cu da bi xoa, nhung chua xac minh duoc commit hien tai nam trong main.')
                print('Giu nguyen ma va lien he de kiem tra merge/squash; khong tu reset.')
                return 1
            if git('for-each-ref', '--format=%(refname)', 'refs/heads/main').strip():
                git('switch', 'main')
            else:
                git('switch', '-c', 'main', '--track', 'origin/main')
            branch = 'main'
        print(git('merge', '--ff-only', 'origin/'+branch))
        if previous != requirements_hash():
            print('Thu vien da thay doi. Dang cap nhat thu vien...', flush=True)
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'],
                           cwd=ROOT, check=True)
            subprocess.run([sys.executable, '-m', 'pip', 'check'], cwd=ROOT, check=True)
        print('Cap nhat thanh cong. Du lieu trong data khong bi xoa.')
        return 0
    except FileNotFoundError:
        print('Khong tim thay Git hoac tep can thiet. Kiem tra cai dat va thu muc du an.')
    except subprocess.CalledProcessError as error:
        print('Cap nhat chua hoan tat. Khong tu reset hoac xoa du lieu.')
        if error.stderr:
            print(error.stderr)
        print('Neu cai thu vien bi loi, chay lai cai-dat.bat truoc khi mo app.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
