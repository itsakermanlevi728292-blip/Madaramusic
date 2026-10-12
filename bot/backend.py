"""The real call backend: py-tgcalls driven by the assistant account(s)."""

from __future__ import annotations

import logging

from .errors import NoVoiceChat, PlaybackError

log = logging.getLogger("bot.backend")


class TgCallsBackend:
    def __init__(self, calls: list):
        if not calls:
            raise ValueError("at least one assistant is required")
        self.calls = calls

    def index_for(self, chat_id: int) -> int:
        """Each group is always served by the same assistant, so its queue never jumps accounts."""
        return abs(int(chat_id)) % len(self.calls)

    def call_for(self, chat_id: int):
        return self.calls[self.index_for(chat_id)]

    # ── playback ──────────────────────────────────────────────────────────
    async def play(self, chat_id: int, url: str, *, video: bool = False, seek: int = 0) -> None:
        from pytgcalls import exceptions as tge
        from pytgcalls.types import AudioQuality, GroupCallConfig, MediaStream, VideoQuality

        flags = MediaStream.Flags
        stream = MediaStream(
            url,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
            audio_flags=flags.REQUIRED,
            video_flags=flags.AUTO_DETECT if video else flags.IGNORE,
            ffmpeg_parameters=f"-ss {int(seek)}" if seek else None,
        )
        try:
            await self.call_for(chat_id).play(chat_id, stream, config=GroupCallConfig(auto_start=False))
        except tge.NoActiveGroupCall:
            raise NoVoiceChat("There is no voice chat running. Start one in this group, then try again.")
        except (tge.NoAudioSourceFound, tge.NoVideoSourceFound, tge.LiveStreamFound):
            raise PlaybackError("That source has no playable audio.")
        except FileNotFoundError:
            raise PlaybackError("The stream could not be opened.")

    async def pause(self, chat_id: int) -> None:
        await self.call_for(chat_id).pause(chat_id)

    async def resume(self, chat_id: int) -> None:
        await self.call_for(chat_id).resume(chat_id)

    async def stop(self, chat_id: int) -> None:
        from pytgcalls.exceptions import NotInCallError

        try:
            await self.call_for(chat_id).leave_call(chat_id)
        except NotInCallError:
            pass

    async def set_volume(self, chat_id: int, volume: int) -> None:
        await self.call_for(chat_id).change_volume_call(chat_id, volume)

    async def participants(self, chat_id: int) -> int | None:
        found = await self.call_for(chat_id).get_participants(chat_id)
        return None if found is None else len(found)

    async def is_active(self, chat_id: int) -> bool:
        return chat_id in await self.call_for(chat_id).calls

    # ── events ────────────────────────────────────────────────────────────
    def attach(self, player) -> None:
        """Route stream-end and call-closed events from every assistant to the player."""
        from pytgcalls import filters as fl
        from pytgcalls.types import ChatUpdate

        for call in self.calls:

            @call.on_update(fl.stream_end())
            async def _ended(_, update):
                await player.on_stream_end(update.chat_id)

            @call.on_update(fl.chat_update(ChatUpdate.Status.LEFT_CALL))
            async def _closed(_, update):
                await player.on_call_closed(update.chat_id)
