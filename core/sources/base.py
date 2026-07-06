"""Abstracao de fonte de video: VideoSource (ABC) + contrato do dict source.

Cada plataforma implementa matches(url) para o registry (core.sources.get_source)
e fetch(url, workspace) para baixar o video e os metadados no workspace.
"""
from abc import ABC, abstractmethod
from pathlib import Path


class VideoSource(ABC):
    """Fonte de video identificada por URL."""

    name: str = ""

    @classmethod
    @abstractmethod
    def matches(cls, url: str) -> bool:
        """True se esta fonte sabe tratar a URL."""

    @abstractmethod
    def probe_id(self, url: str) -> str:
        """Retorna o video_id canonico da URL sem baixar o video."""

    @abstractmethod
    def fetch(self, url: str, workspace: Path) -> dict:
        """Baixa video + metadados para o workspace e retorna o dict source.

        Artefatos obrigatorios no workspace: source.mp4 e source.info.json
        (caminhos canonicos em core.paths).

        Contrato do dict retornado (vira o bloco "source" do clips.json):
        {
          "video_id": str,      # id canonico na plataforma
          "url": str,           # URL canonica do video
          "title": str,
          "channel": str,
          "duration_s": float,
          "width": int | None,
          "height": int | None,
          "fps": float | None,
          "language": str | None,
          "path": str,          # caminho do source.mp4 relativo a raiz do projeto
        }
        """
