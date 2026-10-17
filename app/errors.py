import asyncio

from telethon.errors import (
    ChannelInvalidError, ChannelPrivateError, ChatAdminRequiredError,
    ChatWriteForbiddenError, FloodWaitError, RPCError,
)

from app.models import ErrorKind
from app.rate_limit import AccountCooldownError


def classify_error(exc: Exception) -> ErrorKind:
    if isinstance(exc, (FloodWaitError, AccountCooldownError)):
        return ErrorKind.FLOOD_WAIT
    if isinstance(exc, ChannelPrivateError):
        return ErrorKind.PRIVATE
    if isinstance(exc, ChannelInvalidError):
        return ErrorKind.DELETED
    if isinstance(exc, (ChatAdminRequiredError, ChatWriteForbiddenError)):
        return ErrorKind.FORBIDDEN
    if isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError)):
        return ErrorKind.NETWORK
    if isinstance(exc, RPCError):
        return ErrorKind.UNAVAILABLE
    return ErrorKind.UNKNOWN
