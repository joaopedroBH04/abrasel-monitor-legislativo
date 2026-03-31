"""Coletores de dados legislativos de todas as fontes."""

from abrasel_monitor.collectors.camara import CamaraCollector
from abrasel_monitor.collectors.senado import SenadoCollector

__all__ = ["CamaraCollector", "SenadoCollector"]
