# requires: google-generativeai protobuf==3.20.3
# meta developer: @Sy4enish, @sekir0q, @Elynusae

import logging
import asyncio
import random
import re
import google.generativeai as genai
from telethon.tl.types import Message, InputStickerSetShortName
from telethon.tl.functions.messages import GetStickerSetRequest
from telethon.utils import get_display_name
from .. import loader, utils

logger = logging.getLogger(__name__)

class GeminiResponderMod(loader.Module):
    """умный автоответчик на базе google gemini со стикерами"""
    strings = {"name": "GeminiResponder"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            "API_KEY", "", "api ключ (скрыт)",
            "CHATS", [], "список айди чатов",
            "SYSTEM_PROMPT", "ты бот", "инструкция",
            "MODEL", "gemini-3-pro-preview", "название модели",
            "HISTORY_LIMIT", 10, "сообщений помнить",
            "MAX_CHARS", 50, "максимум символов",
            "TYPING_DELAY", True, "включить имитацию печатания",
            "RANDOM_TALK", False, "включить ответы на случайные сообщения",
            "RANDOM_CHANCE", 10, "шанс ответа на рандомное сообщение от 0 до 100",
            "IGNORE_USERS", [], "список айди игнора",
            "USE_STICKERS", True, "включить отправку стикеров",
            "STICKER_PACK", "HikariNozomifxst", "ссылка или название стикерпака"
        )
        self.is_active = False
        self.chat_sessions = {}
        self.me = None
        self.sticker_mapping = {}
        self.all_stickers = []
        self.current_pack = ""

    async def client_ready(self, client, db):
        self.client = client
        self.me = await client.get_me()
        logger.info("[GeminiResponder] модуль успешно запущен")

    def _get_chats_list(self):
        chats = self.config["CHATS"]
        if isinstance(chats, (int, str)):
            return [chats]
        return list(chats)

    async def _get_chat_name(self, chat_id):
        try:
            entity = await self.client.get_entity(int(chat_id))
            return get_display_name(entity)
        except Exception:
            return str(chat_id)

    async def _get_pack_mapping(self):
        pack_name = self.config["STICKER_PACK"].strip().split('/')[-1]
        
        if self.sticker_mapping and self.all_stickers and self.current_pack == pack_name:
            return self.sticker_mapping, self.all_stickers
            
        self.sticker_mapping = {}
        self.all_stickers = []
        self.current_pack = pack_name
        
        try:
            pack = await self.client(GetStickerSetRequest(
                InputStickerSetShortName(short_name=pack_name),
                0
            ))
            for doc in pack.documents:
                self.all_stickers.append(doc)
            for p in pack.packs:
                for doc_id in p.documents:
                    doc = next((d for d in pack.documents if d.id == doc_id), None)
                    if doc:
                        self.sticker_mapping[p.emoticon] = doc
        except Exception as e:
            logger.error(f"[GeminiResponder] ошибка при загрузке стикерпака: {e}")
            
        return self.sticker_mapping, self.all_stickers

    async def goncmd(self, message):
        """включить автоответчик"""
        self.is_active = True
        await utils.answer(message, "✅ включен")

    async def goffcmd(self, message):
        """выключить автоответчик"""
        self.is_active = False
        await utils.answer(message, "❌ выключен")

    async def gaddcmd(self, message):
        """добавить чат в разрешенные"""
        chat_id = message.chat_id
        chats = self._get_chats_list()
        if chat_id not in chats:
            chats.append(chat_id)
            self.config["CHATS"] = chats
            await utils.answer(message, "➕ чат добавлен")
        else:
            await utils.answer(message, "⚠️ уже в списке")

    async def gdelcmd(self, message):
        """удалить чат из разрешенных"""
        chat_id = message.chat_id
        chats = self._get_chats_list()
        if chat_id in chats:
            chats.remove(chat_id)
            self.config["CHATS"] = chats
            await utils.answer(message, "➖ чат удален")
        else:
            await utils.answer(message, "⚠️ чата нет в списке")

    async def gclearcmd(self, message):
        """очистить историю диалога"""
        chat_id = message.chat_id
        if chat_id in self.chat_sessions:
            del self.chat_sessions[chat_id]
            await utils.answer(message, "🗑 история очищена")
        else:
            await utils.answer(message, "⚠️ история пуста")

    async def gresetcmd(self, message):
        """сбросить память везде"""
        self.chat_sessions.clear()
        await utils.answer(message, "♻️ память сброшена везде")

    async def gpromptcmd(self, message):
        """<текст> изменить промпт"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, f"ℹ️ текущий промпт: {self.config['SYSTEM_PROMPT']}")
            return
        self.config["SYSTEM_PROMPT"] = args
        self.chat_sessions.clear()
        await utils.answer(message, f"✅ промпт изменен на:\n{args}")

    async def gmodelcmd(self, message):
        """<название> поменять модель"""
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, f"ℹ️ текущая модель: {self.config['MODEL']}")
            return
        self.config["MODEL"] = args
        self.chat_sessions.clear()
        await utils.answer(message, f"✅ модель изменена на {args}")

    async def gstatcmd(self, message):
        """показать статус"""
        status = "🟢 активен" if self.is_active else "🔴 отключен"
        text = (
            f"<b>📊 статистика GeminiResponder:</b>\n\n"
            f"<b>состояние:</b> {status}\n"
            f"<b>модель:</b> {self.config['MODEL']}\n"
            f"<b>лимит символов:</b> {self.config['MAX_CHARS']}\n"
            f"<b>рандом мод:</b> {'включен' if self.config['RANDOM_TALK'] else 'выключен'}\n"
            f"<b>рандом шанс:</b> {self.config['RANDOM_CHANCE']}%\n"
            f"<b>стикеры:</b> {'да' if self.config['USE_STICKERS'] else 'нет'}\n"
            f"<b>пак стикеров:</b> {self.config['STICKER_PACK'].split('/')[-1]}\n"
            f"<b>активных сессий:</b> {len(self.chat_sessions)}"
        )
        await utils.answer(message, text)

    async def gigncmd(self, message):
        """<id/reply> добавить в игнор"""
        reply = await message.get_reply_message()
        user_id = reply.sender_id if reply else None
        if not user_id:
            args = utils.get_args_raw(message)
            user_id = int(args) if args.isdigit() else None
        if not user_id:
            return await utils.answer(message, "укажи айди или реплайни")
        ignores = list(self.config["IGNORE_USERS"])
        if user_id not in ignores:
            ignores.append(user_id)
            self.config["IGNORE_USERS"] = ignores
            await utils.answer(message, "✅ добавлен в игнор")
        else:
            await utils.answer(message, "⚠️ уже в игноре")

    async def gunigncmd(self, message):
        """<id/reply> убрать из игнора"""
        reply = await message.get_reply_message()
        user_id = reply.sender_id if reply else None
        if not user_id:
            args = utils.get_args_raw(message)
            user_id = int(args) if args.isdigit() else None
        if not user_id:
            return await utils.answer(message, "укажи айди или реплайни")
        ignores = list(self.config["IGNORE_USERS"])
        if user_id in ignores:
            ignores.remove(user_id)
            self.config["IGNORE_USERS"] = ignores
            await utils.answer(message, "✅ убран из игнора")
        else:
            await utils.answer(message, "⚠️ его там нет")

    async def gstickcmd(self, message):
        """включить или выключить стикеры"""
        self.config["USE_STICKERS"] = not self.config["USE_STICKERS"]
        state = "включены" if self.config["USE_STICKERS"] else "выключены"
        await utils.answer(message, f"стикеры {state}")
        
    async def gchatcmd(self, message):
        """включить ответы всем подряд с шансом"""
        self.config["RANDOM_TALK"] = not self.config["RANDOM_TALK"]
        state = "включены" if self.config["RANDOM_TALK"] else "выключены"
        await utils.answer(message, f"случайные ответы всем {state}")

    async def grandomcmd(self, message):
        """<0-100> шанс случайного ответа"""
        args = utils.get_args_raw(message)
        if not args or not args.isdigit():
            return await utils.answer(message, f"текущий шанс: {self.config['RANDOM_CHANCE']}%")
        self.config["RANDOM_CHANCE"] = int(args)
        await utils.answer(message, f"шанс установлен на {args}%")

    def _get_model(self, api_key):
        genai.configure(api_key=api_key)
        safety = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
        ]
        return genai.GenerativeModel(
            model_name=self.config["MODEL"],
            system_instruction=self.config["SYSTEM_PROMPT"],
            safety_settings=safety
        )

    async def askcmd(self, message):
        """<текст> задать вопрос вручную"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "⚠️ напишите текст запроса")
        api_key = self.config["API_KEY"]
        if not api_key:
            return await utils.answer(message, "❌ api ключ не настроен")
        msg = await utils.answer(message, "⏳ нейросеть думает...")
        try:
            model = self._get_model(api_key)
            response = await asyncio.wait_for(model.generate_content_async(args), timeout=120.0)
            reply_text = response.text if response.text else ""
            if reply_text:
                max_chars = self.config["MAX_CHARS"]
                if max_chars > 0 and len(reply_text) > max_chars:
                    reply_text = reply_text[:max_chars]
                try:
                    await utils.answer(msg, reply_text)
                except Exception as e:
                    logger.error(f"[GeminiResponder] ошибка при ручном ответе: {e}")
                    await utils.answer(msg, reply_text, parse_mode=None)
            else:
                logger.warning("[GeminiResponder] получен пустой ответ при ручном запросе")
                await utils.answer(msg, "❌ пустой ответ")
        except asyncio.TimeoutError:
            logger.error("[GeminiResponder] превышено время ожидания ответа от api гугла (таймаут)")
            await utils.answer(msg, "❌ гугл завис, попробуй еще раз")
        except Exception as e:
            logger.error(f"[GeminiResponder] фатальная ошибка ручного запроса: {e}")
            await utils.answer(msg, f"❌ ошибка:\n{e}")

    async def _get_or_create_session(self, chat_id, api_key):
        if chat_id not in self.chat_sessions:
            model = self._get_model(api_key)
            self.chat_sessions[chat_id] = model.start_chat(history=[])
        return self.chat_sessions[chat_id]

    async def _simulate_typing(self, chat_id):
        delay = random.uniform(0.5, 1.2)
        async with self.client.action(chat_id, 'typing'):
            await asyncio.sleep(delay)

    async def watcher(self, message):
        if not self.is_active or getattr(message, 'out', False):
            return
        if getattr(message, 'is_channel', False) and not getattr(message, 'is_group', False):
            return
        if not getattr(message, 'raw_text', None) and not getattr(message, 'photo', None):
            return
        if message.sender_id in self.config["IGNORE_USERS"]:
            return
            
        raw_chats = self._get_chats_list()
        valid_chats = [int(c) for c in raw_chats if str(c).lstrip('-').isdigit()]
        if message.chat_id not in valid_chats:
            return

        is_reply_to_me = False
        if message.is_reply:
            reply = await message.get_reply_message()
            if reply and self.me and reply.sender_id == self.me.id:
                is_reply_to_me = True
                
        is_mentioned = getattr(message, 'mentioned', False)
        if not is_mentioned and self.me and getattr(self.me, 'username', None):
            if f"@{self.me.username.lower()}" in message.raw_text.lower():
                is_mentioned = True
                
        is_private = getattr(message, 'is_private', False)
        is_random = False

        if not is_reply_to_me and not is_mentioned and not is_private:
            if self.config["RANDOM_TALK"]:
                chance = self.config["RANDOM_CHANCE"]
                if chance > 0 and random.randint(1, 100) <= chance:
                    is_random = True
            if not is_random:
                return
            
        api_key = self.config["API_KEY"]
        if not api_key:
            logger.warning("[GeminiResponder] запрос пропущен так как не настроен api ключ")
            return
            
        try:
            session = await self._get_or_create_session(message.chat_id, api_key)
            sender = await message.get_sender()
            sender_name = get_display_name(sender) if sender else "неизвестно"
            
            content = []
            if message.photo:
                photo_bytes = await message.download_media(bytes)
                content.append({"mime_type": "image/jpeg", "data": photo_bytes})
                
            prompt = f"[сообщение от {sender_name}]: {message.raw_text}"
            max_chars = self.config["MAX_CHARS"]
            
            sys_add = "\n\n[инструкция: "
            if max_chars > 0:
                sys_add += f"ответь строго до {max_chars} символов, "
            sys_add += "не упоминай никого через @, просто напиши текст ответа]"
            
            mapping = {}
            if self.config["USE_STICKERS"]:
                mapping, _ = await self._get_pack_mapping()
                av_emojis = "".join(mapping.keys()) if mapping else "👍👎❤️😂🤔"
                sys_add += f"\n[выбери ОДИН подходящий эмодзи из списка: {av_emojis} и вставь его в конце в формате [STICKER:эмодзи]]"
            
            prompt += sys_add
            
            async with self.client.action(message.chat_id, 'typing'):
                if message.photo:
                    content = [{"mime_type": "image/jpeg", "data": photo_bytes}, prompt]
                    response = await asyncio.wait_for(session.send_message_async(content), timeout=120.0)
                else:
                    response = await asyncio.wait_for(session.send_message_async(prompt), timeout=120.0)
            
            reply_text = response.text if response.text else ""
                
            sticker_to_send = None
            if self.config["USE_STICKERS"] and reply_text:
                sticker_match = re.search(r'\[STICKER:(.+?)\]', reply_text)
                if sticker_match:
                    reaction_emoji = sticker_match.group(1).strip()
                    reply_text = reply_text.replace(sticker_match.group(0), "").strip()
                    if reaction_emoji in mapping:
                        sticker_to_send = mapping[reaction_emoji]
                    else:
                        logger.warning(f"[GeminiResponder] нейросеть выбрала эмодзи {reaction_emoji} но его нет в маппинге стикеров")
                        
            reply_text = re.sub(r'@\w+', '', reply_text).strip()
            
            if max_chars > 0 and len(reply_text) > max_chars:
                reply_text = reply_text[:max_chars]
                
            if not reply_text and not sticker_to_send:
                logger.error("[GeminiResponder] нейросеть вернула пустой ответ и не выбрала стикер")
                return

            if self.config["TYPING_DELAY"]:
                await self._simulate_typing(message.chat_id)

            if reply_text:
                try:
                    await message.reply(reply_text)
                except Exception as e:
                    logger.error(f"[GeminiResponder] ошибка при отправке текста: {e}")
                    await message.reply(reply_text, parse_mode=None)

            if sticker_to_send:
                try:
                    await message.respond(file=sticker_to_send)
                except Exception as e:
                    logger.error(f"[GeminiResponder] ошибка при отправке стикера: {e}")
                    
        except asyncio.TimeoutError:
            logger.error("[GeminiResponder] превышено время ожидания ответа от api гугла (таймаут)")
            if message.chat_id in self.chat_sessions:
                del self.chat_sessions[message.chat_id]
        except Exception as e:
            logger.error(f"[GeminiResponder] критическая ошибка watcher: {e}")
            if message.chat_id in self.chat_sessions:
                del self.chat_sessions[message.chat_id]
            if "API_KEY_INVALID" in str(e):
                self.is_active = False
                logger.error("[GeminiResponder] модуль отключен из за неверного api ключа")
