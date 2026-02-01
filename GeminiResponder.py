# meta developer: @Sy4enish
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

    async def client_ready(self, client, db):
        self._client = client
        self.me_id = (await client.get_me()).id
        if not genai:
            await utils.answer(
                await client.send_message("me", "Please install google-generativeai"),
                "pip install google-generativeai"
            )

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
        if not self.config["enabled"] or not self.config["api_key"]:
            return
        
        if not genai:
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

        # Configure AI
        try:
            genai.configure(api_key=self.config["api_key"])
            model = genai.GenerativeModel(self.config["model_name"])
            
            # Construct prompt
            # We send the system prompt + user message
            full_prompt = (
                f"System Instruction: {self.config['system_prompt']}\n\n"
                f"Incoming Message: {message.text}\n"
                f"Reply to this message."
            )

            # Send typing action
            async with message.client.action(message.chat_id, "typing"):
                response = await model.generate_content_async(full_prompt)
                response_text = response.text

            # Reply to the user
            await message.reply(response_text)

        except Exception as e:
            logger.error(f"Gemini Error: {e}")
            # Optional: Send error to logs or self, but better to keep silent in chat to avoid spam
            pass