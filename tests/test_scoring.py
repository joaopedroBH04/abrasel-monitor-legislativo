"""Testes do Motor de Relevancia (Scoring Engine)."""

import pytest
from abrasel_monitor.scoring.engine import ScoringEngine, KeywordsConfig


@pytest.fixture
def engine():
    config = KeywordsConfig("config/keywords.yaml")
    return ScoringEngine(config)


class TestScoringEngine:
    def test_proposicao_alta_relevancia(self, engine):
        """Proposicao com keyword primaria deve ter score alto."""
        result = engine.score_proposicao(
            ementa="Altera regras do SIMPLES Nacional para restaurantes e bares"
        )
        assert result.score >= 5
        assert result.nivel == "Alta"
        assert "restaurante" in [k.lower() for k in result.keywords_matched] or "bar" in [k.lower() for k in result.keywords_matched]

    def test_proposicao_media_relevancia(self, engine):
        """Proposicao com keywords secundarias deve ter score medio."""
        result = engine.score_proposicao(
            ementa="Altera regras de vigilancia sanitaria para estabelecimentos comerciais"
        )
        assert result.score >= 1
        assert result.nivel in ("Media", "Baixa")

    def test_proposicao_irrelevante(self, engine):
        """Proposicao sem keywords deve ser irrelevante."""
        result = engine.score_proposicao(
            ementa="Altera regras de aposentadoria do funcionalismo publico federal"
        )
        assert result.score == 0
        assert result.nivel == "Irrelevante"

    def test_exclusao_rebaixa_score(self, engine):
        """Termos de exclusao devem rebaixar o score."""
        result = engine.score_proposicao(
            ementa="Programa de alimentacao escolar nas escolas publicas"
        )
        # Exclusao "alimentacao escolar" deve rebaixar
        assert result.exclusion_triggered

    def test_tema_camara_adiciona_pontos(self, engine):
        """Tema da Camara deve adicionar pontos ao score."""
        result = engine.score_proposicao(
            ementa="Projeto sobre restaurantes",
            temas=[{"codTema": 40}],  # Industria, Comercio e Servicos
        )
        assert result.score > 0
        assert len(result.temas_matched) > 0

    def test_batch_scoring(self, engine):
        """Scoring em batch deve processar multiplas proposicoes."""
        proposicoes = [
            {"ementa": "PL sobre restaurantes e bares", "source_id": "1"},
            {"ementa": "PL sobre agricultura", "source_id": "2"},
            {"ementa": "PL sobre food trucks e delivery", "source_id": "3"},
        ]
        results = engine.score_batch(proposicoes)
        assert len(results) == 3
        assert results[0]["relevancia_nivel"] in ("Alta", "Media")
        assert results[2]["relevancia_nivel"] in ("Alta", "Media")

    def test_autor_aliado_adiciona_pontos(self, engine):
        """Autor aliado deve adicionar pontos ao score."""
        result = engine.score_proposicao(
            ementa="Projeto generico sobre comercio",
            autores_ids=["123"],
            aliados_ids={"123", "456"},
        )
        # Deve ter pontos do autor aliado
        assert result.score >= 2


class TestKeywordsConfig:
    def test_load_config(self):
        config = KeywordsConfig("config/keywords.yaml")
        assert len(config.primary_terms) > 0
        assert len(config.secondary_terms) > 0
        assert len(config.exclusion_terms) > 0
        assert len(config.theme_codes) > 0

    def test_primary_contains_restaurante(self):
        config = KeywordsConfig("config/keywords.yaml")
        assert "restaurante" in config.primary_terms

    def test_exclusion_contains_merenda(self):
        config = KeywordsConfig("config/keywords.yaml")
        assert "merenda" in config.exclusion_terms
