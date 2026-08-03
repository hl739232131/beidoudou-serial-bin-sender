import os
import subprocess
import sys


def main():
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--name', 'SerialBinSender',
        '--noconfirm',
        '--clean',
        'main.py',
    ]
    print('Running:', ' '.join(cmd))
    subprocess.check_call(cmd)
    print('Build complete. Output: dist/SerialBinSender.exe')


if __name__ == '__main__':
    main()
