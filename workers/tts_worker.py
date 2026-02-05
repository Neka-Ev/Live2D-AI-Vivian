import os
import struct
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from dotenv import load_dotenv
from utils.logger_setup import get_logger

load_dotenv()
logger = get_logger("TTSWorker")

TTS_API_URL = os.getenv("GPT_SOVITS_API_URL")

class TTSWorker(QThread):
    """Worker thread to stream TTS audio from API."""
    audio_setup = pyqtSignal(int, int, int)  # sample_rate, channels, sample_size
    audio_data = pyqtSignal(bytes)
    stream_finished = pyqtSignal() # 数据发送完毕信号
    error = pyqtSignal(str)

    def __init__(
        self,
        text: str,
        ref_audio_path: str,
        prompt_text: str = "",
        text_lang: str = "zh",
        prompt_lang: str = "zh"
    ):
        super().__init__()
        self.text = text
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.text_lang = text_lang
        self.prompt_lang = prompt_lang


    def run(self):
        try:
            params = {
                "text": self.text,
                "ref_audio_path": self.ref_audio_path,
                "prompt_text": self.prompt_text,
                "text_lang": self.text_lang,
                "prompt_lang": self.prompt_lang,
                "streaming_mode": "true",
                "media_type": "wav"
            }

            # Using requests with stream=True for low latency
            with requests.get(TTS_API_URL, params=params, stream=True) as resp:
                resp.raise_for_status()

                buffer = b""
                header_parsed = False

                for chunk in resp.iter_content(chunk_size=4096):
                    if not header_parsed:
                        buffer += chunk
                        if len(buffer) >= 44:
                            # Parse WAV header to get format
                            # Offset 22: Num Channels (2 bytes)
                            # Offset 24: Sample Rate (4 bytes)
                            # Offset 34: Bits Per Sample (2 bytes)
                            channels = struct.unpack_from("<H", buffer, 22)[0]
                            sample_rate = struct.unpack_from("<I", buffer, 24)[0]
                            bits_per_sample = struct.unpack_from("<H", buffer, 34)[0]

                            self.audio_setup.emit(sample_rate, channels, bits_per_sample)

                            # Emit remaining data (skipping 44 byte header)
                            self.audio_data.emit(buffer[44:])
                            header_parsed = True
                            buffer = b""
                            logger.info(f"TTSWorker: Init audio. Rate={sample_rate}, Ch={channels}, Bits={bits_per_sample}")
                    else:
                        self.audio_data.emit(chunk)
                # 循环结束意味着服务器已发送完所有数据
                self.stream_finished.emit()

        except Exception as e:
            self.error.emit(f"TTS Error: {str(e)}")
