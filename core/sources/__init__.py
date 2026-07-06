"""Registry de fontes de video: resolve a implementacao pela URL."""
from .base import VideoSource
from .youtube import YouTubeSource

SOURCES: list[type[VideoSource]] = [
    YouTubeSource,
]


def get_source(url: str) -> VideoSource:
    """Retorna instancia da primeira fonte cujo matches(url) e True."""
    for source_cls in SOURCES:
        if source_cls.matches(url):
            return source_cls()
    known = ", ".join(cls.name for cls in SOURCES)
    raise LookupError(
        f"nenhuma fonte de video reconhece a URL: {url} (fontes disponiveis: {known})"
    )
