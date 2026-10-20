"""Update the existing checkout without discarding local work."""
from pathlib import Path
import subprocess
import sys
import os
from release_support import application_lock, atomic_json, recovery_bundle, prepare_release
from release_support import requirements_hash as dependency_hash


ROOT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True,
                          capture_output=True, text=True, encoding='utf-8', errors='replace').stdout


def requirements_hash():
    return dependency_hash(ROOT/'requirements.txt')


def perform_update():
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
        before = git('rev-parse', 'HEAD').strip()
        original_branch = branch
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
            branch = 'main'
        database = Path(os.environ.get('BOT_DB', str(ROOT/'data'/'tasks.sqlite3'))).absolute()
        prepared = None
        if (ROOT/'app.py').is_file():
            backup = recovery_bundle(ROOT, database, before)
            print('Da luu goi phuc hoi: '+str(backup), flush=True)
            print('Dang thu ban moi tren ban sao du lieu; chua thay ma dang dung...', flush=True)
            prepared = prepare_release(ROOT, 'origin/'+branch, database)
        if branch != original_branch:
            if git('for-each-ref', '--format=%(refname)', 'refs/heads/main').strip():
                git('switch', 'main')
            else:
                git('switch', '-c', 'main', '--track', 'origin/main')
        print(git('merge', '--ff-only', 'origin/'+branch))
        if prepared and prepared['isolated_environment']:
            atomic_json(ROOT/'data'/'runtime-environment.json', {
                'python_relative':str(Path(prepared['python']).relative_to(ROOT)),
                'requirements_sha256':prepared['requirements_sha256']})
        if prepared:
            atomic_json(database.parent/'updates'/'last-update.json', {
                'before':before, 'after':git('rev-parse', 'HEAD').strip(),
                'backup':str(backup), 'preflight':'passed', 'dependency_environment':prepared['isolated_environment']})
        elif previous != requirements_hash():
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
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print('Chua cap nhat hoan tat: '+str(error))
        print('Giu du lieu va goi phuc hoi. Chua tu xoa hay reset ma.')
    return 1


def main():
    if not (ROOT/'app.py').is_file():
        return perform_update()
    database = Path(os.environ.get('BOT_DB', str(ROOT/'data'/'tasks.sqlite3'))).absolute()
    try:
        with application_lock(database):
            return perform_update()
    except (OSError, ValueError) as error:
        print(str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
