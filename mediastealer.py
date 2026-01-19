# meta developer: @memikami, @Sy4enish
from .. import loader, utils
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

@loader.tds
class MediaStealerMod(loader.Module):
    """
    Module for automatically forwarding media and stickers 
    from a specific user in a specific chat (or all media from specific chats)
    to your Saved Messages or custom chat.
    """
    
    strings = {"name": "MediaStealer"}

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "destination",
                "me",
                "Destination chat ID, username, or link (e.g. @username, https://t.me/..., or me)",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "target_chats",
                [],
                "List of chats/channels IDs to steal ALL media from",
                validator=loader.validators.Series(loader.validators.Union(loader.validators.Integer(), loader.validators.String())),
            ),
        )

    async def client_ready(self, client, db):
        self.db = db
        self.client = client

    async def get_dest(self):
        dest = self.config["destination"]
        if not dest or dest.lower() == "me":
            return "me"
        
        dest = str(dest).strip()

        if dest.lstrip("-").isdigit():
            return int(dest)

        if "t.me/" in dest:
            if "t.me/c/" in dest:
                chat_id = dest.split("t.me/c/")[-1].split("/")[0]
                if chat_id.isdigit():
                    return int(f"-100{chat_id}")
            dest = dest.split("t.me/")[-1].split("/")[0]
        
        if not dest.startswith("@") and not dest.lstrip("-").isdigit():
            return f"@{dest}"
            
        return dest

    @loader.command(ru_doc="<reply> - Начать/Закончить пересылку медиа от пользователя")
    async def steal(self, message):
        """<reply> - Start/Stop forwarding media from replied user"""
        reply = await message.get_reply_message()
        if not reply:
            targets = self.db.get(self.strings["name"], "targets", {})
            if not targets:
                await utils.answer(message, "<b>Reply to a user to start stealing their media.</b>")
                return
            
            text = "<b>Active targets:</b>\n"
            for chat_id, user_id in targets.items():
                text += f"Chat: <code>{chat_id}</code> | User: <code>{user_id}</code>\n"
            await utils.answer(message, text)
            return

        target_id = reply.sender_id
        chat_id = utils.get_chat_id(message)
        
        targets = self.db.get(self.strings["name"], "targets", {})
        str_chat_id = str(chat_id)
        
        user_name = "User"
        if reply.sender:
            user_name = getattr(reply.sender, "first_name", None) or getattr(reply.sender, "title", "User")

        if str_chat_id in targets and targets[str_chat_id] == target_id:
            del targets[str_chat_id]
            self.db.set(self.strings["name"], "targets", targets)
            await utils.answer(message, f"<b>❌ Stopped stealing media from {user_name} in this chat.</b>")
        else:
            targets[str_chat_id] = target_id
            self.db.set(self.strings["name"], "targets", targets)
            dest = self.config['destination']
            await utils.answer(message, f"<b>✅ Started stealing media from {user_name} to {dest}.</b>")

    @loader.command(ru_doc="<reply> - Начать/Закончить пересылку ТОЛЬКО видео от пользователя")
    async def stealvideo(self, message):
        """<reply> - Start/Stop forwarding ONLY videos from replied user"""
        reply = await message.get_reply_message()
        if not reply:
            targets = self.db.get(self.strings["name"], "video_targets", {})
            if not targets:
                await utils.answer(message, "<b>Reply to a user to start stealing their videos.</b>")
                return
            
            text = "<b>Active video targets:</b>\n"
            for chat_id, user_id in targets.items():
                text += f"Chat: <code>{chat_id}</code> | User: <code>{user_id}</code>\n"
            await utils.answer(message, text)
            return

        target_id = reply.sender_id
        chat_id = utils.get_chat_id(message)
        
        targets = self.db.get(self.strings["name"], "video_targets", {})
        str_chat_id = str(chat_id)
        
        user_name = "User"
        if reply.sender:
            user_name = getattr(reply.sender, "first_name", None) or getattr(reply.sender, "title", "User")

        if str_chat_id in targets and targets[str_chat_id] == target_id:
            del targets[str_chat_id]
            self.db.set(self.strings["name"], "video_targets", targets)
            await utils.answer(message, f"<b>❌ Stopped stealing videos from {user_name} in this chat.</b>")
        else:
            targets[str_chat_id] = target_id
            self.db.set(self.strings["name"], "video_targets", targets)
            dest = self.config['destination']
            await utils.answer(message, f"<b>✅ Started stealing videos from {user_name} to {dest}.</b>")

    @loader.watcher(only_messages=True)
    async def watcher(self, message):
        if not message.chat_id:
            return
        
        if not message.media:
            return

        chat_id = str(utils.get_chat_id(message))
        should_forward = False

        # Check config targets (Global Steal for Chat/Channel)
        target_chats = self.config["target_chats"]
        if target_chats:
            # Normalize to strings for comparison
            str_target_chats = [str(x) for x in target_chats]
            if str(message.chat_id) in str_target_chats or chat_id in str_target_chats:
                should_forward = True

        # Check DB targets (Specific User in Chat)
        if not should_forward and message.sender_id:
            targets = self.db.get(self.strings["name"], "targets", {})
            video_targets = self.db.get(self.strings["name"], "video_targets", {})

            if chat_id in targets and targets[chat_id] == message.sender_id:
                should_forward = True
            elif chat_id in video_targets and video_targets[chat_id] == message.sender_id:
                if message.video:
                    should_forward = True

        if should_forward:
            try:
                dest = await self.get_dest()
                await message.forward_to(dest)
            except Exception:
                pass

    @loader.command(ru_doc="<count> [reply] - Украсть стикеры из истории чата")
    async def stealstickers(self, message):
        """<count> [reply] - Steal stickers from chat history"""
        args = utils.get_args(message)
        if not args or not args[0].isdigit():
            await utils.answer(message, "<b>Please specify the quantity.</b>\n<code>.stealstickers <count> [reply]</code>")
            return

        count = int(args[0])
        reply = await message.get_reply_message()
        target_user = reply.sender_id if reply else None
        
        await utils.answer(message, f"<b>🔍 Stealing {count} stickers...</b>")
        
        dest = await self.get_dest()
        counter = 0
        
        async for msg in self.client.iter_messages(message.chat_id, limit=None):
            if counter >= count:
                break
            
            if target_user and msg.sender_id != target_user:
                continue
                
            if msg.sticker:
                try:
                    await msg.forward_to(dest)
                    counter += 1
                except Exception:
                    continue
        
        await utils.answer(message, f"<b>✅ Stolen {counter} stickers to {self.config['destination']}.</b>")

    @loader.command(ru_doc="<count> [reply] - Украсть медиа из истории чата")
    async def stealmedia(self, message):
        """<count> [reply] - Steal media (photo/video/gif) from chat history"""
        args = utils.get_args(message)
        if not args or not args[0].isdigit():
            await utils.answer(message, "<b>Please specify the quantity.</b>\n<code>.stealmedia <count> [reply]</code>")
            return

        count = int(args[0])
        reply = await message.get_reply_message()
        target_user = reply.sender_id if reply else None
        
        await utils.answer(message, f"<b>🔍 Stealing {count} media...</b>")
        
        dest = await self.get_dest()
        counter = 0
        
        async for msg in self.client.iter_messages(message.chat_id, limit=None):
            if counter >= count:
                break
            
            if target_user and msg.sender_id != target_user:
                continue
                
            if msg.media and not msg.sticker:
                if isinstance(msg.media, (MessageMediaPhoto, MessageMediaDocument)):
                    try:
                        await msg.forward_to(dest)
                        counter += 1
                    except Exception:
                        continue
        
        await utils.answer(message, f"<b>✅ Stolen {counter} media files to {self.config['destination']}.</b>")