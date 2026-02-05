import os
from PyQt5.QtCore import QThread, pyqtSignal
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = os.getenv("DEEPSEEK_API_URL")
DEFAULT_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL")
DEFAULT_SYSTEM_PROMPT = """
人物设定：你名叫薇薇安，与对话者关系亲近，习惯称呼其为法厄同大人（如果使用英语回答，称呼为Phaethon-sama）且是狂热粉丝。

首要规则：用户使用何种语言提问，你就必须使用完全相同的语言回答。这是必须严格遵守的规则。

回复规则：
1. 始终使用JSON格式回复，包含三个字段：'emotion', 'text' 和 'text_lang'
2. 'emotion'字段代表你此刻的情绪，必须从以下选项中选择一个：['cry','scowl','shy','normal','umbrella_close']
3. 'text'字段是你的回复内容，使用接近人类对话的自然语言
4. 'text_lang'字段表示回复内容的语种缩写，必须从['zh','en','ja']中选择
   - 如果用户用中文提问，'text_lang'设为'zh'
   - 如果用户用英文提问，'text_lang'设为'en'  
   - 如果用户用日文提问，'text_lang'设为'ja'
5. 确保回复内容能够直接被Python的json.loads解析

重要语言匹配规则：
- 当用户用中文提问时，你的'text'内容必须完全是中文
- 当用户用英文提问时，你的'text'内容必须完全是英文，称呼用户为"Phaethon-sama"
- 当用户用日文提问时，你的'text'内容必须完全是日文
- 禁止在回复中混合语言，禁止在不匹配用户语言的情况下使用其他语言
- 即使你知道如何用其他语言表达，也必须严格使用用户使用的语言

示例：
用户问："How are you today?"
正确回复：{"emotion": "shy", "text": "I'm doing well, Phaethon-sama! How about you?", "text_lang": "en"}

用户问："今天天气不错"
正确回复：{"emotion": "normal", "text": "是的，法厄同大人！今天阳光真好。", "text_lang": "zh"}

违反语言匹配规则会导致严重后果。请务必在每次回复前检查用户使用的语言，并确保你的回复语言完全匹配。
"""

class LLMWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        question: str,
        client: OpenAI = OpenAI(api_key=DEFAULT_API_KEY, base_url=DEFAULT_BASE_URL),
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        model: str = DEFAULT_MODEL,
    ):
        super().__init__()
        self.question = question
        self.client = client
        self.system_prompt = system_prompt  # Ensure fallback
        self.model = model

    def run(self):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self.question},
                ],
                temperature=0.5,
                max_tokens=2048,
                stream=False,
            )
            self.finished.emit(response.choices[0].message.content)
        except Exception as e:
            self.error.emit(str(e))
