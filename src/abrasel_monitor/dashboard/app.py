"""Dashboard Streamlit do Monitor Legislativo Abrasel.

Prototipo de visualizacao (conforme secao 9.3 do documento).
Para producao, sera migrado para Metabase auto-hospedado no ECS.

Uso: streamlit run src/abrasel_monitor/dashboard/app.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


# Page config
st.set_page_config(
    page_title="Monitor Legislativo Abrasel",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        background-color: #1a5276;
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 20px;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 15px;
        border-radius: 8px;
        border-left: 4px solid #1a5276;
    }
    .alert-high { border-left-color: #e74c3c; }
    .alert-medium { border-left-color: #f39c12; }
    .alert-low { border-left-color: #27ae60; }
</style>
""", unsafe_allow_html=True)


def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>Monitor Legislativo Abrasel</h1>
        <p>Radar de Pautas e Parlamentares - Setor de Alimentacao Fora do Lar</p>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.image("https://abrasel.com.br/wp-content/uploads/2021/01/Logo-Abrasel-2021.png", width=200)
        st.markdown("---")

        page = st.selectbox("Navegacao", [
            "Visao Geral",
            "Proposicoes",
            "Parlamentares",
            "Agenda e Alertas",
            "Relatorios",
            "Configuracao",
        ])

        st.markdown("---")
        st.markdown("**Filtros**")
        fonte = st.multiselect("Fonte", ["Camara", "Senado", "Assembleias"], default=["Camara", "Senado"])
        relevancia = st.multiselect("Relevancia", ["Alta", "Media", "Baixa", "Irrelevante"], default=["Alta", "Media"])
        periodo = st.date_input("Periodo", value=(datetime.now() - timedelta(days=30), datetime.now()))

    # Pages
    if page == "Visao Geral":
        _render_overview()
    elif page == "Proposicoes":
        _render_proposicoes(relevancia)
    elif page == "Parlamentares":
        _render_parlamentares()
    elif page == "Agenda e Alertas":
        _render_agenda()
    elif page == "Relatorios":
        _render_relatorios()
    elif page == "Configuracao":
        _render_config()


def _render_overview():
    """Pagina de visao geral com metricas resumidas."""
    st.subheader("Visao Geral")

    # Metricas principais
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Proposicoes Monitoradas", "12,847", delta="+23 hoje")
    with col2:
        st.metric("Relevancia Alta", "342", delta="+5 hoje")
    with col3:
        st.metric("Parlamentares Aliados", "87", delta="+2 este mes")
    with col4:
        st.metric("Alertas esta Semana", "12", delta="-3 vs semana anterior")

    st.markdown("---")

    # Graficos
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Proposicoes por Relevancia")
        data = pd.DataFrame({
            "Nivel": ["Alta", "Media", "Baixa", "Irrelevante"],
            "Quantidade": [342, 1205, 3100, 8200],
        })
        fig = px.pie(data, values="Quantidade", names="Nivel",
                     color="Nivel", color_discrete_map={
                         "Alta": "#e74c3c", "Media": "#f39c12",
                         "Baixa": "#3498db", "Irrelevante": "#95a5a6"
                     })
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Evolucao Mensal de Proposicoes Relevantes")
        months = pd.date_range("2024-01", periods=12, freq="ME")
        data = pd.DataFrame({
            "Mes": months,
            "Alta": [28, 35, 42, 31, 38, 45, 29, 33, 41, 37, 44, 42],
            "Media": [95, 88, 102, 91, 97, 110, 85, 92, 105, 99, 108, 103],
        })
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data["Mes"], y=data["Alta"], name="Alta", line=dict(color="#e74c3c")))
        fig.add_trace(go.Scatter(x=data["Mes"], y=data["Media"], name="Media", line=dict(color="#f39c12")))
        st.plotly_chart(fig, use_container_width=True)

    # Ultimas proposicoes relevantes
    st.subheader("Ultimas Proposicoes de Alta Relevancia")
    recent_data = pd.DataFrame({
        "Tipo": ["PL", "PEC", "PL", "MPV", "PL"],
        "Numero": ["1234/2026", "45/2026", "5678/2026", "23/2026", "9012/2026"],
        "Ementa": [
            "Altera regras do SIMPLES Nacional para restaurantes",
            "Reforma tributaria - impacto em servicos de alimentacao",
            "Regulamenta dark kitchens e ghost kitchens",
            "Desoneracoa da folha para setor de servicos",
            "Proibe cobranca de taxa de servico em restaurantes",
        ],
        "Relevancia": ["Alta", "Alta", "Alta", "Alta", "Alta"],
        "Score": [15, 12, 11, 10, 9],
        "Fonte": ["Camara", "Senado", "Camara", "Executivo", "Camara"],
        "Data": ["2026-03-28", "2026-03-27", "2026-03-26", "2026-03-25", "2026-03-24"],
    })
    st.dataframe(recent_data, use_container_width=True)


