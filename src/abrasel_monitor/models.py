"""Modelos SQLAlchemy para a Gold Layer (PostgreSQL).

Schema conforme especificacao do documento Abrasel Monitor Legislativo v1.0.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Proposicao(Base):
    """Proposicoes legislativas (PL, PEC, PLP, PDC, MPV, EMC, etc.)."""

    __tablename__ = "proposicoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # CAMARA | SENADO | ALESP | ALERJ | ALMG | ALRS | ALEP | ALAL | ALEAM | CLDF | ALEMS
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=True)
    ano: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ementa: Mapped[str] = mapped_column(Text, nullable=True)
    ementa_detalhada: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords_matched: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    temas: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    relevancia_score: Mapped[int] = mapped_column(SmallInteger, default=0)
    relevancia_nivel: Mapped[str] = mapped_column(String(15), default="Irrelevante")  # Alta / Media / Baixa / Irrelevante
    situacao_atual: Mapped[str | None] = mapped_column(String(200), nullable=True)
    data_apresentacao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_ultima_atualizacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    casa_origem: Mapped[str | None] = mapped_column(String(15), nullable=True)  # Camara / Senado / Assembleia
    url_inteiro_teor: Mapped[str | None] = mapped_column(Text, nullable=True)
    s3_raw_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relacionamentos
    tramitacoes: Mapped[list[Tramitacao]] = relationship(back_populates="proposicao", cascade="all, delete-orphan")
    votacoes: Mapped[list[VotacaoNominal]] = relationship(back_populates="proposicao", cascade="all, delete-orphan")
    autores: Mapped[list[AutorProposicao]] = relationship(back_populates="proposicao", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_proposicao_source"),
        Index("ix_proposicoes_relevancia", "relevancia_nivel", "relevancia_score"),
        Index("ix_proposicoes_ano", "ano"),
        Index("ix_proposicoes_source", "source"),
        Index("ix_proposicoes_tipo", "tipo"),
        CheckConstraint("relevancia_nivel IN ('Alta', 'Media', 'Baixa', 'Irrelevante')", name="ck_relevancia_nivel"),
    )


class Parlamentar(Base):
    """Deputados, senadores e deputados estaduais."""

    __tablename__ = "parlamentares"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    nome_civil: Mapped[str] = mapped_column(String(200), nullable=False)
    nome_parlamentar: Mapped[str] = mapped_column(String(200), nullable=True)
    partido: Mapped[str | None] = mapped_column(String(30), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    legislatura_atual: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    total_votos_setor: Mapped[int] = mapped_column(SmallInteger, default=0)
    votos_favor_setor: Mapped[int] = mapped_column(SmallInteger, default=0)
    indice_alinhamento: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    classificacao: Mapped[str] = mapped_column(String(20), default="Neutro")  # Aliado Forte / Aliado / Neutro / Opositor
    comissoes_atuais: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    foto_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_oficial: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telefone_pessoal: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Campo manual, acesso restrito
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relacionamentos
    votos: Mapped[list[VotoParlamentar]] = relationship(back_populates="parlamentar")
    autorias: Mapped[list[AutorProposicao]] = relationship(back_populates="parlamentar")
    discursos: Mapped[list[Discurso]] = relationship(back_populates="parlamentar")

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_parlamentar_source"),
        Index("ix_parlamentares_classificacao", "classificacao"),
        Index("ix_parlamentares_partido", "partido"),
        Index("ix_parlamentares_uf", "uf"),
        CheckConstraint(
            "classificacao IN ('Aliado Forte', 'Aliado', 'Neutro', 'Opositor')",
            name="ck_classificacao_parlamentar",
        ),
    )


class Tramitacao(Base):
    """Historico de tramitacao de proposicoes."""

    __tablename__ = "tramitacoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    proposicao_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proposicoes.id", ondelete="CASCADE"), nullable=False)
    data_tramitacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    despacho: Mapped[str | None] = mapped_column(Text, nullable=True)
    orgao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(200), nullable=True)

    proposicao: Mapped[Proposicao] = relationship(back_populates="tramitacoes")

    __table_args__ = (
        Index("ix_tramitacoes_proposicao", "proposicao_id"),
        Index("ix_tramitacoes_data", "data_tramitacao"),
    )


class VotacaoNominal(Base):
    """Votacoes nominais com resultado agregado."""

    __tablename__ = "votacoes_nominais"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    proposicao_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proposicoes.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_votacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    casa: Mapped[str] = mapped_column(String(15), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    resultado: Mapped[str | None] = mapped_column(String(50), nullable=True)
    votos_sim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votos_nao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votos_abstencao: Mapped[int | None] = mapped_column(Integer, nullable=True)

    proposicao: Mapped[Proposicao] = relationship(back_populates="votacoes")
    votos: Mapped[list[VotoParlamentar]] = relationship(back_populates="votacao", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_votacoes_proposicao", "proposicao_id"),
        Index("ix_votacoes_data", "data_votacao"),
    )


class VotoParlamentar(Base):
    """Voto individual de cada parlamentar por votacao."""

    __tablename__ = "votos_parlamentares"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    votacao_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("votacoes_nominais.id", ondelete="CASCADE"), nullable=False)
    parlamentar_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parlamentares.id"), nullable=False)
    voto: Mapped[str] = mapped_column(String(20), nullable=False)  # Sim / Nao / Abstencao / Obstrucao / Ausente
    partido_na_data: Mapped[str | None] = mapped_column(String(30), nullable=True)

    votacao: Mapped[VotacaoNominal] = relationship(back_populates="votos")
    parlamentar: Mapped[Parlamentar] = relationship(back_populates="votos")

    __table_args__ = (
        UniqueConstraint("votacao_id", "parlamentar_id", name="uq_voto_parlamentar"),
        Index("ix_votos_parlamentar", "parlamentar_id"),
    )


class AutorProposicao(Base):
    """Relacao N:N entre proposicoes e autores."""

    __tablename__ = "autores_proposicoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    proposicao_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proposicoes.id", ondelete="CASCADE"), nullable=False)
    parlamentar_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parlamentares.id"), nullable=False)
    tipo_autoria: Mapped[str] = mapped_column(String(30), default="Autor")  # Autor / Coautor / Relator

    proposicao: Mapped[Proposicao] = relationship(back_populates="autores")
    parlamentar: Mapped[Parlamentar] = relationship(back_populates="autorias")

    __table_args__ = (
        UniqueConstraint("proposicao_id", "parlamentar_id", "tipo_autoria", name="uq_autoria"),
    )


class Discurso(Base):
    """Pronunciamentos de parlamentares com mencao a temas do setor."""

    __tablename__ = "discursos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parlamentar_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("parlamentares.id"), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_discurso: Mapped[date | None] = mapped_column(Date, nullable=True)
    casa: Mapped[str] = mapped_column(String(15), nullable=False)
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords_matched: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    parlamentar: Mapped[Parlamentar] = relationship(back_populates="discursos")

    __table_args__ = (
        Index("ix_discursos_parlamentar", "parlamentar_id"),
        Index("ix_discursos_data", "data_discurso"),
    )


class AgendaMonitoramento(Base):
    """Pautas de plenario e comissoes futuras com proposicoes relevantes."""

    __tablename__ = "agenda_monitoramento"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    data_sessao: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    casa: Mapped[str] = mapped_column(String(15), nullable=False)
    orgao: Mapped[str | None] = mapped_column(String(200), nullable=True)
    proposicao_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("proposicoes.id"), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    alerta_enviado: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_agenda_data", "data_sessao"),
    )


class AlertaDisparado(Base):
    """Historico de alertas enviados."""

    __tablename__ = "alertas_disparados"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    proposicao_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("proposicoes.id"), nullable=False)
    tipo_alerta: Mapped[str] = mapped_column(String(50), nullable=False)  # votacao_iminente / nova_proposicao / mudanca_relatoria / discurso
    canal: Mapped[str] = mapped_column(String(20), nullable=False)  # email / slack
    data_envio: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    destinatarios: Mapped[str | None] = mapped_column(Text, nullable=True)
    mensagem_resumo: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_alertas_proposicao", "proposicao_id"),
        Index("ix_alertas_data", "data_envio"),
    )


class ExecucaoRobo(Base):
    """Log de cada execucao do robo com status e metricas."""

    __tablename__ = "execucoes_robo"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fonte: Mapped[str] = mapped_column(String(30), nullable=False)
    tipo_execucao: Mapped[str] = mapped_column(String(30), nullable=False)  # full_load / incremental / agenda / express / relatorio
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running / success / error / partial
    total_coletado: Mapped[int] = mapped_column(Integer, default=0)
    total_relevantes: Mapped[int] = mapped_column(Integer, default=0)
    erro_mensagem: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_execucoes_fonte", "fonte"),
        Index("ix_execucoes_inicio", "inicio"),
    )


class KeywordsConfig(Base):
    """Cache da configuracao de palavras-chave ativa."""

    __tablename__ = "keywords_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    termo: Mapped[str] = mapped_column(String(200), nullable=False)
    peso: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 3=primaria, 1=secundaria, 2=tema
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # primaria / secundaria / tema / exclusao
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("categoria", "termo", name="uq_keyword"),
        Index("ix_keywords_tipo", "tipo"),
    )
