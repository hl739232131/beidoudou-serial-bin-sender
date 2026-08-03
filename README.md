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

## 串口参数

| 参数 | 取值 |
|------|------|
| 波特率 | 默认 `115200`（下拉框可选 9600 / 19200 / 38400 / 57600 / 115200） |
| 数据位 / 校验 / 停止位 | `8 / N / 1`（固定，不可配置） |
| 帧间隔 | 50 ms（每发完一个满帧等待一次） |
| 写超时 | 2 s |
| 读超时 | 1 s |

## 环境准备

需要 **Python 3.10 及以上**（代码使用了 `X | None` 等新式类型标注与 `tuple[...]` 泛型），
开发与测试环境为 Python 3.12。

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 运行测试

```bash
pip install pytest
python -m pytest tests/ -v
```

测试全部使用假串口（不依赖真实硬件），覆盖帧格式与 CRC、串口线路参数、
发送进度与完成回调、停止/关闭串口中断、帧间隔、日志目录退化等。

## 打包成 exe

需在 **Windows** 环境下执行（PyInstaller 在目标平台上打包）：

```bash
python build.py
```

输出：`dist/SerialBinSender.exe`

## 日志

运行时日志保存在 `logs/serial-bin-sender.log`，便于排查问题。日志目录位于程序自身所在目录
（源码运行时为项目目录，打包后为 `.exe` 所在目录），与启动时的工作目录无关。

若该目录不可写（例如装在 `Program Files` 下），会依次退化到：

1. `%LOCALAPPDATA%\SerialBinSender\serial-bin-sender.log`
2. 系统临时目录下的 `SerialBinSender\serial-bin-sender.log`

以上都不可用时程序仍会正常启动，只是日志不落盘。实际生效的日志路径会在启动时
显示在窗口的日志框第一行。串口打开失败、发送异常等错误同样会写入日志文件。
