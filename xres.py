# meta developer: @memikami
from .. import loader, utils
import io
import os
import asyncio
from PIL import Image

@loader.tds
class xres(loader.Module):
    """Модуль для изменения размера изображений, видео и гифок без сохранения соотношения сторон. Примечание: с длинными и тяжелыми видео может не работать либо работать некорректно"""
    strings = {"name": "xres"}

    @loader.command()
    async def rescmd(self, message):
        """<width>x<height> - Resize media from reply without aspect ratio"""
        reply = await message.get_reply_message()
        if not reply or not reply.media:
            await utils.answer(message, "<b>Reply to an image, video, or gif.</b>")
            return

        args = utils.get_args_raw(message)
        if not args or "x" not in args:
            await utils.answer(message, "<b>Usage: .res 1500x500</b>")
            return

        try:
            w, h = map(int, args.split("x"))
        except ValueError:
            await utils.answer(message, "<b>Invalid format. Use: .res WIDTHxHEIGHT (e.g., .res 100x200)</b>")
            return

        message = await utils.answer(message, "<b>Processing...</b>")

        is_video = False
        mime = reply.file.mime_type
        if mime and mime.startswith("video"):
            is_video = True
        elif reply.gif or (mime and "gif" in mime):
            is_video = True

        temp_in = f"xres_in_{reply.id}"
        temp_out = f"xres_out_{reply.id}"
        
        ext = reply.file.ext or ""
        if not ext:
            ext = ".mp4" if is_video else ".png"
        
        temp_in += ext
        temp_out += ".mp4" if is_video else ".png"

        try:
            if is_video:
                await self._client.download_media(reply, file=temp_in)
                
                cmd = f"ffmpeg -y -i \"{temp_in}\" -vf scale={w}:{h} -c:a copy -preset ultrafast \"{temp_out}\""
                
                process = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await process.communicate()
                
                if not os.path.exists(temp_out) or os.path.getsize(temp_out) == 0:
                    await utils.answer(message, f"<b>Error processing video.</b>\n{stderr.decode()[-100:]}")
                    return

                await message.delete()
                await utils.answer_file(
                    message,
                    temp_out,
                    caption=f"<b>Resized to {w}x{h}</b>",
                    force_document=False,
                    supports_streaming=True
                )
            else:
                img_bytes = await self._client.download_media(reply, file=bytes)
                im = Image.open(io.BytesIO(img_bytes))
                
                im = im.resize((w, h))
                
                output = io.BytesIO()
                im.save(output, format="PNG")
                output.seek(0)
                output.name = "resized.png"

                await message.delete()
                await utils.answer_file(
                    message, 
                    output, 
                    caption=f"<b>Resized to {w}x{h}</b>"
                )

        except Exception as e:
            await utils.answer(message, f"<b>Error:</b> {e}")
        finally:
            if os.path.exists(temp_in):
                os.remove(temp_in)
            if os.path.exists(temp_out):
                os.remove(temp_out)