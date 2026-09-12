# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from collections.abc import Callable
from dataclasses import dataclass
from gettext import gettext as _
from urllib.parse import quote


@dataclass
class ShareProvider:
    """Data class for a share provider."""

    id: str
    name: str
    url_template: str | None = None
    handler: Callable[[str], str] | None = None


# Provider definitions
PROVIDERS: list[ShareProvider] = [
    ShareProvider(
        id="email",
        name=_("Email"),
        handler=lambda text: f"mailto:?subject={quote(_('Extracted Text'), safe='')}&body={quote(text.strip(), safe='')}",
    ),
    ShareProvider(
        id="mastodon",
        name=_("Mastodon"),
        handler=lambda text: f"web+mastodon://share?text={quote(text.strip(), safe='')}",
    ),
    ShareProvider(
        id="reddit",
        name=_("Reddit"),
        handler=lambda text: (
            f"https://www.reddit.com/submit?title={quote(text, safe='')}&selftext={quote(text, safe='')}"
            if len(text) < 100
            else f"https://www.reddit.com/submit?selftext={quote(text, safe='')}"
        ),
    ),
    ShareProvider(
        id="telegram",
        name=_("Telegram"),
        handler=lambda text: f"https://t.me/share/url?text={quote(text.strip(), safe='')}",
    ),
    ShareProvider(
        id="x",
        name=_("X"),
        handler=lambda text: f"https://x.com/intent/tweet?text={quote(text.strip(), safe='')}",
    ),
    ShareProvider(
        id="bluesky",
        name=_("Bluesky"),
        handler=lambda text: f"https://bsky.app/intent/compose?text={quote(text.strip(), safe='')}",
    ),
    ShareProvider(
        id="discord",
        name=_("Discord"),
        handler=lambda text: f"https://discord.com/channels/@me?content={quote(text.strip(), safe='')}",
    ),
    ShareProvider(
        id="linkedin",
        name=_("LinkedIn"),
        handler=lambda text: f"https://www.linkedin.com/sharing/share-offsite/?url={quote('https://github.com/D3M-Sudo/Anura', safe='')}&summary={quote(text.strip(), safe='')}",
    ),
    ShareProvider(
        id="threads",
        name=_("Threads"),
        handler=lambda text: f"https://www.threads.net/intent/post?text={quote(text.strip(), safe='')}",
    ),
    # NOTE: "instagram" removed — no URL prefill API available
]


def get_provider_ids() -> list[str]:
    """Get list of provider IDs."""
    return [p.id for p in PROVIDERS]


def get_provider_by_id(provider_id: str) -> ShareProvider | None:
    """Get provider by ID."""
    for provider in PROVIDERS:
        if provider.id == provider_id:
            return provider
    return None


def generate_share_link(provider_id: str, text: str) -> str:
    """Generate share link for a provider."""
    provider = get_provider_by_id(provider_id)
    if not provider or not provider.handler:
        return ""
    return provider.handler(text)
