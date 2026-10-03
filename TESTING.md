# VmTyper 测试说明
- 测试完成：是（2026-10-04）
- 测试日期：2026-10-04
- 测试内容：单元测试覆盖 TypingWorker 参数钳制（cps→0.1、负值→0）、逐字投递与 progress 信号顺序、空文本直接完成；停止/失败路径（钩子）覆盖中途 stop→用户中止、控制器返回失败、控制器抛异常被 run() try/except 兜住不崩线程；注入测试验证 NUL/ANSI 转义/中文/emoji/Tab 逐字原样透传、`\n` 唯一路由到 VK_RETURN；控制器路由覆盖 KeyboardController 的 `\n` vs Unicode 分发、未知 method 返回 False。用 FakeController 替换真实键盘，不真发按键。涉及模块：typing worker、KeyboardController。
- 运行命令：python -m pytest tests/ -v（QT_QPA_PLATFORM=offscreen）
- 测试框架：pytest（PyQt5 offscreen）
- 模型：豆包（Doubao）生成

## 运行方式

```powershell
pip install PyQt5
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/ -v
```

- 预期：**15 passed**（Python 3.14 / Windows）。
- 测试用 FakeController 替换真实键盘控制器，**不会真的向系统发送按键**。

## 覆盖了什么（`tests/test_typing.py`）

| 分组 | 覆盖点 |
| --- | --- |
| 参数钳制 | cps≤0 钳到 0.1、负的开始延迟/抖动钳到 0 |
| 主流程 | 逐字投递与文本一致、`progress` 信号按 1..N 顺序触发、`result(True,"已完成输入")` 恰好一次；空文本直接完成 |
| 停止/失败路径（钩子） | 打字中途 `stop()` → `result(False,"用户中止")`；控制器返回失败 → 错误结果；**控制器抛异常被 run() 的 try/except 兜住**，线程不崩溃，走 `result(False,"发生错误...")` |
| 注入/输入透传 | NUL 字节、ANSI 转义 `\x1b[2J`、中文、emoji、Tab/回车 等任意字符**逐字原样投递**，不被截断/解释/过滤；`\n` 唯一地路由到 VK_RETURN 而非 Unicode 输入 |
| 控制器路由 | `KeyboardController.type("a\nb")` 中 `\n` → `_press_key(VK_RETURN)`，其余字符 → `_send_unicode`；未知 method 返回 False |

## 注入与钩子说明

- **输入即不可信数据**：模拟输入的内容可能含 NUL、ANSI 转义序列等。测试断言
  worker 把它们当普通文本逐字投递，不会把 `\x1b[...]` 当成命令执行——本程序
  无 shell/subprocess/SQL/模板拼接，不存在命令注入面；风险只在"按键投递语义"，
  故以透传 + `\n` 路由正确性作为断言。
- **信号钩子**：`progress`/`result` 是 TypingWorker 的事件回调；测试验证回调
  触发次数、顺序，以及控制器异常被隔离、不影响回调链路。
