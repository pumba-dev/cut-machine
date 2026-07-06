"""Nucleo do pipeline de cortes: contratos, estado, fontes, transcricao, render e publishers.

Camadas:
- contracts/state: dados compartilhados entre etapas (clips.json, state.json)
- sources: obtencao de video por URL (YouTube hoje; outras plataformas via registry)
- publishers: publicacao por plataforma/conta (YouTube hoje; outras via registry)
"""
