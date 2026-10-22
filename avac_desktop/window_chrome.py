"""Themed window controls with native Windows move, snap and edge resizing."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class TitleBar(QFrame):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setObjectName("TitleBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        self.logo = QLabel()
        self.logo.setPixmap(window.windowIcon().pixmap(22, 22))
        layout.addWidget(self.logo)
        self.title = QLabel(window.windowTitle())
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.title)
        layout.addStretch()
        for text, hint, callback in (("−", "Minimize", window.showMinimized),
                                     ("□", "Maximize / restore", self.toggle_maximized),
                                     ("×", "Close", window.close)):
            button = QPushButton(text)
            button.setObjectName("CloseWindow" if hint == "Close" else "WindowControl")
            button.setToolTip(hint)
            button.setAccessibleName(hint)
            button.setFixedSize(46, 34)
            button.clicked.connect(callback)
            layout.addWidget(button)
            if hint == "Maximize / restore":
                self.maximize_button = button
        window.windowTitleChanged.connect(self.title.setText)
        window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.window and event.type() == QEvent.WindowStateChange:
            maximized = self.window.isMaximized()
            self.maximize_button.setText("❐" if maximized else "□")
            self.maximize_button.setToolTip("Restore" if maximized else "Maximize")
            self.maximize_button.setAccessibleName("Restore" if maximized else "Maximize")
        return super().eventFilter(obj, event)

    def toggle_maximized(self):
        self.window.showNormal() if self.window.isMaximized() else self.window.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.window.windowHandle():
            self.window.windowHandle().startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_maximized()
            event.accept()


def windows_resize_hit(window, event_type, message):
    """Retain OS resizing on a frameless window, including high-DPI screens."""
    import sys
    if sys.platform != "win32" or window.isMaximized():
        return None
    import ctypes
    from ctypes import wintypes
    msg = wintypes.MSG.from_address(int(message))
    if msg.message != 0x0084:  # WM_NCHITTEST
        return None
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(int(window.winId()), ctypes.byref(rect))
    x = ctypes.c_short(msg.lParam & 0xffff).value
    y = ctypes.c_short((msg.lParam >> 16) & 0xffff).value
    border = round(6 * window.devicePixelRatioF())
    left, right = x < rect.left+border, x >= rect.right-border
    top, bottom = y < rect.top+border, y >= rect.bottom-border
    if top and left: return True, 13
    if top and right: return True, 14
    if bottom and left: return True, 16
    if bottom and right: return True, 17
    if left: return True, 10
    if right: return True, 11
    if top: return True, 12
    if bottom: return True, 15
    return None
