from PyQt5.QtWidgets import QLabel, QGraphicsOpacityEffect
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QPoint

class BubbleLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BubbleLabel")
        # 样式现在通过 QSS 处理
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignTop | Qt.AlignCenter)
        self.setVisible(False)

        # 透明度效果
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        # 显示动画组
        self.anim_group = QParallelAnimationGroup()
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(500)
        self.pos_anim = QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(500)
        self.pos_anim.setEasingCurve(QEasingCurve.OutBack)

        self.anim_group.addAnimation(self.fade_anim)
        self.anim_group.addAnimation(self.pos_anim)

        # 隐藏动画
        self.hide_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.hide_anim.setDuration(1000)
        self.hide_anim.setStartValue(1.0)
        self.hide_anim.setEndValue(0.0)
        self.hide_anim.finished.connect(self._on_hide_finished)

        # 自动隐藏定时器
        self.delay_timer = QTimer(self)
        self.delay_timer.setSingleShot(True)
        self.delay_timer.setInterval(2000)
        self.delay_timer.timeout.connect(self.start_hide_anim)

    def start_show_anim(self):
        self.delay_timer.stop()
        self.hide_anim.stop()

        # 确保可见以计算大小/位置，但利用透明度
        if not self.isVisible():
            self.opacity_effect.setOpacity(0)
            self.setVisible(True)
            self.adjustSize() # 确保大小与文本更新一致

            # 最终位置 (固定标准位置) -> 起始位置 (从上方滑入)
            final_pos = QPoint(20, 40) # 固定位置
            start_pos = QPoint(20, -100) # 从上方开始

            self.move(start_pos) # 移动到起始位置

            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)

            self.pos_anim.setStartValue(start_pos)
            self.pos_anim.setEndValue(final_pos)

            self.anim_group.start()
        else:
            # 如果已经可见，只需确保不透明度为 1
             self.opacity_effect.setOpacity(1.0)

    def start_hide_anim(self):
        self.hide_anim.start()

    def _on_hide_finished(self):
        self.setVisible(False)

    def schedule_hide(self):
        self.delay_timer.start()

    def cancel_hide(self):
        self.delay_timer.stop()
        self.hide_anim.stop()
        self.opacity_effect.setOpacity(1.0)
        self.setVisible(True)
