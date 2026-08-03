# 串口 BIN 文件发送上位机

Windows 桌面 `.exe` 上位机，用于通过串口以固定帧格式发送二进制文件。

## 数据帧格式

| 字段 | 长度 | 说明 |
|------|------|------|
| 帧头 | 2 字节 | `0xAA 0x55` |
| 数据段 | 128 字节 | bin 数据，不足时填充 `0xFF` |
| CRC32 | 4 字节 | 小端序，计算范围为 128 字节数据段（含填充） |

## 环境准备

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 打包成 exe

需在 **Windows** 环境下执行（PyInstaller 在目标平台上打包）：

```bash
python build.py
```

输出：`dist/SerialBinSender.exe`

## 日志

运行时日志保存在 `logs/serial-bin-sender.log`，便于排查问题。
