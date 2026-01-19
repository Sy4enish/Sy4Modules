# meta developer: @Xpansee, @Sy4enish
# requires: google-generativeai

import os
import logging
import google.generativeai as genai
from .. import loader, utils

logger = logging.getLogger(__name__)

@loader.tds
class TextOfMusicMod(loader.Module):
    """
    Module for extracting text/lyrics from audio files using Google Gemini API.
    """

    strings = {
        "name": "textofmusic",
        "no_api_key": "<b>🚫 API Key missing!</b>\nPlease set it in config: <code>.config textofmusic</code>\nGet key: <a href='https://aistudio.google.com/app/apikey'>Google AI Studio</a>",
        "no_reply": "<b>🚫 Reply to an audio/voice message.</b>",
        "no_audio": "<b>🚫 The replied message does not contain audio.</b>",
        "processing": "<b>🎧 Listening and transcribing...</b>",
        "error": "<b>🚫 Error:</b>\n<code>{}</code>",
        "result_header": "<b>🎤 Transcription Result:</b>\n\n",
    }

    strings_ru = {
        "no_api_key": "<b>🚫 Нет API ключа!</b>\nУстановите его в конфиге: <code>.config textofmusic</code>\nПолучить ключ: <a href='https://aistudio.google.com/app/apikey'>Google AI Studio</a>",
        "no_reply": "<b>🚫 Ответьте на аудио или голосовое сообщение.</b>",
        "no_audio": "<b>🚫 В сообщении нет аудио.</b>",
        "processing": "<b>🎧 Слушаю и транскрибирую...</b>",
        "error": "<b>🚫 Ошибка:</b>\n<code>{}</code>",
        "result_header": "<b>🎤 Результат транскрипции:</b>\n\n",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                None,
                lambda: "Google Gemini API Key (from aistudio.google.com)",
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "model_name",
                "gemini-3-pro-preview",
                lambda: "Model version to use (e.g. gemini-2.0-flash-exp)",
            ),
        )

    @loader.command(
        ru_doc="<reply> - Извлечь текст/текст песни из аудио"
    )
    async def textcmd(self, message):
        """<reply to audio> - Extract text/lyrics from audio using Gemini"""
        
        # 1. Check API Key
        api_key = self.config["api_key"]
        if not api_key:
            await utils.answer(message, self.strings("no_api_key"))
            return

        # 2. Check Reply
        reply = await message.get_reply_message()
        if not reply:
            await utils.answer(message, self.strings("no_reply"))
            return

        # 3. Check Audio
        if not (reply.voice or reply.audio or reply.video): # Video often has audio too
            await utils.answer(message, self.strings("no_audio"))
            return

        # 4. Process
        await utils.answer(message, self.strings("processing"))
        
        local_file = None
        gemini_file = None

        try:
            # Download
            local_file = await reply.download_media()
            
            # Configure Gemini
            genai.configure(api_key=api_key)
            
            # Upload to Gemini File API
            gemini_file = genai.upload_file(local_file)
            
            # Initialize Model
            model = genai.GenerativeModel(self.config["model_name"])
            
            # Prompt
            prompt = "Listen to this audio file carefully. Transcribe the spoken text or lyrics exactly as they are hearing. If it is a song, format it as lyrics. Ignore background noise. Output only the text."
            
            # Generate
            response = model.generate_content([prompt, gemini_file])
            
            # Result
            text_out = response.text.strip()
            await utils.answer(message, self.strings("result_header") + f"<blockquote expandable>{text_out}</blockquote>")

        except Exception as e:
            logger.exception("TextOfMusic Error")
            await utils.answer(message, self.strings("error").format(str(e)))
        
        finally:
            # Cleanup local file
            if local_file and os.path.exists(local_file):
                os.remove(local_file)
            
            # Cleanup remote file (optional but good practice)
            if gemini_file:
                try:
                    gemini_file.delete()
                except:
                    pass