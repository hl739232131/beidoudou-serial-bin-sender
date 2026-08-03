import os
import subprocess
import sys


def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))

    if sys.platform != 'win32':
        print('警告: PyInstaller 不支持交叉编译，当前平台不是 Windows。')
        print('      本项目的交付物是 Windows .exe，请在 Windows 上运行本脚本。')

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name', 'SerialBinSender',
        '--noconfirm',
        '--clean',
        'main.py',
    ]
    print('Running:', ' '.join(cmd))
    subprocess.check_call(cmd, cwd=project_dir)

    output = 'dist/SerialBinSender.exe' if sys.platform == 'win32' else 'dist/SerialBinSender'
    print(f'Build complete. Output: {os.path.join(project_dir, output)}')
    if sys.platform != 'win32':
        print('提示: 该产物只能在当前平台运行，Windows .exe 需在 Windows 上重新打包。')


if __name__ == '__main__':
    main()
