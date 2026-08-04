import sys
from pathlib import Path

# 顶层导入 PyQt6 核心模块，帮助 PyInstaller 在打包时识别依赖
import PyQt6  # noqa: F401
from PyQt6.QtCore import Qt  # noqa: F401
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def resource_path(*parts: str) -> Path:
    """返回资源路径：源码运行用项目目录，打包后用 PyInstaller 临时目录。"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)


def load_app_icon() -> QIcon:
    icon = QIcon()
    png = resource_path('assets', 'app-icon.png')
    ico = resource_path('assets', 'app-icon.ico')
    if png.is_file():
        icon.addFile(str(png))
    if ico.is_file():
        icon.addFile(str(ico))
    return icon


def main():
    app = QApplication(sys.argv)
    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    window = MainWindow()
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