def _render_proposicoes(relevancia: list[str]):
    """Pagina de proposicoes com busca e filtros."""
    st.subheader("Proposicoes Legislativas")

    # Busca
    search = st.text_input("Buscar por palavra-chave, numero ou ementa", placeholder="Ex: restaurante, PL 1234/2026")

    # Filtros
    col1, col2, col3 = st.columns(3)
    with col1:
        tipo = st.multiselect("Tipo", ["PL", "PEC", "PLP", "PDC", "MPV", "EMC"], default=["PL", "PEC", "MPV"])
    with col2:
        situacao = st.selectbox("Situacao", ["Todas", "Em tramitacao", "Aprovada", "Arquivada"])
    with col3:
        ordenar = st.selectbox("Ordenar por", ["Score (maior)", "Data (mais recente)", "Tipo"])

    st.info(f"Filtros ativos: Relevancia={relevancia}, Tipos={tipo}")

    # Tabela de resultados (dados de exemplo)
    st.dataframe(pd.DataFrame({
        "ID": range(1, 11),
        "Tipo": ["PL"] * 5 + ["PEC"] * 3 + ["MPV"] * 2,
        "Numero/Ano": [f"{n}/2026" for n in range(1000, 1010)],
        "Ementa": ["Proposicao de exemplo..."] * 10,
        "Score": [15, 12, 11, 9, 8, 7, 6, 5, 4, 3],
        "Nivel": ["Alta"] * 3 + ["Media"] * 4 + ["Baixa"] * 3,
        "Fonte": ["Camara"] * 6 + ["Senado"] * 4,
    }), use_container_width=True)


def _render_parlamentares():
    """Pagina de monitoramento de parlamentares."""
    st.subheader("Parlamentares - Indice de Alinhamento")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Top 10 Aliados")
        aliados = pd.DataFrame({
            "Parlamentar": [f"Dep. Parlamentar {i}" for i in range(1, 11)],
            "Partido": ["PSD", "MDB", "PP", "PSDB", "DEM", "PL", "MDB", "PP", "PSD", "PSDB"],
            "UF": ["SP", "MG", "RS", "PR", "RJ", "SP", "BA", "GO", "SC", "CE"],
            "Indice": [92.5, 88.3, 85.1, 82.7, 80.0, 78.5, 75.2, 73.8, 71.1, 70.0],
            "Classificacao": ["Aliado Forte"] * 10,
        })
        st.dataframe(aliados, use_container_width=True)

    with col2:
        st.subheader("Distribuicao por Classificacao")
        data = pd.DataFrame({
            "Classificacao": ["Aliado Forte", "Aliado", "Neutro", "Opositor"],
            "Quantidade": [87, 145, 198, 83],
        })
        fig = px.bar(data, x="Classificacao", y="Quantidade",
                     color="Classificacao", color_discrete_map={
                         "Aliado Forte": "#27ae60", "Aliado": "#2ecc71",
                         "Neutro": "#f39c12", "Opositor": "#e74c3c"
                     })
        st.plotly_chart(fig, use_container_width=True)


def _render_agenda():
    """Pagina de agenda e alertas."""
    st.subheader("Agenda - Proximas Votacoes")

    st.warning("3 votacoes de alta relevancia nas proximas 72h!")

    for i in range(3):
        with st.expander(f"PL {1234 + i}/2026 - Pauta para {(datetime.now() + timedelta(days=i+1)).strftime('%d/%m')}"):
            st.write(f"**Ementa:** Proposicao de exemplo {i+1} impactando o setor AFL")
            st.write(f"**Score:** {15 - i*2} | **Orgao:** Plenario da Camara")
            st.write(f"**Keywords:** restaurante, SIMPLES Nacional, alimentacao fora do lar")

    st.markdown("---")
    st.subheader("Historico de Alertas")
    alertas = pd.DataFrame({
        "Data": [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d %H:%M") for i in range(10)],
        "Tipo": ["Votacao Iminente"] * 4 + ["Nova Proposicao"] * 3 + ["Discurso Relevante"] * 3,
        "Proposicao": [f"PL {1000 + i}/2026" for i in range(10)],
        "Canal": ["Slack", "Email"] * 5,
        "Status": ["Enviado"] * 10,
    })
    st.dataframe(alertas, use_container_width=True)


def _render_relatorios():
    """Pagina de relatorios periodicos."""
    st.subheader("Relatorios")
    st.info("Relatorios semanais sao gerados automaticamente toda sexta-feira as 18h.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Gerar Relatorio Semanal"):
            st.success("Relatorio semanal gerado e enviado por email!")
    with col2:
        if st.button("Gerar Relatorio Mensal"):
            st.success("Relatorio mensal gerado!")

    # Download
    st.download_button(
        label="Baixar CSV de Proposicoes Relevantes",
        data="tipo,numero,ano,ementa,score,nivel\nPL,1234,2026,Exemplo,15,Alta\n",
        file_name="proposicoes_relevantes.csv",
        mime="text/csv",
    )


def _render_config():
    """Pagina de configuracao."""
    st.subheader("Configuracao")

    st.markdown("### Palavras-chave")
    st.info("A lista de palavras-chave e gerenciada via arquivo YAML (config/keywords.yaml). "
            "Alteracoes nao requerem deploy.")

    st.markdown("### Fontes de Dados")
    sources = pd.DataFrame({
        "Fonte": ["Camara", "Senado", "ALESP", "ALMG", "ALERJ", "ALRS", "ALEP", "ALAL", "ALEAM", "CLDF", "ALEMS"],
        "Status": ["Ativo"] * 5 + ["Piloto"] * 4 + ["Piloto"] * 2,
        "Ultima Coleta": [(datetime.now() - timedelta(hours=i*2)).strftime("%Y-%m-%d %H:%M") for i in range(11)],
        "Cobertura Historica": ["1987", "1991", "1990", "1988", "1995", "1999", "2002", "2000", "2000", "2000", "2000"],
    })
    st.dataframe(sources, use_container_width=True)


if __name__ == "__main__":
    main()
