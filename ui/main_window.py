import logging
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QLineEdit, QFileDialog, QProgressBar, QTextEdit,
    QMessageBox, QGroupBox, QGridLayout,
)
from PyQt6.QtCore import pyqtSignal
import serial.tools.list_ports
from serial_sender import SerialSender
from config import BAUDRATE
from logger import get_logger, get_log_file_path


class MainWindow(QWidget):
    log_signal = pyqtSignal(str)
    # current_x 用 -1 表示 A5 重置（尚无发送包）
    progress_signal = pyqtSignal(int, int, int)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('串口 BIN 发送上位机（从机模式）')
        self.resize(650, 500)
        self._logger = get_logger(__name__)
        self._sender = SerialSender()
        self.bin_path = ''

        self.log_signal.connect(self.append_log)
        self.progress_signal.connect(self._update_progress_ui)
        self._sender.set_callbacks(
            on_command=lambda msg: self.log_signal.emit(f'[主机命令] {msg}'),
            on_response=lambda msg: self.log_signal.emit(f'[从机回复] {msg}'),
            on_error=lambda msg: self.log_signal.emit(f'[错误] {msg}'),
            on_progress=self._on_progress,
        )

        self._init_ui()
        self.refresh_ports()
        self._log_startup_info()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 串口设置
        port_group = QGroupBox('串口设置')
        port_layout = QGridLayout(port_group)

        port_layout.addWidget(QLabel('串口:'), 0, 0)
        self.port_combo = QComboBox()
        port_layout.addWidget(self.port_combo, 0, 1)
        self.refresh_btn = QPushButton('刷新')
        self.refresh_btn.clicked.connect(self.refresh_ports)
        port_layout.addWidget(self.refresh_btn, 0, 2)

        port_layout.addWidget(QLabel('波特率:'), 1, 0)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200'])
        self.baud_combo.setCurrentText(str(BAUDRATE))
        port_layout.addWidget(self.baud_combo, 1, 1)

        self.open_btn = QPushButton('打开串口')
        self.open_btn.clicked.connect(self.toggle_port)
        port_layout.addWidget(self.open_btn, 1, 2)

        layout.addWidget(port_group)

        # 文件与状态
        file_group = QGroupBox('bin 文件与状态')
        file_layout = QGridLayout(file_group)

        self.select_file_btn = QPushButton('加载 bin 文件')
        self.select_file_btn.clicked.connect(self.select_file)
        file_layout.addWidget(self.select_file_btn, 0, 0)

        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText('请选择 .bin 文件')
        file_layout.addWidget(self.file_edit, 0, 1, 1, 2)

        file_layout.addWidget(QLabel('文件大小:'), 1, 0)
        self.file_size_label = QLabel('未加载')
        file_layout.addWidget(self.file_size_label, 1, 1)

        file_layout.addWidget(QLabel('包大小 N:'), 1, 2)
        self.packet_size_label = QLabel('未设置')
        file_layout.addWidget(self.packet_size_label, 1, 3)

        file_layout.addWidget(QLabel('总包数:'), 2, 0)
        self.packet_count_label = QLabel('未设置')
        file_layout.addWidget(self.packet_count_label, 2, 1)

        file_layout.addWidget(QLabel('当前发送:'), 2, 2)
        self.current_packet_label = QLabel('等待主机请求')
        file_layout.addWidget(self.current_packet_label, 2, 3)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat('%v / %m')
        file_layout.addWidget(self.progress, 3, 0, 1, 4)

        layout.addWidget(file_group)

        # 日志
        layout.addWidget(QLabel('日志:'))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        layout.addWidget(self.log_box)

    def _log_startup_info(self):
        log_path = get_log_file_path()
        if log_path:
            self.log(f'日志文件: {log_path}')
        else:
            self.log('未找到可写的日志目录，日志仅保留在本窗口')

    def refresh_ports(self):
        self.port_combo.clear()
        ports = [p.device for p in serial.tools.list_ports.comports()]
        for device in ports:
            self.port_combo.addItem(device, device)
        if not ports:
            self.port_combo.addItem('未找到串口', None)

    def selected_port(self):
        return self.port_combo.currentData()

    def toggle_port(self):
        if self._sender.is_open():
            self._sender.close()
            self.open_btn.setText('打开串口')
            self.log('串口已关闭')
        else:
            port = self.selected_port()
            if not port:
                QMessageBox.warning(self, '警告', '请先选择有效串口')
                return
            try:
                baud = int(self.baud_combo.currentText())
                self._sender.open(port, baud)
                self.open_btn.setText('关闭串口')
                self.log(f'串口已打开: {port} @ {baud}')
                self.log('已进入从机监听模式，等待主机发送 A5 / A6 / A7 命令')
            except Exception as e:
                self.log(f'打开串口失败: {e}', logging.ERROR, exc_info=True)
                QMessageBox.critical(self, '错误', f'打开串口失败: {e}')

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 bin 文件', '', 'BIN 文件 (*.bin);;所有文件 (*)')
        if not path:
            return
        try:
            self._sender.load_bin(path)
            self.bin_path = path
            self.file_edit.setText(path)
            size = len(self._sender._bin_data)
            self.file_size_label.setText(f'{size} bytes')
            self.packet_size_label.setText('等待 A5 设置 N')
            self.packet_count_label.setText('等待 A5 设置 N')
            self.current_packet_label.setText('等待主机请求')
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.log(f'已加载 bin 文件: {path} ({size} bytes)')
        except Exception as e:
            self.log(f'加载 bin 文件失败: {e}', logging.ERROR, exc_info=True)
            QMessageBox.critical(self, '错误', f'加载 bin 文件失败: {e}')

    def _on_progress(self, current_x, total_packets: int, packet_size: int) -> None:
        # 串口监听线程回调，转到主线程更新 UI
        x = -1 if current_x is None else int(current_x)
        self.progress_signal.emit(x, int(total_packets), int(packet_size))

    def _update_progress_ui(self, current_x: int, total_packets: int, packet_size: int) -> None:
        self.packet_size_label.setText(str(packet_size))
        self.packet_count_label.setText(str(total_packets))

        maximum = max(total_packets, 1)
        self.progress.setMaximum(maximum)

        if current_x < 0:
            self.current_packet_label.setText('等待主机请求')
            self.progress.setValue(0)
            return

        self.current_packet_label.setText(f'第 {current_x} / {total_packets - 1} 包')
        # 已发送到第 current_x 包（含），进度为 current_x + 1
        self.progress.setValue(min(current_x + 1, maximum))

    def append_log(self, msg):
        self.log_box.append(msg)

    def log(self, msg, level=logging.INFO, exc_info=False):
        self.append_log(msg)
        self._logger.log(level, msg, exc_info=exc_info)

    def closeEvent(self, event):
        self._sender.close()
        event.accept()
