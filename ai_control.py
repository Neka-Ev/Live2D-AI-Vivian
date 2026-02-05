import os
import json
import re
import audioop
from typing import Optional

from PyQt5.QtCore import pyqtSignal, QObject, QTimer, QIODevice, QUrl
from PyQt5.QtMultimedia import QAudioFormat, QAudioOutput, QAudioDeviceInfo, QAudio, QSoundEffect
from live2d.utils.lipsync import WavHandler
from dotenv import load_dotenv
from openai import OpenAI

from utils import resources
from utils.logger_setup import get_logger
from workers.llm_worker import LLMWorker
from workers.tts_worker import TTSWorker
from workers.asr_worker_ifly import ASRWorker

from canvas_live2d import Live2DSignals

load_dotenv()
logger = get_logger("AIControl")


TTS_REF_AUDIO_PATH = os.getenv("REF_AUDIO_PATH")
TTS_REF_PROMPT_TEXT = os.getenv("REF_PROMPT_TEXT")

class Controller(QObject):
    """Controller class to emit signals for Live2D model control."""
    expression_state_changed = pyqtSignal(str)
    attribute_state_changed = pyqtSignal(str)
    call_state_changed = pyqtSignal(str)
    lip_sync_state_changed = pyqtSignal(float, float)
    audio_output_stopped = pyqtSignal()

