class BotError(Exception):
    """An error whose message is safe to show to the user."""


class NoVoiceChat(BotError):
    """The group has no active voice chat for the assistant to join."""


class PlaybackError(BotError):
    """The call layer could not start or change the stream."""


class AssistantError(BotError):
    """The assistant account could not join the group."""
