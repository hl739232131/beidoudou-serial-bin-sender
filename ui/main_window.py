import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QLineEdit, QFileDialog, QProgressBar, QTextEdit,
    QMessageBox
)
from PyQt6.QtCore import pyqtSignal
from serial_sender import SerialSender
from config import BAUDRATE


class MainWindow(QWidget):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('串口 BIN 发送上位机')
        self.resize(600, 450)
        self._sender = SerialSender()
        self.bin_path = ''
        self._user_stopped = False

        self.log_signal.connect(self.append_log)
        self.progress_signal.connect(self.update_progress)
        self.finished_signal.connect(self.on_send_finished)

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
        for device in ports:
            # 真实串口把设备名存进 userData，占位项的 userData 为 None
            self.port_combo.addItem(device, device)
        if not ports:
            self.port_combo.addItem('未找到串口', None)

    def selected_port(self):
        return self.port_combo.currentData()

    def toggle_port(self):
        if self._sender.is_open():
            self._sender.close()
            self.open_btn.setText('打开串口')
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
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
            except Exception as e:
                QMessageBox.critical(self, '错误', f'打开串口失败: {e}')

    def select_file(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择 bin 文件', '', 'BIN 文件 (*.bin);;所有文件 (*)')
        if path:
            self.bin_path = path
            self.file_edit.setText(path)
            self.log(f'已选择文件: {path}')

    def start_send(self):
        if not self._sender.is_open():
            QMessageBox.warning(self, '警告', '请先打开串口')
            return
        if not self.bin_path or not os.path.exists(self.bin_path):
            QMessageBox.warning(self, '警告', '请选择有效的 bin 文件')
            return

        self._user_stopped = False
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)

        try:
            self._sender.send_bin(
                self.bin_path,
                on_progress=lambda c, t: self.progress_signal.emit(c, t),
                on_log=lambda msg: self.log_signal.emit(msg),
                on_finished=lambda ok, msg: self.finished_signal.emit(ok, msg),
            )
        except Exception as e:
            QMessageBox.critical(self, '错误', f'发送失败: {e}')
            self.send_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def stop_send(self):
        self._user_stopped = True
        self.stop_btn.setEnabled(False)
        # stop() 不阻塞；按钮状态由 on_send_finished 恢复
        self._sender.stop()

    def update_progress(self, current, total):
        if total > 0:
            self.progress.setValue(int(current * 100 / total))

    def on_send_finished(self, success, message):
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.append_log(message)
        if not success and not self._user_stopped:
            QMessageBox.critical(self, '错误', message)
        self._user_stopped = False

    def append_log(self, msg):
        self.log_box.append(msg)

    def log(self, msg):
        self.append_log(msg)

    def closeEvent(self, event):
        self._sender.close()
        event.accept()