class AIManager(QObject):
    """Manager class to handle AI logic: LLM, TTS, ASR, and Audio."""

    # Signals to update UI
    response_ready = pyqtSignal(str)          # Full response text available
    typing_update = pyqtSignal(str)           # Current text for typewriter effect
    typing_finished = pyqtSignal()
    status_update = pyqtSignal(str)           # Status update (KEY)
    asr_partial_update = pyqtSignal(str)      # ASR partial/final result to update input box
    listening_state_changed = pyqtSignal(bool)# True if recording started, False if stopped

    def __init__(self,
                 controller: Controller,
                 live2dSignals: Live2DSignals,
                 ):
        super().__init__()
        self.controller = controller
        self.live2dSignals = live2dSignals

        self.Expressions = ["normal", "panic", "scowl", "shy", "umbrella_close", "cry"]

        # Worker placeholders
        self.client: Optional[OpenAI] = None
        self.LLMWorker: Optional[LLMWorker] = None
        self.TTSWorker: Optional[TTSWorker] = None
        self.ASRWorker: Optional[ASRWorker] = None

        self.tts_init_info = {"ref_sound_path": "", "prompt_text": "", "text_lang": "zh", "prompt_lang": "zh" }

        # Audio
        self.audio_output: Optional[QAudioOutput] = None
        self.audio_device: Optional[QIODevice] = None
        self.audio_buffer = bytearray()
        self.sample_width = 2
        self.is_tts_fully_downloaded = False
        self.audio_timer = QTimer(self)
        self.lip_sync = 1.5

        # Text/Logic State
        self.text_response: str = ""
        self.text_response_lang: str = "zh"
        self.emotion_from_response: str = "normal"
        self.current_typing_text: str = ""

        # Typewriter
        self.typewriter_timer: Optional[QTimer] = None
        self.typing_index: int = 0
        self.typing_speed_map: dict = {"zh": 100, "en": 50, "ja": 80}

        # Tap Sound
        self._tap_sound = QSoundEffect(self)
        self.wav_handler = WavHandler()
        self.wav_timer = QTimer(self)

        self.status = {
            "idle": "薇薇安正在拉电线>_<",
            "asr-listening": "薇薇安正在收集语音信息. . . (松开按钮结束) (•̀ᴗ•́)و",
            "asr-recognizing": "薇薇安正在尝试大语音识别术>_<",
            "asr-invalid": "薇薇安没有听清呢 (っ °Д °;)っ",
            "asr-success": "薇薇安听的对吗( *´▽`*)？",
            "asr-error": "大语音识别术因为不可抗力失败了QAQ 请使用文本输入 (╥﹏╥)",
            "llm-error": "信号丢失到异世界了QAQ",
            "llm-waiting": "薇薇安，陷入思考>_< ",
            "tts-synthesizing": "薇薇安正在尝试大语音合成术>_<",
            "tts-error": "大语音合成术因为不可抗力失败了QAQ 仅显示文字 (╥﹏╥)",
            "tts-success": "薇薇安正在说话 ♫･◡･๑"
        }
        self.directly_send = False

        self.initAPI()
        self.initTimers()
        self.connect_signals()

    def connect_signals(self):
        # Internal signals
        self.live2dSignals.tap_signal.connect(self.tap_handler)

    def initAPI(self):
        """Initialize Workers"""
        self.tts_init_info["ref_sound_path"] = TTS_REF_AUDIO_PATH
        self.tts_init_info["prompt_text"] = TTS_REF_PROMPT_TEXT

        try:
            self.ASRWorker = ASRWorker()
            self.ASRWorker.recording_started.connect(self.on_recording_started)
            self.ASRWorker.recording_stopped.connect(self.on_recording_stopped)
            self.ASRWorker.speech_recognized.connect(self.on_speech_recognized)
            self.ASRWorker.recognition_failed.connect(lambda e: logger.error(f"ASR Error: {e}"))
            self.ASRWorker.recognition_failed.connect(lambda : self.status_update.emit("asr-error"))
            self.ASRWorker.start()
        except Exception as e:
            logger.error(f"Failed to start ASR Worker: {e}")

    def initTimers(self):
        self.audio_timer.setInterval(20)
        self.audio_timer.timeout.connect(self.process_audio_queue)
        self.wav_timer.setInterval(30)
        self.wav_timer.timeout.connect(self.process_wav_lipsync)

    def process_input_text(self, text: str):
        """Process text input from UI (Send button)"""
        question = text.strip()
        if not question:
            return

        # Start Waiting State
        self.current_waiting_state = 0
        self.status_update.emit("llm-waiting")
        self.controller.call_state_changed.emit("normal")
        # Stop previous audio
        self.stop_audio_playback()

        self.is_tts_fully_downloaded = False
        self.LLMWorker = LLMWorker(question)
        self.LLMWorker.finished.connect(self.call_success_handler)
        self.LLMWorker.error.connect(self.call_error_handler)
        self.LLMWorker.start()

    def start_voice_input(self):
        """Start ASR recording"""
        if self.ASRWorker:
            self.ASRWorker.start_recording()

    def stop_voice_input(self):
        """Stop ASR recording"""
        if self.ASRWorker:
            self.ASRWorker.stop_recording()

    def on_recording_started(self):
        self.status_update.emit("asr-listening")
        self.listening_state_changed.emit(True)
        # Stop playback if any
        if self.audio_output and self.audio_output.state() == QAudio.ActiveState:
            self.stop_audio_playback()
            self.controller.audio_output_stopped.emit()

    def on_recording_stopped(self):
         self.status_update.emit("asr-recognizing")
         self.listening_state_changed.emit(False)

    def on_speech_recognized(self, text: str):
        if not text:
            self.status_update.emit("asr-invalid")
            return
        logger.info(f"User said: {text}")
        self.asr_partial_update.emit(text)
        if self.directly_send:
            self.process_input_text(text)
        else:
            self.status_update.emit("asr-success")

    def set_voice_directly_mode(self, enabled: bool):
        self.directly_send = enabled

    def stop_audio_playback(self):
        if self.audio_output:
            self.audio_output.stop()
            self.audio_output.deleteLater()
            self.audio_output = None
            self.audio_device = None
        self.audio_buffer.clear()

    def call_success_handler(self, content: str):
        emotion = "normal"
        text_content = content
        text_lang = "zh"
        self.is_tts_fully_downloaded = False
        try:
            # Attempt to clean potential markdown wrappers
            clean_content = content.replace("```json", "").replace("```", "").strip()
            # Try to find JSON object if there's extra text
            json_match = re.search(r'\{.*\}', clean_content, re.DOTALL)
            if json_match:
                clean_content = json_match.group(0)

            data = json.loads(clean_content)
            if isinstance(data, dict):
                emotion = data.get("emotion", "shy")
                logger.info(f"Parsed emotion: {emotion}")
                text_content = data.get("text", content)
                text_lang = data.get("text_lang")
        except Exception as e:
            logger.error(f"JSON Parse Error: {e}, using raw content.")

        self.emotion_from_response = emotion if (emotion in self.Expressions) else "normal"
        # Filter out text in brackets for TTS
        # Matches (text) or （text）
        tts_text = re.sub(r'[（\(].*?[）\)]', '', text_content)
        # Start typewriter effect
        self.typing_index = 0
        self.text_response_lang = text_lang
        self.text_response = text_content


        # Start TTS
        ref_path = self.tts_init_info.get("ref_sound_path")
        prompt_text = self.tts_init_info.get("prompt_text")

        try:
            self.status_update.emit("tts-synthesizing")
            self.TTSWorker = TTSWorker(tts_text, ref_path, prompt_text, text_lang)
            self.TTSWorker.audio_setup.connect(self.init_audio_output)
            self.TTSWorker.audio_data.connect(self.feed_audio_data)
            self.TTSWorker.stream_finished.connect(self.on_tts_stream_finished)
            self.TTSWorker.error.connect(lambda e: logger.error(f"TTS Error: {e}"))
            self.TTSWorker.error.connect(lambda : self.status_update.emit("tts-error"))
            self.TTSWorker.error.connect(lambda : self.startTypingEffect())
            self.TTSWorker.start()
        except Exception:
            logger.error("TTS Starting error, only output response.")


    def call_error_handler(self, error_msg: str):
        logger.error(f"LLM Call Error:{error_msg}")
        self.status_update.emit("llm-error")
        if len(self.Expressions) > 4:
            self.controller.call_state_changed.emit(self.Expressions[4]) # 'umbrella_close' or error exp

    def init_audio_output(self, sample_rate, channels, sample_size):
        self.status_update.emit("tts-success")

        self.stop_audio_playback()

        self.sample_width = sample_size // 8

        format = QAudioFormat()
        format.setSampleRate(sample_rate)
        format.setChannelCount(channels)
        format.setSampleSize(sample_size)
        format.setCodec("audio/pcm")
        format.setByteOrder(QAudioFormat.LittleEndian)
        format.setSampleType(QAudioFormat.SignedInt)

        info = QAudioDeviceInfo.defaultOutputDevice()
        if not info.isFormatSupported(format):
            format = info.nearestFormat(format)

        self.audio_output = QAudioOutput(format, self)
        self.audio_output.stateChanged.connect(self.on_audio_state_changed)

        buffer_duration = 0.2
        buffer_size = int(sample_rate * channels * (sample_size // 8) * buffer_duration)
        self.audio_output.setBufferSize(buffer_size)

        self.audio_device = self.audio_output.start()

        self.audio_buffer.clear()
        self.audio_timer.start()
        self.startTypingEffect()

    def startTypingEffect(self, text: str = None):
        """开始打字机效果"""
        target_text = text if text is not None else self.text_response
        typing_speed = self.typing_speed_map.get(self.text_response_lang, 100) # zh 100 en 50 ja 80
        self.current_typing_text = target_text
        self.typing_index = 0

        self.response_ready.emit(target_text)

        if self.typewriter_timer:
            self.typewriter_timer.stop()

        self.typewriter_timer = QTimer(self)
        self.typewriter_timer.timeout.connect(self.typewriteEffect)
        self.typewriter_timer.start(typing_speed)

        # Only trigger emotion change if using internal LLM response (text is None)
        if text is None:
            self.controller.expression_state_changed.emit(self.emotion_from_response)

    def on_tts_stream_finished(self):
        logger.info("AIManager: TTS Data Stream Download Complete.")
        self.is_tts_fully_downloaded = True
        if self.audio_output and self.audio_output.state() == QAudio.IdleState and len(self.audio_buffer) == 0:
            self.status_update.emit("idle")
            self.controller.audio_output_stopped.emit()

    def on_audio_state_changed(self, state):
        if state == QAudio.IdleState and len(self.audio_buffer) == 0:
            if self.is_tts_fully_downloaded:
                self.status_update.emit("idle")
                self.controller.audio_output_stopped.emit()
            self.controller.lip_sync_state_changed.emit(0.0, self.lip_sync)

    def feed_audio_data(self, data: bytes):
        self.audio_buffer.extend(data)
        self.process_audio_queue()

    def process_audio_queue(self):
        if not self.audio_output or not self.audio_device:
            return

        state = self.audio_output.state()
        chunks_free = self.audio_output.bytesFree()
        if chunks_free > 0 and len(self.audio_buffer) > 0:
            to_write = min(chunks_free, len(self.audio_buffer))
            data_to_write = self.audio_buffer[:to_write]

            try:
                rms = audioop.rms(data_to_write, self.sample_width)
                mouth_open = min(1.0, rms / 10000.0)
                self.controller.lip_sync_state_changed.emit(mouth_open, self.lip_sync)
            except Exception:
                pass

            written = self.audio_device.write(bytes(data_to_write))
            if written > 0:
                del self.audio_buffer[:written]

    def typewriteEffect(self):
        if self.typing_index <= len(self.current_typing_text):
            # Emit just the substring to display
            current_text = self.current_typing_text[: self.typing_index]
            self.typing_update.emit(current_text)
            self.typing_index += 1
        else:
            if self.typewriter_timer:
                self.typewriter_timer.stop()
            self.typing_finished.emit()

    def tap_handler(self, sound_path: str, text: str):
        if not sound_path:
            return
        sound_path = os.path.join(resources.RESOURCES_DIRECTORY, sound_path)
        if not os.path.exists(sound_path):
            logger.error(f"Tap sound not found: {sound_path}")
            return
        self._tap_sound.setSource(QUrl.fromLocalFile(sound_path))
        self._tap_sound.setLoopCount(1)
        self._tap_sound.setVolume(1.0)
        self._tap_sound.play()
        self.wav_handler.Start(sound_path)
        self.wav_timer.start()
        self.status_update.emit("tts-success")
        self.startTypingEffect(text)


    def process_wav_lipsync(self):
        if self.wav_handler.Update():
            rms = self.wav_handler.GetRms()
            self.controller.lip_sync_state_changed.emit(rms, self.lip_sync * 2)
        else:
            self.wav_timer.stop()
            self.status_update.emit("idle")
            self.controller.audio_output_stopped.emit()
            self.controller.lip_sync_state_changed.emit(0.0, self.lip_sync)
