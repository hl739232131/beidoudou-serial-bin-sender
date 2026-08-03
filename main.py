import sys

# 顶层导入 PyQt6 核心模块，帮助 PyInstaller 在打包时识别依赖
import PyQt6  # noqa: F401
from PyQt6.QtCore import Qt  # noqa: F401
from PyQt6.QtGui import QIcon  # noqa: F401
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
