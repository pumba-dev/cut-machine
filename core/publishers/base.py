"""Abstracao de destino de publicacao (Publisher).

Cada plataforma implementa authenticate() + upload(). Publishers recebem a
conta ja resolvida por core.accounts.get_account e usam
core.accounts.credentials_dir(account) — nunca assumem caminho fixo de
token/secret.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class QuotaExceededError(Exception):
    """Quota diaria da API de upload esgotada; o clip deve voltar para 'queued'."""


class Publisher(ABC):
    """Destino de publicacao (YouTube hoje; TikTok/Instagram/... via registry)."""

    platform: str

    @abstractmethod
    def authenticate(self, account: dict) -> Any:
        """Garante credenciais validas para a conta; retorna as credenciais.

        Idempotente: reusa token existente, renova se expirado e so abre o
        fluxo interativo quando nao ha token utilizavel.
        """

    @abstractmethod
    def upload(self, video_path: Path, metadata: dict, account: dict) -> dict:
        """Envia o video e retorna {"remote_id", "url", "published_at"}.

        metadata keys:
        - title: str (truncado ao limite da plataforma)
        - description: str
        - tags: list[str]
        - category_id: str
        - privacy: str ("public" por default)
        - made_for_kids: bool
        - language: str (ex.: "pt-BR")
        - thumbnail_path: str | None (opcional; miniatura para thumbnails.set
          best-effort — falha nao derruba o upload)

        Lanca QuotaExceededError quando a quota diaria da API esgotar.
        """
