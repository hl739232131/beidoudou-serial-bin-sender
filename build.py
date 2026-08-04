import importlib.util
import os
import subprocess
import sys


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec('PyInstaller') is not None:
        return
    print('错误: 当前 Python 环境未安装 PyInstaller。')
    print(f'      解释器: {sys.executable}')
    print('请先安装依赖后再打包，任选其一：')
    print(f'  {sys.executable} -m pip install -r requirements.txt')
    print(f'  {sys.executable} -m pip install "pyinstaller>=6.0.0"')
    sys.exit(1)


def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    icon_ico = os.path.join(project_dir, 'assets', 'app-icon.ico')
    icon_png = os.path.join(project_dir, 'assets', 'app-icon.png')
    data_sep = ';' if sys.platform == 'win32' else ':'

    ensure_pyinstaller()

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
        '--icon', icon_ico,
        # 运行时窗口图标（源码与打包后均可加载）
        '--add-data', f'{icon_png}{data_sep}assets',
        '--add-data', f'{icon_ico}{data_sep}assets',
        # PyQt6 子模块：显式收集，避免 Windows 打包后运行时找不到模块
        '--hidden-import', 'PyQt6',
        '--hidden-import', 'PyQt6.sip',
        '--hidden-import', 'PyQt6.QtCore',
        '--hidden-import', 'PyQt6.QtGui',
        '--hidden-import', 'PyQt6.QtWidgets',
        # pyserial 在 ui/main_window.py 中动态导入
        '--hidden-import', 'serial.tools.list_ports',
        # 收集 PyQt6 与 pyserial 的全部资源/子模块，确保 Qt 插件和平台文件完整
        '--collect-all', 'PyQt6',
        '--collect-all', 'pyserial',
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
