# meta developer: @Sy4enish , @SKBerryXXX
# meta name: AllAi
# meta banner: https://github.com/Sy4enish/Sy4Modules/blob/main/IMG_20260609_074927_794.jpg

import asyncio
import base64
import io
import logging
import os
import re
import subprocess
import tempfile
import time
import urllib.parse

import aiohttp
from telethon import functions
from telethon.tl.types import Message

from .. import loader, utils
from ..inline.types import InlineCall

logger = logging.getLogger(__name__)

# ─── актуальные модели по провайдерам ────────────────────────────────────────
PROVIDER_MODELS = {
    "openai": [
        "gpt-5.5", "gpt-5.5-instant",
        "gpt-5.4", "gpt-5.4-mini",
        "gpt-5", "gpt-5-mini",
        "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
        "o3", "o4-mini",
    ],
    "anthropic": [
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "gemini": [
        "gemini-3.5-flash",
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
    ],
    "gemini_hub": [
        "gemini-3.5-flash",
        "gemini-3.1-pro-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
    ],
    "deepseek": [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "deepseek-chat",
        "deepseek-reasoner",
    ],
    "qwen": [
        "qwen3.7-max",
        "qwen3.6-max-preview",
        "qwen3.5-plus",
        "qwen3.5-flash",
        "qwen3-max",
        "qwen3-coder-plus",
        "qwq-plus",
    ],
    "openrouter": [
        "anthropic/claude-opus-4-8",
        "anthropic/claude-opus-4-7",
        "anthropic/claude-sonnet-4-6",
        "openai/gpt-5.5",
        "openai/gpt-4.1",
        "google/gemini-3.5-flash",
        "google/gemini-3.1-pro-preview",
        "deepseek/deepseek-v4-pro",
        "x-ai/grok-4.20",
        "qwen/qwen3.7-max",
        "mistralai/mistral-large-2411",
        "meta-llama/llama-3.3-70b-instruct",
    ],
    "codex": [
        "gpt-5.5",
        "gpt-5",
        "gpt-4.1",
        "o3",
        "o4-mini",
    ],
    "nvidia": [
        "meta/llama-3.3-70b-instruct",
        "nvidia/llama-3.1-nemotron-70b-instruct",
        "mistralai/mixtral-8x22b-instruct-v0.1",
    ],
    "custom": [],
}

# ─── модели картинок по провайдерам ──────────────────────────────────────────
IMAGE_MODELS = {
    "openai": ["dall-e-3", "gpt-image-1"],
    "gemini": ["imagen-3.0-generate-001", "imagen-3.0-generate-002", "gemini-2.0-flash-exp"],
    "gemini_hub": ["gemini-2.5-flash-image", "gemini-2.0-flash-exp", "gemini-2.5-pro"],
}

# Модели, генерирующие картинки через чат-комплитины (нативная генерация)
CHAT_IMAGE_MODELS = {"gemini-2.0-flash-exp", "gemini-2.5-pro"}

# ─── безопасные HTML-теги Telegram ──────────────────────────────────────────
_SAFE_HTML_RE = re.compile(
    r"""</?(?:b|i|u|s|code|pre|a|blockquote|tg-emoji|br)\b[^>]*>""",
    re.IGNORECASE,
)

# ─── агентные инструменты ─────────────────────────────────────────────────────
AGENT_TOOLS_SYSTEM = """
[АГЕНТНЫЕ ИНСТРУМЕНТЫ]
У тебя есть реальные инструменты. Вставляй теги ПРЯМО в текст ответа — система их выполнит и вернёт результат.

• Веб-поиск:                  <TOOL:search:запрос>
• Написать сообщение:         <TOOL:send:цель|текст>
• Несколько сообщений подряд: <TOOL:send_multi:цель|сообщение1||сообщение2||сообщение3>
• Удалить сообщение:          <TOOL:delete:reply>  или  <TOOL:delete:msg_id>
• Заблокировать:              <TOOL:block:цель>
• Разблокировать:             <TOOL:unblock:цель>
• Анализ чата:                <TOOL:analyze_chat:число_сообщений>
• Сменить имя/фамилию:        <TOOL:set_name:Имя|Фамилия>  (фамилия необязательна)
• Сменить био (о себе):       <TOOL:set_bio:текст bio>
• Сменить юзернейм:           <TOOL:set_username:новый_юзернейм>  (без @)
• Создать/сохранить скилл:    <TOOL:createskill:название|промпт текст>
• Улучшить системный промпт:  <TOOL:improveself_prompt:инструкция что улучшить>
• Выполнить JS-код:           <TOOL:eval_js:код на javascript>

ВАЖНО: <TOOL:search:запрос> — это НАСТОЯЩИЙ веб-поиск в интернете. Используй его всегда когда нужна актуальная информация: новости, цены, курсы, погода, время, последние модели техники, события и т.д. После поиска ты получишь реальные результаты и сможешь ответить точно.

Когда пользователь спрашивает о чём-то актуальном — сначала ищи, потом отвечай. Не придумывай устаревшие данные.
Когда пользователь просит написать несколько сообщений подряд — используй send_multi, разделяя их через ||.
Когда пользователь просит поменять ник/имя — используй set_name. Для bio/о себе — set_bio. Для @username — set_username.
Когда пользователь просит создать/сохранить скилл — используй createskill с названием и текстом промпта.
Когда пользователь просит улучшить промпт/инструкцию бота — используй improveself_prompt, опиши что изменить.
Когда нужно выполнить код, вычисления, обработать данные — используй eval_js с JavaScript-кодом любой сложности. Используй return для возврата результата.
После каждого инструмента система возвращает результат. Максимум 5 шагов.
"""


@loader.tds
class AIRouteUltimateMod(loader.Module):
    """Мульти-провайдерный AI-модуль с агентами, шагами и инлайн-управлением"""

    strings = {
        "name": "AIRoute",
        "processing": "<tg-emoji emoji-id=5776213190387961618>🕓</tg-emoji> <b>Обработка...</b>",
        "no_key": "<tg-emoji emoji-id=5879813604068298387>❗️</tg-emoji> <b>Ключ API не найден!</b>",
        "error": "<tg-emoji emoji-id=5778527486270770928>❌</tg-emoji> <b>Ошибка:</b> <code>{}</code>",
        "cleared": "<tg-emoji emoji-id=6007942490076745785>🧹</tg-emoji> <b>История очищена!</b>",
        "provider_set": "<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> <b>Провайдер:</b> <code>{}</code>",
        "no_prompt": "<tg-emoji emoji-id=5879813604068298387>❗️</tg-emoji> <i>Нужен текст или медиа.</i>",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue("active_provider", "gemini",
                "Текущий провайдер (openai/anthropic/gemini/gemini_hub/deepseek/qwen/openrouter/codex/nvidia/custom)"),
            loader.ConfigValue("image_provider", "gemini",
                "Провайдер картинок (openai/gemini/gemini_hub)"),
            
            loader.ConfigValue("openai_api_key", "", "API ключ OpenAI", validator=loader.validators.Hidden()),
            loader.ConfigValue("openai_model", "gpt-5.5", "Модель OpenAI"),
            loader.ConfigValue("openai_image_model", "dall-e-3", "Модель картинок OpenAI"),
            
            loader.ConfigValue("anthropic_api_key", "", "API ключ Anthropic", validator=loader.validators.Hidden()),
            loader.ConfigValue("anthropic_model", "claude-opus-4-8", "Модель Claude"),
            
            loader.ConfigValue("gemini_api_key", "", "API ключ Gemini (AIza...)", validator=loader.validators.Hidden()),
            loader.ConfigValue("gemini_model", "gemini-3.5-flash", "Модель Gemini (текст)"),
            loader.ConfigValue("gemini_image_model", "imagen-3.0-generate-001", "Модель Gemini (картинки)"),

            loader.ConfigValue("gemini_hub_api_key", "", "API ключ Gemini Hub (sk-...)", validator=loader.validators.Hidden()),
            loader.ConfigValue("gemini_hub_model", "gemini-2.5-pro", "Модель Gemini Hub"),
            loader.ConfigValue("gemini_hub_image_model", "gemini-2.5-flash-image", "Модель Gemini Hub (картинки)"),
            
            loader.ConfigValue("deepseek_api_key", "", "API ключ DeepSeek", validator=loader.validators.Hidden()),
            loader.ConfigValue("deepseek_model", "deepseek-v4-pro", "Модель DeepSeek"),
            
            loader.ConfigValue("qwen_api_key", "", "API ключ Qwen", validator=loader.validators.Hidden()),
            loader.ConfigValue("qwen_model", "qwen3.7-max", "Модель Qwen"),
            
            loader.ConfigValue("openrouter_api_key", "", "API ключ OpenRouter", validator=loader.validators.Hidden()),
            loader.ConfigValue("openrouter_model", "anthropic/claude-opus-4-8", "Модель OpenRouter"),
            
            loader.ConfigValue("codex_api_key", "", "API ключ Codex (OpenAI)", validator=loader.validators.Hidden()),
            loader.ConfigValue("codex_model", "gpt-4.1", "Модель Codex"),
            
            loader.ConfigValue("nvidia_api_key", "", "API ключ NVIDIA", validator=loader.validators.Hidden()),
            loader.ConfigValue("nvidia_model", "meta/llama-3.3-70b-instruct", "Модель NVIDIA"),
            
            loader.ConfigValue("custom_api_key", "", "API ключ кастомного провайдера", validator=loader.validators.Hidden()),
            loader.ConfigValue("custom_base_url", "", "Base URL кастомного провайдера (напр. https://my-api.com/v1/chat/completions)"),
            loader.ConfigValue("custom_model", "gpt-4o", "Модель кастомного провайдера"),
            

            loader.ConfigValue("system_instruction", "Ты полезный ассистент.", "Системный промпт"),
            loader.ConfigValue("agent_mode", True, "Режим агента"),
            loader.ConfigValue("agent_max_steps", 5, "Максимум шагов агента"),
            loader.ConfigValue("max_history_length", 40, "Размер истории сообщений"),
            loader.ConfigValue("show_agent_steps", True, "Показывать шаги агента в ответе"),
            loader.ConfigValue("read_incoming", False, "Читать входящие ответы в диалогах (бот/человек видит ИИ)"),
        )
        self.history = {}
        self.skills = {}
        self._ffmpeg_checked = None
        self._no_inline_chats = set()  # чаты где инлайн запрещён
        self._tracked_dialogs = set()  # диалоги, где ИИ ждёт ответа

    async def client_ready(self, client, db):
        self.client = client
        self.db = db
        self.me = await client.get_me()
        self.history = self.db.get(self.strings["name"], "chat_history", {})
        self.skills = self.db.get(self.strings["name"], "saved_skills", {})

    def _save_db(self):
        self.db.set(self.strings["name"], "chat_history", self.history)
        self.db.set(self.strings["name"], "saved_skills", self.skills)

    def _get_history(self, chat_id):
        cid = str(chat_id)
        if cid not in self.history:
            self.history[cid] = []
        return self.history[cid]

    def _update_history(self, chat_id, role, text):
        cid = str(chat_id)
        hist = self._get_history(cid)
        hist.append({"role": role, "content": text, "timestamp": time.time()})
        max_len = self.config["max_history_length"]
        if len(hist) > max_len:
            self.history[cid] = hist[-max_len:]
        self._save_db()

    def _add_exchange_to_history(self, chat_id, user_text, model_text):
        """Сохраняет обмен user+model как ОДНУ запись в историю (вместо 2 отдельных)"""
        cid = str(chat_id)
        hist = self._get_history(cid)
        # Защита от дублирования: если последний exchange тот же самый — не сохраняем
        if hist and hist[-1].get("role") == "exchange":
            if hist[-1].get("user") == user_text and hist[-1].get("model") == model_text:
                return  # уже сохранено, не дублируем
        hist.append({
            "role": "exchange",
            "user": user_text,
            "model": model_text,
            "timestamp": time.time()
        })
        max_len = self.config["max_history_length"]
        if len(hist) > max_len:
            self.history[cid] = hist[-max_len:]
        self._save_db()

    def _get_history_expanded(self, chat_id):
        """Разворачивает историю для API-вызовов: exchange → user+model пары"""
        result = []
        for msg in self._get_history(chat_id):
            if msg.get("role") == "exchange":
                result.append({"role": "user", "content": msg["user"], "timestamp": msg.get("timestamp", 0)})
                result.append({"role": "model", "content": msg["model"], "timestamp": msg.get("timestamp", 0)})
            else:
                result.append(msg)
        return result

    def _get_msg_count(self, chat_id):
        """Считает количество реальных сообщений в истории (expanded)"""
        count = 0
        for msg in self._get_history(chat_id):
            if msg.get("role") == "exchange":
                count += 2  # user + model
            else:
                count += 1
        return count

    def _clear_chat_history(self, chat_id=None):
        if chat_id:
            cid = str(chat_id)
            if cid in self.history:
                del self.history[cid]
        else:
            self.history = {}
        self._save_db()

    def _get_provider_prompt(self, provider):
        prompts = self.db.get(self.strings["name"], "provider_prompts", {})
        return prompts.get(provider, self.config["system_instruction"])

    def _set_provider_prompt(self, provider, text):
        prompts = self.db.get(self.strings["name"], "provider_prompts", {})
        prompts[provider] = text
        self.db.set(self.strings["name"], "provider_prompts", prompts)

    def _extract_ai_flag(self, text):
        if "-ai" in text.lower():
            return re.sub(r"-ai\s*", "", text, flags=re.IGNORECASE).strip(), True
        return text, False

    def _format_res(self, text):
        """Форматирует текст ответа: сохраняет разрешённые HTML-теги, экранирует остальное"""
        if not text:
            return ""
        # 1) Вынимаем безопасные HTML-теги, заменяем плейсхолдерами
        placeholders = {}
        counter = [0]
        def _sub(m):
            key = f"\x00PH{counter[0]}\x00"
            placeholders[key] = m.group(0)
            counter[0] += 1
            return key
        safe_text = _SAFE_HTML_RE.sub(_sub, text)

        # 2) Экранируем весь остальной HTML
        escaped = utils.escape_html(safe_text)

        # 3) Возвращаем безопасные теги обратно
        for key, val in placeholders.items():
            escaped = escaped.replace(utils.escape_html(key), val)

        # 4) Блоки кода ```...```
        escaped = re.sub(
            r"```([a-zA-Z0-9_+\-]+)?\n(.*?)```",
            lambda m: f'<pre><code class="language-{m.group(1) or "text"}">{m.group(2)}</code></pre>',
            escaped, flags=re.DOTALL,
        )
        # 5) Инлайн-код `...`
        escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
        return escaped

    def _extract_code_file(self, text):
        match = re.search(r"```([a-zA-Z0-9_+\-]+)?\n(.*?)```", text, re.DOTALL)
        ext = (match.group(1) or "txt") if match else "txt"
        content = match.group(2).strip() if match else text.strip()
        ext_map = {"python": "py", "javascript": "js", "html": "html", "bash": "sh", "json": "json"}
        ext = ext_map.get(ext.lower(), ext.lower())
        f = io.BytesIO(content.encode("utf-8"))
        f.name = f"code.{ext}"
        return f

    # ─── FFmpeg ────────────────────────────────────────────────────────────

    @property
    def _ffmpeg_available(self):
        if self._ffmpeg_checked is None:
            try:
                r = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
                self._ffmpeg_checked = r.returncode == 0
            except Exception:
                self._ffmpeg_checked = False
        return self._ffmpeg_checked

    async def _extract_video_frames(self, video_bytes, fps=0.5, max_frames=5):
        """Извлекает кадры из видео через FFmpeg. Возвращает список (bytes, mime)."""
        if not self._ffmpeg_available:
            return []
        frames = []
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            with open(video_path, "wb") as vf:
                vf.write(video_bytes)
            frame_pattern = os.path.join(tmpdir, "frame_%03d.jpg")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-i", video_path, "-vf", f"fps={fps}",
                    "-frames:v", str(max_frames), "-q:v", "2",
                    frame_pattern,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.wait(), timeout=30)
            except Exception as e:
                logger.debug(f"FFmpeg frame extraction failed: {e}")
                return []
            for fname in sorted(os.listdir(tmpdir)):
                if fname.startswith("frame_") and fname.endswith(".jpg"):
                    with open(os.path.join(tmpdir, fname), "rb") as imgf:
                        frames.append((imgf.read(), "image/jpeg"))
        return frames

    # ─── распознавание людей ───────────────────────────────────────────────

    async def _get_person_info(self, user_id):
        """Получает полную информацию о пользователе: имя, юзернейм, био, канал, заметки."""
        try:
            full = await self.client(functions.users.GetFullUserRequest(user_id))
            user = full.users[0] if full.users else None
            if not user:
                return None
            info_parts = []
            first = getattr(user, "first_name", "") or ""
            last = getattr(user, "last_name", "") or ""
            name = f"{first} {last}".strip()
            if name:
                info_parts.append(f"Имя: {name}")
            username = getattr(user, "username", "")
            if username:
                info_parts.append(f"Юзернейм: @{username}")
            user_id_val = getattr(user, "id", "")
            if user_id_val:
                info_parts.append(f"ID: {user_id_val}")
            bio = getattr(full, "about", "") or ""
            if bio:
                info_parts.append(f"Био: {bio}")
            # Канал (если есть связанный)
            linked_chat = getattr(full, "personal_channel_id", None)
            if linked_chat:
                try:
                    ch = await self.client.get_entity(linked_chat)
                    ch_title = getattr(ch, "title", str(linked_chat))
                    ch_username = getattr(ch, "username", "")
                    ch_link = f"https://t.me/{ch_username}" if ch_username else str(linked_chat)
                    info_parts.append(f"Канал: {ch_title} ({ch_link})")
                except Exception:
                    info_parts.append(f"Канал ID: {linked_chat}")
            # Заметки (personal channel message)
            linked_msg = getattr(full, "personal_channel_message", None)
            if linked_msg:
                info_parts.append(f"Закреп в канале: ID сообщения {linked_msg}")
            # Общие чаты
            common = getattr(full, "common_chats_count", 0)
            if common:
                info_parts.append(f"Общих чатов: {common}")
            # Фото профиля
            photo = getattr(user, "photo", None)
            if photo:
                info_parts.append("Аватарка: есть")
            # Статус
            status = getattr(user, "status", None)
            if status:
                status_type = type(status).__name__
                if "Online" in status_type:
                    info_parts.append("Статус: онлайн")
                elif "Offline" in status_type:
                    info_parts.append("Статус: недавно был(а)")
                elif "Recently" in status_type:
                    info_parts.append("Статус: был(а) недавно")
            # Премиум
            premium = getattr(user, "premium", False)
            if premium:
                info_parts.append("Telegram Premium: да")
            # Верификация
            verified = getattr(user, "verified", False)
            if verified:
                info_parts.append("Верификация: да")
            return "\n".join(info_parts) if info_parts else None
        except Exception as e:
            logger.debug(f"Failed to get person info: {e}")
            return None

    # ─── провайдеры ──────────────────────────────────────────────────────────

    async def _call_openai_compat(self, url, api_key, model, prompt, hist, sys_prompt,
                                   image_bytes=None, mime_type=None):
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        messages = [{"role": "system", "content": sys_prompt}]
        for msg in hist:
            messages.append({"role": "assistant" if msg["role"] == "model" else "user",
                              "content": msg["content"]})
        user_content = prompt or "опиши это"
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode()
            user_content = [
                {"type": "text", "text": prompt or "опиши это"},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type or 'image/jpeg'};base64,{b64}"}},
            ]
        messages.append({"role": "user", "content": user_content})
        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(url, headers=headers,
                              json={"model": model, "messages": messages}) as resp:
                if resp.status != 200:
                    return f"ошибка {resp.status}: {await resp.text()}"
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def _call_openai(self, prompt, hist, model, key, sys, img=None, mime=None):
        return await self._call_openai_compat(
            "https://api.openai.com/v1/chat/completions", key, model, prompt, hist, sys, img, mime)

    async def _call_anthropic(self, prompt, hist, model, key, sys, img=None, mime=None):
        url = "https://api.anthropic.com/v1/messages"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        messages = []
        for msg in hist:
            messages.append({"role": "assistant" if msg["role"] == "model" else "user",
                              "content": msg["content"]})
        user_content = prompt or "опиши это"
        if img:
            b64 = base64.b64encode(img).decode()
            user_content = [
                {"type": "image", "source": {"type": "base64", "media_type": mime or "image/jpeg", "data": b64}},
                {"type": "text", "text": prompt or "опиши это"},
            ]
        messages.append({"role": "user", "content": user_content})
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.post(url, headers=headers,
                              json={"model": model, "max_tokens": 4096,
                                    "system": sys, "messages": messages}) as resp:
                if resp.status != 200:
                    return f"ошибка anthropic {resp.status}: {await resp.text()}"
                data = await resp.json()
                return data["content"][0]["text"]

    async def _call_gemini(self, prompt, hist, model, key, sys, img=None, mime=None):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        headers = {"Content-Type": "application/json"}
        contents = []
            
        for msg in hist:
            role = "model" if msg["role"] == "model" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            
        user_parts = [{"text": prompt or "опиши это"}]
        if img:
            b64 = base64.b64encode(img).decode('utf-8')
            user_parts.insert(0, {"inlineData": {"mimeType": mime or "image/jpeg", "data": b64}})
            
        contents.append({"role": "user", "parts": user_parts})

        body = {"contents": contents}
        if sys:
            body["systemInstruction"] = {"parts": [{"text": sys}]}
        
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.post(url, headers=headers, json=body) as resp:
                if resp.status != 200:
                    return f"ошибка api gemini: {await resp.text()}"
                data = await resp.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    return "ошибка парсинга ответа gemini"

    async def _call_gemini_hub(self, prompt, hist, model, key, sys, img=None, mime=None):
        """Gemini Hub — ТОЛЬКО ТЕКСТ. Не отправляет изображения, хаб их не поддерживает."""
        # Gemini Hub не поддерживает изображения — всегда только текст
        last_err = None
        for attempt in range(3):
            try:
                return await self._call_openai_compat(
                    "https://ai-model-hub--skberrghhh.replit.app/api/v1/chat/completions",
                    key, model, prompt, hist, sys, image_bytes=None, mime_type=None)
            except Exception as e:
                last_err = e
                if attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
        return f"ошибка gemini_hub (3 попытки): {last_err}"

    async def _call_deepseek(self, prompt, hist, model, key, sys, img=None, mime=None):
        return await self._call_openai_compat(
            "https://api.deepseek.com/v1/chat/completions", key, model, prompt, hist, sys, img, mime)

    async def _call_qwen(self, prompt, hist, model, key, sys, img=None, mime=None):
        return await self._call_openai_compat(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            key, model, prompt, hist, sys, img, mime)

    async def _call_openrouter(self, prompt, hist, model, key, sys, img=None, mime=None):
        return await self._call_openai_compat(
            "https://openrouter.ai/api/v1/chat/completions", key, model, prompt, hist, sys, img, mime)

    async def _call_codex(self, prompt, hist, model, key, sys, img=None, mime=None):
        return await self._call_openai_compat(
            "https://api.openai.com/v1/chat/completions", key, model, prompt, hist, sys, img, mime)
            
    async def _call_nvidia(self, prompt, hist, model, key, sys, img=None, mime=None):
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        return await self._call_openai_compat(url, key, model, prompt, hist, sys, img, mime)

    async def _call_custom(self, prompt, hist, model, key, url, sys, img=None, mime=None):
        return await self._call_openai_compat(url, key, model, prompt, hist, sys, img, mime)

    # ─── мультимедиа-анализ через Gemini ────────────────────────────────────

    async def _analyze_media_gemini(self, media_bytes, mime_type, prompt, key=None):
        """Отправляет медиа (видео, аудио, картинку) напрямую в Gemini API для анализа."""
        key = key or self.config.get("gemini_api_key")
        if not key:
            key = self.config.get("gemini_hub_api_key")
            if not key:
                return None, "нет ключа gemini_api_key или gemini_hub_api_key для анализа медиа"
            return await self._analyze_media_gemini_hub(media_bytes, mime_type, prompt, key)

        model = self.config.get("gemini_model", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
        b64 = base64.b64encode(media_bytes).decode('utf-8')
        body = {
            "contents": [{
                "parts": [
                    {"inlineData": {"mimeType": mime_type, "data": b64}},
                    {"text": prompt or "Опиши что здесь происходит"},
                ]
            }]
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.post(url, headers={"Content-Type": "application/json"}, json=body) as resp:
                if resp.status != 200:
                    return None, f"ошибка gemini media {resp.status}: {await resp.text()}"
                data = await resp.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"], None
                except Exception:
                    return None, "ошибка парсинга ответа gemini media"

    async def _analyze_media_gemini_hub(self, media_bytes, mime_type, prompt, key=None):
        """Отправляет медиа через Gemini Hub (OpenAI-совместимый API)."""
        key = key or self.config.get("gemini_hub_api_key")
        if not key:
            return None, "нет ключа gemini_hub_api_key"

        model = self.config.get("gemini_hub_model", "gemini-2.5-pro")
        url = "https://ai-model-hub--skberrghhh.replit.app/api/v1/chat/completions"
        b64 = base64.b64encode(media_bytes).decode()
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt or "Опиши что здесь происходит"},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            ]
        }]
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.post(url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages}) as resp:
                if resp.status != 200:
                    return None, f"ошибка hub media {resp.status}: {await resp.text()}"
                data = await resp.json()
                try:
                    return data["choices"][0]["message"]["content"], None
                except Exception:
                    return None, "ошибка парсинга ответа hub media"

    # ─── транскрипция через Whisper ─────────────────────────────────────────

    async def _transcribe_whisper(self, audio_bytes, key=None):
        """Транскрибирует аудио через OpenAI Whisper API."""
        key = key or self.config.get("openai_api_key")
        if not key:
            return None, "нет openai_api_key для Whisper"
        url = "https://api.openai.com/v1/audio/transcriptions"
        f = io.BytesIO(audio_bytes)
        f.name = "audio.ogg"
        data = aiohttp.FormData()
        data.add_field("file", f, filename="audio.ogg", content_type="audio/ogg")
        data.add_field("model", "whisper-1")
        data.add_field("language", "ru")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.post(url,
                headers={"Authorization": f"Bearer {key}"},
                data=data) as resp:
                if resp.status != 200:
                    return None, f"ошибка whisper {resp.status}: {await resp.text()}"
                result = await resp.json()
                return result.get("text", ""), None

    # ─── картинки ────────────────────────────────────────────────────────────

    async def _call_openai_image(self, prompt, key, model):
        url = "https://api.openai.com/v1/images/generations"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {"prompt": prompt, "model": model, "n": 1, "size": "1024x1024"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            async with s.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    return None, f"ошибка openai image: {await resp.text()}"
                data = await resp.json()
                img_url = data["data"][0].get("url")
                if not img_url:
                    return None, "апишка не отдала ссылку на картинку"
            async with s.get(img_url) as img_resp:
                if img_resp.status == 200:
                    return await img_resp.read(), None
                return None, f"ошибка скачивания картинки: {img_resp.status}"

    async def _call_gemini_image(self, prompt, key):
        model = self.config.get("gemini_image_model", "imagen-3.0-generate-001")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={key}"
        headers = {"Content-Type": "application/json"}
        payload = {"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1}}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    return None, f"ошибка api imagen: {await resp.text()}"
                data = await resp.json()
                try:
                    b64_img = data["predictions"][0]["bytesBase64Encoded"]
                    return base64.b64decode(b64_img), None
                except Exception as e:
                    return None, f"ошибка парсинга картинки imagen: {e}"

    async def _call_gemini_hub_image(self, prompt, key):
        model = self.config.get("gemini_hub_image_model", "gemini-2.5-flash-image")

        # ─── Модели с нативной генерацией картинок через чат ─────────────────
        if model in CHAT_IMAGE_MODELS:
            return await self._call_gemini_hub_chat_image(prompt, key, model)

        # ─── Стандартные модели через /images/generations ────────────────────
        url = "https://ai-model-hub--skberrghhh.replit.app/api/v1/images/generations"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    return None, f"ошибка hub imagen: {await resp.text()}"
                data = await resp.json()
                try:
                    item = data["data"][0]
                    if item.get("b64_json"):
                        return base64.b64decode(item["b64_json"]), None
                    if item.get("url"):
                        async with session.get(item["url"]) as r:
                            if r.status == 200:
                                return await r.read(), None
                except Exception:
                    pass
                return None, "хаб не отдал картинку"

    async def _call_gemini_hub_chat_image(self, prompt, key, model):
        """Генерация картинок через чат-комплитины (нативная генерация модели).
        Модели вроде gemini-2.0-flash-exp и gemini-2.5-pro умеют рисовать
        прямо в чате — отправляем промпт, получаем картинку в ответе."""
        url = "https://ai-model-hub--skberrghhh.replit.app/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        messages = [
            {"role": "system", "content": "You are an image generation assistant. Generate images based on user descriptions. Always output the image directly."},
            {"role": "user", "content": f"Generate an image: {prompt}"},
        ]
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 4096,
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=180)) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    return None, f"ошибка hub chat image ({model}): {await resp.text()}"
                data = await resp.json()
                try:
                    content = data["choices"][0]["message"]["content"]

                    # 1) Пробуем извлечь base64 из контента
                    b64_match = re.search(r'data:image/[a-zA-Z+]+;base64,([A-Za-z0-9+/=]+)', content)
                    if b64_match:
                        return base64.b64decode(b64_match.group(1)), None

                    # 2) Пробуем извлечь чистый base64 (без data URI)
                    # Ищем длинные base64-строки (минимум 100 символов — явно картинка)
                    b64_candidates = re.findall(r'([A-Za-z0-9+/]{100,}={0,2})', content)
                    for candidate in b64_candidates:
                        try:
                            decoded = base64.b64decode(candidate)
                            # Проверяем что это реально картинка (PNG/JPEG/WEBP заголовки)
                            if decoded[:4] == b'\x89PNG' or decoded[:2] == b'\xff\xd8' or decoded[:4] == b'RIFF':
                                return decoded, None
                        except Exception:
                            continue

                    # 3) Пробуем извлечь URL картинки из ответа
                    url_match = re.search(r'(https?://[^\s"<>]+\.(?:png|jpg|jpeg|webp|gif)[^\s"<>]*)', content, re.IGNORECASE)
                    if url_match:
                        img_url = url_match.group(1)
                        async with session.get(img_url) as r:
                            if r.status == 200:
                                return await r.read(), None

                    # 4) Проверяем есть ли inline_data в ответе (OpenAI-совместимый формат)
                    for choice in data.get("choices", []):
                        msg = choice.get("message", {})
                        # Проверяем мультимодальный контент (список частей)
                        if isinstance(msg.get("content"), list):
                            for part in msg["content"]:
                                if isinstance(part, dict):
                                    img_data = part.get("image_url", {}).get("url") or part.get("image", {}).get("data")
                                    if img_data:
                                        if img_data.startswith("data:"):
                                            b64_part = img_data.split(",", 1)[1]
                                            return base64.b64decode(b64_part), None
                                        async with session.get(img_data) as r:
                                            if r.status == 200:
                                                return await r.read(), None

                    return None, f"модель {model} не сгенерировала картинку (текстовый ответ)"
                except Exception as e:
                    return None, f"ошибка парсинга chat image ({model}): {e}"

    # ─── вызов провайдера ────────────────────────────────────────────────────

    async def _call_provider_api(self, provider, prompt, hist, sys_prompt,
                                  image_bytes=None, mime_type=None):
        p = provider
        if p == "openai":
            k = self.config["openai_api_key"]
            if not k: return "укажите openai_api_key"
            return await self._call_openai(prompt, hist, self.config["openai_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "anthropic":
            k = self.config["anthropic_api_key"]
            if not k: return "укажите anthropic_api_key"
            return await self._call_anthropic(prompt, hist, self.config["anthropic_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "gemini":
            k = self.config["gemini_api_key"]
            if not k: return "укажите gemini_api_key"
            return await self._call_gemini(prompt, hist, self.config["gemini_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "gemini_hub":
            k = self.config["gemini_hub_api_key"]
            if not k: return "укажите gemini_hub_api_key"
            return await self._call_gemini_hub(prompt, hist, self.config["gemini_hub_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "deepseek":
            k = self.config["deepseek_api_key"]
            if not k: return "укажите deepseek_api_key"
            return await self._call_deepseek(prompt, hist, self.config["deepseek_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "qwen":
            k = self.config["qwen_api_key"]
            if not k: return "укажите qwen_api_key"
            return await self._call_qwen(prompt, hist, self.config["qwen_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "openrouter":
            k = self.config["openrouter_api_key"]
            if not k: return "укажите openrouter_api_key"
            return await self._call_openrouter(prompt, hist, self.config["openrouter_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "codex":
            k = self.config["codex_api_key"]
            if not k: return "укажите codex_api_key"
            return await self._call_codex(prompt, hist, self.config["codex_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "nvidia":
            k = self.config["nvidia_api_key"]
            if not k: return "укажите nvidia_api_key"
            return await self._call_nvidia(prompt, hist, self.config["nvidia_model"], k, sys_prompt, image_bytes, mime_type)
        if p == "custom":
            k = self.config["custom_api_key"]
            url = self.config["custom_base_url"]
            if not url: return "укажите custom_base_url"
            return await self._call_custom(prompt, hist, self.config["custom_model"], k, url, sys_prompt, image_bytes, mime_type)
        return f"неизвестный провайдер: {provider}"

    # ─── агент: обработка тулов ──────────────────────────────────────────────

    async def _resolve_target(self, target_str):
        target = target_str.strip()
        if target.lstrip("-").isdigit():
            target = int(target)
        try:
            return await self.client.get_input_entity(target)
        except Exception:
            e = await self.client.get_entity(target)
            return await self.client.get_input_entity(e)

    async def _execute_tools(self, text, message=None):
        """Выполняет все TOOL-теги в тексте, возвращает (clean_text, results_list, has_tools)"""
        logs = []
        has_tools = False

        # send
        for target, msg_text in re.findall(r"<TOOL:send:([^|>]+)\|([^>]+)>", text):
            has_tools = True
            try:
                entity = await self._resolve_target(target)
                await self.client.send_message(entity, msg_text.strip())
                # Запоминаем диалог для отслеживания ответов
                try:
                    eid = getattr(entity, "user_id", None) or getattr(entity, "chat_id", None) or getattr(entity, "channel_id", None)
                    if eid:
                        self._tracked_dialogs.add(eid)
                except Exception:
                    pass
                logs.append(f"✅ send → {target}: отправлено")
            except Exception as e:
                logs.append(f"❌ send → {target}: {e}")

        # send_multi — несколько сообщений подряд
        for target, msgs_raw in re.findall(r"<TOOL:send_multi:([^|>]+)\|([^>]+)>", text):
            has_tools = True
            parts = [p.strip() for p in msgs_raw.split("||") if p.strip()]
            for part in parts:
                try:
                    entity = await self._resolve_target(target)
                    await self.client.send_message(entity, part)
                    try:
                        eid = getattr(entity, "user_id", None) or getattr(entity, "chat_id", None) or getattr(entity, "channel_id", None)
                        if eid:
                            self._tracked_dialogs.add(eid)
                    except Exception:
                        pass
                    logs.append(f"✅ send_multi → {target}: {part[:60]}")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logs.append(f"❌ send_multi → {target}: {e}")

        # set_name — сменить имя/фамилию
        for name_raw in re.findall(r"<TOOL:set_name:([^>]+)>", text):
            has_tools = True
            try:
                parts = name_raw.strip().split("|", 1)
                first = parts[0].strip()
                last = parts[1].strip() if len(parts) > 1 else ""
                await self.client(functions.account.UpdateProfileRequest(
                    first_name=first, last_name=last
                ))
                self.me = await self.client.get_me()
                logs.append(f"✅ set_name: имя изменено на «{(first + ' ' + last).strip()}»")
            except Exception as e:
                logs.append(f"❌ set_name: {e}")

        # set_bio — сменить о себе
        for bio_text in re.findall(r"<TOOL:set_bio:([^>]+)>", text):
            has_tools = True
            try:
                await self.client(functions.account.UpdateProfileRequest(about=bio_text.strip()))
                logs.append(f"✅ set_bio: bio изменено")
            except Exception as e:
                logs.append(f"❌ set_bio: {e}")

        # set_username — сменить юзернейм
        for uname in re.findall(r"<TOOL:set_username:([^>]+)>", text):
            has_tools = True
            try:
                uname_clean = uname.strip().lstrip("@")
                await self.client(functions.account.UpdateUsernameRequest(username=uname_clean))
                logs.append(f"✅ set_username: @{uname_clean}")
            except Exception as e:
                logs.append(f"❌ set_username: {e}")

        # delete
        for del_t in re.findall(r"<TOOL:delete:([^>]+)>", text):
            has_tools = True
            try:
                if del_t.lower() == "reply" and message and message.reply_to_msg_id:
                    await self.client.delete_messages(message.chat_id, [message.reply_to_msg_id])
                    logs.append("✅ delete: реплай удалён")
                elif del_t.isdigit() and message:
                    await self.client.delete_messages(message.chat_id, [int(del_t)])
                    logs.append(f"✅ delete: сообщение {del_t} удалено")
                else:
                    logs.append(f"❌ delete: не могу удалить '{del_t}'")
            except Exception as e:
                logs.append(f"❌ delete: {e}")

        # block
        for b_t in re.findall(r"<TOOL:block:([^>]+)>", text):
            has_tools = True
            try:
                entity = await self._resolve_target(b_t)
                from telethon import functions as tfn
                await self.client(tfn.contacts.BlockRequest(id=entity))
                logs.append(f"✅ block: {b_t} заблокирован")
            except Exception as e:
                logs.append(f"❌ block → {b_t}: {e}")

        # unblock
        for ub_t in re.findall(r"<TOOL:unblock:([^>]+)>", text):
            has_tools = True
            try:
                entity = await self._resolve_target(ub_t)
                from telethon import functions as tfn
                await self.client(tfn.contacts.UnblockRequest(id=entity))
                logs.append(f"✅ unblock: {ub_t} разблокирован")
            except Exception as e:
                logs.append(f"❌ unblock → {ub_t}: {e}")

        # search — реальный веб-поиск
        for sq in re.findall(r"<TOOL:search:([^>]+)>", text):
            has_tools = True
            try:
                results = await self._web_search(sq.strip(), max_results=5)
                if results:
                    snippets = "\n".join(
                        f"[{i}] {r['title']}: {r['snippet']}" + (f" ({r['url']})" if r.get('url') else "")
                        for i, r in enumerate(results, 1)
                    )
                    logs.append(f"🔍 search '{sq}':\n{snippets[:800]}")
                else:
                    logs.append(f"🔍 search '{sq}': ничего не найдено")
            except Exception as se:
                logs.append(f"🔍 search '{sq}': ошибка — {se}")

        # analyze_chat
        for ac in re.findall(r"<TOOL:analyze_chat:(\d+)>", text):
            has_tools = True
            try:
                n = min(int(ac), 100)
                msgs = []
                async for m in self.client.iter_messages(message.chat_id if message else "me", limit=n):
                    if m.text:
                        sender = getattr(m.sender, "username", None) or str(getattr(m.sender, "id", "?"))
                        msgs.append(f"{sender}: {m.text[:80]}")
                summary = "\n".join(msgs[-20:])
                logs.append(f"📊 analyze_chat ({n} сообщ.):\n{summary}")
            except Exception as e:
                logs.append(f"❌ analyze_chat: {e}")

        # createskill — создать/сохранить скилл
        for skill_raw in re.findall(r"<TOOL:createskill:([^|>]+)\|([^>]+)>", text):
            has_tools = True
            skill_name, skill_prompt = skill_raw[0].strip(), skill_raw[1].strip()
            try:
                self.skills[skill_name] = skill_prompt
                self._save_db()
                logs.append(f"✅ createskill: скилл «{skill_name}» сохранён ({len(skill_prompt)} симв.)")
            except Exception as e:
                logs.append(f"❌ createskill: {e}")

        # improveself_prompt — улучшить системный промпт текущего провайдера через ИИ
        for improve_instr in re.findall(r"<TOOL:improveself_prompt:([^>]+)>", text):
            has_tools = True
            try:
                provider = self.config["active_provider"]
                cur_prompt = self._get_provider_prompt(provider)
                meta_prompt = (
                    f"Вот текущий системный промпт ИИ-бота:\n\n{cur_prompt}\n\n"
                    f"Улучши его согласно инструкции: {improve_instr.strip()}\n\n"
                    "Верни ТОЛЬКО новый улучшенный промпт, без пояснений."
                )
                new_prompt = await self._call_provider_api(
                    provider, meta_prompt, [], "Ты эксперт по промпт-инженерии.")
                if new_prompt and not new_prompt.startswith("укажите"):
                    self._set_provider_prompt(provider, new_prompt)
                    logs.append(f"✅ improveself_prompt: промпт провайдера «{provider}» обновлён")
                else:
                    logs.append(f"❌ improveself_prompt: ошибка генерации — {new_prompt}")
            except Exception as e:
                logs.append(f"❌ improveself_prompt: {e}")

        # eval_js — выполнение JavaScript-кода через Node.js
        # Поддерживаем два формата:
        # 1) <TOOL:eval_js:код> — для простого кода без угловых скобок
        # 2) <TOOL:eval_js>\nкод\n</TOOL:eval_js> — для сложного кода
        js_snippets = []
        # Формат 2: блочный тег
        for js_code in re.findall(r"<TOOL:eval_js>(.*?)</TOOL:eval_js>", text, re.DOTALL):
            js_snippets.append(js_code.strip())
        # Формат 1: инлайн (без > внутри)
        for js_code in re.findall(r"<TOOL:eval_js:([^>]+)>", text):
            js_snippets.append(js_code.strip())

        for js_code in js_snippets:
            has_tools = True
            try:
                # Оборачиваем чтобы поддержать return и top-level await
                wrapped = (
                    "(async () => { try { const __fn = async () => {\n"
                    + js_code
                    + "\n}; const __v = await __fn(); "
                    "if (__v !== undefined) process.stdout.write(JSON.stringify(__v, null, 2) + '\\n'); "
                    "} catch(e) { process.stderr.write('JS_ERR: ' + e.message + '\\n'); } })()"
                )
                proc = await asyncio.create_subprocess_exec(
                    "node", "--input-type=module",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(wrapped.encode()), timeout=15)
                except asyncio.TimeoutError:
                    try: proc.kill()
                    except Exception: pass
                    logs.append("❌ eval_js: таймаут (15 сек)")
                    continue
                out = stdout.decode().strip()
                err_out = stderr.decode().strip()
                if out:
                    logs.append(f"✅ eval_js:\n{out[:800]}")
                elif err_out:
                    logs.append(f"⚠️ eval_js stderr:\n{err_out[:400]}")
                else:
                    logs.append("✅ eval_js: выполнено (нет вывода)")
            except FileNotFoundError:
                logs.append("❌ eval_js: Node.js не установлен")
            except Exception as e:
                logs.append(f"❌ eval_js: {e}")

        clean = re.sub(r"<TOOL:eval_js>.*?</TOOL:eval_js>", "", text, flags=re.DOTALL)
        clean = re.sub(r"<TOOL:[^>]+>", "", clean).strip()
        return clean, logs, has_tools

    # ─── агентный цикл ───────────────────────────────────────────────────────

    async def _run_agent_loop(self, provider, prompt, chat_id, message,
                               override_sys=None, needs_file=False,
                               image_bytes=None, mime_type=None,
                               status_msg=None):
        sys_prompt = override_sys or self._get_provider_prompt(provider)

        if self.config["agent_mode"] and not override_sys:
            sys_prompt += "\n\n" + AGENT_TOOLS_SYSTEM

        if needs_file:
            sys_prompt += "\n\nВыдай готовый код, обёрнутый в ``` с указанием языка."

        # Разворачиваем историю для API (exchange → user+model пары)
        hist = self._get_history_expanded(chat_id) if (not override_sys and chat_id is not None) else []
        # Рабочая копия для контекста API — промежуточные шаги НЕ сохраняются в БД
        working_hist = list(hist)

        current_prompt = prompt
        final_res = ""
        all_step_logs = []
        max_steps = int(self.config["agent_max_steps"]) if self.config["agent_mode"] else 1

        for step_num in range(1, max_steps + 1):
            # обновляем статус с номером шага
            if status_msg and step_num > 1:
                try:
                    await utils.answer(
                        status_msg,
                        f"<tg-emoji emoji-id=5776213190387961618>🕓</tg-emoji> "
                        f"<b>Шаг {step_num}/{max_steps}...</b>",
                    )
                except Exception:
                    pass

            img = image_bytes if step_num == 1 else None
            mime = mime_type if step_num == 1 else None

            res = await self._call_provider_api(provider, current_prompt, working_hist, sys_prompt, img, mime)

            # Добавляем обмен в рабочий контекст (НЕ в БД — API-функция уже добавляет промпт)
            if not override_sys and chat_id is not None:
                working_hist.append({"role": "user", "content": current_prompt})
                working_hist.append({"role": "model", "content": res})

            if not self.config["agent_mode"] or override_sys:
                final_res = res
                break

            clean_text, step_logs, has_tools = await self._execute_tools(res, message)

            if step_logs:
                formatted = "\n".join(f"  {l}" for l in step_logs)
                all_step_logs.append(f"— Шаг {step_num}\n{formatted}")

            if not has_tools:
                final_res = clean_text or res
                break

            # готовим следующий промпт для модели
            tool_result = "\n".join(step_logs)
            current_prompt = (
                f"[Результаты шага {step_num}]\n{tool_result}\n\n"
                "Продолжай выполнение или завершай ответ пользователю."
            )

            final_res = clean_text or res

        # Сохраняем в историю ОДИН обмен (user+model) вместо 2+ записей
        if not override_sys and chat_id is not None:
            self._add_exchange_to_history(chat_id, prompt, final_res)

        agent_report = ""
        if all_step_logs and self.config.get("show_agent_steps", True):
            steps_text = "\n\n".join(all_step_logs)
            # Ограничиваем отчёт агента до 350 символов
            if len(steps_text) > 350:
                steps_text = steps_text[:347] + "..."
            agent_report = (
                "<tg-emoji emoji-id=5985780596268339498>🤖</tg-emoji> "
                "<b>Отчёт агента:</b>\n"
                f"<blockquote expandable>{utils.escape_html(steps_text)}</blockquote>"
            )

        return final_res, agent_report

    # ─── инлайн кнопки ──────────────────────────────────────────────────────

    def _ai_buttons(self, provider, chat_id, prompt, model_name):
        short_model = model_name[:22] if model_name else provider
        return [
            [
                {"text": "🔄 Повторить", "callback": self._regen_cb,
                 "args": (provider, str(chat_id), prompt[:500])},
                {"text": "🧹 Сброс памяти", "callback": self._reset_cb,
                 "args": (str(chat_id),)},
            ],
            [
                {"text": f"🤖 {short_model}", "callback": self._switch_model_inline_cb,
                 "args": (provider,)},
                {"text": "🔀 Провайдер", "callback": self._switch_provider_cb, "args": ()},
            ],
        ]

    def _img_buttons(self, provider, prompt):
        img_model = self.config.get(f"{provider}_image_model", "—")
        short_img_model = img_model[:20] if img_model else "—"
        return [
            [
                {"text": "🔄 Перегенерировать", "callback": self._regen_img_cb,
                 "args": (provider, prompt[:300])},
                {"text": "🔀 Провайдер", "callback": self._switch_img_provider_cb, "args": ()},
            ],
            [
                {"text": f"🖼 {short_img_model}", "callback": self._switch_img_model_inline_cb,
                 "args": (provider,)},
            ],
        ]

    async def _try_inline(self, message, text, buttons):
        """Пробуем инлайн, фолбек — обычный ответ. Кэширует чаты без инлайна."""
        chat_id = getattr(message, "chat_id", None)
        if chat_id and str(chat_id) in self._no_inline_chats:
            return await utils.answer(message, text)
        try:
            await self.inline.form(message=message, text=text, reply_markup=buttons)
        except Exception:
            if chat_id:
                self._no_inline_chats.add(str(chat_id))
            await utils.answer(message, text)

    async def _safe_inline(self, message, text, buttons=None, *, always_text=True):
        """Универсальный инлайн с автозапоминанием чатов без инлайна.
        Если buttons=None — пишет обычным сообщением.
        Если always_text=True — при недоступности инлайна отправит текст без кнопок."""
        chat_id = getattr(message, "chat_id", None)
        cid = str(chat_id) if chat_id else None

        # Кнопок нет — просто текст
        if not buttons:
            return await utils.answer(message, text)

        # Уже знаем что инлайн не работает в этом чате
        if cid and cid in self._no_inline_chats:
            return await utils.answer(message, text)

        try:
            await self.inline.form(message=message, text=text, reply_markup=buttons)
        except Exception:
            if cid:
                self._no_inline_chats.add(cid)
            if always_text:
                await utils.answer(message, text)

    # ── коллбеки ─────────────────────────────────────────────────────────────

    async def _regen_cb(self, call: InlineCall, provider: str, chat_id: str, prompt: str):
        await call.edit(
            "<tg-emoji emoji-id=5776213190387961618>🕓</tg-emoji> <b>Регенерирую...</b>",
            reply_markup=None,
        )
        try:
            sys_prompt = self._get_provider_prompt(provider)
            hist = self._get_history_expanded(chat_id)
            if hist and hist[-1]["role"] == "model":
                hist = hist[:-1]
            res = await self._call_provider_api(provider, prompt, hist, sys_prompt)
            self._add_exchange_to_history(chat_id, prompt, res)
            model_name = self.config.get(f"{provider}_model", provider)
            msg_count = self._get_msg_count(chat_id)
            exchanges = len(self._get_history(chat_id))
            meta = f"🗜 [{exchanges}/{self.config['max_history_length']}] {model_name} | 🔄 рег."
            final_text = (
                f"<i>{utils.escape_html(meta)}</i>\n\n"
                f"💬 <b>Запрос:</b>\n<blockquote>{utils.escape_html(prompt[:500])}</blockquote>\n\n"
                f"✨ <b>{provider.upper()}:</b>\n<blockquote expandable>{self._format_res(res)}</blockquote>"
            )
            await call.edit(final_text, reply_markup=self._ai_buttons(provider, chat_id, prompt, model_name))
        except Exception as e:
            await call.edit(self.strings["error"].format(str(e)), reply_markup=None)

    async def _reset_cb(self, call: InlineCall, chat_id: str):
        self._clear_chat_history(chat_id)
        await call.answer("🧹 Память очищена!", show_alert=False)
        provider = self.config["active_provider"]
        model_name = self.config.get(f"{provider}_model", provider)
        max_len = self.config["max_history_length"]
        meta = f"🗜 [0/{self.config['max_history_length']}] {model_name} | 🧹 память сброшена"
        try:
            await call.edit(
                f"<i>{utils.escape_html(meta)}</i>\n\n"
                f"🧹 <b>Память чата очищена.</b>",
                reply_markup=self._ai_buttons(provider, chat_id, "", model_name),
            )
        except Exception:
            pass

    async def _switch_model_inline_cb(self, call: InlineCall, provider: str):
        models = PROVIDER_MODELS.get(provider, [])
        if not models:
            return await call.answer("Нет моделей", show_alert=True)
        btns = []
        row = []
        for m in models:
            row.append({"text": m, "callback": self._set_model_cb, "args": (provider, m)})
            if len(row) == 2:
                btns.append(row); row = []
        if row: btns.append(row)
        btns.append([{"text": "◀️ Назад", "callback": self._close_menu_cb, "args": ()}])
        await call.edit(
            f"<b>Модели {provider.upper()}:</b>",
            reply_markup=btns,
        )

    async def _set_model_cb(self, call: InlineCall, provider: str, model: str):
        self.config[f"{provider}_model"] = model
        await call.answer(f"✅ {model}", show_alert=False)
        await call.edit(
            f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
            f"<b>Модель:</b> <code>{model}</code>",
            reply_markup=[[{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}]],
        )

    async def _switch_provider_cb(self, call: InlineCall):
        current = self.config["active_provider"]
        providers = list(PROVIDER_MODELS.keys())
        btns = []
        row = []
        for p in providers:
            mark = "✅ " if p == current else ""
            row.append({"text": f"{mark}{p}", "callback": self._set_provider_cb, "args": (p,)})
            if len(row) == 2:
                btns.append(row); row = []
        if row: btns.append(row)
        btns.append([{"text": "◀️ Назад", "callback": self._close_menu_cb, "args": ()}])
        await call.edit(
            f"<b>Выберите провайдера:</b>\nТекущий: <code>{current}</code>",
            reply_markup=btns,
        )

    async def _set_provider_cb(self, call: InlineCall, provider: str):
        self.config["active_provider"] = provider
        model_name = self.config.get(f"{provider}_model", provider)
        await call.answer(f"✅ {provider}", show_alert=False)
        await call.edit(
            f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
            f"<b>Провайдер:</b> <code>{provider}</code>",
            reply_markup=self._ai_buttons(provider, "", "", model_name),
        )

    async def _regen_img_cb(self, call: InlineCall, provider: str, prompt: str):
        await call.answer("🎨 Запускаю...", show_alert=False)
        try:
            if provider == "openai":
                key = self.config.get("openai_api_key")
                if not key: return await call.answer("укажите openai_api_key", show_alert=True)
                img_bytes, err = await self._call_openai_image(prompt, key, self.config["openai_image_model"])
            elif provider == "gemini":
                key = self.config.get("gemini_api_key")
                if not key: return await call.answer("укажите gemini_api_key", show_alert=True)
                img_bytes, err = await self._call_gemini_image(prompt, key)
            elif provider == "gemini_hub":
                key = self.config.get("gemini_hub_api_key")
                if not key: return await call.answer("укажите gemini_hub_api_key", show_alert=True)
                img_bytes, err = await self._call_gemini_hub_image(prompt, key)
            else:
                return await call.answer(f"Провайдер {provider} не поддерживается", show_alert=True)
            if err:
                try:
                    safe_prompt = urllib.parse.quote(prompt)
                    url = f"https://image.pollinations.ai/prompt/{safe_prompt}?nologo=true"
                    async with aiohttp.ClientSession() as s:
                        async with s.get(url) as r:
                            if r.status == 200:
                                img_bytes = await r.read()
                                err = None
                            else:
                                err = "резервный сервер тоже пошел по пизде"
                except Exception as fb_err:
                    err = f"ошибка резерва: {fb_err}"

            if err:
                return await call.answer(f"Ошибка: {err}", show_alert=True)
                
            f = io.BytesIO(img_bytes); f.name = "image.png"
            chat_id = getattr(call, "chat_id", None)
            img_model_name = self.config.get(f"{provider}_image_model", provider)
            gen_method = "чат" if img_model_name in CHAT_IMAGE_MODELS else "imagen"
            if chat_id:
                await self.client.send_file(
                    chat_id, f,
                    caption=f"🔄 <b>{provider.upper()}</b> | <code>{img_model_name}</code> [{gen_method}]\n<blockquote>{utils.escape_html(prompt[:300])}</blockquote>",
                )
        except Exception as e:
            await call.answer(f"Ошибка: {e}", show_alert=True)

    async def _switch_img_provider_cb(self, call: InlineCall):
        current = self.config["image_provider"]
        btns = []
        row = []
        for p in ["openai", "gemini", "gemini_hub"]:
            row.append({"text": ("✅ " if p == current else "") + p,
                        "callback": self._set_img_provider_cb, "args": (p,)})
            if len(row) == 2:
                btns.append(row); row = []
        if row: btns.append(row)
        btns.append([{"text": "◀️ Назад", "callback": self._close_menu_cb, "args": ()}])
        await call.edit(f"<b>Провайдер картинок:</b> <code>{current}</code>", reply_markup=btns)

    async def _set_img_provider_cb(self, call: InlineCall, provider: str):
        self.config["image_provider"] = provider
        await call.answer(f"✅ {provider}", show_alert=False)
        await call.edit(
            f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
            f"<b>Провайдер картинок:</b> <code>{provider}</code>",
            reply_markup=self._img_buttons(provider, ""),
        )

    async def _switch_img_model_inline_cb(self, call: InlineCall, provider: str):
        """Показывает список моделей картинок для выбранного провайдера"""
        models = IMAGE_MODELS.get(provider, [])
        if not models:
            return await call.answer("Нет моделей картинок для этого провайдера", show_alert=True)
        btns = []
        row = []
        for m in models:
            current = self.config.get(f"{provider}_image_model", "")
            mark = "✅ " if m == current else ""
            row.append({"text": f"{mark}{m}", "callback": self._set_img_model_cb, "args": (provider, m)})
            if len(row) == 2:
                btns.append(row); row = []
        if row: btns.append(row)
        btns.append([{"text": "◀️ Назад", "callback": self._close_menu_cb, "args": ()}])
        await call.edit(
            f"<b>Модели картинок {provider.upper()}:</b>",
            reply_markup=btns,
        )

    async def _set_img_model_cb(self, call: InlineCall, provider: str, model: str):
        """Устанавливает модель картинок — РЕАЛЬНО меняет модель в API"""
        self.config[f"{provider}_image_model"] = model
        await call.answer(f"✅ Модель картинок: {model}", show_alert=False)
        await call.edit(
            f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
            f"<b>Модель картинок {provider.upper()}:</b> <code>{model}</code>",
            reply_markup=[[{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}]],
        )

    async def _close_menu_cb(self, call: InlineCall):
        await call.delete()

    async def _confirm_reset_cb(self, call: InlineCall, chat_id: str, all_chats: bool):
        if all_chats:
            self._clear_chat_history()
            await call.edit("🧹 <b>Вся память очищена!</b>", reply_markup=None)
        else:
            self._clear_chat_history(chat_id)
            await call.edit("🧹 <b>Память чата очищена!</b>", reply_markup=None)

    # ─── инлайн конфиг ───────────────────────────────────────────────────────

    async def _cfg_main_menu(self, call_or_msg, edit=True):
        providers = list(PROVIDER_MODELS.keys())
        btns = []
        row = []
        for p in providers:
            has_key = bool(self.config.get(f"{p}_api_key", ""))
            mark = "🟢" if has_key else "🔴"
            row.append({"text": f"{mark} {p}", "callback": self._cfg_provider_menu_cb, "args": (p,)})
            if len(row) == 2:
                btns.append(row); row = []
        if row: btns.append(row)
        btns.append([
            {"text": "⚙️ Общие", "callback": self._cfg_general_cb, "args": ()},
            {"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()},
        ])
        text = (
            "⚙️ <b>AIRoute — Конфигурация</b>\n\n"
            "🟢 ключ задан  |  🔴 не задан\n\n"
            f"Текст: <code>{self.config['active_provider']}</code>  "
            f"Фото: <code>{self.config['image_provider']}</code>"
        )
        if edit and hasattr(call_or_msg, "edit"):
            await call_or_msg.edit(text, reply_markup=btns)
        else:
            await self._safe_inline(call_or_msg, text, btns)

    async def _cfg_provider_menu_cb(self, call: InlineCall, provider: str):
        key = self.config.get(f"{provider}_api_key", "")
        model = self.config.get(f"{provider}_model", "—")
        key_display = (key[:6] + "..." + key[-4:]) if len(key) > 10 else ("задан" if key else "не задан")
        text = (
            f"⚙️ <b>{provider.upper()}</b>\n\n"
            f"🔑 Ключ: <code>{key_display}</code>\n"
            f"🤖 Модель: <code>{model}</code>"
        )
        btns = [
            [
                {"text": "🔑 Задать ключ", "callback": self._cfg_set_key_prompt_cb, "args": (provider,)},
                {"text": "🤖 Модель", "callback": self._switch_model_inline_cb, "args": (provider,)},
            ],
            [
                {"text": "✏️ Промпт", "callback": self._cfg_set_prompt_cb, "args": (provider,)},
                {"text": "🗑 Удалить ключ", "callback": self._cfg_clear_key_cb, "args": (provider,)},
            ],
        ]
        if provider in ("openai", "gemini", "gemini_hub"):
            img_model = self.config.get(f"{provider}_image_model", "—")
            text += f"\n🖼 Модель картинок: <code>{img_model}</code>"
            btns.insert(1, [
                {"text": f"🖼 Модель картинок", "callback": self._switch_img_model_inline_cb, "args": (provider,)},
            ])
        btns.append([{"text": "◀️ Назад", "callback": self._cfg_back_cb, "args": ()}])
        await call.edit(text, reply_markup=btns)

    async def _cfg_set_key_prompt_cb(self, call: InlineCall, provider: str):
        await call.answer(f"Введи: .acfg {provider} api_key <ключ>", show_alert=True)

    async def _cfg_set_prompt_cb(self, call: InlineCall, provider: str):
        await call.answer(f"Введи: .{provider}prompt <текст>", show_alert=True)

    async def _cfg_clear_key_cb(self, call: InlineCall, provider: str):
        self.config[f"{provider}_api_key"] = ""
        await call.answer("🗑 Ключ удалён", show_alert=False)
        await self._cfg_provider_menu_cb(call, provider)

    async def _cfg_back_cb(self, call: InlineCall):
        await self._cfg_main_menu(call, edit=True)

    async def _cfg_general_cb(self, call: InlineCall):
        agent = self.config["agent_mode"]
        steps = self.config["agent_max_steps"]
        show_steps = self.config.get("show_agent_steps", True)
        text = (
            "⚙️ <b>Общие настройки</b>\n\n"
            f"🤖 Агент: <b>{'вкл' if agent else 'выкл'}</b>\n"
            f"📶 Макс. шагов: <b>{steps}</b>\n"
            f"📋 Показывать шаги: <b>{'да' if show_steps else 'нет'}</b>\n"
            f"🗜 Макс. история: <b>{self.config['max_history_length']}</b>"
        )
        btns = [
            [
                {"text": f"{'✅' if agent else '❌'} Агент", "callback": self._cfg_toggle_agent_cb, "args": ()},
                {"text": f"{'👁' if show_steps else '🙈'} Шаги", "callback": self._cfg_toggle_steps_cb, "args": ()},
            ],
            [
                {"text": "📝 Промпт", "callback": self._cfg_show_prompt_cb, "args": ()},
                {"text": "🧹 Сброс всей памяти", "callback": self._cfg_reset_all_cb, "args": ()},
            ],
            [{"text": "◀️ Назад", "callback": self._cfg_back_cb, "args": ()}],
        ]
        await call.edit(text, reply_markup=btns)

    async def _cfg_toggle_agent_cb(self, call: InlineCall):
        self.config["agent_mode"] = not self.config["agent_mode"]
        await self._cfg_general_cb(call)

    async def _cfg_toggle_steps_cb(self, call: InlineCall):
        self.config["show_agent_steps"] = not self.config.get("show_agent_steps", True)
        await self._cfg_general_cb(call)

    async def _cfg_show_prompt_cb(self, call: InlineCall):
        p = self.config["system_instruction"]
        await call.answer(p[:200], show_alert=True)

    async def _cfg_reset_all_cb(self, call: InlineCall):
        self._clear_chat_history()
        await call.answer("🧹 Всё очищено!", show_alert=False)
        await self._cfg_general_cb(call)

    # ─── вспомогательные для команд ─────────────────────────────────────────

    async def _handle_prompt_helper(self, message, provider):
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        prompt_text = args
        if reply and reply.file:
            try:
                prompt_text = (await message.client.download_file(reply.media, bytes)).decode("utf-8")
            except Exception:
                pass
        elif reply and reply.text:
            prompt_text = reply.text
        if not prompt_text:
            cur = self._get_provider_prompt(provider)
            return await utils.answer(
                message,
                f"<b>Промпт для {provider}:</b>\n\n<code>{utils.escape_html(cur)}</code>",
            )
        self._set_provider_prompt(provider, prompt_text)
        await utils.answer(message, f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> <b>Промпт для {provider} сохранён!</b>")

    async def _collect_media(self, message, prompt):
        """Собирает медиа из реплая: фото, видео, ГС, кружки, музыку, документы.
        Возвращает (prompt, image_bytes, mime_type).
        Если провайдер gemini_hub — медиа НЕ скачивается, только текстовые пометки."""
        image_bytes = None
        mime_type = None
        reply = await message.get_reply_message()
        if not reply:
            return prompt, None, None

        # Gemini Hub не поддерживает медиа — пропускаем скачивание
        is_text_only_provider = self.config["active_provider"] == "gemini_hub"

        # ─── Фото ───
        if getattr(reply, "photo", None):
            if is_text_only_provider:
                prompt += "\n\n[фото прикреплено, но текущий провайдер не поддерживает изображения]"
            else:
                try:
                    image_bytes = await message.client.download_media(reply.media, bytes)
                    mime_type = "image/jpeg"
                    prompt += "\n\n[фото прикреплено — опиши что на нём]"
                except Exception:
                    pass

        # ─── Документ-картинка ───
        elif getattr(reply, "document", None) and getattr(reply.file, "mime_type", "").startswith("image/"):
            if is_text_only_provider:
                prompt += "\n\n[картинка прикреплена, но текущий провайдер не поддерживает изображения]"
            else:
                try:
                    image_bytes = await message.client.download_media(reply.media, bytes)
                    mime_type = reply.file.mime_type
                    prompt += "\n\n[картинка прикреплена — опиши что на ней]"
                except Exception:
                    pass

        # ─── Видео ───
        elif getattr(reply, "video", None) or (
            getattr(reply, "document", None) and getattr(reply.file, "mime_type", "").startswith("video/")
        ):
            if is_text_only_provider:
                prompt += "\n\n[видео прикреплено, но текущий провайдер не поддерживает видео]"
            else:
                try:
                    video_bytes = await message.client.download_media(reply.media, bytes)
                    video_mime = getattr(reply.file, "mime_type", "") or "video/mp4"
                    provider = self.config["active_provider"]
                    if provider == "gemini":
                        # Gemini поддерживает видео напрямую
                        description, err = await self._analyze_media_gemini(
                            video_bytes, video_mime, prompt or "Опиши что происходит на этом видео")
                        if description:
                            prompt += f"\n\n[содержимое видео]:\n{description}"
                        else:
                            frames = await self._extract_video_frames(video_bytes)
                            if frames:
                                image_bytes, mime_type = frames[0]
                                prompt += "\n\n[кадр из видео прикреплён — опиши что на нём]"
                                if len(frames) > 1:
                                    extra_desc = ""
                                    for i, (fb, fm) in enumerate(frames[1:], 2):
                                        d, _ = await self._analyze_media_gemini(fb, fm, "Кратко опиши что на этом кадре")
                                        if d:
                                            extra_desc += f"\nКадр {i}: {d[:200]}"
                                    if extra_desc:
                                        prompt += f"\n[другие кадры]:{extra_desc}"
                            else:
                                prompt += "\n\n[видео прикреплено, но FFmpeg не установлен — установи для анализа видео]"
                    else:
                        frames = await self._extract_video_frames(video_bytes)
                        if frames:
                            image_bytes, mime_type = frames[0]
                            prompt += "\n\n[кадр из видео прикреплён — опиши что на нём]"
                            if len(frames) > 1:
                                extra_desc = ""
                                for i, (fb, fm) in enumerate(frames[1:], 2):
                                    d, _ = await self._analyze_media_gemini(fb, fm, "Кратко опиши что на этом кадре")
                                    if d:
                                        extra_desc += f"\nКадр {i}: {d[:200]}"
                                if extra_desc:
                                    prompt += f"\n[другие кадры]:{extra_desc}"
                        else:
                            prompt += "\n\n[видео прикреплено, но FFmpeg не установлен — установи для анализа видео]"
                except Exception as e:
                    prompt += f"\n\n[ошибка обработки видео: {e}]"

        # ─── Кружок (видеозаметка) ───
        elif getattr(reply, "video_note", None):
            if is_text_only_provider:
                prompt += "\n\n[кружок прикреплён, но текущий провайдер не поддерживает видео]"
            else:
                try:
                    vn_bytes = await message.client.download_media(reply.media, bytes)
                    provider = self.config["active_provider"]
                    if provider == "gemini":
                        description, err = await self._analyze_media_gemini(
                            vn_bytes, "video/mp4", prompt or "Опиши что происходит в этом кружке")
                        if description:
                            prompt += f"\n\n[содержимое кружка]:\n{description}"
                        else:
                            frames = await self._extract_video_frames(vn_bytes)
                            if frames:
                                image_bytes, mime_type = frames[0]
                                prompt += "\n\n[кадр из кружка прикреплён — опиши что на нём]"
                            else:
                                prompt += "\n\n[кружок прикреплён, но FFmpeg не установлен — установи для анализа]"
                    else:
                        frames = await self._extract_video_frames(vn_bytes)
                        if frames:
                            image_bytes, mime_type = frames[0]
                            prompt += "\n\n[кадр из кружка прикреплён — опиши что на нём]"
                        else:
                            prompt += "\n\n[кружок прикреплён, но FFmpeg не установлен — установи для анализа]"
                except Exception as e:
                    prompt += f"\n\n[ошибка обработки кружка: {e}]"

        # ─── Голосовое сообщение (ГС) ───
        elif getattr(reply, "voice", None):
            if is_text_only_provider:
                prompt += "\n\n[голосовое сообщение прикреплено, но текущий провайдер не поддерживает аудио]"
            else:
                try:
                    voice_bytes = await message.client.download_media(reply.media, bytes)
                    voice_mime = getattr(reply.file, "mime_type", "") or "audio/ogg"
                    transcription, err = await self._transcribe_whisper(voice_bytes)
                    if transcription:
                        prompt += f"\n\n[текст голосового сообщения]:\n{transcription}"
                    else:
                        provider = self.config["active_provider"]
                        if provider == "gemini":
                            description, err = await self._analyze_media_gemini(
                                voice_bytes, voice_mime, "Транскрибируй это аудио. Напиши весь текст что слышишь.")
                            if description:
                                prompt += f"\n\n[текст голосового сообщения]:\n{description}"
                            else:
                                prompt += f"\n\n[голосовое сообщение прикреплено, но не удалось распознать: {err}]"
                        else:
                            prompt += "\n\n[голосовое сообщение прикреплено, но нет OpenAI ключа для Whisper и текущий провайдер не поддерживает аудио]"
                except Exception as e:
                    prompt += f"\n\n[ошибка обработки голосового: {e}]"

        # ─── Аудио / музыка ───
        elif getattr(reply, "audio", None) or (
            getattr(reply, "document", None) and getattr(reply.file, "mime_type", "").startswith("audio/")
        ):
            if is_text_only_provider:
                prompt += "\n\n[аудио прикреплено, но текущий провайдер не поддерживает аудио]"
            else:
                try:
                    audio_bytes = await message.client.download_media(reply.media, bytes)
                    audio_mime = getattr(reply.file, "mime_type", "") or "audio/mpeg"
                    transcription, err = await self._transcribe_whisper(audio_bytes)
                    provider = self.config["active_provider"]
                    if provider == "gemini":
                        description, err = await self._analyze_media_gemini(
                            audio_bytes, audio_mime,
                            prompt or "Проанализируй это аудио. Если это музыка — назови трек/исполнителя если узнаёшь. Если речь — транскрибируй.")
                        if description:
                            prompt += f"\n\n[содержимое аудио]:\n{description}"
                        elif transcription:
                            prompt += f"\n\n[транскрипция аудио]:\n{transcription}"
                        else:
                            prompt += f"\n\n[аудио прикреплено, но не удалось распознать: {err}]"
                    elif transcription:
                        prompt += f"\n\n[транскрипция аудио]:\n{transcription}"
                    else:
                        prompt += "\n\n[аудио прикреплено, но нет ключа для распознавания]"
                except Exception as e:
                    prompt += f"\n\n[ошибка обработки аудио: {e}]"

        # ─── Обычный файл ───
        elif getattr(reply, "file", None):
            try:
                txt = (await message.client.download_file(reply.media, bytes)).decode("utf-8")
                prompt += f"\n\n[файл {getattr(reply.file, 'name', 'файл')}]:\n{txt}"
            except Exception:
                pass

        # ─── Аватарка по ключевым словам ───
        if not image_bytes and getattr(reply, "sender_id", None) and not is_text_only_provider:
            if any(w in prompt.lower() for w in ["ава", "аватар", "аву", "фото профил"]):
                try:
                    av = await message.client.download_profile_photo(reply.sender_id, bytes)
                    if av:
                        image_bytes = av
                        mime_type = "image/jpeg"
                        prompt += "\n\n[аватарка прикреплена]"
                except Exception:
                    pass

        # ─── Текст из реплая (если не медиа) ───
        if getattr(reply, "text", None) and not image_bytes and not getattr(reply, "voice", None) and not getattr(reply, "audio", None):
            reply_context = await self._build_reply_context(reply)
            prompt += reply_context

        # Если провайдер gemini_hub — гарантированно обнуляем медиа
        if is_text_only_provider:
            image_bytes = None
            mime_type = None

        return prompt, image_bytes, mime_type

    async def _build_reply_context(self, reply_msg, depth=0, max_depth=5):
        """Строит читаемый контекст из цепочки реплаев.
        depth=0 — сообщение на которое отвечает пользователь,
        глубже — вложенные реплаи этого сообщения."""
        if not reply_msg or depth > max_depth:
            return ""

        # Определяем автора
        sender_id = getattr(reply_msg, "sender_id", None)
        sender_name = "?"
        is_me = False
        try:
            if sender_id:
                me_id = getattr(self.me, "id", None) if hasattr(self, "me") and self.me else None
                if me_id and sender_id == me_id:
                    sender_name = "я (userbot)"
                else:
                    sender = await reply_msg.get_sender()
                    if sender:
                        uname = getattr(sender, "username", None)
                        fname = getattr(sender, "first_name", None) or ""
                        lname = getattr(sender, "last_name", None) or ""
                        fullname = (fname + " " + lname).strip()
                        if uname:
                            sender_name = f"@{uname}"
                            if fullname:
                                sender_name = f"{fullname} (@{uname})"
                        elif fullname:
                            sender_name = fullname
                        is_bot = getattr(sender, "bot", False)
                        if is_bot:
                            sender_name += " [бот]"
        except Exception:
            pass

        text = getattr(reply_msg, "text", None) or ""

        # Рекурсивно тянем цепочку вглубь (сообщение на которое ответил reply_msg)
        chain_context = ""
        if reply_msg.reply_to_msg_id and depth < max_depth:
            try:
                parent = await reply_msg.get_reply_message()
                if parent and getattr(parent, "text", None):
                    chain_context = await self._build_reply_context(parent, depth + 1, max_depth)
            except Exception:
                pass

        # Формируем блок
        if depth == 0:
            # Корень — главное сообщение контекста
            result = f"\n\n[Сообщение от {sender_name}]:\n{text}"
            if chain_context:
                result = chain_context + result
        else:
            # Вложенные — показываем как треад
            indent = "  " * depth
            result = f"\n\n{indent}[Ранее, {sender_name}]:\n{indent}{text}"
            if chain_context:
                result = chain_context + result

        return result

    # ─── команды ─────────────────────────────────────────────────────────────

    @loader.command(ru_name="1a", en_name="1a")
    async def acmd(self, message: Message):
        """[текст/reply] — отправить запрос активному провайдеру"""
        args = utils.get_args_raw(message)
        prompt = args or ""
        # Сохраняем оригинальный текст пользователя для отображения
        original_prompt = prompt
        prompt, image_bytes, mime_type = await self._collect_media(message, prompt)

        # ─── Распознавание человека (если реплай на чужое сообщение) ───
        reply = await message.get_reply_message()
        person_context = ""
        provider = self.config["active_provider"]
        is_text_only_provider = provider == "gemini_hub"
        if reply and reply.sender_id and reply.sender_id != self.me.id:
            person_info = await self._get_person_info(reply.sender_id)
            if person_info:
                person_context = f"\n\n[Информация о собеседнике]:\n{person_info}"
                # Пробуем скачать аватарку если ещё нет медиа И провайдер поддерживает изображения
                if not image_bytes and not is_text_only_provider:
                    try:
                        av = await message.client.download_profile_photo(reply.sender_id, bytes)
                        if av:
                            image_bytes = av
                            mime_type = "image/jpeg"
                            person_context += "\n[аватарка собеседника прикреплена]"
                    except Exception:
                        pass
                elif is_text_only_provider:
                    person_info_text = person_info.replace("Аватарка: есть", "Аватарка: есть (не прикреплена — провайдер не поддерживает изображения)")
                    person_context = f"\n\n[Информация о собеседнике]:\n{person_info_text}"

        if person_context:
            prompt += person_context

        # Гарантированно обнуляем медиа для текстовых провайдеров
        if is_text_only_provider:
            image_bytes = None
            mime_type = None

        if not prompt and not image_bytes:
            return await utils.answer(message, self.strings["no_prompt"])

        provider = self.config["active_provider"]
        status = await utils.answer(message, self.strings["processing"])

        try:
            t0 = time.time()
            res, agent_report = await self._run_agent_loop(
                provider, prompt, message.chat_id, message,
                image_bytes=image_bytes, mime_type=mime_type,
                status_msg=status,
            )
            elapsed = round(time.time() - t0)
            model_name = self.config.get(f"{provider}_model", provider)
            msg_count = self._get_msg_count(message.chat_id)
            exchanges = len(self._get_history(message.chat_id))
            meta = f"🗜 [{exchanges}/{self.config['max_history_length']}] {model_name} | {elapsed}с"
            # Показываем только оригинальный текст пользователя, без контекста
            display_prompt = original_prompt or args or ""
            safe_prompt = utils.escape_html(display_prompt[:800]) + ("…" if len(display_prompt) > 800 else "")
            final_text = (
                f"<i>{utils.escape_html(meta)}</i>\n\n"
                f"💬 <b>Запрос:</b>\n<blockquote>{safe_prompt}</blockquote>\n\n"
                f"✨ <b>{provider.upper()}:</b>\n<blockquote expandable>{self._format_res(res)}</blockquote>"
            )
            if agent_report:
                final_text += f"\n\n{agent_report}"
            if len(final_text) > 4096:
                f_obj = self._extract_code_file(res)
                await message.client.send_file(message.chat_id, f_obj,
                    caption=f"<b>{provider.upper()} (слишком длинный ответ)</b>", reply_to=message.id)
                await status.delete()
            else:
                await self._try_inline(status, final_text,
                                       self._ai_buttons(provider, message.chat_id, prompt, model_name))
        except Exception as e:
            await utils.answer(status, self.strings["error"].format(e))

    @loader.command(ru_name="1acode", en_name="1acode")
    async def acodecmd(self, message: Message):
        """[текст/reply] — запрос с ответом-кодом"""
        args = utils.get_args_raw(message)
        prompt = args or ""
        # Сохраняем оригинальный текст для отображения
        original_prompt = prompt
        prompt, image_bytes, mime_type = await self._collect_media(message, prompt)

        if not prompt and not image_bytes:
            return await utils.answer(message, self.strings["no_prompt"])

        provider = self.config["active_provider"]
        status = await utils.answer(message, self.strings["processing"])

        try:
            t0 = time.time()
            res, agent_report = await self._run_agent_loop(
                provider, prompt, message.chat_id, message,
                needs_file=True, image_bytes=image_bytes, mime_type=mime_type,
                status_msg=status,
            )
            elapsed = round(time.time() - t0)
            model_name = self.config.get(f"{provider}_model", provider)
            msg_count = self._get_msg_count(message.chat_id)
            exchanges = len(self._get_history(message.chat_id))
            meta = f"🗜 [{exchanges}/{self.config['max_history_length']}] {model_name} | {elapsed}с"
            # Показываем только оригинальный текст пользователя
            display_prompt = original_prompt or args or ""
            safe_prompt = utils.escape_html(display_prompt[:800]) + ("…" if len(display_prompt) > 800 else "")
            final_text = (
                f"<i>{utils.escape_html(meta)}</i>\n\n"
                f"💬 <b>Запрос:</b>\n<blockquote>{safe_prompt}</blockquote>\n\n"
                f"✨ <b>{provider.upper()}:</b>\n<blockquote expandable>{self._format_res(res)}</blockquote>"
            )
            if agent_report:
                final_text += f"\n\n{agent_report}"
            if len(final_text) > 4096:
                f_obj = self._extract_code_file(res)
                await message.client.send_file(message.chat_id, f_obj,
                    caption=f"<b>{provider.upper()} (код)</b>", reply_to=message.id)
                await status.delete()
            else:
                await self._try_inline(status, final_text,
                                       self._ai_buttons(provider, message.chat_id, prompt, model_name))
        except Exception as e:
            await utils.answer(status, self.strings["error"].format(e))

    @loader.command(ru_name="1aimg", en_name="1aimg")
    async def aimgcmd(self, message: Message):
        """[-ai] [текст/reply] — сгенерировать картинку"""
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        prompt = args or ""
        if reply and reply.text:
            prompt += f" {reply.text}"
        elif reply and getattr(reply, "file", None):
            try:
                prompt += (await message.client.download_file(reply.media, bytes)).decode("utf-8")
            except Exception:
                pass

        prompt, use_ai = self._extract_ai_flag(prompt)
        if not prompt:
            return await utils.answer(message, self.strings["no_prompt"])

        provider = self.config["image_provider"]
        status = await utils.answer(message, self.strings["processing"])

        if use_ai:
            await utils.answer(status, "🤖 <b>Улучшаю промпт...</b>")
            try:
                prompt, _ = await self._run_agent_loop(
                    self.config["active_provider"], prompt, message.chat_id, message,
                    override_sys="Улучши промпт для генерации картинки. Добавь детали, стиль, освещение. "
                                  "ВЫДАЙ ТОЛЬКО ПРОМПТ НА АНГЛИЙСКОМ БЕЗ КАВЫЧЕК.",
                )
                await utils.answer(status, "🕓 <b>Промпт улучшен, рисую...</b>")
            except Exception as e:
                return await utils.answer(status, f"❌ Ошибка улучшения промпта: {e}")

        if provider == "openai":
            key = self.config.get("openai_api_key")
            if not key: return await utils.answer(status, "укажите openai_api_key")
            img_bytes, err = await self._call_openai_image(prompt, key, self.config["openai_image_model"])
        elif provider == "gemini":
            key = self.config.get("gemini_api_key")
            if not key: return await utils.answer(status, "укажите gemini_api_key")
            img_bytes, err = await self._call_gemini_image(prompt, key)
        elif provider == "gemini_hub":
            key = self.config.get("gemini_hub_api_key")
            if not key: return await utils.answer(status, "укажите gemini_hub_api_key")
            img_bytes, err = await self._call_gemini_hub_image(prompt, key)
        else:
            return await utils.answer(status, f"Провайдер {provider} не поддерживает картинки")

        if err:
            await utils.answer(status, f"⚠️ <b>Основной API выдал ошибку:</b>\n<code>{err}</code>\n\n<tg-emoji emoji-id=5985780596268339498>🤖</tg-emoji> <b>Юзаю бесплатный резервный сервер...</b>")
            try:
                safe_prompt = urllib.parse.quote(prompt)
                fallback_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?nologo=true"
                async with aiohttp.ClientSession() as s:
                    async with s.get(fallback_url) as r:
                        if r.status == 200:
                            img_bytes = await r.read()
                            err = None
                            display_provider = "pollinations"
                        else:
                            err = "даже резервный сервер сожрал говна"
            except Exception as fb_err:
                err = f"ошибка резерва: {fb_err}"
        else:
            display_provider = provider

        if err:
            return await utils.answer(status, self.strings["error"].format(err))

        # Показываем реальную модель картинок и метод генерации
        img_model_name = self.config.get(f"{provider}_image_model", provider)
        gen_method = "чат" if img_model_name in CHAT_IMAGE_MODELS else "imagen"
        f = io.BytesIO(img_bytes); f.name = "image.png"
        caption = (f"<tg-emoji emoji-id=5985780596268339498>🤖</tg-emoji> "
                   f"<b>{display_provider.upper()}</b> | <code>{img_model_name}</code> [{gen_method}]\n"
                   f"<blockquote>{utils.escape_html(prompt[:600])}</blockquote>")
        await message.client.send_file(message.chat_id, f, caption=caption, reply_to=message.id)
        await self._safe_inline(status, "🖼 <b>Действия с картинкой:</b>", self._img_buttons(provider, prompt))

    # ─── веб-поиск ──────────────────────────────────────────────────────────

    async def _web_search(self, query: str, max_results: int = 5) -> list:
        """Поиск через SearXNG → DDG → Brave → Google. Возвращает список {title, snippet, url}"""
        results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            "Accept": "application/json, text/html",
        }

        # 1) SearXNG публичные инстансы (JSON, без ключа)
        searx_instances = [
            "https://searx.be",
            "https://search.inetol.net",
            "https://searxng.world",
            "https://search.sapti.me",
            "https://searx.work",
            "https://search.bus-hit.me",
            "https://searx.fmac.xyz",
            "https://search.mdosch.de",
            "https://searx.tiekoetter.com",
            "https://searx.priv.pw",
        ]
        for base in searx_instances:
            if results:
                break
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        f"{base}/search",
                        params={"q": query, "format": "json", "language": "auto", "categories": "general"},
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        if r.status == 200:
                            try:
                                d = await r.json(content_type=None)
                            except Exception:
                                continue
                            for item in d.get("results", [])[:max_results]:
                                title = item.get("title", "")
                                snippet = item.get("content", "") or item.get("snippet", "")
                                url = item.get("url", "")
                                if snippet:
                                    results.append({"title": title, "snippet": snippet[:300], "url": url})
            except Exception:
                continue

        # 2) DDG HTML fallback (обновлённые селекторы)
        if not results:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        "https://html.duckduckgo.com/html/",
                        params={"q": query, "kl": "ru-ru"},
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=12),
                    ) as r:
                        if r.status == 200:
                            html = await r.text()
                            # DDG обновлённые паттерны
                            titles = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
                            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</(?:span|div|a|td)>', html, re.DOTALL)
                            urls = re.findall(r'uddg=(https?[^&"]+)', html)
                            # Альтернативные паттерны для новой вёрстки DDG
                            if not snippets:
                                snippets = re.findall(r'result__snippet[^>]*>(.*?)<', html, re.DOTALL)
                            if not urls:
                                urls = re.findall(r'href="(https?://[^"]+)"', html)
                                urls = [u for u in urls if "duckduckgo" not in u and "javascript" not in u][:max_results]
                            for i in range(min(max_results, max(len(snippets), len(titles)))):
                                title = re.sub(r'<[^>]+>', '', titles[i] if i < len(titles) else "").strip()
                                snippet = re.sub(r'<[^>]+>', '', snippets[i] if i < len(snippets) else "").strip()
                                url = urllib.parse.unquote(urls[i]) if i < len(urls) else ""
                                if snippet or title:
                                    results.append({"title": title, "snippet": snippet or title, "url": url})
            except Exception:
                pass

        # 3) Brave Search fallback
        if not results:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        "https://search.brave.com/search",
                        params={"q": query},
                        headers={
                            **headers,
                            "Accept": "text/html",
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        if r.status == 200:
                            html = await r.text()
                            # Brave Search парсинг
                            snippets_b = re.findall(r'<p[^>]*class="snippet-description[^"]*"[^>]*>(.*?)</p>', html, re.DOTALL)
                            titles_b = re.findall(r'<a[^>]*class="result-header[^"]*"[^>]*>.*?<span[^>]*>(.*?)</span>', html, re.DOTALL)
                            urls_b = re.findall(r'<a[^>]*class="result-header[^"]*"[^>]*href="(https?[^"]+)"', html)
                            for i in range(min(max_results, max(len(snippets_b), len(titles_b)))):
                                title = re.sub(r'<[^>]+>', '', titles_b[i] if i < len(titles_b) else "").strip()
                                snippet = re.sub(r'<[^>]+>', '', snippets_b[i] if i < len(snippets_b) else "").strip()
                                url = urls_b[i] if i < len(urls_b) else ""
                                if snippet or title:
                                    results.append({"title": title, "snippet": snippet or title, "url": url})
            except Exception:
                pass

        # 4) Google fallback (HTML scraping)
        if not results:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        "https://www.google.com/search",
                        params={"q": query, "hl": "ru", "num": str(max_results)},
                        headers={
                            **headers,
                            "Accept-Language": "ru-RU,ru;q=0.9",
                        },
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        if r.status == 200:
                            html = await r.text()
                            # Google парсинг
                            blocks = re.findall(r'<div[^>]*class="[^"]*g[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>', html, re.DOTALL)
                            if not blocks:
                                blocks = re.findall(r'<div class="tF2Cxc">(.*?)</div>\s*</div>', html, re.DOTALL)
                            for block in blocks[:max_results]:
                                title_m = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
                                snippet_m = re.search(r'<span[^>]*>(.*?)</span>', block, re.DOTALL)
                                url_m = re.search(r'href="(https?://[^"]+)"', block)
                                title = re.sub(r'<[^>]+>', '', title_m.group(1) if title_m else "").strip()
                                snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1) if snippet_m else "").strip()
                                url = url_m.group(1) if url_m else ""
                                if url and "google.com" not in url:
                                    results.append({"title": title, "snippet": snippet or title, "url": url})
            except Exception:
                pass

        # 5) fallback: worldtimeapi для запросов о времени
        if not results:
            q = query.lower()
            if any(w in q for w in ["время", "час", "time", "дата", "date"]):
                try:
                    city_map = {
                        "москва": "Moscow", "москве": "Moscow", "moscow": "Moscow",
                        "лондон": "London", "london": "London",
                        "нью-йорк": "New_York", "new york": "New_York",
                        "токио": "Tokyo", "tokyo": "Tokyo",
                        "берлин": "Berlin", "berlin": "Berlin",
                        "париж": "Paris", "paris": "Paris",
                        "баку": "Baku", "baku": "Baku",
                        "дубай": "Dubai", "dubai": "Dubai",
                    }
                    city = "Moscow"
                    for k, v in city_map.items():
                        if k in q:
                            city = v
                            break
                    tz_region = "Europe" if city not in ("Baku", "Dubai", "Tokyo", "Beijing") else (
                        "Asia" if city in ("Baku", "Dubai", "Tokyo", "Beijing") else "America"
                    )
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                            f"https://worldtimeapi.org/api/timezone/{tz_region}/{city}",
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as r:
                            if r.status == 200:
                                d = await r.json()
                                dt_str = d.get("datetime", "")[:19].replace("T", " ")
                                tz = d.get("timezone", city)
                                results.append({
                                    "title": f"Время в {city}",
                                    "snippet": f"Текущее время: {dt_str} ({tz})",
                                    "url": "worldtimeapi.org"
                                })
                except Exception:
                    import datetime as dt_mod
                    now = dt_mod.datetime.utcnow() + dt_mod.timedelta(hours=3)
                    results.append({
                        "title": "Время Москва (UTC+3)",
                        "snippet": f"Текущее время: {now.strftime('%Y-%m-%d %H:%M:%S')}",
                        "url": ""
                    })
        return results

    @loader.command(ru_name="1as", en_name="1as")
    async def asearchcmd(self, message: Message):
        """[запрос] — поиск в интернете + ответ AI на основе результатов"""
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        query = args or ""
        if not query and reply and reply.text:
            query = reply.text
        if not query:
            return await utils.answer(message, self.strings["no_prompt"])

        provider = self.config["active_provider"]
        status = await utils.answer(message, "🌐 <b>Ищу в интернете...</b>")

        try:
            t0 = time.time()
            results = await self._web_search(query, max_results=6)

            if not results:
                await utils.answer(status, "❌ <b>Ничего не нашёл. Попробуй переформулировать запрос.</b>")
                return

            # собираем контекст для AI
            context_parts = []
            sources_text = ""
            for i, r in enumerate(results, 1):
                context_parts.append(
                    f"[{i}] {r['title']}\n{r['snippet']}"
                    + (f"\nИсточник: {r['url']}" if r['url'] else "")
                )
                if r['url']:
                    sources_text += f"\n{i}. {r['title'] or r['url']} — {r['url']}"

            context = "\n\n".join(context_parts)
            sys_prompt = (
                "Ты помощник который отвечает на вопросы используя результаты веб-поиска. "
                "Дай чёткий, структурированный ответ на основе предоставленных результатов поиска. "
                "Можешь использовать информацию из результатов, дополняя своими знаниями. "
                "Не выдумывай факты которых нет в результатах. Отвечай на языке вопроса."
            )
            ai_prompt = f"Вопрос: {query}\n\nРезультаты поиска:\n{context}"

            await utils.answer(status, "🤖 <b>Анализирую результаты...</b>")

            res, _ = await self._run_agent_loop(
                provider, ai_prompt, message.chat_id, message,
                override_sys=sys_prompt,
            )

            elapsed = round(time.time() - t0)
            model_name = self.config.get(f"{provider}_model", provider)
            meta = f"🌐 поиск | {model_name} | {elapsed}с | {len(results)} рез."

            final_text = (
                f"<i>{utils.escape_html(meta)}</i>\n\n"
                f"🔍 <b>Запрос:</b>\n<blockquote>{utils.escape_html(query[:300])}</blockquote>\n\n"
                f"✨ <b>Ответ:</b>\n<blockquote expandable>{self._format_res(res)}</blockquote>"
            )
            if sources_text:
                final_text += f"\n\n📎 <b>Источники:</b><blockquote expandable>{utils.escape_html(sources_text[:600])}</blockquote>"

            btns = [[
                {"text": "🔄 Переспросить", "callback": self._search_regen_cb,
                 "args": (provider, query[:300])},
                {"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()},
            ]]
            try:
                await self._safe_inline(status, final_text, btns)
            except Exception:
                await utils.answer(status, final_text)
        except Exception as e:
            await utils.answer(status, self.strings["error"].format(e))

    async def _search_regen_cb(self, call: InlineCall, provider: str, query: str):
        await call.edit("🌐 <b>Ищу снова...</b>", reply_markup=None)
        try:
            results = await self._web_search(query, max_results=6)
            if not results:
                return await call.edit("❌ Ничего не нашёл.", reply_markup=None)
            context = "\n\n".join(
                f"[{i}] {r['title']}\n{r['snippet']}" for i, r in enumerate(results, 1)
            )
            sys_prompt = (
                "Ты помощник который отвечает на вопросы используя результаты веб-поиска. "
                "Дай чёткий ответ на основе результатов. Отвечай на языке вопроса."
            )
            ai_prompt = f"Вопрос: {query}\n\nРезультаты поиска:\n{context}"
            res, _ = await self._run_agent_loop(
                provider, ai_prompt, None, None, override_sys=sys_prompt,
            )
            model_name = self.config.get(f"{provider}_model", provider)
            sources_text = "\n".join(
                f"{i}. {r['url']}" for i, r in enumerate(results, 1) if r['url']
            )
            final_text = (
                f"<i>🌐 поиск | {model_name} | 🔄 рег.</i>\n\n"
                f"🔍 <b>Запрос:</b>\n<blockquote>{utils.escape_html(query[:300])}</blockquote>\n\n"
                f"✨ <b>Ответ:</b>\n<blockquote expandable>{self._format_res(res)}</blockquote>"
            )
            if sources_text:
                final_text += f"\n\n📎 <b>Источники:</b><blockquote expandable>{utils.escape_html(sources_text[:400])}</blockquote>"
            btns = [[
                {"text": "🔄 Переспросить", "callback": self._search_regen_cb,
                 "args": (provider, query)},
                {"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()},
            ]]
            await call.edit(final_text, reply_markup=btns)
        except Exception as e:
            await call.edit(self.strings["error"].format(str(e)), reply_markup=None)

    @loader.command()
    async def aprovidercmd(self, message: Message):
        """[provider] — переключить провайдер или открыть меню"""
        args = utils.get_args_raw(message).strip().lower()
        valid = list(PROVIDER_MODELS.keys())
        if args and args in valid:
            self.config["active_provider"] = args
            return await utils.answer(message, self.strings["provider_set"].format(args))
        current = self.config["active_provider"]
        btns = []
        row = []
        for p in valid:
            mark = "✅ " if p == current else ""
            row.append({"text": f"{mark}{p}", "callback": self._set_provider_cb, "args": (p,)})
            if len(row) == 2:
                btns.append(row); row = []
        if row: btns.append(row)
        btns.append([{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}])
        await self._safe_inline(
            message,
            f"<b>Выберите провайдера:</b>\nТекущий: <code>{current}</code>",
            btns,
        )

    @loader.command(ru_name="1aauth", en_name="1aauth")
    async def aauthcmd(self, message: Message):
        """алиас для .aprovider"""
        await self.aprovidercmd(message)

    @loader.command()
    async def aimgauthcmd(self, message: Message):
        """[provider] — провайдер для картинок"""
        args = utils.get_args_raw(message).strip().lower()
        valid = ["openai", "gemini", "gemini_hub"]
        current = self.config["image_provider"]
        if args and args in valid:
            self.config["image_provider"] = args
            return await utils.answer(message, f"✅ <b>Картинки:</b> <code>{args}</code>")
        btns = [
            [{"text": ("✅ " if p == current else "") + p,
              "callback": self._set_img_provider_cb, "args": (p,)} for p in valid],
            [{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}],
        ]
        await self._safe_inline(
            message,
            f"<b>Провайдер картинок:</b> <code>{current}</code>",
            btns,
        )

    @loader.command()
    async def arescmd(self, message: Message):
        """[-a] — сбросить память чата"""
        args = utils.get_args_raw(message)
        all_chats = args.strip() == "-a"
        chat_id = str(message.chat_id)
        text = "🧹 <b>Сбросить всю память?</b>" if all_chats else "🧹 <b>Сбросить память этого чата?</b>"
        btns = [[
            {"text": "✅ Да", "callback": self._confirm_reset_cb, "args": (chat_id, all_chats)},
            {"text": "❌ Отмена", "callback": self._close_menu_cb, "args": ()},
        ]]
        # В чатах без инлайна — сразу сбрасываем без подтверждения
        if str(message.chat_id) in self._no_inline_chats:
            self._clear_chat_history(None if all_chats else message.chat_id)
            return await utils.answer(message, self.strings["cleared"])
        # Пробуем инлайн для подтверждения, фолбек — сразу сброс
        try:
            await self.inline.form(message=message, text=text, reply_markup=btns)
        except Exception:
            self._no_inline_chats.add(str(message.chat_id))
            self._clear_chat_history(None if all_chats else message.chat_id)
            await utils.answer(message, self.strings["cleared"])

    @loader.command()
    async def apromptcmd(self, message: Message):
        """[текст] — задать промпт для текущего провайдера"""
        await self._handle_prompt_helper(message, self.config["active_provider"])

    @loader.command()
    async def aconfigcmd(self, message: Message):
        """— интерактивное меню конфигурации"""
        try:
            await self._cfg_main_menu(message, edit=False)
        except Exception as e:
            await utils.answer(message, f"❌ Инлайн недоступен: {e}\nИспользуй .acfg")

    @loader.command()
    async def acfgcmd(self, message: Message):
        """[provider field value] — конфиг. Без аргументов — инлайн меню"""
        args = utils.get_args_raw(message).split(maxsplit=2)
        if len(args) < 3:
            try:
                return await self._cfg_main_menu(message, edit=False)
            except Exception:
                return await utils.answer(message, "<b>Формат:</b> <code>.acfg провайдер поле значение</code>")
        prov, field, val = args[0].lower(), args[1].lower(), args[2]
        cfg_key = f"{prov}_{field}"
        if cfg_key in self.config:
            self.config[cfg_key] = val
            await utils.answer(message,
                f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
                f"<code>{cfg_key}</code> = <code>{val}</code>")
        else:
            await utils.answer(message, "❌ <b>Нет такого поля в конфиге!</b>")

    @loader.command()
    async def amodelcmd(self, message: Message):
        """[-s] — выбор модели. -s проверяет реальный список через API"""
        args = utils.get_args_raw(message).lower()
        check_api = "-s" in args
        provider = self.config["active_provider"]
        status = await utils.answer(message, "⏳ <b>Получаю список моделей...</b>")
        models = []

        try:
            if check_api:
                if provider == "openai":
                    key = self.config["openai_api_key"]
                    if not key: return await utils.answer(status, "нет openai_api_key")
                    async with aiohttp.ClientSession() as s:
                        async with s.get("https://api.openai.com/v1/models",
                                         headers={"Authorization": f"Bearer {key}"}) as r:
                            if r.status != 200:
                                return await utils.answer(status, f"ошибка OpenAI API: {r.status}")
                            data = await r.json()
                            models = sorted([
                                m["id"] for m in data.get("data", [])
                                if any(x in m["id"] for x in ("gpt-5", "gpt-4", "o3", "o4", "o1"))
                                and "instruct" not in m["id"]
                                and "vision" not in m["id"]
                            ])

                elif provider == "anthropic":
                    key = self.config["anthropic_api_key"]
                    if not key: return await utils.answer(status, "нет anthropic_api_key")
                    async with aiohttp.ClientSession() as s:
                        async with s.get("https://api.anthropic.com/v1/models",
                                         headers={"x-api-key": key,
                                                  "anthropic-version": "2023-06-01"}) as r:
                            if r.status != 200:
                                return await utils.answer(status, f"ошибка Anthropic API: {r.status}")
                            data = await r.json()
                            models = [m["id"] for m in data.get("data", [])]

                elif provider == "gemini":
                    key = self.config["gemini_api_key"]
                    if not key: return await utils.answer(status, "нет gemini_api_key")
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                            f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                        ) as r:
                            if r.status != 200:
                                return await utils.answer(status, f"ошибка Gemini API: {r.status}")
                            data = await r.json()
                            models = [
                                m["name"].replace("models/", "")
                                for m in data.get("models", [])
                                if "gemini" in m.get("name", "").lower()
                                and "generateContent" in m.get("supportedGenerationMethods", [])
                            ]

                elif provider == "gemini_hub":
                    key = self.config["gemini_hub_api_key"]
                    if not key: return await utils.answer(status, "нет gemini_hub_api_key")
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                            "https://ai-model-hub--skberrghhh.replit.app/api/v1/models",
                            headers={"Authorization": f"Bearer {key}"},
                        ) as r:
                            if r.status != 200:
                                return await utils.answer(status, f"ошибка Hub API: {r.status}")
                            data = await r.json()
                            models = [m["id"] for m in data.get("data", [])
                                      if "gemini" in m.get("id", "").lower()]

                elif provider == "deepseek":
                    key = self.config["deepseek_api_key"]
                    if not key: return await utils.answer(status, "нет deepseek_api_key")
                    async with aiohttp.ClientSession() as s:
                        async with s.get("https://api.deepseek.com/models",
                                         headers={"Authorization": f"Bearer {key}"}) as r:
                            if r.status != 200:
                                return await utils.answer(status, f"ошибка DeepSeek API: {r.status}")
                            data = await r.json()
                            models = [m["id"] for m in data.get("data", [])]

                elif provider == "qwen":
                    key = self.config["qwen_api_key"]
                    if not key: return await utils.answer(status, "нет qwen_api_key")
                    async with aiohttp.ClientSession() as s:
                        async with s.get(
                            "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
                            headers={"Authorization": f"Bearer {key}"},
                        ) as r:
                            if r.status != 200:
                                return await utils.answer(status, f"ошибка Qwen API: {r.status}")
                            data = await r.json()
                            models = [m["id"] for m in data.get("data", [])]

                elif provider == "openrouter":
                    key = self.config["openrouter_api_key"]
                    headers_or = {"Authorization": f"Bearer {key}"} if key else {}
                    async with aiohttp.ClientSession() as s:
                        async with s.get("https://openrouter.ai/api/v1/models",
                                         headers=headers_or) as r:
                            if r.status != 200:
                                return await utils.answer(status, f"ошибка OpenRouter API: {r.status}")
                            data = await r.json()
                            all_m = [m["id"] for m in data.get("data", [])]
                            models = all_m[:50]

                elif provider == "codex":
                    key = self.config["codex_api_key"]
                    if not key: return await utils.answer(status, "нет codex_api_key")
                    async with aiohttp.ClientSession() as s:
                        async with s.get("https://api.openai.com/v1/models",
                                         headers={"Authorization": f"Bearer {key}"}) as r:
                            if r.status != 200:
                                return await utils.answer(status, f"ошибка Codex/OpenAI API: {r.status}")
                            data = await r.json()
                            models = sorted([
                                m["id"] for m in data.get("data", [])
                                if any(x in m["id"] for x in ("gpt-5", "gpt-4", "o3", "o4", "o1"))
                                and "instruct" not in m["id"]
                            ])
                elif provider == "nvidia":
                    models = PROVIDER_MODELS.get(provider, [])

                else:
                    models = PROVIDER_MODELS.get(provider, [])
            else:
                models = PROVIDER_MODELS.get(provider, [])

            if not models:
                return await utils.answer(status, "список моделей пуст / ключ недействителен")

            btns = []
            row = []
            for m in models[:40]:
                row.append({"text": m, "callback": self._set_model_cb, "args": (provider, m)})
                if len(row) == 2:
                    btns.append(row); row = []
            if row: btns.append(row)
            btns.append([{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}])

            source_label = "🌐 API" if check_api else "📋 список"
            await self._safe_inline(
                status,
                (f"<tg-emoji emoji-id=5985780596268339498>🤖</tg-emoji> "
                 f"<b>Модели {provider.upper()} ({source_label}):</b>"),
                btns,
            )
        except Exception as e:
            await utils.answer(status, self.strings["error"].format(e))

    @loader.command()
    async def acheckcmd(self, message: Message):
        """[ключи/reply] — проверить ключи OpenAI"""
        args = utils.get_args_raw(message)
        reply = await message.get_reply_message()
        text = args
        if reply and reply.text:
            text += f" {reply.text}"
        elif reply and getattr(reply, "file", None):
            try:
                text += (await message.client.download_file(reply.media, bytes)).decode("utf-8")
            except Exception:
                pass
        keys = list(set(re.findall(r"sk-[a-zA-Z0-9_\-]{20,}", text)))
        if not keys:
            return await utils.answer(message, "❌ <b>Нет ключей для проверки!</b>")

        status = await utils.answer(message, f"⏳ <b>Проверяю {len(keys)} ключей...</b>")
        valid, invalid = [], []

        async def check(session, k):
            try:
                async with session.get("https://api.openai.com/v1/models",
                                        headers={"Authorization": f"Bearer {k}"},
                                        timeout=aiohttp.ClientTimeout(total=10)) as r:
                    (valid if r.status == 200 else invalid).append(k)
            except Exception:
                invalid.append(k)

        async with aiohttp.ClientSession() as session:
            await asyncio.gather(*[check(session, k) for k in keys])

        res = (f"<b>Проверка {len(keys)} ключей:</b>\n"
               f"✅ Валидных: <b>{len(valid)}</b>\n"
               f"🚫 Невалидных: <b>{len(invalid)}</b>")
        if valid:
            res += "\n\n<b>Рабочие:</b>\n" + "\n".join(f"<code>{k}</code>" for k in valid)
        if len(res) > 4096:
            f = io.BytesIO(res.encode()); f.name = "keys.txt"
            await message.client.send_file(message.chat_id, f,
                caption=f"Валидных: {len(valid)}", reply_to=message.id)
            await status.delete()
        else:
            await utils.answer(status, res)

    # промпт-команды на каждый провайдер
    @loader.command()
    async def openpromptcmd(self, message: Message):
        """промпт для openai"""
        await self._handle_prompt_helper(message, "openai")

    @loader.command()
    async def geminipromptcmd(self, message: Message):
        """промпт для gemini"""
        await self._handle_prompt_helper(message, "gemini")

    @loader.command()
    async def anthropicpromptcmd(self, message: Message):
        """промпт для anthropic"""
        await self._handle_prompt_helper(message, "anthropic")

    @loader.command()
    async def deepseekpromptcmd(self, message: Message):
        """промпт для deepseek"""
        await self._handle_prompt_helper(message, "deepseek")

    @loader.command()
    async def qwenpromptcmd(self, message: Message):
        """промпт для qwen"""
        await self._handle_prompt_helper(message, "qwen")

    @loader.command()
    async def codexpromptcmd(self, message: Message):
        """промпт для codex"""
        await self._handle_prompt_helper(message, "codex")

    @loader.command()
    async def openrouterpromptcmd(self, message: Message):
        """промпт для openrouter"""
        await self._handle_prompt_helper(message, "openrouter")

    @loader.command()
    async def aagentcmd(self, message: Message):
        """— включить/выключить режим агента (инлайн)"""
        agent = self.config["agent_mode"]
        steps = int(self.config["agent_max_steps"])
        show_steps = self.config.get("show_agent_steps", True)
        text = (
            "<tg-emoji emoji-id=5985780596268339498>🤖</tg-emoji> <b>Настройки агента</b>\n\n"
            f"Режим агента: <b>{'✅ включён' if agent else '❌ выключен'}</b>\n"
            f"Макс. шагов: <b>{steps}</b>\n"
            f"Показывать шаги: <b>{'✅ да' if show_steps else '❌ нет'}</b>"
        )
        btns = [
            [
                {"text": f"{'🔴 Выключить' if agent else '🟢 Включить'} агента",
                 "callback": self._cfg_toggle_agent_cb, "args": ()},
            ],
            [
                {"text": f"📶 Шагов: {steps}", "callback": self._agent_steps_menu_cb, "args": ()},
                {"text": f"{'👁 Скрыть' if show_steps else '👁 Показать'} шаги",
                 "callback": self._cfg_toggle_steps_cb, "args": ()},
            ],
            [{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}],
        ]
        await self._safe_inline(message, text, btns)

    async def _agent_steps_menu_cb(self, call: InlineCall):
        """Выбор макс. числа шагов агента"""
        btns = [
            [
                {"text": str(n), "callback": self._agent_set_steps_cb, "args": (n,)}
                for n in [1, 2, 3]
            ],
            [
                {"text": str(n), "callback": self._agent_set_steps_cb, "args": (n,)}
                for n in [4, 5, 7]
            ],
            [{"text": "◀️ Назад", "callback": self._close_menu_cb, "args": ()}],
        ]
        await call.edit(
            f"<b>Максимум шагов агента:</b>\nТекущее: <b>{self.config['agent_max_steps']}</b>",
            reply_markup=btns,
        )

    async def _agent_set_steps_cb(self, call: InlineCall, steps: int):
        self.config["agent_max_steps"] = steps
        await call.answer(f"✅ Шагов: {steps}", show_alert=False)
        await call.edit(
            f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
            f"<b>Максимум шагов агента:</b> <code>{steps}</code>",
            reply_markup=[[{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}]],
        )

    @loader.command()
    async def astatcmd(self, message: Message):
        """— статистика: история, провайдер, модели"""
        provider = self.config["active_provider"]
        img_provider = self.config["image_provider"]
        model = self.config.get(f"{provider}_model", "—")
        img_model = self.config.get(f"{img_provider}_image_model",
                                    self.config.get(f"{img_provider}_model", "—"))
        agent = self.config["agent_mode"]
        steps = self.config["agent_max_steps"]

        total_exchanges = sum(len(h) for h in self.history.values())
        total_msgs = sum(self._get_msg_count(cid) for cid in self.history)
        chat_count = len(self.history)

        key_status = {}
        for p in PROVIDER_MODELS:
            k = self.config.get(f"{p}_api_key", "")
            key_status[p] = "🟢" if k else "🔴"

        keys_line = "  ".join(f"{mark} {p}" for p, mark in key_status.items())

        ffmpeg_status = "✅ установлен" if self._ffmpeg_available else "❌ не установлен"

        text = (
            "<tg-emoji emoji-id=5985780596268339498>🤖</tg-emoji> <b>AIRoute — Статус</b>\n\n"
            f"📡 <b>Провайдер (текст):</b> <code>{provider}</code> → <code>{model}</code>\n"
            f"🖼 <b>Провайдер (фото):</b> <code>{img_provider}</code> → <code>{img_model}</code>\n"
            f"🤖 <b>Агент:</b> {'✅ вкл' if agent else '❌ выкл'} | шагов: {steps}\n"
            f"🗜 <b>История:</b> {total_exchanges} запр. в {chat_count} чатах\n"
            f"🎬 <b>FFmpeg:</b> {ffmpeg_status}\n\n"
            f"<b>Ключи:</b>\n{keys_line}"
        )
        btns = [
            [
                {"text": "⚙️ Конфиг", "callback": self._cfg_back_cb, "args": ()},
                {"text": "🤖 Агент", "callback": self._cfg_toggle_agent_cb, "args": ()},
            ],
            [
                {"text": "🔀 Провайдер", "callback": self._switch_provider_cb, "args": ()},
                {"text": "🧹 Сброс памяти", "callback": self._cfg_reset_all_cb, "args": ()},
            ],
            [{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}],
        ]
        await self._safe_inline(message, text, btns)

    @loader.command()
    async def askillcmd(self, message: Message):
        """[name|list|delete name] — управление скиллами (системными промптами)"""
        args = utils.get_args_raw(message).strip()

        if not args or args == "list":
            if not self.skills:
                skills_text = "<i>Скиллов нет</i>"
            else:
                skills_text = "\n".join(
                    f"• <code>{k}</code>" for k in self.skills
                )
            text = f"📚 <b>Сохранённые скиллы:</b>\n{skills_text}"
            btns = []
            if self.skills:
                row = []
                for name in list(self.skills.keys())[:20]:
                    row.append({"text": name, "callback": self._skill_apply_cb, "args": (name,)})
                    if len(row) == 2:
                        btns.append(row); row = []
                if row: btns.append(row)
            btns.append([{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}])
            return await self._safe_inline(message, text, btns)

        if args.startswith("delete "):
            name = args[7:].strip()
            if name in self.skills:
                del self.skills[name]
                self._save_db()
                return await utils.answer(message, f"🗑 <b>Скилл</b> <code>{name}</code> <b>удалён</b>")
            return await utils.answer(message, f"❌ Скилл <code>{name}</code> не найден")

        if args in self.skills:
            self._set_provider_prompt(self.config["active_provider"], self.skills[args])
            return await utils.answer(
                message,
                f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
                f"<b>Скилл</b> <code>{args}</code> <b>применён к {self.config['active_provider']}</b>",
            )

        reply = await message.get_reply_message()
        if reply and reply.text:
            self.skills[args] = reply.text
            self._save_db()
            return await utils.answer(
                message,
                f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
                f"<b>Скилл</b> <code>{args}</code> <b>сохранён!</b>\n"
                f"<blockquote>{utils.escape_html(reply.text[:200])}</blockquote>",
            )

        await utils.answer(
            message,
            "❌ Реплайни на сообщение с промптом, чтобы сохранить скилл.\n"
            "Или используй <code>.askill list</code> для просмотра.",
        )

    async def _skill_apply_cb(self, call: InlineCall, name: str):
        if name not in self.skills:
            return await call.answer("Скилл не найден", show_alert=True)
        provider = self.config["active_provider"]
        self._set_provider_prompt(provider, self.skills[name])
        await call.answer(f"✅ {name} применён к {provider}", show_alert=False)
        await call.edit(
            f"<tg-emoji emoji-id=5776375003280838798>✅</tg-emoji> "
            f"<b>Скилл</b> <code>{name}</code> <b>→ {provider}</b>",
            reply_markup=[[{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}]],
        )

    @loader.command()
    async def ahelpcmd(self, message: Message):
        """— список команд AIRoute с кнопками"""
        ffmpeg_status = "✅" if self._ffmpeg_available else "❌"
        text = (
            "<tg-emoji emoji-id=5985780596268339498>🤖</tg-emoji> <b>AIRoute — Команды</b>\n\n"
            "<b>Основные:</b>\n"
            "• <code>.1a [текст]</code> — запрос к AI\n"
            "• <code>.1acode [текст]</code> — запрос → код-файл\n"
            "• <code>.1aimg [текст]</code> — генерация картинки\n"
            "• <code>.1aimg -ai [текст]</code> — улучшить промпт → картинка\n"
            "• <code>.1as [запрос]</code> — поиск в интернете + ответ AI\n\n"
            "<b>Мультимедиа (через reply):</b>\n"
            "• Фото — описание\n"
            "• Видео — анализ содержания\n"
            "• ГС (голосовые) — транскрипция\n"
            "• Кружки (видеозаметки) — анализ\n"
            "• Аудио/музыка — распознавание\n"
            f"• FFmpeg: {ffmpeg_status}\n\n"
            "<b>Управление:</b>\n"
            "• <code>.aprovider [name]</code> — сменить провайдер (+ custom)\n"
            "• <code>.aimgauth [name]</code> — провайдер картинок\n"
            "• <code>.amodel</code> — выбрать модель\n"
            "• <code>.amodel -s</code> — модели с реального API\n"
            "• <code>.ares</code> — сброс памяти чата\n"
            "• <code>.ares -a</code> — сброс всей памяти\n\n"
            "<b>Конфиг:</b>\n"
            "• <code>.aconfig</code> — инлайн конфиг\n"
            "• <code>.acfg [prov] [field] [val]</code> — задать параметр\n"
            "• <code>.aagent</code> — настройки агента\n"
            "• <code>.astat</code> — статус и статистика\n\n"
            "<b>Промпты:</b>\n"
            "• <code>.aprompt [текст]</code> — промпт текущего провайдера\n"
            "• <code>.askill [name]</code> — применить/сохранить скилл\n"
            "• <code>.askill list</code> — список скиллов\n\n"
            "<b>Прочее:</b>\n"
            "• <code>.acheck [ключи]</code> — проверить OpenAI ключи\n"
            "• <code>.atrack [on/off]</code> — читать ответы в диалогах\n\n"
            "<b>ИИ-тулы (без команды, по просьбе):</b>\n"
            "• Написать боту/человеку несколько сообщений подряд\n"
            "• Сменить имя / фамилию / юзернейм / bio\n"
            "• Создать скилл: «сохрани скилл [название] с текстом [...]»\n"
            "• Улучшить свой промпт: «улучши промпт — добавь X»\n"
            "• Выполнить JS-код: «посчитай/выполни через eval_js»\n"
        )
        btns = [
            [
                {"text": "⚙️ Конфиг", "callback": self._cfg_back_cb, "args": ()},
                {"text": "🤖 Агент", "callback": self._agent_steps_menu_cb, "args": ()},
            ],
            [
                {"text": "🔀 Провайдер", "callback": self._switch_provider_cb, "args": ()},
                {"text": "📊 Статус", "callback": self._astat_inline_cb, "args": ()},
            ],
            [{"text": "❌ Закрыть", "callback": self._close_menu_cb, "args": ()}],
        ]
        await self._safe_inline(message, text, btns)

    async def _astat_inline_cb(self, call: InlineCall):
        """Показать статус прямо из кнопки"""
        provider = self.config["active_provider"]
        model = self.config.get(f"{provider}_model", "—")
        total_msgs = sum(len(h) for h in self.history.values())
        agent = self.config["agent_mode"]
        text = (
            f"📡 <b>{provider.upper()}</b> → <code>{model}</code>\n"
            f"🤖 Агент: {'✅' if agent else '❌'} | "
            f"🗜 История: {total_msgs} сообщ."
        )
        await call.answer(text, show_alert=True)

    # ─── watcher: ИИ видит входящие ответы ─────────────────────────────────

    async def watcher(self, message: Message):
        """Перехватывает входящие сообщения от ботов/людей, добавляет в историю чата."""
        if not self.config.get("read_incoming", False):
            return
        # Только входящие (не наши) личные диалоги
        try:
            if not message or not message.is_private:
                return
            # Игнорируем собственные сообщения
            sender_id = getattr(message, "sender_id", None) or getattr(message, "from_id", None)
            if sender_id and hasattr(sender_id, "user_id"):
                sender_id = sender_id.user_id
            if sender_id == getattr(self.me, "id", None):
                return
            # Игнорируем системные/пустые сообщения
            if not message.text:
                return

            chat_id = message.chat_id
            # Только если в этом диалоге недавно писал ИИ (tracked) ИЛИ есть история
            cid = str(chat_id)
            has_history = bool(self._get_history(chat_id))
            is_tracked = (sender_id in self._tracked_dialogs) or has_history

            if not is_tracked:
                return

            # Определяем тип отправителя
            try:
                sender = await message.get_sender()
                is_bot = getattr(sender, "bot", False)
                sender_name = (
                    getattr(sender, "username", None)
                    or getattr(sender, "first_name", None)
                    or str(sender_id)
                )
            except Exception:
                is_bot = False
                sender_name = str(sender_id)

            who = "🤖 Бот" if is_bot else "👤 Человек"
            context_line = f"[{who} @{sender_name} ответил]: {message.text}"

            # Добавляем в историю как user-сообщение (чтобы ИИ видел при след. обращении)
            self._update_history(chat_id, "user", context_line)

        except Exception:
            pass

    @loader.command()
    async def atrackcmd(self, message: Message):
        """[on/off] — включить/выключить чтение входящих ответов ботов/людей"""
        args = utils.get_args_raw(message).strip().lower()
        if args == "on":
            self.config["read_incoming"] = True
            return await utils.answer(
                message,
                "👁 <b>Слежка за ответами включена.</b>\n"
                "ИИ будет видеть что отвечают боты и люди в диалогах, куда он пишет."
            )
        elif args == "off":
            self.config["read_incoming"] = False
            self._tracked_dialogs.clear()
            return await utils.answer(message, "🙈 <b>Слежка за ответами отключена.</b>")
        else:
            status = "✅ включена" if self.config.get("read_incoming", False) else "❌ выключена"
            await utils.answer(
                message,
                f"👁 <b>Слежка за ответами:</b> {status}\n\n"
                f"• <code>.atrack on</code> — включить\n"
                f"• <code>.atrack off</code> — выключить\n\n"
                f"Когда включено, ИИ видит ответы ботов и людей в диалогах "
                f"и может на них реагировать при следующем запросе."
            )
