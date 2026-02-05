import os
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QFrame, QGridLayout, QRadioButton, QApplication)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QSurfaceFormat

from ai_control import Controller, AIManager
from canvas_live2d import Live2DSignals, Live2DCanvas
from custom_widgets.bubble_label import BubbleLabel
from custom_widgets.input_text_edit import InputTextEdit
from utils import logger_setup, resources

logger = logger_setup.get_logger("MainWindow")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live2D AI-Vivian")

        # 基于屏幕动态调整大小
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        screen_height = screen_geometry.height()

        logger.info(f"Screen height detected: {screen_height}px")

        target_height = int(screen_height * 0.8)
        target_width = int(target_height * (9/16))

        logger.info(f"Setting window size to: {target_width}x{target_height}px")

        # 居中窗口
        self.resize(target_width, target_height)
        frame_geometry = self.frameGeometry()
        center_point = screen_geometry.center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

        # 移除固定大小标志以允许响应式调整

        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        QSurfaceFormat.setDefaultFormat(fmt)

        # 核心组件
        self.controller = Controller()
        self.live2dSignals = Live2DSignals()
        self.ai_manager = AIManager(self.controller, self.live2dSignals)
        self.current_status_key = "idle"

        # 设置中央窗口
        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(self.central_widget)

        # 主布局 (垂直)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # 显示容器 (Canvas + 气泡叠加)，使用 Grid 堆叠
        self.display_container = QWidget()
        self.display_layout = QGridLayout(self.display_container)
        self.display_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Canvas (背景)
        self.canvas = Live2DCanvas(self.controller, self.live2dSignals)
        self.canvas.setAttribute(Qt.WA_TranslucentBackground)
        self.display_layout.addWidget(self.canvas, 0, 0)

        # 2. 气泡叠加层 (前景)
        self.bubble_container = QWidget()
        self.bubble_container.setAttribute(Qt.WA_TranslucentBackground)
        self.bubble_container.setAttribute(Qt.WA_TransparentForMouseEvents) # 让点击穿透到 Live2D
        self.bubble_layout = QVBoxLayout(self.bubble_container)
        self.bubble_layout.setContentsMargins(20, 40, 20, 20)

        self.bubble_label = BubbleLabel()
        self.bubble_layout.addWidget(self.bubble_label, 0, Qt.AlignTop)
        self.bubble_layout.addStretch()

        self.display_layout.addWidget(self.bubble_container, 0, 0)

        # 添加显示容器到主布局 (扩展)
        self.layout.addWidget(self.display_container, stretch=1)

        # 控制面板 (底部)
        self.controls_frame = QFrame()
        self.controls_frame.setObjectName("ControlsFrame")

        self.controls_layout = QVBoxLayout(self.controls_frame)
        self.controls_layout.setContentsMargins(20, 20, 20, 20)
        self.controls_layout.setSpacing(15)

        # 状态标签
        self.status_label = QLabel("薇薇安正在拉电线. . .")
        self.status_label.setObjectName("StatusLabel")

        self.controls_layout.addWidget(self.status_label)

        # 输入行
        self.input_row = QHBoxLayout()

        # 语音输入列
        self.voice_input_col = QVBoxLayout()
        self.voice_input_col.setSpacing(5)

        self.voice_btn = QPushButton("🎙️")
        self.voice_btn.setObjectName("VoiceBtn")
        self.voice_btn.setFixedSize(60, 60)

        self.voice_directly_radio = QRadioButton("直达")
        self.voice_directly_radio.setObjectName("VoiceRadio")
        self.voice_directly_radio.setChecked(False)

        self.voice_input_col.addWidget(self.voice_btn, 0, Qt.AlignHCenter)
        self.voice_input_col.addWidget(self.voice_directly_radio, 0, Qt.AlignHCenter)

        self.input_text = InputTextEdit()
        self.input_text.setFixedHeight(80) # 设置更高一点以获得更好外观

        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("SendBtn")
        self.send_btn.setFixedSize(80, 60)

        self.input_row.addLayout(self.voice_input_col)
        self.input_row.addWidget(self.input_text)
        self.input_row.addWidget(self.send_btn)
        self.controls_layout.addLayout(self.input_row)
        self.layout.addWidget(self.controls_frame)

        # 设置鼠标追踪以进行模型拖拽
        self.central_widget.setMouseTracking(True)
        self.controls_frame.setMouseTracking(True)
        self.status_label.setMouseTracking(True)
        self.voice_btn.setMouseTracking(True)
        self.voice_directly_radio.setMouseTracking(True)
        self.input_text.setMouseTracking(True)
        self.send_btn.setMouseTracking(True)
        self.bubble_container.setMouseTracking(True)

        # 初始化样式和状态
        self.init_styles()
        # 初始化事件过滤器
        self.init_event_filters()
        # 连接信号
        self.connect_ai_signals()
        self.connect_interal_signals()

    def init_styles(self):
        # 薇薇安主题: 淡紫色 (#C8A2C8), 深黑灰色 (#1e1e24), 白色
        qss_path = os.path.join(resources.RESOURCES_DIRECTORY, "styles/vivian.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                style_sheet = f.read()
                self.setStyleSheet(style_sheet)
        else:
            logger.warning(f"QSS file not found at: {qss_path}")

    def init_event_filters(self):
        self.central_widget.installEventFilter(self)
        self.controls_frame.installEventFilter(self)
        self.status_label.installEventFilter(self)
        self.voice_btn.installEventFilter(self)
        self.voice_directly_radio.installEventFilter(self)
        self.input_text.installEventFilter(self)
        self.send_btn.installEventFilter(self)
        self.bubble_container.installEventFilter(self)

    def connect_interal_signals(self):
        self.voice_btn.pressed.connect(self.ai_manager.start_voice_input)
        self.voice_btn.released.connect(self.ai_manager.stop_voice_input)
        self.voice_directly_radio.toggled.connect(self.ai_manager.set_voice_directly_mode)
        self.input_text.send_signal.connect(self.on_send_clicked)
        self.send_btn.clicked.connect(self.on_send_clicked)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseMove:
            if self.canvas and self.canvas.model:
                 # 将全局坐标映射到 canvas 本地坐标
                 canvas_pos = self.canvas.mapFromGlobal(event.globalPos())
                 self.canvas.model.Drag(canvas_pos.x(), canvas_pos.y())
        return super().eventFilter(obj, event)

    def connect_ai_signals(self):
        self.ai_manager.response_ready.connect(self.on_response_ready)
        self.ai_manager.typing_update.connect(self.on_typing_update)
        self.ai_manager.typing_finished.connect(self.on_typing_finished)
        self.ai_manager.status_update.connect(self.on_status_update)
        self.ai_manager.asr_partial_update.connect(self.on_asr_update)
        self.ai_manager.listening_state_changed.connect(self.on_listening_state)
        self.controller.audio_output_stopped.connect(self.on_audio_finished)

    def on_send_clicked(self):
        text = self.input_text.toPlainText()
        self.input_text.clear()
        self.bubble_label.setVisible(False)
        self.ai_manager.process_input_text(text)

    def on_response_ready(self, text):
        # 触发显示动画
        self.bubble_label.start_show_anim()

    def on_status_update(self, status_key):
        self.current_status_key = status_key
        text = self.ai_manager.status.get(status_key, status_key)
        self.status_label.setText(text)

    def on_typing_finished(self):
        if self.current_status_key == "tts-error" or self.current_status_key == "idle":
            # 如果 TTS 失败，我们不会收到 audio_finished 信号，所以在打字完成后隐藏
            self.bubble_label.schedule_hide()
            self.current_status_key = "idle"  # tts异常，因为打字机一般先于语音结束，不可由controller重置，由ui界面重置状态

    def on_typing_update(self, current_text):
        self.bubble_label.cancel_hide()
        if not self.bubble_label.isVisible():
            self.bubble_label.start_show_anim()
        self.bubble_label.setText(current_text)

    def on_audio_finished(self):
        # 音频完成 (TTS 或播放)，安排隐藏
        self.bubble_label.schedule_hide()

    def on_asr_update(self, text):
        self.input_text.setPlainText(text)

    def on_listening_state(self, is_listening):
        if is_listening:
            self.voice_btn.setStyleSheet("""
                QPushButton#VoiceBtn {
                    background-color: #ff6b6b;
                    border: 2px solid #ff4444;
                    color: white;
                }
            """)
            self.input_text.setPlaceholderText("正在聆听...")
        else:
            # 清除内联样式恢复默认样式表
            self.voice_btn.setStyleSheet("")
            self.input_text.setPlaceholderText("与薇薇安交谈... (Enter发送, Ctrl+Enter换行)")
