"""Restore a release recovery bundle into a new folder, leaving the current app intact."""
import argparse
from pathlib import Path
import zipfile
from release_support import restore_bundle


def main():
    parser = argparse.ArgumentParser(description='Phuc hoi Bao Mat sang thu muc moi')
    parser.add_argument('--bundle')
    parser.add_argument('--destination')
    args = parser.parse_args()
    bundle = args.bundle or input('Duong dan ZIP update-... can phuc hoi: ').strip().strip('"')
    destination = args.destination or input('Thu muc MOI de phuc hoi: ').strip().strip('"')
    if not bundle or not destination:
        raise ValueError('Can duong dan goi va thu muc moi')
    result = restore_bundle(Path(bundle), Path(destination))
    print('Da phuc hoi vao: '+str(result))
    print('Giu ban dang dung. Chay cai-dat.bat roi chay-phuc-hoi.bat trong thu muc moi. Khong can tat Ollama.')
    print('Day la ban ma nguon theo commit, khong co Git history. Khong chay cap-nhat.bat o ban phuc hoi nay.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(str(error)); raise SystemExit(1)
