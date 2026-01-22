# meta developer: Xpanse (ID: 795326542)
from .. import loader, utils
import os
import requests
from telethon.tl.types import DocumentAttributeAudio

@loader.tds
class XmusicEditorMod(loader.Module):
    """Module for editing audio metadata (title, performer) and cover art."""
    strings = {"name": "XmusicEditor"}

    async def client_ready(self, client, db):
        self.client = client

    async def namecmd(self, message):
        """[title] - [artist] <reply>
        Change title and artist of the replied audio file.
        Use ' - ' to separate title and artist.
        Example: .name My Song - My Artist"""
        
        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, "<b>Reply to an audio file!</b>")
            return

        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, "<b>Usage: .name Title - Artist</b>")
            return

        if " - " in args:
            title, performer = args.split(" - ", 1)
        else:
            title = args
            performer = ""

        title = title.strip()
        performer = performer.strip()

        await utils.answer(message, "<b>Downloading audio...</b>")
        
        try:
            f = await reply.download_media()
        except Exception as e:
             await utils.answer(message, f"<b>Download error:</b> {e}")
             return

        # Preserve duration from original file
        duration = 0
        if reply.document:
            for attr in reply.document.attributes:
                if isinstance(attr, DocumentAttributeAudio):
                    duration = attr.duration
                    break

        await utils.answer(message, f"<b>Uploading as:</b> {title} - {performer}")
        
        try:
            await message.client.send_file(
                message.peer_id,
                f,
                caption=reply.text or "",
                attributes=[DocumentAttributeAudio(
                    duration=duration,
                    title=title,
                    performer=performer
                )],
                reply_to=reply.id
            )
            await message.delete()
        except Exception as e:
            await utils.answer(message, f"<b>Upload error:</b> {e}")
        finally:
            if f and os.path.exists(f):
                os.remove(f)

    async def oblcmd(self, message):
        """<link> <reply>
        Change cover (thumbnail) of the replied audio file using a direct link."""
        
        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, "<b>Reply to an audio file!</b>")
            return

        url = utils.get_args_raw(message)
        if not url:
            await utils.answer(message, "<b>Usage: .obl <image_link></b>")
            return

        await utils.answer(message, "<b>Downloading audio and new cover...</b>")

        # Download Audio
        try:
            audio_path = await reply.download_media()
        except Exception as e:
            await utils.answer(message, f"<b>Audio download error:</b> {e}")
            return

        # Download Thumbnail
        thumb_path = f"temp_thumb_{message.id}.jpg"
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            r = requests.get(url, headers=headers, stream=True)
            r.raise_for_status()
            with open(thumb_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            await utils.answer(message, f"<b>Cover download error:</b> {e}")
            return

        # Preserve existing attributes (Title, Performer, Duration)
        attributes = []
        if reply.document:
            for attr in reply.document.attributes:
                if isinstance(attr, DocumentAttributeAudio):
                    attributes.append(attr)

        await utils.answer(message, "<b>Uploading with new cover...</b>")

        try:
            await message.client.send_file(
                message.peer_id,
                audio_path,
                caption=reply.text or "",
                thumb=thumb_path,
                attributes=attributes,
                reply_to=reply.id
            )
            await message.delete()
        except Exception as e:
            await utils.answer(message, f"<b>Upload error:</b> {e}")
        finally:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            if os.path.exists(thumb_path):
                os.remove(thumb_path)