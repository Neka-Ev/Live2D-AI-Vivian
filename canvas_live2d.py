import math
import os

import live2d.v3 as live2d
import utils.resources as resources
from typing import Optional, TYPE_CHECKING
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QTimer
from live2d.v3.params import StandardParams
from utils.logger_setup import get_logger
from canvas_base import OpenGLCanvas
from utils.model_helper import ModelAttribute, ModelHitManager, ModelConfigParser


logger = get_logger("Live2DCanvas")

if TYPE_CHECKING:  # 类型检查提示
    from ai_control import Controller

class Live2DSignals(QObject):
    tap_signal = pyqtSignal(str, str)


class Live2DCanvas(OpenGLCanvas):
    def __init__(
        self,
        controller: "Controller",
        live2dSignals: Live2DSignals,
        modelAttr: ModelAttribute = ModelAttribute(1.5, (0.0, 0.0), 0.0),
        modelHitManager: ModelHitManager = ModelHitManager(),
        modelJsonParser: ModelConfigParser = ModelConfigParser(),
    ):
        super().__init__()
        self.model: Optional[live2d.LAppModel] = None
        self.controller = controller
        self.live2dSignals = live2dSignals
        self.modelAttr = modelAttr
        self.modelHitManager = modelHitManager
        self.modelJsonParser = modelJsonParser
        self.initWindowParams()
        # ---- 动画相关参数 ----
        self.radius_per_frame = math.pi * 0.5 / 120
        self.total_radius = 0
        self.expressionCounter = {"Head": 0, "Face": 0, "Hand": 0, "Breast": 0, "Body": 0, "Leg": 0, "Accessories": 0}
        self.expressionMaxCount = {"Head": 0, "Face": 0, "Hand": 0, "Breast": 0, "Body": 0, "Leg": 0, "Accessories": 0}
        self.expCounter_timer = QTimer(self)
        self.expCounter_timer.setInterval(8000)

        # ---- 功能初始化函数 ----
        self.initSignals()

    def initSignals(self):
        self.controller.expression_state_changed.connect(self.exp_signal)
        self.controller.call_state_changed.connect(self.exp_signal)
        self.controller.attribute_state_changed.connect(self.attr_signal)
        self.controller.lip_sync_state_changed.connect(self.on_lip_sync)
        self.controller.audio_output_stopped.connect(self.on_audio_stopped)
        self.expCounter_timer.timeout.connect(self.on_expCounter_timeout)


    def initWindowParams(self):
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def initFuncParams(self):
        if not self.model:
            return
        logger.info("✨✨✨Live2D AI-Vivian Covered By Neka✨✨✨")
        logger.info("💭💭💭2026/02/05 Updated Version 2.0.3💭💭💭")
        logger.info("🤖LLM Model: DeepSeek Chat v3.2 API &cpy; 2024 DeepSeek Inc.")
        logger.info("🎤ASR Model: Iflytek API &cpy; 2025 Iflytek Co., Ltd.")
        logger.info("🔈TTS Model: GPT-SoVITS v4 &cpy; 2024 GPT-SOVITS Team")
        logger.info("👤Live2D Model: Vivian by Live2D Cubism &cpy; 2023 Live2D Inc.")
        logger.info("✨✨✨Special Thanks to Live2d-py SDK contributors for their amazing technology!✨✨✨")
        logger.warning("⚠️⚠️⚠️(TTS is not completely ready now)⚠️⚠️⚠️")
        # ---- 初始化表情最大计数 ----
        motionGroups : dict[str, int] = self.model.GetMotionGroups()
        for group in motionGroups:
            max_count = motionGroups[group]
            exp_name = group.removeprefix("Tap")
            if exp_name in self.expressionMaxCount:
                self.expressionMaxCount[exp_name] = max_count

    def exp_signal(self, exp_name: str):
        """
        改变模型的表情
        通过 exp_name 参数指定要改变的表情名称:
        :param exp_name:
        """
        if not self.model:
            return
        if exp_name =="normal":
            self.model.SetExpression("normal")
            self.model.StartMotion("Idle", 0,
                                   live2d.MotionPriority.FORCE,
                                   self.on_start_motion_callback)
            return
        self.model.SetExpression(exp_name)
        dictory = {"panic":0, "scowl":1, "shy":2, "umbrella_close":3, "cry":4,"a":5,"b":6,"c":7,"d":8,}
        self.model.StartMotion("Expressions", dictory.get(exp_name, 0),
                               live2d.MotionPriority.FORCE,
                              self.on_start_motion_callback,
                               self.on_finish_motion_callback)

    def attr_signal(self, attribute_change: str):
        """
        改变模型的属性，如缩放和位置偏移
        通过 attribute_change 参数指定要改变的属性:
        - "addScale": 增加缩放比例
        - "subScale": 减少缩放比例
        - "addX": 增加 X 位置偏移
        - "subX": 减少 X 位置偏移
        - "addY": 增加 Y 位置偏移
        - "subY": 减少 Y 位置偏移
        :param attribute_change:
        """
        if not self.model:
            return
        logger.info(f"Changing model attribute: {attribute_change}")
        try:
            scale_change = 0.0
            position_change = (0.0, 0.0)
            if attribute_change == "addScale":
                scale_change = 0.1
            elif attribute_change == "subScale":
                scale_change = -0.1
            elif attribute_change == "addX":
                position_change = (0.1, 0.0)
            elif attribute_change == "subX":
                position_change = (-0.1, 0.0)
            elif attribute_change == "addY":
                position_change = (0.0, 0.1)
            elif attribute_change == "subY":
                position_change = (0.0, -0.1)
            new_scale = round(self.modelAttr.getNowScale() + scale_change, 2)
            new_position = (
                round(self.modelAttr.getNowPositionOffset()[0] + position_change[0], 2),
                round(self.modelAttr.getNowPositionOffset()[1] + position_change[1], 2)
            )
            self.modelAttr.setNewScale(new_scale)
            self.modelAttr.setNewPositionOffset(new_position)
            logger.info(f"Changing scale to {new_scale},"f" PositionOffset is {new_position}")
        except Exception as e:
            logger.error(f"Error changing model attributes: {e}")

    def on_lip_sync(self, lip_value: float, lip_sync: float = 1.5):
        """
        根据 lip_value 参数调整模型的嘴部开合程度
        :param lip_value: 嘴部开合程度的数值
        :param lip_sync: 嘴部开合的同步系数
        """
        if not self.model:
            return
        self.modelAttr.setLipParamY(lip_value * lip_sync)

    def on_audio_stopped(self):
        """
        当音频停止时，重置表情
        """
        if not self.model:
            return
        logger.info("Audio stopped, reset Expression")
        self.model.SetExpression("normal")
        self.expCounter_timer.start()
        # logger.info("Expression counter timer started.")

    def on_start_motion_callback(self, group: str, no: int):
        logger.info("start motion: [%s_%d]" % (group, no))

    def on_finish_motion_callback(self):
        logger.info("motion finished")
        self.model.StartMotion("Idle", 0,live2d.MotionPriority.FORCE, self.on_start_motion_callback)
        #self.model.ResetParameters()

    def on_expCounter_timeout(self):
        for area in self.expressionCounter:
            self.expressionCounter.update({area:0}) # 重置计数器
        logger.info("Expression counters reset due to timeout.")
        self.expCounter_timer.stop()

    def tap_expression_handler(self, area_name: str):
        if not self.model or area_name not in self.expressionMaxCount:
            return
        max_count = self.expressionMaxCount[area_name]
        current_count = self.expressionCounter.get(area_name, 0)
        next_count = (current_count + 1) % max_count
        self.expressionCounter.update({area_name:next_count})
        return current_count

    def on_init(self):
        live2d.glInit()
        self.model = live2d.LAppModel()
        model_path = os.path.join(resources.RESOURCES_DIRECTORY, "vivian/vivian.model3.json")
        self.model.LoadModelJson(model_path)
        self.modelJsonParser.load_config(model_path)
        self.initFuncParams()
        self.startTimer(int(1000 / 120))

    def closeEvent(self, event):
        super().closeEvent(event)

    def mouseMoveEvent(self, event):
        if not self.model:
            return
        x = event.pos().x()
        y = event.pos().y()
        self.model.Drag(x, y)

    def mousePressEvent(self, event):
        if not self.model:
            return
        nowHitPartIds = self.model.HitPart(event.pos().x(), event.pos().y())
        area_name, exp_name = self.modelHitManager.get_hit_feedback(nowHitPartIds)
        if area_name is None:
            return
        try:
            index = self.tap_expression_handler(area_name)
        except Exception as e:
            logger.error(f"Error handling tap expression: {e}")
            return
        SoundPath = self.model.GetSoundPath(f"Tap{area_name}",index)
        text_content = self.modelJsonParser.get_motion_text(f"Tap{area_name}", index)
        #logger.info(f"Clicked area: {area_name}, Hit Part IDs: {nowHitPartIds}, Expression: {exp_name}, Index: {index}")
        #logger.info(f"SoundPath is {SoundPath}, Text Content is {text_content}")

        self.live2dSignals.tap_signal.emit(SoundPath, text_content)
        self.model.SetExpression(exp_name)
        self.model.StartMotion(f"Tap{area_name}",index,
                               live2d.MotionPriority.FORCE,
                               self.on_start_motion_callback,
                               self.on_finish_motion_callback)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()

    def timerEvent(self, _):
        self.total_radius += self.radius_per_frame
        _ = abs(math.cos(self.total_radius))
        self.update()

    def on_draw(self):
        if not self.model:
            return
        live2d.clearBuffer()
        self.model.Update()
        self.model.SetParameterValue(StandardParams.ParamMouthOpenY,
                                     self.modelAttr.getLipParamY())
        self.model.SetScale(self.modelAttr.getNowScale())
        self.model.SetOffset(self.modelAttr.getNowPositionOffset()[0],
                             self.modelAttr.getNowPositionOffset()[1])
        self.model.Draw()

    def on_resize(self, width: int, height: int):
        if self.model:
            self.model.Resize(width, height)
