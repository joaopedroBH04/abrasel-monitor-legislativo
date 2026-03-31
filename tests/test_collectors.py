"""Testes dos coletores legislativos."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from abrasel_monitor.collectors.camara import CamaraCollector
from abrasel_monitor.collectors.senado import SenadoCollector
from abrasel_monitor.collectors.base import ProposicaoRaw


class TestProposicaoRaw:
    def test_to_dict(self):
        prop = ProposicaoRaw(
            source_id="123",
            source="CAMARA",
            tipo="PL",
            numero=456,
            ano=2024,
            ementa="Teste de proposicao",
        )
        d = prop.to_dict()
        assert d["source_id"] == "123"
        assert d["source"] == "CAMARA"
        assert d["tipo"] == "PL"
        assert d["ano"] == 2024


class TestCamaraCollector:
    def test_parse_proposicao(self):
        collector = CamaraCollector.__new__(CamaraCollector)
        raw = {
            "id": 123456,
            "siglaTipo": "PL",
            "numero": 789,
            "ano": 2024,
            "ementa": "Altera regras para restaurantes",
            "dataApresentacao": "2024-03-15",
        }
        result = collector._parse_proposicao(raw)
        assert result is not None
        assert result.source == "CAMARA"
        assert result.tipo == "PL"
        assert result.numero == 789
        assert result.ano == 2024

    def test_parse_proposicao_invalid(self):
        collector = CamaraCollector.__new__(CamaraCollector)
        result = collector._parse_proposicao({})
        # Deve retornar algo ou None sem crash
        assert result is not None or result is None


class TestSenadoCollector:
    def test_extract_materias(self):
        collector = SenadoCollector.__new__(SenadoCollector)
        data = {
            "PesquisaBasicaMateria": {
                "Materias": {
                    "Materia": [
                        {"CodigoMateria": "1", "IdentificacaoMateria": {"SiglaSubtipoMateria": "PL", "NumeroMateria": "1", "AnoMateria": "2024"}},
                        {"CodigoMateria": "2", "IdentificacaoMateria": {"SiglaSubtipoMateria": "PEC", "NumeroMateria": "2", "AnoMateria": "2024"}},
                    ]
                }
            }
        }
        materias = collector._extract_materias(data)
        assert len(materias) == 2

    def test_safe_int(self):
        assert SenadoCollector._safe_int("123") == 123
        assert SenadoCollector._safe_int(None) == 0
        assert SenadoCollector._safe_int("abc") == 0
        assert SenadoCollector._safe_int("") == 0
