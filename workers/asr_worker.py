import os
import json
import time
import queue
import sounddevice as sd
from PyQt5.QtCore import QThread, pyqtSignal
from dotenv import load_dotenv
from utils.logger_setup import get_logger
from websockets.sync.client import connect

load_dotenv()
logger = get_logger("ASRWorker")

# 音频配置常量
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16'
BLOCK_SIZE = 4096
DEFAULT_WS_URL = os.getenv("QWEN_ASR_API_URL")

class ASRWorker(QThread):
    """
    ASR工作线程，负责与本地Qwen3-ASR WebSocket服务通信。
    采用“按下说话”模式：
    - 调用 start_recording() 开始录音并推流。
    - 调用 stop_recording() 停止录音并获取识别结果。
    """

    # 信号定义
    speech_recognized = pyqtSignal(str)     # 识别成功，携带文本结果
    recognition_failed = pyqtSignal(str)    # 识别失败或发生错误，携带错误信息
    recording_started = pyqtSignal()        # 开始录音事件
    recording_stopped = pyqtSignal()        # 停止录音事件

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ws_url = os.getenv("ASR_WS_URL", DEFAULT_WS_URL)
        self._is_running = True  # 线程运行标志

        # 录音控制标志
        self._request_start = False
        self._request_stop = False
        self._is_recording_active = False

        # 音频数据队列
        self.audio_queue = queue.Queue()

    def start_recording(self):
        """
        请求开始录音。
        连接到UI的按下(pressed)信号。
        """
        if not self._is_recording_active:
            logger.info("收到开始录音请求")
            self._request_start = True
            self._request_stop = False

    def stop_recording(self):
        """
        请求停止录音。
        连接到UI的松开(released)信号。
        """
        if self._is_recording_active:
            logger.info("收到停止录音请求")
            self._request_stop = True
            self._request_start = False

    def stop_worker(self):
        """停止Worker线程，通常在程序退出时调用"""
        self._is_running = False
        self.stop_recording()
        self.wait()

    def run(self):
        """QThread 主循环"""
        if not sd or not connect:
            msg = "缺少 sounddevice 或 websockets 库，ASRWorker 无法工作。"
            logger.error(msg)
            self.recognition_failed.emit(msg)
            return

        logger.info("ASRWorker 线程已启动，等待指令...")

        while self._is_running:
            # 检查是否有开始录音的请求
            if self._request_start:
                self._request_start = False # 复位信号
                self._run_session()         # 进入一次能够完整的录音会话
            else:
                time.sleep(0.01)

    def _run_session(self):
        """执行一次完整的 录音->推流->识别 会话"""
        self._is_recording_active = True
        self.recording_started.emit()
        #logger.info(f"正在连接 ASR 服务: {self.ws_url}")

        stream = None
        # 清空队列，防止残留上一段录音
        with self.audio_queue.mutex:
            self.audio_queue.queue.clear()

        ws = None
        try:
            # 1. 优先启动音频采集，确保用户按下按钮瞬间的话语被捕获到队列中
            # 即使 WebSocket 连接需要几百毫秒，音频也不会丢失
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback
            )
            stream.start()
            #logger.info("麦克风流已启动，开始缓存音频...")

            # 2. 建立 WebSocket 连接
            # ping_interval 和 ping_timeout 用于保持长连接稳定性，虽然这里是一次性会话，但防止网络波动
            ws = connect(self.ws_url, ping_interval=20, ping_timeout=120)
            #logger.info("WebSocket 连接成功，开始推流")

            # 发送 WAV 头 (必须在首包发送)
            header = self._create_wav_header(SAMPLE_RATE, CHANNELS, 16, 0x7FFFFFFF)
            ws.send(header)

            # 推流循环
            while self._is_recording_active:
                # 检查是否收到停止信号
                if self._request_stop:
                    #logger.info("检测到停止请求，准备结束推流")
                    break

                # 检查线程是否被强制终止
                if not self._is_running:
                    break

                try:
                    # 从队列获取音频数据，设置短超时以便快速响应停止信号
                    data = self.audio_queue.get(timeout=0.05)
                    ws.send(data.tobytes())
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"WebSocket 发送错误: {e}")
                    raise e # 抛出异常中断会话

            # 停止录音流
            if stream:
                stream.stop()
                stream.close()
                stream = None

            # 发送队列中剩余的音频帧 (Flush)
            while not self.audio_queue.empty():
                try:
                    data = self.audio_queue.get_nowait()
                    ws.send(data.tobytes())
                except:
                    break
            self.recording_stopped.emit()
            # 发送 EOF 标记音频结束
            # logger.info("录音停止，发送 EOF，等待识别结果...")
            ws.send("EOF")

            # 接收识别结果
            # 设置接收超时，避免无限等待
            result_msg = ws.recv() # 这里可能会阻塞直到服务器处理完成

            try:
                result = json.loads(result_msg)
                text = result.get("text", "")
                status = result.get("status", "unknown")

                if status == "success" and text:
                    # logger.info(f"语音识别结果: {text}")
                    self.speech_recognized.emit(text)
                else:
                    # logger.info("识别完成，但内容为空或无效")
                    self.speech_recognized.emit("") # 哪怕空也发送?
                    # 这里选择不发送，或者视为空闲
            except json.JSONDecodeError:
                # logger.error(f"无法解析服务端响应: {result_msg}")
                self.recognition_failed.emit("服务端响应格式错误")

        except Exception as e:
            # logger.error(f"ASR 会话发生错误: {traceback.format_exc()}")
            self.recording_stopped.emit()  # 发生ws错误仍触发记录停止操作防止卡住
            self.recognition_failed.emit(f"错误: {str(e)}")
        finally:
            # 清理资源
            if stream:
                stream.stop()
                stream.close()
            if ws:
                try:
                    ws.close()
                except:
                    pass

            self._is_recording_active = False
            #logger.info("会话结束")

    def _audio_callback(self, indata, frames, time_info, status):
        """音频采集回调函数，运行在 sounddevice 的后台线程"""
        if status:
            logger.warning(f"Audio Input Status: {status}")
        if self._is_recording_active:
            # 必须 copy，因为 indata 是复用的 buffer
            self.audio_queue.put(indata.copy())

    def _create_wav_header(self, sample_rate, channels, bits_per_sample, data_size):
        """构建 WAV 文件头，告诉服务端音频格式"""
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8

        # RIFF header
        o = b'RIFF'
        o += (data_size + 36).to_bytes(4, 'little')
        o += b'WAVE'

        # fmt chunk
        o += b'fmt '
        o += (16).to_bytes(4, 'little')
        o += (1).to_bytes(2, 'little')
        o += channels.to_bytes(2, 'little')
        o += sample_rate.to_bytes(4, 'little')
        o += byte_rate.to_bytes(4, 'little')
        o += block_align.to_bytes(2, 'little')
        o += bits_per_sample.to_bytes(2, 'little')

        # data chunk
        o += b'data'
        o += data_size.to_bytes(4, 'little')

        return o
