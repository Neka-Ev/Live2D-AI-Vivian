from fastapi import FastAPI, UploadFile, File, Form, HTTPException, WebSocket, WebSocketDisconnect
import uvicorn
import torch
import shutil
import os
import tempfile
import sys
import uuid
import asyncio
import argparse  # 新增引用

# Append current path to sys.path to ensure local modules can be found
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- Pares the arguments from shell ---
parser = argparse.ArgumentParser(description="Qwen3 ASR API Server")
parser.add_argument("--model_path", type=str, default="Qwen/Qwen3-ASR-0.6B", help="Path to the AS model or HF repo ID")
parser.add_argument("--device", type=str, default="auto", help="Device (e.g., 'cuda:0', 'cpu', 'auto')")
parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface to bind")
parser.add_argument("--port", type=int, default=13651, help="Port to listen on")

args, _ = parser.parse_known_args()

MODEL_PATH = args.model_path
if args.device == "auto":
    DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
else:
    DEVICE = args.device
HOST = args.host
PORT = args.port
# ----------------------

# Try importing the model class
try:
    from qwen_asr import Qwen3ASRModel
except ImportError:
    print("Warning: could not import 'qwen_asr'. Please ensure it is installed.")

app = FastAPI(title="Qwen3 ASR API")
model = None


@app.on_event("startup")
async def load_model():
    global model
    try:
        if not os.path.exists(MODEL_PATH) and not MODEL_PATH.startswith("Qwen/"):
            print(f"Warning: Model path '{MODEL_PATH}' seems to be missing relative to CWD.")

        print(f"Loading Qwen3-ASR model from {MODEL_PATH} on {DEVICE}...")
        # Load model using Qwen3ASRModel (non-vllm or wrapper)
        model = Qwen3ASRModel.from_pretrained(
            MODEL_PATH,
            dtype=torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16,
            device_map=DEVICE,
            max_inference_batch_size=32,
            max_new_tokens=256,
        )
        print("Model loaded successfully!")
    except Exception as e:
        print(f"FATAL ERROR: Failed to load model. {e}")


@app.post("/asr")
async def transcribe_audio(file: UploadFile = File(...), language: str = Form(None)):
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not loaded.")
    filename = file.filename or "audio.wav"
    _, ext = os.path.splitext(filename)
    if not ext: ext = ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        lang_param = language if language and language.strip() != "" else None
        print(f"Transcribing {filename}, Language: {lang_param}...")
        # Call model
        results = model.transcribe(audio=tmp_path, language=lang_param, context=["薇薇安"])
        if results and len(results) > 0:
            res = results[0]
            return {"status": "success", "language": res.language, "text": res.text}
        else:
            return {"status": "success", "language": "unknown", "text": ""}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass


@app.websocket("/asr/ws")
async def websocket_asr(websocket: WebSocket):
    """
    WebSocket Endpoint for streaming audio upload.
    Protocol:
    1. Client connects.
    2. Client optionally sends JSON config: {"language": "en"}
    3. Client sends binary audio chunks (WAV header included in the first chunk preferred, or raw PCM if model supports it - but we assume WAV/format valid file stream).
    4. Client sends text "EOF" to signal end of stream.
    5. Server runs inference and returns JSON result.
    """
    await websocket.accept()
    print("WebSocket connected.")

    # Create a unique temp file
    filename = f"ws_audio_{uuid.uuid4().hex}.wav"
    tmp_path = os.path.join(tempfile.gettempdir(), filename)

    language_param = None

    try:
        with open(tmp_path, 'wb') as f:
            while True:
                # Receive message
                message = await websocket.receive()

                if "text" in message and message["text"]:
                    text_data = message["text"]
                    if text_data == "EOF":
                        break

                    # Try parsing as JSON for config
                    try:
                        import json
                        config = json.loads(text_data)
                        if "language" in config:
                            language_param = config["language"]
                            print(f"WS Config: Set language to {language_param}")
                    except:
                        pass  # Ignore non-JSON text that isn't EOF

                if "bytes" in message and message["bytes"]:
                    f.write(message["bytes"])

        print(f"WS Audio received: {tmp_path}. Starting inference...")

        if model is None:
            await websocket.send_json({"status": "error", "message": "Model not loaded"})
            return

        # Use asyncio.to_thread to run the blocking inference in a separate thread
        # This prevents blocking the asyncio event loop, allowing pings/pongs to be processed.
        results = await asyncio.to_thread(
            model.transcribe,
            audio=tmp_path,
            language=language_param,
            context=["薇薇安"]
        )

        if results and len(results) > 0:
            res = results[0]
            await websocket.send_json({
                "status": "success",
                "language": res.language,
                "text": res.text
            })
        else:
            await websocket.send_json({"status": "success", "language": "unknown", "text": ""})

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WS Error: {e}")
        # Try to send error if connection is open
        try:
            await websocket.send_json({"status": "error", "message": str(e)})
        except:
            pass
    finally:
        # Cleanup
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass


if __name__ == "__main__":
    # Use HOST and PORT from args
    uvicorn.run(app, host=HOST, port=PORT)
