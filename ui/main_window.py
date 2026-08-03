import os
import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QLineEdit, QFileDialog, QProgressBar, QTextEdit,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from serial_sender import SerialSender
from config import BAUDRATE


class MainWindow(QWidget):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('串口 BIN 发送上位机')
        self.resize(600, 450)
        self.sender = SerialSender()
        self.bin_path = ''

        self.log_signal.connect(self.append_log)
        self.progress_signal.connect(self.update_progress)

        self._init_ui()
        self.refresh_ports()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 串口选择
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel('串口:'))
        self.port_combo = QComboBox()
        port_layout.addWidget(self.port_combo)
        self.refresh_btn = QPushButton('刷新')
        self.refresh_btn.clicked.connect(self.refresh_ports)
        port_layout.addWidget(self.refresh_btn)
        layout.addLayout(port_layout)

        # 波特率
        baud_layout = QHBoxLayout()
        baud_layout.addWidget(QLabel('波特率:'))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200'])
        self.baud_combo.setCurrentText(str(BAUDRATE))
        baud_layout.addWidget(self.baud_combo)
        layout.addLayout(baud_layout)

        # 打开/关闭串口
        self.open_btn = QPushButton('打开串口')
        self.open_btn.clicked.connect(self.toggle_port)
        layout.addWidget(self.open_btn)

        # 文件选择
        file_layout = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText('请选择 .bin 文件')
        file_layout.addWidget(self.file_edit)
        self.select_file_btn = QPushButton('选择文件')
        self.select_file_btn.clicked.connect(self.select_file)
        file_layout.addWidget(self.select_file_btn)
        layout.addLayout(file_layout)

        # 发送控制
        self.send_btn = QPushButton('开始发送')
        self.send_btn.clicked.connect(self.start_send)
        self.stop_btn = QPushButton('停止发送')
        self.stop_btn.clicked.connect(self.stop_send)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.send_btn)
        layout.addWidget(self.stop_btn)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        # 日志
        layout.addWidget(QLabel('日志:'))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

    def refresh_ports(self):
        import serial.tools.list_ports
        self.port_combo.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo.addItems(ports)
        if not ports:
            self.port_combo.addItem('未找到串口')

    def toggle_port(self):
        if self.sender.is_open():
            self.sender.close()
            self.open_btn.setText('打开串口')
            self.log('串口已关闭')
        else:
            port = self.port_combo.currentText()
            if not port or port == '未找到串口':
                QMessageBox.warning(self, '警告', '请先选择有效串口')
                return
            try:
                baud = int(self.baud_combo.currentText())
                self.sender.open(port, baud)
                self.open_btn.setText('关闭串口')
                self.log(f'串口已打开: {port} @ {baud}')
            except Exception as e:
                QMessageBox.critical(self, '错误', f'打开串口失败: {e}')

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 bin 文件', '', 'BIN 文件 (*.bin);;所有文件 (*)')
        if path:
            self.bin_path = path
            self.file_edit.setText(path)
            self.log(f'已选择文件: {path}')

    def start_send(self):
        if not self.sender.is_open():
            QMessageBox.warning(self, '警告', '请先打开串口')
            return
        if not self.bin_path or not os.path.exists(self.bin_path):
            QMessageBox.warning(self, '警告', '请选择有效的 bin 文件')
            return

        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)

        try:
            self.sender.send_bin(
                self.bin_path,
                on_progress=lambda c, t: self.progress_signal.emit(c, t),
                on_log=lambda msg: self.log_signal.emit(msg),
            )
        except Exception as e:
            QMessageBox.critical(self, '错误', f'发送失败: {e}')
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def stop_send(self):
        self.sender.stop()
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def update_progress(self, current, total):
        if total > 0:
            self.progress.setValue(int(current * 100 / total))
        if current >= total:
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def append_log(self, msg):
        self.log_box.append(msg)

    def log(self, msg):
        self.append_log(msg)

    def closeEvent(self, event):
        self.sender.close()
        event.accept()
