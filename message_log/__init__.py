"""Self-contained rendering package: user-profile / message-log HTML fragments -> PDF.

Public API: :func:`build_profile_context` + :func:`user_profile` (the subject
metadata fragment), :func:`build_message_log_context` + :func:`message_log`
(the strictly-chronological transcript fragment -- never grouped by guild or
channel), and :func:`make_pdf` to turn any HTML string -- typically the two
fragments concatenated -- into PDF bytes. The lower-level :func:`format_dt`
and :func:`build_message_list` helpers are exposed for tests. See
:mod:`cogs.message_log.render` for the full contract.
"""

from .render import (
    build_message_list,
    format_dt,
    make_pdf,
    message_log,
    user_profile,
)

__all__ = [
    "build_message_list",
    "format_dt",
    "make_pdf",
    "message_log",
    "user_profile",
]
