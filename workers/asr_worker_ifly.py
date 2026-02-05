import os
import time
import json
import base64
import hmac
import hashlib
import datetime
import pyaudio
import websocket
from wsgiref.handlers import format_date_time
from urllib.parse import urlencode

from PyQt5.QtCore import QThread, pyqtSignal
from dotenv import load_dotenv
from utils.logger_setup import get_logger


load_dotenv()
logger = get_logger("ASRWorker_ifly")

class ASRWorker(QThread):
    """
    ASR Worker using iFlyTek (Xunfei) Streaming API.
    Refactored to Push-to-Talk mode to match local ASR interface.
    """
    # Signals matching asr_worker.py
    speech_recognized = pyqtSignal(str)     # Final recognition result
    recognition_failed = pyqtSignal(str)    # Error message
    recording_started = pyqtSignal()        # Recording started
    recording_stopped = pyqtSignal()        # Recording stopped

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = True

        # Recording control flags
        self._request_start = False
        self._request_stop = False
        self._is_recording_active = False

        # Audio Configuration
        self.pa = None
        self.audio_stream = None
        self.sample_rate = 16000
        # iFlyTek recommends ~40ms buffer (16000 * 0.04 = 640 samples = 1280 bytes)
        self.frames_per_buffer = 1280

        # iFlyTek Credentials
        self.iflytek_appid = os.getenv("IFLYTEK_APPID")
        self.iflytek_api_secret = os.getenv("IFLYTEK_API_SECRET")
        self.iflytek_api_key = os.getenv("IFLYTEK_API_KEY")

    def start_recording(self):
        """Request to start recording."""
        if not self._is_recording_active:
            self._request_start = True
            self._request_stop = False

    def stop_recording(self):
        """Request to stop recording and finalize."""
        if self._is_recording_active:
            self._request_stop = True
            self._request_start = False

    def stop(self):
        """Stop worker thread completely."""
        self._is_running = False
        self.wait()

    def run(self):
        """Main thread loop."""
        if not pyaudio or not websocket:
            self.recognition_failed.emit("Missing dependencies: pyaudio or websocket-client")
            return

        self._init_audio()
        if not self.audio_stream:
            self.recognition_failed.emit("Failed to initialize Audio Stream")
            return

        logger.info("ASRWorker (iFlyTek) 准备就绪. 等待录音指令...")

        while self._is_running:
            if self._request_start:
                self._request_start = False
                self._run_session()
            else:
                time.sleep(0.01)

        self._cleanup()

    def _init_audio(self):
        try:
            self.pa = pyaudio.PyAudio()
            self.audio_stream = self.pa.open(
                rate=self.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=self.frames_per_buffer
            )
        except Exception as e:
            logger.error(f"Audio Init Error: {e}")
            self.audio_stream = None

    def _cleanup(self):
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except: pass
        if self.pa:
            try:
                self.pa.terminate()
            except: pass

    def _create_iflytek_url(self):
        """Generate auth URL."""
        url = 'wss://iat-api.xfyun.cn/v2/iat'
        host = 'iat-api.xfyun.cn'
        now = datetime.datetime.now()
        date = format_date_time(time.mktime(now.timetuple()))

        signature_origin = "host: {}\ndate: {}\nGET /v2/iat HTTP/1.1".format(host, date)
        signature_sha = hmac.new(self.iflytek_api_secret.encode('utf-8'), signature_origin.encode('utf-8'),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = "api_key=\"{}\", algorithm=\"hmac-sha256\", headers=\"host date request-line\", signature=\"{}\"".format(
            self.iflytek_api_key, signature_sha)
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')

        v = {
            "authorization": authorization,
            "date": date,
            "host": host
        }
        return url + '?' + urlencode(v)

    def _run_session(self):
        """Run one recording session."""
        if not self.iflytek_appid or not self.iflytek_api_key or not self.iflytek_api_secret:
            self.recognition_failed.emit("Missing iFlyTek credentials in .env")
            return

        self._is_recording_active = True
        self.recording_started.emit()

        ws_url = self._create_iflytek_url()
        ws = None
        try:
            ws = websocket.create_connection(ws_url, timeout=5)
        except Exception as e:
            logger.error(f"WS Connect Failed: {e}")
            self.recording_stopped.emit()
            self.recognition_failed.emit(f"Connection Error: {e}")
            self._is_recording_active = False

            return

        logger.info("iFlyTek Connected. Streaming...")

        status = 0 # 0=first, 1=middle, 2=last
        final_parts = []

        try:
            while self._is_recording_active and self._is_running:
                # 1. Check if user requested stop
                if self._request_stop:
                    status = 2

                # 2. Read Audio
                try:
                    # Blocking read
                    chunk = self.audio_stream.read(self.frames_per_buffer, exception_on_overflow=False)
                except Exception as e:
                    logger.error(f"Audio Read Error: {e}")
                    break

                # 3. Send to WS
                data = {
                    "data": {
                        "status": status,
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": base64.b64encode(chunk).decode('utf-8')
                    }
                }

                # First frame needs common/business args
                if status == 0:
                    data = {
                        "common": {"app_id": self.iflytek_appid},
                        "business": {
                            "domain": "iat",
                            "language": "zh_cn",
                            "accent": "mandarin",
                            "vad_eos": 10000
                        },
                        "data": data["data"]
                    }

                ws.send(json.dumps(data))

                if status == 0:
                    status = 1

                # If we sent status=2, we break loop and wait for result
                if status == 2:
                    break

                # 4. Try to receive partial results (non-blockingish)
                try:
                    ws.settimeout(0.01)
                    resp = ws.recv()
                    txt = self._parse_result(resp)
                    if txt: final_parts.append(txt)
                except websocket.WebSocketTimeoutException:
                    pass

            # 5. Flush / Wait for final
            ws.settimeout(2.0)
            while True:
                try:
                    resp = ws.recv()
                    txt = self._parse_result(resp)
                    if txt: final_parts.append(txt)

                    # Check for server end signal
                    d = json.loads(resp)
                    if d.get("code") != 0 or d.get("data", {}).get("status") == 2:
                        break
                except (websocket.WebSocketTimeoutException, Exception):
                    break

        except Exception as e:
            logger.error(f"Session Error: {e}")
            self.recognition_failed.emit(str(e))
        finally:
            if ws:
                ws.close()
            self._is_recording_active = False
            self.recording_stopped.emit()

            # Emit final full text
            full_text = "".join(final_parts)
            logger.info(f"Recognition Result: {full_text}")
            self.speech_recognized.emit(full_text)

    def _parse_result(self, json_str):
        try:
            data = json.loads(json_str)
            if data.get("code") != 0:
                logger.warning(f"iFly Error: {data.get('message')}")
                return ""

            text = ""
            if "data" in data and "result" in data["data"]:
                ws = data["data"]["result"]["ws"]
                for w in ws:
                    for cw in w["cw"]:
                        text += cw["w"]
            return text
        except Exception:
            return ""
