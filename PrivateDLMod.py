# meta developer: @Xpansee, @Sy4enish
from .. import loader, utils
import re
import io
from telethon.tl.types import Message

@loader.tds
class PrivateDLMod(loader.Module):
    """
    Скачивает медиа из приватных каналов по ссылке.
    Примечание: Вы должны быть участником канала для работы этого модуля.
    Модуль может скачивать контент, даже если в канале запрещено сохранение.
    """
    strings = {"name": "miprivate"}

    async def dbcmd(self, message: Message):
        """<link> - Скачать медиа по ссылке на пост"""
        args = utils.get_args_raw(message)
        if not args:
            return await utils.answer(message, "<b>❌ Link required. Usage: .db <link></b>")

        args = args.strip()

        # Regex patterns
        # Private: https://t.me/c/1234567890/123
        private_pattern = r"t\.me/c/(\d+)/(\d+)"
        # Public: https://t.me/username/123
        public_pattern = r"t\.me/([^/]+)/(\d+)"

        chat = None
        msg_id = None

        priv_match = re.search(private_pattern, args)
        pub_match = re.search(public_pattern, args)

        if priv_match:
            # Construct channel ID: -100 + ID for private channels
            chat = int(f"-100{priv_match.group(1)}")
            msg_id = int(priv_match.group(2))
        elif pub_match:
            chat = pub_match.group(1)
            msg_id = int(pub_match.group(2))
        else:
            return await utils.answer(message, "<b>❌ Invalid link format.</b>")

        await utils.answer(message, "<b>📥 Downloading...</b>")

        try:
            # Fetch message
            msg = await self._client.get_messages(chat, ids=msg_id)
            
            if not msg:
                return await utils.answer(message, "<b>❌ Message not found. Are you in the channel?</b>")
            
            if not msg.media:
                return await utils.answer(message, "<b>❌ This message contains no media.</b>")

            # Download to memory (BytesIO)
            # This effectively bypasses 'restricted content' flags by creating a fresh copy
            out = io.BytesIO()
            await self._client.download_media(msg, out)
            out.seek(0)
            
            # Determine filename for proper upload
            fname = "media"
            if hasattr(msg.media, 'document') and msg.media.document.attributes:
                for attr in msg.media.document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        fname = attr.file_name
                        break
            
            if fname == "media":
                if msg.photo: fname = "photo.jpg"
                elif msg.video: fname = "video.mp4"
                elif msg.voice: fname = "voice.ogg"
                elif msg.audio: fname = "audio.mp3"
                elif msg.sticker: fname = "sticker.webp"
                # Check for GIF (video with no sound usually treated as gif)
                elif hasattr(msg, 'gif') and msg.gif: fname = "animation.mp4"

            out.name = fname

            # Upload the file to the current chat
            await utils.answer_file(message, out, caption=msg.raw_text or "")

        except Exception as e:
            await utils.answer(message, f"<b>❌ Error:</b> {e}")