"""Testes do Motor de Alinhamento Parlamentar."""

from abrasel_monitor.parlamentares.alignment import AlignmentEngine


class TestAlignmentClassification:
    def test_aliado_forte(self):
        engine = AlignmentEngine()
        assert engine.classify(92.5) == "Aliado Forte"
        assert engine.classify(70.0) == "Aliado Forte"

    def test_aliado(self):
        engine = AlignmentEngine()
        assert engine.classify(65.0) == "Aliado"
        assert engine.classify(50.0) == "Aliado"

    def test_neutro(self):
        engine = AlignmentEngine()
        assert engine.classify(45.0) == "Neutro"
        assert engine.classify(30.0) == "Neutro"

    def test_opositor(self):
        engine = AlignmentEngine()
        assert engine.classify(29.9) == "Opositor"
        assert engine.classify(0.0) == "Opositor"

    def test_boundary_values(self):
        engine = AlignmentEngine()
        assert engine.classify(69.9) == "Aliado"
        assert engine.classify(49.9) == "Neutro"
        assert engine.classify(29.9) == "Opositor"
