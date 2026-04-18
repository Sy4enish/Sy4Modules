# meta developer: @Sy4enish
# перед скачиванием (либо после) в терминал вписать « echo "google-generativeai" >> requirements.txt» и « echo "markdown-it-py" >> requirements.txt »
from .. import loader, utils
import logging

try:
    import google.generativeai as genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)

@loader.tds
class GeminiResponderMod(loader.Module):
    """
    Auto-responder module using Google Gemini AI.
    Replies to messages that are replies to you.
    """
    strings = {
        "name": "GeminiResponder",
        "no_api": "<b>[GeminiResponder]</b> API Key is missing! Go to .config to set it.",
        "no_lib": "<b>[GeminiResponder]</b> Library 'google-generativeai' not found. Please install it via pip.",
        "processing": "<i>Thinking...</i>",
        "error": "<b>[Gemini Error]</b>: {}",
        "toggled_on": "<b>[GeminiResponder]</b> Auto-reply enabled.",
        "toggled_off": "<b>[GeminiResponder]</b> Auto-reply disabled."
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "api_key",
                None,
                "Google Gemini API Key (Get it from aistudio.google.com)",
                validator=loader.validators.Hidden(),
            ),
            loader.ConfigValue(
                "system_prompt",
                "You are a helpful assistant answering on behalf of the user. Keep answers concise.",
                "System instruction (prompt) for the AI",
            ),
            loader.ConfigValue(
                "enabled",
                True,
                "Enable or disable the auto-responder globally",
            ),
            loader.ConfigValue(
                "model_name",
                "gemini-1.5-flash",
                "Model version to use (e.g., gemini-1.5-flash, gemini-pro)",
            ),
        )
        self.me_id = None
        self.model = None # Инициализируем модель здесь

    async def client_ready(self, client, db):
        self._client = client
        self.me_id = (await client.get_me()).id
        
        if not genai:
            logger.error(self.strings("no_lib"))
            # Можно отправить сообщение пользователю, если юзербот поддерживает
            await utils.answer(
                await client.send_message("me", "Please install google-generativeai library for GeminiResponder to work. Command: pip install google-generativeai"),
                "pip install google-generativeai"
            )
            return

        await self._configure_gemini() # Вызываем конфигурацию при запуске

    async def _configure_gemini(self):
        """Конфигурирует Gemini API и инициализирует модель."""
        if not self.config["api_key"]:
            logger.warning(self.strings("no_api"))
            self.model = None
            return
        
        try:
            genai.configure(api_key=self.config["api_key"])
            self.model = genai.GenerativeModel(self.config["model_name"])
            logger.info(f"Gemini model {self.config['model_name']} configured successfully.")
        except Exception as e:
            logger.error(f"Failed to configure Gemini API or model: {e}")
            self.model = None
            await self._client.send_message("me", f"<b>[GeminiResponder]</b> Ошибка конфигурации API Gemini: {e}. Проверьте ваш ключ и модель.")

    @loader.command(
        ru_doc="Переключить режим автоответчика",
        en_doc="Toggle auto-responder mode"
    )
    async def geminitogglecmd(self, message):
        """Toggle the auto-responder on/off"""
        self.config["enabled"] = not self.config["enabled"]
        status = self.strings("toggled_on") if self.config["enabled"] else self.strings("toggled_off")
        await utils.answer(message, status)

    @loader.watcher(only_messages=True)
    async def watcher(self, message):
        # Basic checks
        if not self.config["enabled"]:
            return
        
        if not self.model: # Проверяем, инициализирована ли модель
            # Логируем, если ключ отсутствует или модель не сконфигурирована
            if not self.config["api_key"]:
                logger.warning(self.strings("no_api"))
            else:
                logger.warning("Gemini model is not initialized, skipping auto-reply.")
            return
            
        if self.me_id is None:
            return

        if message.out or message.sender_id == self.me_id:
            return

        # Check if it is a reply
        if not message.is_reply:
            return

        # Check if the reply is directed to the user (owner of the userbot)
        reply = await message.get_reply_message()
        if not reply or reply.sender_id != self.me_id:
            return

        # Ensure text exists
        if not message.text:
            return

        # Avoid processing commands
        if message.text.startswith((".", "/", "!")):
            return

        # Configure AI (removed from here, now in _configure_gemini)
        try:
            # Construct prompt
            # We send the system prompt + user message
            full_prompt = (
                f"System Instruction: {self.config['system_prompt']}\n\n"
                f"Incoming Message: {message.text}\n"
                f"Reply to this message."
            )

            # Send typing action
            async with message.client.action(message.chat_id, "typing"):
                response = await self.model.generate_content_async(full_prompt) # Используем self.model
                response_text = response.text

            # Reply to the user
            await message.reply(response_text)

        except Exception as e:
            logger.error(f"Gemini Error during response generation: {e}")
            # Optional: Send error to logs or self, but better to keep silent in chat to avoid spam
            # await message.client.send_message("me", f"<b>[GeminiResponder]</b> Произошла ошибка при генерации ответа: {e}")
            pass
