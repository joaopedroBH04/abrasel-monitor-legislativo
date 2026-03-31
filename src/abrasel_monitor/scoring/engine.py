"""Motor de Relevancia (Scoring Engine).

Implementa RN-01 e RN-02 do documento:
- RN-01: Proposicao e RELEVANTE se contem palavras-chave, tema ou autor aliado
- RN-02: Score = keyword_primaria*3 + keyword_secundaria*1 + tema*2 + autor_aliado*2
  Score >= 5 = Alta, 3-4 = Media, 1-2 = Baixa, 0 = Irrelevante

Conforme RN-06: configuracao via arquivo YAML (sem necessidade de alteracao de codigo).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
import structlog

from abrasel_monitor.settings import settings

logger = structlog.get_logger()


@dataclass
class ScoringResult:
    """Resultado da classificacao de uma proposicao."""

    score: int = 0
    nivel: str = "Irrelevante"  # Alta / Media / Baixa / Irrelevante
    keywords_matched: list[str] = field(default_factory=list)
    temas_matched: list[str] = field(default_factory=list)
    exclusion_triggered: bool = False
    justificativa: str = ""


class KeywordsConfig:
    """Carrega e gerencia a configuracao de palavras-chave do YAML."""

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or settings.keywords_config_path
        self._config: dict[str, Any] = {}
        self._primary_terms: list[str] = []
        self._secondary_terms: list[str] = []
        self._exclusion_terms: list[str] = []
        self._theme_codes: dict[int, str] = {}
        self._frentes: list[str] = []
        self.load()

    def load(self) -> None:
        path = Path(self.config_path)
        if not path.exists():
            # Tenta caminho relativo ao projeto
            path = Path(__file__).parent.parent.parent.parent / self.config_path
        if not path.exists():
            logger.warning("keywords_config_not_found", path=str(path))
            return

        with open(path, encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}

        # Flatten primarias
        primarias = self._config.get("primarias", {})
        self._primary_terms = []
        for categoria_terms in primarias.values():
            if isinstance(categoria_terms, list):
                self._primary_terms.extend([t.lower() for t in categoria_terms])

        # Flatten secundarias
        secundarias = self._config.get("secundarias", {})
        self._secondary_terms = []
        for categoria_terms in secundarias.values():
            if isinstance(categoria_terms, list):
                self._secondary_terms.extend([t.lower() for t in categoria_terms])

        # Exclusao
        self._exclusion_terms = [t.lower() for t in self._config.get("exclusao", [])]

        # Temas da Camara
        self._theme_codes = {int(k): v for k, v in self._config.get("temas_camara", {}).items()}

        # Frentes parlamentares
        self._frentes = self._config.get("frentes_parlamentares", [])

        logger.info(
            "keywords_loaded",
            primarias=len(self._primary_terms),
            secundarias=len(self._secondary_terms),
            exclusao=len(self._exclusion_terms),
            temas=len(self._theme_codes),
        )

    @property
    def primary_terms(self) -> list[str]:
        return self._primary_terms

    @property
    def secondary_terms(self) -> list[str]:
        return self._secondary_terms

    @property
    def exclusion_terms(self) -> list[str]:
        return self._exclusion_terms

    @property
    def theme_codes(self) -> dict[int, str]:
        return self._theme_codes

    @property
    def frentes_parlamentares(self) -> list[str]:
        return self._frentes


class ScoringEngine:
    """Motor de classificacao de relevancia de proposicoes legislativas.

    Pesos conforme RN-02:
    - Keyword primaria: 3 pts
    - Keyword secundaria: 1 pt
    - Tema associado: 2 pts
    - Autor aliado: 2 pts

    Niveis:
    - Score >= 5 = Alta
    - Score 3-4 = Media
    - Score 1-2 = Baixa
    - Score 0 = Irrelevante
    """

    def __init__(self, keywords_config: KeywordsConfig | None = None):
        self.config = keywords_config or KeywordsConfig()

    def score_proposicao(
        self,
        ementa: str | None,
        ementa_detalhada: str | None = None,
        temas: list[dict[str, Any]] | None = None,
        autores_ids: list[str] | None = None,
        aliados_ids: set[str] | None = None,
    ) -> ScoringResult:
        """Calcula score de relevancia de uma proposicao."""
        result = ScoringResult()

        # Texto para analise
        text = self._normalize_text(f"{ementa or ''} {ementa_detalhada or ''}")

        if not text.strip():
            return result

        # 1. Verificar exclusoes primeiro
        if self._check_exclusion(text):
            result.exclusion_triggered = True
            # Nao retorna 0 direto - apenas rebaixa se nao houver match primario

        # 2. Match de keywords primarias (peso 3)
        primary_matches = self._match_terms(text, self.config.primary_terms)
        result.keywords_matched.extend(primary_matches)
        primary_score = len(primary_matches) * settings.score_keyword_primary

        # 3. Match de keywords secundarias (peso 1)
        secondary_matches = self._match_terms(text, self.config.secondary_terms)
        result.keywords_matched.extend(secondary_matches)
        secondary_score = len(secondary_matches) * settings.score_keyword_secondary

        # 4. Match de temas da Camara (peso 2)
        theme_score = 0
        if temas:
            for tema in temas:
                codigo = tema.get("codTema") or tema.get("codigo")
                if codigo and int(codigo) in self.config.theme_codes:
                    result.temas_matched.append(self.config.theme_codes[int(codigo)])
                    theme_score += settings.score_theme

        # 5. Autor aliado (peso 2)
        allied_score = 0
        if autores_ids and aliados_ids:
            for autor_id in autores_ids:
                if autor_id in aliados_ids:
                    allied_score += settings.score_allied_author

        # Score total
        result.score = primary_score + secondary_score + theme_score + allied_score

        # Rebaixar se apenas exclusao sem match primario
        if result.exclusion_triggered and not primary_matches:
            result.score = max(0, result.score - 2)

        # Classificacao
        result.nivel = self._classify(result.score)

        # Justificativa
        parts = []
        if primary_matches:
            parts.append(f"Keywords primarias: {', '.join(primary_matches[:5])}")
        if secondary_matches:
            parts.append(f"Keywords secundarias: {', '.join(secondary_matches[:5])}")
        if result.temas_matched:
            parts.append(f"Temas: {', '.join(result.temas_matched)}")
        if allied_score > 0:
            parts.append(f"Autor aliado (+{allied_score})")
        if result.exclusion_triggered:
            parts.append("Termo de exclusao detectado")
        result.justificativa = " | ".join(parts) if parts else "Nenhum match encontrado"

        return result

    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para comparacao (lowercase, remove acentos extras)."""
        return text.lower().strip()

    def _match_terms(self, text: str, terms: list[str]) -> list[str]:
        """Faz matching de termos usando regex word boundary."""
        matched: list[str] = []
        for term in terms:
            pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
            if pattern.search(text):
                matched.append(term)
        return matched

    def _check_exclusion(self, text: str) -> bool:
        """Verifica se texto contem apenas termos de exclusao sem contexto do setor."""
        for term in self.config.exclusion_terms:
            if term in text:
                return True
        return False

    def _classify(self, score: int) -> str:
        """Classifica nivel de relevancia baseado no score."""
        if score >= settings.score_threshold_high:
            return "Alta"
        elif score >= settings.score_threshold_medium:
            return "Media"
        elif score >= settings.score_threshold_low:
            return "Baixa"
        return "Irrelevante"

    def score_batch(
        self,
        proposicoes: list[dict[str, Any]],
        aliados_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Classifica um lote de proposicoes em batch."""
        results: list[dict[str, Any]] = []
        for prop in proposicoes:
            scoring = self.score_proposicao(
                ementa=prop.get("ementa"),
                ementa_detalhada=prop.get("ementa_detalhada"),
                temas=prop.get("temas"),
                autores_ids=prop.get("autores_ids"),
                aliados_ids=aliados_ids,
            )
            results.append({
                **prop,
                "relevancia_score": scoring.score,
                "relevancia_nivel": scoring.nivel,
                "keywords_matched": scoring.keywords_matched,
                "temas_matched": scoring.temas_matched,
                "scoring_justificativa": scoring.justificativa,
            })

        # Estatisticas
        nivels = {"Alta": 0, "Media": 0, "Baixa": 0, "Irrelevante": 0}
        for r in results:
            nivels[r["relevancia_nivel"]] += 1
        logger.info("scoring_batch_done", total=len(results), **nivels)

        return results
