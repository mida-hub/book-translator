from typing import Callable

from pynput import keyboard


class HotkeyListener:
    """
    グローバルホットキーを監視する。

    - Cmd+Option+T : 翻訳実行
    - Cmd+Option+C : クリック透過 ON/OFF 切り替え
    """

    _TRANSLATE_HOTKEY = "<cmd>+<alt>+t"
    _CLICK_THROUGH_HOTKEY = "<cmd>+<alt>+c"

    def __init__(
        self,
        on_translate: Callable[[], None],
        on_toggle_click_through: Callable[[], None],
    ) -> None:
        self._on_translate = on_translate
        self._on_toggle_click_through = on_toggle_click_through
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        translate_hotkey = keyboard.HotKey(
            keyboard.HotKey.parse(self._TRANSLATE_HOTKEY),
            self._on_translate,
        )
        click_through_hotkey = keyboard.HotKey(
            keyboard.HotKey.parse(self._CLICK_THROUGH_HOTKEY),
            self._on_toggle_click_through,
        )

        def on_press(key: keyboard.Key) -> None:
            assert self._listener is not None
            translate_hotkey.press(self._listener.canonical(key))
            click_through_hotkey.press(self._listener.canonical(key))

        def on_release(key: keyboard.Key) -> None:
            assert self._listener is not None
            translate_hotkey.release(self._listener.canonical(key))
            click_through_hotkey.release(self._listener.canonical(key))

        self._listener = keyboard.Listener(
            on_press=on_press,
            on_release=on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None
