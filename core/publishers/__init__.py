"""Registry de publishers por plataforma.

Nova plataforma: implementar Publisher em um modulo proprio e registrar a
classe em _PUBLISHERS.
"""
from .base import Publisher, QuotaExceededError
from .youtube import YouTubePublisher

_PUBLISHERS: dict[str, type[Publisher]] = {
    YouTubePublisher.platform: YouTubePublisher,
}


def get_publisher(platform: str) -> Publisher:
    cls = _PUBLISHERS.get(platform)
    if cls is None:
        known = ", ".join(sorted(_PUBLISHERS))
        raise LookupError(
            f"nenhum publisher registrado para a plataforma {platform!r} "
            f"(disponiveis: {known})")
    return cls()
