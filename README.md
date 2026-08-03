# 串口 BIN 文件发送上位机

Windows 桌面 `.exe` 上位机，用于通过串口以固定帧格式发送二进制文件。

## 数据帧格式

| 字段 | 长度 | 说明 |
|------|------|------|
| 帧头 | 2 字节 | `0xAA 0x55` |
| 数据段 | 128 字节 | bin 数据，不足时填充 `0xFF` |
| CRC32 | 4 字节 | 小端序，计算范围为 128 字节数据段（含填充） |

> **注意：本帧格式与仓库内 Android App 的帧格式不同，两者互不兼容。**
> Android App 使用「帧头 + 长度字段 + 数据」的格式，不带 CRC 校验；
> 本上位机使用「帧头 + 定长 128 字节数据段（`0xFF` 填充）+ CRC32」，没有长度字段。
> 如需与 Android 侧互通，必须先在协议层达成一致再改动其中一端。

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

运行时日志保存在 `logs/serial-bin-sender.log`，便于排查问题。日志目录位于程序自身所在目录
（源码运行时为项目目录，打包后为 `.exe` 所在目录），与启动时的工作目录无关。若该目录不可写，
程序仍会正常启动，只把日志输出到控制台。
