# requires: google-genai markdown-it-py
# meta developer: @Sy4enish, @sekir0q, @Elynusae

import asyncio
import copy
import io
import logging
import random
import re
import uuid
from typing import Dict, List, Optional, Tuple

from google import genai
from google.genai import types as genai_types
from herokutl.extensions import html as heroku_html
from herokutl.tl.functions.messages import GetStickerSetRequest
from herokutl.tl.types import InputStickerSetShortName, Message
from herokutl.utils import get_display_name
from markdown_it import MarkdownIt

from .. import loader, utils

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 120.0


@loader.tds
class GeminiResponderMod(loader.Module):
    """умный автоответчик на базе google gemini со стикерами"""

    strings = {"name": "GeminiResponder"}
    strings_ru = strings

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "API_KEY",
                "",
                "API ключ Gemini",
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "ENABLED",
                False,
                "Включить автоответчик",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "CHATS",
                [],
                "Список ID чатов, где модуль отвечает",
                validator=loader.validators.Series(loader.validators.Integer()),
            ),
            loader.ConfigValue(
                "SYSTEM_PROMPT",
                "ты бот",
                "Системная инструкция",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "MODEL",
                "gemini-2.5-flash",
                "Модель Gemini",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "HISTORY_LIMIT",
                10,
                "Сколько последних диалоговых ходов помнить на чат",
                validator=loader.validators.Integer(minimum=0, maximum=50),
            ),
            loader.ConfigValue(
                "MAX_CHARS",
                50,
                "Максимум символов в ответе",
                validator=loader.validators.Integer(minimum=0, maximum=4000),
            ),
            loader.ConfigValue(
                "TYPING_DELAY",
                True,
                "Включить имитацию печатания",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "RANDOM_TALK",
                False,
                "Включить ответы на случайные сообщения",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "RANDOM_CHANCE",
                10,
                "Шанс случайного ответа от 0 до 100",
                validator=loader.validators.Integer(minimum=0, maximum=100),
            ),
            loader.ConfigValue(
                "IGNORE_USERS",
                [],
                "Список ID игнорируемых пользователей",
                validator=loader.validators.Series(loader.validators.Integer()),
            ),
            loader.ConfigValue(
                "USE_STICKERS",
                True,
                "Включить отправку стикеров",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "STICKER_PACK",
                "HikariNozomifxst",
                "Название или ссылка на стикерпак",
                validator=loader.validators.String(),
            ),
        )

        self.chat_sessions: Dict[int, List[genai_types.Content]] = {}
        self.chat_locks: Dict[int, asyncio.Lock] = {}
        self.me = None
        self.sticker_mapping = {}
        self.current_pack = ""
        self.gmodel_picker_cache = {}

    async def client_ready(self, client, db):
        self.client = client
        self._db = db
        self.me = await client.get_me()
        logger.info("[GeminiResponder] модуль успешно запущен")

    def _get_chats_list(self) -> List[int]:
        return [int(chat_id) for chat_id in (self.config["CHATS"] or [])]

    def _get_ignore_list(self) -> List[int]:
        return [int(user_id) for user_id in (self.config["IGNORE_USERS"] or [])]

    def _get_lock(self, chat_id: int) -> asyncio.Lock:
        if chat_id not in self.chat_locks:
            self.chat_locks[chat_id] = asyncio.Lock()
        return self.chat_locks[chat_id]

    def _message_has_image(self, message: Message) -> bool:
        if getattr(message, "photo", None):
            return True

        document = getattr(message, "document", None)
        mime_type = getattr(document, "mime_type", "") if document else ""
        return bool(document and mime_type.startswith("image/"))

    async def _extract_image_from_message(
        self, message: Message
    ) -> Tuple[Optional[bytes], Optional[str]]:
        if getattr(message, "photo", None):
            return await message.download_media(bytes), "image/jpeg"

        document = getattr(message, "document", None)
        mime_type = getattr(document, "mime_type", "") if document else ""
        if document and mime_type.startswith("image/"):
            return await message.download_media(bytes), mime_type

        return None, None

    async def _extract_image_from_reply(
        self, message: Message
    ) -> Tuple[Optional[bytes], Optional[str]]:
        reply = await message.get_reply_message()
        if not reply:
            return None, None

        return await self._extract_image_from_message(reply)

    async def _get_pack_mapping(self):
        pack_name = str(self.config["STICKER_PACK"] or "").strip().split("/")[-1]

        if self.sticker_mapping and self.current_pack == pack_name:
            return self.sticker_mapping

        self.sticker_mapping = {}
        self.current_pack = pack_name

        if not pack_name:
            return self.sticker_mapping

        try:
            pack = await self.client(
                GetStickerSetRequest(
                    InputStickerSetShortName(short_name=pack_name),
                    0,
                )
            )
            doc_map = {doc.id: doc for doc in pack.documents}
            for pack_item in pack.packs:
                for doc_id in pack_item.documents:
                    doc = doc_map.get(doc_id)
                    if doc:
                        self.sticker_mapping[pack_item.emoticon] = doc
        except Exception as e:
            logger.error(
                f"[GeminiResponder] ошибка при загрузке стикерпака: {e}"
            )

        return self.sticker_mapping

    def _build_generation_config(
        self,
        *,
        with_safety: bool = True,
    ) -> genai_types.GenerateContentConfig:
        config_kwargs = {}
        system_prompt = str(self.config["SYSTEM_PROMPT"] or "").strip()
        if system_prompt:
            config_kwargs["system_instruction"] = system_prompt

        if with_safety:
            config_kwargs["safety_settings"] = [
                genai_types.SafetySetting(
                    category="HARM_CATEGORY_HARASSMENT",
                    threshold="BLOCK_NONE",
                ),
                genai_types.SafetySetting(
                    category="HARM_CATEGORY_HATE_SPEECH",
                    threshold="BLOCK_NONE",
                ),
                genai_types.SafetySetting(
                    category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    threshold="BLOCK_NONE",
                ),
                genai_types.SafetySetting(
                    category="HARM_CATEGORY_DANGEROUS_CONTENT",
                    threshold="BLOCK_NONE",
                ),
            ]

        return genai_types.GenerateContentConfig(**config_kwargs)

    async def _generate_content(
        self,
        api_key: str,
        contents: List[genai_types.Content],
    ):
        async with genai.Client(api_key=api_key).aio as client:
            try:
                return await asyncio.wait_for(
                    client.models.generate_content(
                        model=str(self.config["MODEL"] or "").strip(),
                        contents=contents,
                        config=self._build_generation_config(with_safety=True),
                    ),
                    timeout=REQUEST_TIMEOUT,
                )
            except Exception as e:
                error_text = str(e).lower()
                if "safety" not in error_text and "block_none" not in error_text:
                    raise

                logger.warning(
                    "[GeminiResponder] safety settings rejected, retrying without them"
                )

                return await asyncio.wait_for(
                    client.models.generate_content(
                        model=str(self.config["MODEL"] or "").strip(),
                        contents=contents,
                        config=self._build_generation_config(with_safety=False),
                    ),
                    timeout=REQUEST_TIMEOUT,
                )

    def _extract_response_text(self, response) -> str:
        try:
            text = response.text
            if text:
                return str(text).strip()
        except Exception:
            pass

        chunks = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                text = getattr(part, "text", None)
                if text:
                    chunks.append(str(text))

        return "\n".join(chunks).strip()

    def _extract_model_content(self, response, reply_text: str):
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            if content and getattr(content, "parts", None):
                return content

        if reply_text:
            return genai_types.Content(
                role="model",
                parts=[genai_types.Part.from_text(text=reply_text)],
            )

        return None

    def _sanitize_reply_text(self, text: str) -> str:
        text = re.sub(r"@\w+", "", str(text or "")).strip()
        return text

    def _should_relax_length_limit(self, text: str) -> bool:
        text = str(text or "").lower()
        if not text:
            return False

        keywords = (
            "формат",
            "форматирован",
            "markdown",
            "html",
            "blockquote",
            "expandable",
            "спойлер",
            "spoiler",
            "код",
            "code",
            "python",
            "тег",
            "разметк",
        )
        return any(keyword in text for keyword in keywords)

    def _markdown_to_html(self, text: str) -> str:
        text = re.sub(r".*?", "", str(text or ""), flags=re.DOTALL)
        text = re.sub(r".*?", "", text, flags=re.DOTALL)
        text = re.sub(r"(?i)", "\n", text)

        def heading_replacer(match):
            level = len(match.group(1))
            title = match.group(2).strip()
            indent = "   " * (level - 1)
            return f"{indent}{title}"

        text = re.sub(r"^(#+)\s+(.*)", heading_replacer, text, flags=re.MULTILINE)

        def list_replacer(match):
            indent = match.group(1)
            return f"{indent}• "

        text = re.sub(r"^([ \t]*)[-*+]\s+", list_replacer, text, flags=re.MULTILINE)

        md = MarkdownIt("commonmark", {"html": True, "linkify": True})
        md.enable("strikethrough")
        md.disable("hr")
        md.disable("heading")
        md.disable("list")
        html_text = md.render(text)

        def format_code(match):
            lang = utils.escape_html(match.group(1).strip())
            code = utils.escape_html(match.group(2).strip())
            if lang:
                return f'{code}'
            return f"{code}"

        html_text = re.sub(r"```(.*?)\n([\s\S]+?)\n```", format_code, html_text)
        html_text = re.sub(r"([\s\S]*?)", r"\1", html_text, flags=re.DOTALL)
        html_text = html_text.replace("", "").replace("", "\n")
        html_text = re.sub(r"(?i)", "\n", html_text).strip()
        return html_text

    def _limit_rendered_html(self, html_text: str) -> str:
        max_chars = int(self.config["MAX_CHARS"] or 0)
        if max_chars <= 0 or not html_text:
            return html_text

        clean_text, entities = heroku_html.parse(html_text)
        if len(clean_text) <= max_chars:
            return html_text

        truncated_text = clean_text[:max_chars].rstrip()
        truncated_entities = []
        for entity in entities:
            if entity.offset >= len(truncated_text):
                continue

            available = len(truncated_text) - entity.offset
            if available <= 0:
                continue

            entity_copy = copy.copy(entity)
            entity_copy.length = min(entity.length, available)
            truncated_entities.append(entity_copy)

        return heroku_html.html_decoration.unparse(truncated_text, truncated_entities)

    def _render_reply_html(self, text: str, *, apply_limit: bool = True) -> str:
        html_text = self._markdown_to_html(text)
        if not html_text:
            return ""

        try:
            clean_text, entities = heroku_html.parse(html_text)
            html_text = heroku_html.html_decoration.unparse(clean_text, entities)
        except Exception as e:
            logger.warning("[GeminiResponder] html sanitize failed: %s", e)

        if apply_limit:
            try:
                html_text = self._limit_rendered_html(html_text)
            except Exception as e:
                logger.warning("[GeminiResponder] html limit failed: %s", e)

        return html_text

    def _trim_history(self, history: List[genai_types.Content]) -> List[genai_types.Content]:
        limit = int(self.config["HISTORY_LIMIT"] or 0)
        if limit <= 0:
            return []

        max_items = limit * 2
        if len(history) <= max_items:
            return list(history)

        return list(history[-max_items:])

    def _remember_turn(
        self,
        chat_id: int,
        user_content: genai_types.Content,
        model_content: Optional[genai_types.Content],
    ):
        limit = int(self.config["HISTORY_LIMIT"] or 0)
        if limit <= 0:
            self.chat_sessions.pop(chat_id, None)
            return

        history = list(self.chat_sessions.get(chat_id, []))
        history.append(user_content)
        if model_content is not None:
            history.append(model_content)

        self.chat_sessions[chat_id] = self._trim_history(history)

    def _build_prompt(
        self,
        sender_name: str,
        message_text: str,
        *,
        has_image: bool,
        mapping: Optional[dict] = None,
    ) -> str:
        safe_text = message_text or "[без текста]"
        if has_image and not message_text:
            safe_text = "[изображение]"

        prompt = f"[сообщение от {sender_name}]: {safe_text}"
        max_chars = int(self.config["MAX_CHARS"] or 0)

        instructions = []
        if max_chars > 0 and not self._should_relax_length_limit(message_text):
            instructions.append(f"ответь строго до {max_chars} символов")
        instructions.append("не упоминай никого через @")
        instructions.append("пиши только готовый ответ")
        instructions.append("если это делает ответ понятнее, используй телеграм-форматирование")
        instructions.append(
            'можно использовать markdown и html-теги , , , , , , ..., '
        )
        instructions.append("не используй неподдерживаемые html-теги и не ломай разметку")

        if self.config["USE_STICKERS"]:
            instructions.append("не пиши служебные теги и технические маркеры")

        return f"{prompt}\n\n[инструкция: {'; '.join(instructions)}]"

    def _build_request_content(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        image_mime: Optional[str] = None,
    ) -> genai_types.Content:
        parts = [genai_types.Part.from_text(text=prompt)]

        if image_bytes:
            parts.append(
                genai_types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=image_mime or "image/jpeg",
                )
            )

        return genai_types.Content(role="user", parts=parts)

    def _build_history_user_content(self, prompt: str) -> genai_types.Content:
        return genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=prompt)],
        )

    async def _simulate_typing(self, chat_id: int):
        delay = random.uniform(0.5, 1.2)
        async with self.client.action(chat_id, "typing"):
            await asyncio.sleep(delay)

    def _format_error(self, error: Exception) -> str:
        text = " ".join(str(error).split()).strip()
        if not text:
            return error.__class__.__name__
        if len(text) > 300:
            text = text[:297] + "..."
        return text

    def _normalize_emoji_token(self, value: str) -> str:
        return str(value or "").replace("\ufe0f", "").strip()

    def _resolve_sticker_doc(self, mapping: dict, emojis: List[str]):
        if not mapping:
            return None

        normalized_mapping = {
            self._normalize_emoji_token(emoji): doc
            for emoji, doc in mapping.items()
            if self._normalize_emoji_token(emoji)
        }

        for emoji in emojis:
            doc = normalized_mapping.get(self._normalize_emoji_token(emoji))
            if doc:
                return doc

        return None

    def _pick_auto_sticker_doc(
        self,
        reply_text: str,
        source_text: str,
        mapping: dict,
    ):
        if not mapping:
            return None

        reply_clean = str(reply_text or "").strip()
        source_clean = str(source_text or "").strip()
        if not reply_clean and not source_clean:
            return None

        normalized_reply = self._normalize_emoji_token(reply_clean)
        if normalized_reply:
            for emoji, doc in mapping.items():
                normalized_emoji = self._normalize_emoji_token(emoji)
                if normalized_emoji and normalized_emoji in normalized_reply:
                    return doc

        combined = f"{reply_clean}\n{source_clean}".lower()
        reply_lower = reply_clean.lower()

        rules = [
            (
                ("аха", "хаха", "лол", "кек", "ору", "орнул", "смешно", "ржу", "угар"),
                ["😂", "🤣", "😁", "😹"],
            ),
            (
                ("спасибо", "пасиб", "люблю", "обожаю", "мило", "няш", "класс", "супер", "круто", "ура", "молодец"),
                ["❤️", "🥰", "😍", "😘", "👍", "🔥"],
            ),
            (
                ("жаль", "груст", "печаль", "сочув", "соболез", "прости", "извини", "плак"),
                ["😢", "😭", "💔", "🙏"],
            ),
            (
                ("бесит", "ужас", "кошмар", "фигня", "ненавиж", "злит", "трэш"),
                ["😡", "🤬", "👎"],
            ),
            (
                ("вау", "ого", "офиг", "ничего себе", "жесть", "шок"),
                ["😮", "😳", "🤯", "🔥"],
            ),
        ]

        for keywords, emojis in rules:
            if any(keyword in combined for keyword in keywords):
                doc = self._resolve_sticker_doc(mapping, emojis)
                if doc:
                    return doc

        if "?" in source_clean or any(
            keyword in reply_lower
            for keyword in ("хм", "мм", "думаю", "не знаю", "возможно", "кажется", "наверно")
        ):
            doc = self._resolve_sticker_doc(mapping, ["🤔", "🧐", "😐"])
            if doc:
                return doc

        if len(reply_clean) <= 24 and any(
            keyword in reply_lower for keyword in ("ок", "окей", "ага", "да", "готово", "сделано", "хорошо")
        ):
            doc = self._resolve_sticker_doc(mapping, ["👍", "👌", "😎"])
            if doc:
                return doc

        return None

    def _get_prompt_stats(self, text: str) -> Tuple[int, int]:
        normalized = str(text or "").strip()
        if not normalized:
            return 0, 0

        return len(normalized), len(normalized.splitlines())

    async def _extract_prompt_text_from_reply(
        self, message: Message
    ) -> Tuple[Optional[str], Optional[str]]:
        reply = await message.get_reply_message()
        if not reply:
            return None, ""

        document = getattr(reply, "document", None)
        if document:
            file_name = str(getattr(document, "file_name", "") or "").lower()
            mime_type = str(getattr(document, "mime_type", "") or "").lower()
            if mime_type and not mime_type.startswith("text/") and file_name:
                if not file_name.endswith((".txt", ".md", ".prompt", ".log", ".json")):
                    return None, "⚠️ файл должен быть текстовым"

            data = await reply.download_media(bytes)
            if not data:
                return None, "⚠️ не удалось прочитать файл"

            if len(data) > 1024 * 1024:
                return None, "⚠️ файл слишком большой (лимит 1 МБ)"

            for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1251"):
                try:
                    text = data.decode(encoding).strip()
                except Exception:
                    continue

                if text:
                    return text, None

            return None, "⚠️ не удалось декодировать файл как текст"

        reply_text = str(getattr(reply, "raw_text", "") or "").strip()
        if reply_text:
            return reply_text, None

        return None, "⚠️ реплайни на текст или текстовый файл"

    async def _fetch_gmodel_entries(self, query: str = "") -> List[str]:
        api_key = str(self.config["API_KEY"] or "").strip()
        if not api_key:
            raise ValueError("❌ api ключ не настроен")

        query = str(query or "").strip().lower()
        entries = set()

        async with genai.Client(api_key=api_key).aio as client:
            pager = await client.models.list()
            async for item in pager:
                model_name = str(getattr(item, "name", "") or "").split("/")[-1].strip()
                if not model_name.startswith("gemini-"):
                    continue
                if query and query not in model_name.lower():
                    continue
                entries.add(model_name)

        return sorted(entries)

    def _build_gmodel_plain_text(self, models: List[str], query: str = "") -> str:
        current_model = str(self.config["MODEL"] or "").strip()
        lines = [
            "🧠 Выбор модели",
            f"• Текущая: {utils.escape_html(current_model or '-')}",
            f"• Найдено: {len(models)}",
        ]
        if query:
            lines.append(
                f"• Фильтр: {utils.escape_html(query)}"
            )
        lines.append("")
        lines.extend(f"• {utils.escape_html(model)}" for model in models)
        return "\n".join(lines)

    async def _open_gmodel_picker(
        self, message: Message, models: List[str], query: str = ""
    ) -> bool:
        uid = uuid.uuid4().hex[:8]
        self.gmodel_picker_cache[uid] = {
            "models": list(models),
            "query": str(query or "").strip(),
            "chat_id": utils.get_chat_id(message),
        }

        try:
            await self._render_gmodel_picker(uid, 0, message)
            return True
        except Exception:
            self.gmodel_picker_cache.pop(uid, None)
            return False

    async def _render_gmodel_picker(self, uid: str, page_num: int, entity):
        data = self.gmodel_picker_cache.get(uid)
        if not data:
            if hasattr(entity, "edit"):
                await entity.edit(
                    "⚠️ Список моделей устарел. Открой .rmod -s заново.",
                    reply_markup=None,
                )
            return

        models = data.get("models") or []
        if not models:
            if hasattr(entity, "edit"):
                await entity.edit("⚠️ Не удалось получить список моделей.", reply_markup=None)
            return

        page_size = 8
        total_pages = max((len(models) + page_size - 1) // page_size, 1)
        page_num = max(0, min(page_num, total_pages - 1))
        start = page_num * page_size
        page_models = models[start:start + page_size]
        current_model = str(self.config["MODEL"] or "").strip()
        query = str(data.get("query") or "").strip()

        text_lines = [
            "🧠 Выбор модели",
            f"• Текущая: {utils.escape_html(current_model or '-')}",
            f"• Найдено: {len(models)}",
        ]
        if query:
            text_lines.append(
                f"• Фильтр: {utils.escape_html(query)}"
            )
        text_lines.extend(
            [
                "",
                "Нажми на кнопку ниже, чтобы установить модель.",
            ]
        )
        text = "\n".join(text_lines)

        buttons = []
        for offset, model_name in enumerate(page_models):
            absolute_index = start + offset
            prefix = "✅ " if model_name == current_model else ""
            label = f"{prefix}{model_name}"
            if len(label) > 32:
                label = label[:29] + "..."
            buttons.append(
                [
                    {
                        "text": label,
                        "data": f"gresponder:gmsel:{uid}:{absolute_index}",
                    }
                ]
            )

        nav_row = []
        if page_num > 0:
            nav_row.append(
                {"text": "◀️", "data": f"gresponder:gmpg:{uid}:{page_num - 1}"}
            )
        nav_row.append({"text": f"{page_num + 1}/{total_pages}", "data": "gresponder:noop"})
        if page_num < total_pages - 1:
            nav_row.append(
                {"text": "▶️", "data": f"gresponder:gmpg:{uid}:{page_num + 1}"}
            )
        buttons.append(nav_row)
        buttons.append([{"text": "❌ Закрыть", "data": f"gresponder:gmclose:{uid}"}])

        if isinstance(entity, Message):
            if not await self.inline.form(text=text, message=entity, reply_markup=buttons):
                raise RuntimeError("inline unavailable")
            return

        await entity.edit(text=text, reply_markup=buttons)

    async def roncmd(self, message):
        """включить автоответчик"""
        self.config["ENABLED"] = True
        await utils.answer(message, "✅ включен")

    async def roffcmd(self, message):
        """выключить автоответчик"""
        self.config["ENABLED"] = False
        await utils.answer(message, "❌ выключен")

    async def raddcmd(self, message):
        """добавить текущий чат в разрешенные"""
        chat_id = int(message.chat_id)
        chats = self._get_chats_list()
        if chat_id not in chats:
            chats.append(chat_id)
            self.config["CHATS"] = chats
            await utils.answer(message, "➕ чат добавлен")
        else:
            await utils.answer(message, "⚠️ уже в списке")

    async def rdelcmd(self, message):
        """удалить текущий чат из разрешенных"""
        chat_id = int(message.chat_id)
        chats = self._get_chats_list()
        if chat_id in chats:
            chats.remove(chat_id)
            self.config["CHATS"] = chats
            self.chat_sessions.pop(chat_id, None)
            await utils.answer(message, "➖ чат удален")
        else:
            await utils.answer(message, "⚠️ чата нет в списке")

    async def rclrcmd(self, message):
        """очистить историю текущего чата"""
        chat_id = int(message.chat_id)
        if chat_id in self.chat_sessions:
            del self.chat_sessions[chat_id]
            await utils.answer(message, "🗑 история очищена")
        else:
            await utils.answer(message, "⚠️ история пуста")

    async def rrstcmd(self, message):
        """сбросить память во всех чатах"""
        self.chat_sessions.clear()
        await utils.answer(message, "♻️ память сброшена везде")

    async def rprcmd(self, message):
        """[текст] | изменить промпт; reply на текст/файл; -c очистить"""
        args = utils.get_args_raw(message).strip()
        if args in {"-c", "--clear"}:
            self.config["SYSTEM_PROMPT"] = ""
            self.chat_sessions.clear()
            await utils.answer(message, "✅ промпт очищен")
            return

        if not args:
            prompt_text, error_text = await self._extract_prompt_text_from_reply(message)
            if prompt_text is not None:
                args = prompt_text
            elif error_text:
                await utils.answer(message, error_text)
                return
            else:
                current_prompt = str(self.config["SYSTEM_PROMPT"] or "").strip()
                if current_prompt:
                    await utils.answer(
                        message,
                        f"ℹ️ текущий промпт:\n{utils.escape_html(current_prompt)}",
                    )
                else:
                    await utils.answer(message, "ℹ️ промпт пуст")
                return

        self.config["SYSTEM_PROMPT"] = args.strip()
        self.chat_sessions.clear()
        char_count, line_count = self._get_prompt_stats(args)
        await utils.answer(
            message,
            f"✅ промпт обновлен\n• строк: {line_count}\n• длина: {char_count} символов",
        )

    async def rmodcmd(self, message):
        """[модель] [-s] | показать или сменить модель; -s список моделей"""
        args_raw = utils.get_args_raw(message).strip()
        args_list = args_raw.split()
        is_list_request = "-s" in args_list
        query = " ".join(token for token in args_list if token != "-s").strip()

        if is_list_request:
            status_msg = await utils.answer(message, "⏳ получаю список моделей...")
            try:
                models = await self._fetch_gmodel_entries(query)
                if not models:
                    return await utils.answer(status_msg, "⚠️ Не удалось получить список моделей.")
                await status_msg.delete()
                opened = await self._open_gmodel_picker(message, models, query)
                if not opened:
                    text = self._build_gmodel_plain_text(models, query)
                    file_obj = io.BytesIO(text.encode("utf-8"))
                    file_obj.name = "models_list.txt"
                    await self.client.send_file(
                        message.chat_id,
                        file=file_obj,
                        caption="📋 Список доступных моделей",
                        reply_to=message.id,
                    )
            except Exception as e:
                await utils.answer(
                    status_msg,
                    f"❌ ошибка: {utils.escape_html(self._format_error(e))}",
                )
            return

        if not args_raw:
            await utils.answer(
                message,
                f"ℹ️ текущая модель: {utils.escape_html(str(self.config['MODEL']))}",
            )
            return

        self.config["MODEL"] = args_raw.strip()
        self.chat_sessions.clear()
        await utils.answer(
            message,
            f"✅ модель изменена на {utils.escape_html(args_raw.strip())}",
        )

    async def rstatcmd(self, message):
        """показать статус, модель и настройки"""
        status = "🟢 активен" if self.config["ENABLED"] else "🔴 отключен"
        text = (
            f"📊 статистика GeminiResponder:\n\n"
            f"состояние: {status}\n"
            f"модель: {utils.escape_html(str(self.config['MODEL']))}\n"
            f"лимит символов: {self.config['MAX_CHARS']}\n"
            f"история: {self.config['HISTORY_LIMIT']} ходов\n"
            f"рандом мод: {'включен' if self.config['RANDOM_TALK'] else 'выключен'}\n"
            f"рандом шанс: {self.config['RANDOM_CHANCE']}%\n"
            f"стикеры: {'да' if self.config['USE_STICKERS'] else 'нет'}\n"
            f"пак стикеров: {utils.escape_html(str(self.config['STICKER_PACK']).split('/')[-1])}\n"
            f"активных сессий: {len(self.chat_sessions)}"
        )
        await utils.answer(message, text)

    async def rigncmd(self, message):
        """ добавить пользователя в игнор"""
        reply = await message.get_reply_message()
        user_id = reply.sender_id if reply else None

        if not user_id:
            args = utils.get_args_raw(message)
            user_id = int(args) if args and args.lstrip("-").isdigit() else None

        if user_id is None:
            return await utils.answer(message, "укажи айди или реплайни")

        ignores = self._get_ignore_list()
        if user_id not in ignores:
            ignores.append(int(user_id))
            self.config["IGNORE_USERS"] = ignores
            await utils.answer(message, "✅ добавлен в игнор")
        else:
            await utils.answer(message, "⚠️ уже в игноре")

    async def runicmd(self, message):
        """ убрать пользователя из игнора"""
        reply = await message.get_reply_message()
        user_id = reply.sender_id if reply else None

        if not user_id:
            args = utils.get_args_raw(message)
            user_id = int(args) if args and args.lstrip("-").isdigit() else None

        if user_id is None:
            return await utils.answer(message, "укажи айди или реплайни")

        ignores = self._get_ignore_list()
        if user_id in ignores:
            ignores.remove(int(user_id))
            self.config["IGNORE_USERS"] = ignores
            await utils.answer(message, "✅ убран из игнора")
        else:
            await utils.answer(message, "⚠️ его там нет")

    async def rstkcmd(self, message):
        """включить или выключить автостикеры"""
        self.config["USE_STICKERS"] = not self.config["USE_STICKERS"]
        state = "включены" if self.config["USE_STICKERS"] else "выключены"
        await utils.answer(message, f"стикеры {state}")

    async def rchatcmd(self, message):
        """включить или выключить случайные ответы в чатах"""
        self.config["RANDOM_TALK"] = not self.config["RANDOM_TALK"]
        state = "включены" if self.config["RANDOM_TALK"] else "выключены"
        await utils.answer(message, f"случайные ответы всем {state}")

    async def rrndcmd(self, message):
        """<0-100> установить шанс случайного ответа"""
        args = utils.get_args_raw(message)
        if not args or not args.lstrip("-").isdigit():
            return await utils.answer(
                message, f"текущий шанс: {self.config['RANDOM_CHANCE']}%"
            )

        chance = int(args)
        if chance < 0 or chance > 100:
            return await utils.answer(message, "⚠️ укажи число от 0 до 100")

        self.config["RANDOM_CHANCE"] = chance
        await utils.answer(message, f"шанс установлен на {chance}%")

    async def raskcmd(self, message):
        """[текст] | ручной запрос; reply на картинку тоже работает"""
        args = utils.get_args_raw(message).strip()
        image_bytes, image_mime = await self._extract_image_from_reply(message)

        if not args and not image_bytes:
            return await utils.answer(message, "⚠️ напишите текст запроса")

        api_key = str(self.config["API_KEY"] or "").strip()
        if not api_key:
            return await utils.answer(message, "❌ api ключ не настроен")

        msg = await utils.answer(message, "⏳ нейросеть думает...")

        try:
            prompt = args or "Опиши это изображение."
            request_content = self._build_request_content(prompt, image_bytes, image_mime)
            response = await self._generate_content(api_key, [request_content])
            reply_text = self._sanitize_reply_text(self._extract_response_text(response))

            if not reply_text:
                logger.warning(
                    "[GeminiResponder] получен пустой ответ при ручном запросе"
                )
                return await utils.answer(msg, "❌ пустой ответ")

            formatted_reply = self._render_reply_html(reply_text, apply_limit=False)
            try:
                await utils.answer(msg, formatted_reply or reply_text)
            except Exception as e:
                logger.error(f"[GeminiResponder] ошибка при ручном ответе: {e}")
                await utils.answer(msg, reply_text, parse_mode=None)
        except asyncio.TimeoutError:
            logger.error("[GeminiResponder] превышено время ожидания ответа от Gemini")
            await utils.answer(msg, "❌ gemini завис, попробуй еще раз")
        except Exception as e:
            logger.error(f"[GeminiResponder] фатальная ошибка ручного запроса: {e}")
            await utils.answer(msg, f"❌ ошибка: {utils.escape_html(self._format_error(e))}")

    async def watcher(self, message: Message):
        if not self.config["ENABLED"] or getattr(message, "out", False):
            return

        if getattr(message, "is_channel", False) and not getattr(message, "is_group", False):
            return

        message_text = str(getattr(message, "raw_text", "") or "").strip()
        has_image = self._message_has_image(message)
        if not message_text and not has_image:
            return

        if int(message.sender_id or 0) in self._get_ignore_list():
            return

        if int(message.chat_id) not in self._get_chats_list():
            return

        is_reply_to_me = False
        if message.is_reply:
            reply = await message.get_reply_message()
            if reply and self.me and reply.sender_id == self.me.id:
                is_reply_to_me = True

        is_mentioned = getattr(message, "mentioned", False)
        if (
            not is_mentioned
            and self.me
            and getattr(self.me, "username", None)
            and message_text
            and f"@{self.me.username.lower()}" in message_text.lower()
        ):
            is_mentioned = True

        is_private = getattr(message, "is_private", False)
        is_random = False
        if not is_reply_to_me and not is_mentioned and not is_private:
            if self.config["RANDOM_TALK"]:
                chance = int(self.config["RANDOM_CHANCE"] or 0)
                if chance > 0 and random.randint(1, 100) <= chance:
                    is_random = True
            if not is_random:
                return

        api_key = str(self.config["API_KEY"] or "").strip()
        if not api_key:
            logger.warning(
                "[GeminiResponder] запрос пропущен: не настроен api ключ"
            )
            return

        lock = self._get_lock(int(message.chat_id))
        async with lock:
            try:
                sender = await message.get_sender()
                sender_name = get_display_name(sender) if sender else "неизвестно"
                image_bytes, image_mime = (
                    await self._extract_image_from_message(message) if has_image else (None, None)
                )

                mapping = {}
                if self.config["USE_STICKERS"]:
                    mapping = await self._get_pack_mapping()

                prompt = self._build_prompt(
                    sender_name,
                    message_text,
                    has_image=bool(image_bytes),
                    mapping=mapping,
                )

                history = list(self.chat_sessions.get(int(message.chat_id), []))
                request_content = self._build_request_content(prompt, image_bytes, image_mime)
                history_content = self._build_history_user_content(prompt)
                request_contents = history + [request_content]

                async with self.client.action(message.chat_id, "typing"):
                    response = await self._generate_content(api_key, request_contents)

                reply_text = self._extract_response_text(response)

                sticker_to_send = None
                if self.config["USE_STICKERS"] and reply_text:
                    sticker_match = re.search(r"\[STICKER:(.+?)\]", reply_text)
                    if sticker_match:
                        reaction_emoji = sticker_match.group(1).strip()
                        reply_text = reply_text.replace(sticker_match.group(0), "").strip()
                        if reaction_emoji in mapping:
                            sticker_to_send = mapping[reaction_emoji]
                        else:
                            logger.warning(
                                "[GeminiResponder] нейросеть выбрала эмодзи %s, но его нет в паке",
                                reaction_emoji,
                            )

                reply_text = self._sanitize_reply_text(reply_text)
                if self.config["USE_STICKERS"] and not sticker_to_send and reply_text:
                    sticker_to_send = self._pick_auto_sticker_doc(
                        reply_text,
                        message_text,
                        mapping,
                    )

                model_content = self._extract_model_content(response, reply_text)
                self._remember_turn(int(message.chat_id), history_content, model_content)

                if not reply_text and not sticker_to_send:
                    logger.warning(
                        "[GeminiResponder] нейросеть вернула пустой ответ без стикера"
                    )
                    return

                if self.config["TYPING_DELAY"]:
                    await self._simulate_typing(int(message.chat_id))

                if reply_text:
                    formatted_reply = self._render_reply_html(
                        reply_text,
                        apply_limit=not self._should_relax_length_limit(message_text),
                    )
                    try:
                        await utils.answer(
                            message,
                            formatted_reply or reply_text,
                            reply_to=message.id,
                        )
                    except Exception as e:
                        logger.error(
                            f"[GeminiResponder] ошибка при отправке текста: {e}"
                        )
                        await message.reply(reply_text, parse_mode=None)

                if sticker_to_send:
                    try:
                        await self.client.send_file(
                            message.chat_id,
                            sticker_to_send
                        )
                    except Exception as e:
                        logger.error(
                            f"[GeminiResponder] ошибка при отправке стикера: {e}"
                        )
            except asyncio.TimeoutError:
                logger.error(
                    "[GeminiResponder] превышено время ожидания ответа от Gemini"
                )
            except Exception as e:
                logger.error(f"[GeminiResponder] критическая ошибка watcher: {e}")
                error_text = str(e).lower()
                if "api_key_invalid" in error_text or "api key not valid" in error_text:
                    self.config["ENABLED"] = False
                    logger.error(
                        "[GeminiResponder] модуль отключен из-за неверного api ключа"
                    )

    @loader.callback_handler()
    async def gemini_responder_callback_handler(self, call):
        data = str(getattr(call, "data", "") or "")
        if not data.startswith("gresponder:"):
            return

        parts = data.split(":")
        action = parts[1]

        if action == "noop":
            await call.answer()
            return

        if action == "gmclose":
            uid = parts[2]
            self.gmodel_picker_cache.pop(uid, None)
            try:
                await call.answer()
            except Exception:
                pass
            try:
                await call.edit("🗑 Выбор модели закрыт.", reply_markup=None)
            except Exception:
                pass
            return

        if action == "gmpg":
            uid = parts[2]
            page = int(parts[3])
            await self._render_gmodel_picker(uid, page, call)
            return

        if action == "gmsel":
            uid = parts[2]
            model_index = int(parts[3])
            data = self.gmodel_picker_cache.get(uid)
            if not data:
                await call.answer(
                    "⚠️ Список моделей устарел. Открой .rmod -s заново.",
                    show_alert=True,
                )
                return

            models = data.get("models") or []
            if model_index < 0 or model_index >= len(models):
                await call.answer(
                    "⚠️ Список моделей устарел. Открой .rmod -s заново.",
                    show_alert=True,
                )
                return

            model_name = str(models[model_index]).strip()
            if not model_name:
                await call.answer(
                    "⚠️ Список моделей устарел. Открой .rmod -s заново.",
                    show_alert=True,
                )
                return

            self.config["MODEL"] = model_name
            self.chat_sessions.clear()
            try:
                await call.answer(
                    f"✅ Модель установлена: {model_name}",
                    show_alert=False,
                )
            except Exception:
                pass
            await self._render_gmodel_picker(uid, model_index // 8, call)
