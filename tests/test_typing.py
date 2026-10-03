# -*- coding: utf-8 -*-
"""TypingWorker / KeyboardController 单元测试。

用 FakeController 替换真实键盘控制器，直接同步调用 ``worker.run()``，
验证逐字投递、信号回调（钩子）、停止/失败路径与输入字符透传（注入）。
"""
from __future__ import annotations

import pytest

import main as app_main


class FakeController:
    """记录型假键盘控制器。"""

    def __init__(self, fail_on: str | None = None, raise_on: str | None = None):
        self.typed: list[str] = []
        self.fail_on = fail_on
        self.raise_on = raise_on

    def type(self, ch: str) -> bool:
        self.typed.append(ch)
        if self.raise_on is not None and ch == self.raise_on:
            raise RuntimeError("boom from controller")
        if self.fail_on is not None and ch == self.fail_on:
            return False
        return True


def make_worker(text, controller=None, **kw):
    w = app_main.TypingWorker(
        text=text, cps=5000.0, start_delay_ms=0, jitter_ms=0, input_method="test"
    )
    for k, v in kw.items():
        setattr(w, k, v)
    w.controller = controller or FakeController()
    return w


class TestParameterClamping:
    def test_clamps_negative_and_zero(self):
        w = app_main.TypingWorker(text="", cps=0, start_delay_ms=-1, jitter_ms=-9, input_method="x")
        assert w.cps == 0.1
        assert w.start_delay_ms == 0
        assert w.jitter_ms == 0


class TestWorkerFlow:
    def test_types_every_char_and_signals(self, qapp):
        w = make_worker("ab\nc")
        progress: list[int] = []
        result: list[tuple] = []
        w.progress.connect(lambda c: progress.append(c))
        w.result.connect(lambda ok, msg: result.append((ok, msg)))
        w.run()
        assert w.controller.typed == ["a", "b", "\n", "c"]
        assert progress == [1, 2, 3, 4]
        assert result == [(True, "已完成输入")]

    def test_empty_text_completes(self, qapp):
        w = make_worker("")
        result: list[tuple] = []
        w.result.connect(lambda ok, msg: result.append((ok, msg)))
        w.run()
        assert result == [(True, "已完成输入")]

    def test_stop_mid_run_emits_aborted(self, qapp):
        ctrl = FakeController()
        w = make_worker("abc", controller=ctrl)

        # 打字 2 个字符后要求停止
        orig = ctrl.type

        def spy(ch):
            r = orig(ch)
            if len(ctrl.typed) >= 2:
                w._stopping = True
            return r

        ctrl.type = spy
        result: list[tuple] = []
        w.result.connect(lambda ok, msg: result.append((ok, msg)))
        w.run()
        assert ctrl.typed == ["a", "b"]
        assert result == [(False, "用户中止")]

    def test_controller_failure_emits_error(self, qapp):
        w = make_worker("ab", controller=FakeController(fail_on="b"))
        result: list[tuple] = []
        w.result.connect(lambda ok, msg: result.append((ok, msg)))
        w.run()
        assert result and result[0][0] is False
        assert "失败" in result[0][1]

    def test_controller_exception_is_caught(self, qapp):
        # 失败隔离：控制器抛异常不应让线程崩溃，而是走 result(False, "发生错误...")
        w = make_worker("ab", controller=FakeController(raise_on="b"))
        result: list[tuple] = []
        w.result.connect(lambda ok, msg: result.append((ok, msg)))
        w.run()
        assert result and result[0][0] is False
        assert "发生错误" in result[0][1]


class TestInputPassthrough:
    """注入测试：任意字符（NUL、ANSI 转义、中文、emoji）必须逐字原样投递，
    不能被截断/解释/过滤。"""

    @pytest.mark.parametrize(
        "text",
        [
            "\x00",
            "\x1b[2J",
            "中文输入",
            "emoji🚀😀",
            "a\tb\rc",
            "混合\x00NUL与\x1b转义 end",
        ],
    )
    def test_arbitrary_chars_passed_through(self, qapp, text):
        w = make_worker(text)
        w.run()
        assert w.controller.typed == list(text)


class TestKeyboardControllerRouting:
    def test_newline_routes_to_return_not_unicode(self):
        kc = app_main.KeyboardController()
        pressed, sent = [], []
        kc.method = "winapi"
        kc._press_key = lambda vk: pressed.append(vk)
        kc._send_unicode = lambda c: sent.append(c)
        kc.type("a\nb")
        assert sent == ["a", "b"]
        assert pressed == [kc.VK_RETURN]

    def test_unknown_method_returns_false(self):
        kc = app_main.KeyboardController()
        kc.method = "none"
        kc.controller = None
        assert kc.type("x") is False

    def test_darwin_fallback_error_swallowed(self):
        # 没有 pynput 时，非 Windows 平台 winapi 初始化失败，method 保持 none
        kc = app_main.KeyboardController.__new__(app_main.KeyboardController)
        kc.method = "none"
        kc.controller = None
        assert kc.type("x") is False
