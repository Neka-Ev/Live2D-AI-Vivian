from PyQt5.QtWidgets import QTextEdit, QToolButton
from PyQt5.QtCore import pyqtSignal, Qt

class InputTextEdit(QTextEdit):
    send_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatInput")
        self.setPlaceholderText("这里是输入文字的地方...\n左边是按住说话的东西...\n「Enter发送,Ctrl+Enter换行」")

        # 清除按钮
        self.clear_btn = QToolButton(self)
        self.clear_btn.setObjectName("ClearBtn")
        self.clear_btn.setText("×")
        self.clear_btn.setCursor(Qt.ArrowCursor)
        self.clear_btn.hide()
        self.clear_btn.clicked.connect(self.clear)
        self.textChanged.connect(self.check_text)

    def check_text(self):
        self.clear_btn.setVisible(bool(self.toPlainText()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        sz = self.clear_btn.sizeHint()
        # 垂直居中，右对齐
        x = self.width() - sz.width() - 5
        y = (self.height() - sz.height()) // 2
        self.clear_btn.move(x, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if event.modifiers() & Qt.ControlModifier:
                self.insertPlainText("\n")
            else:
                self.send_signal.emit()
            return
        super().keyPressEvent(event)
