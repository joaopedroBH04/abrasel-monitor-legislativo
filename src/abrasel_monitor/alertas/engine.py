"""Motor de Alertas - Disparo por email (SES) e Slack.

Conforme RN-03: Alertas imediatos so para proposicoes de relevancia Alta
que entrarem em pauta de votacao em menos de 72h.

Tipos de alerta (secao 11.3):
- Votacao iminente de proposicao de alta relevancia
- Parlamentar aliado assume relatoria
- Parlamentar muda de partido
- Parlamentar faz discurso mencionando temas do setor
- Parlamentar aliado nao comparece a votacao critica
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from abrasel_monitor.models import (
    AgendaMonitoramento,
    AlertaDisparado,
    Proposicao,
)
from abrasel_monitor.settings import settings

logger = structlog.get_logger()


class AlertEngine:
    """Motor de alertas que coordena verificacao e disparo."""

    async def check_votacoes_iminentes(self, session: AsyncSession) -> list[dict[str, Any]]:
        """Verifica proposicoes de alta relevancia com votacao nas proximas 72h."""
        now = datetime.now(timezone.utc)
        window = now + timedelta(hours=settings.alert_voting_window_hours)

        stmt = (
            select(AgendaMonitoramento, Proposicao)
            .join(Proposicao, AgendaMonitoramento.proposicao_id == Proposicao.id)
            .where(
                and_(
                    AgendaMonitoramento.data_sessao >= now,
                    AgendaMonitoramento.data_sessao <= window,
                    AgendaMonitoramento.alerta_enviado == False,
                    Proposicao.relevancia_nivel == "Alta",
                )
            )
            .order_by(AgendaMonitoramento.data_sessao)
        )

        result = await session.execute(stmt)
        rows = result.all()

        alertas: list[dict[str, Any]] = []
        for agenda, proposicao in rows:
            alertas.append({
                "tipo": "votacao_iminente",
                "proposicao_id": proposicao.id,
                "titulo": f"{proposicao.tipo} {proposicao.numero}/{proposicao.ano}",
                "ementa": proposicao.ementa,
                "relevancia": proposicao.relevancia_nivel,
                "score": proposicao.relevancia_score,
                "data_sessao": agenda.data_sessao.isoformat(),
                "orgao": agenda.orgao,
                "keywords": proposicao.keywords_matched,
            })

        if alertas:
            logger.info("votacoes_iminentes_encontradas", count=len(alertas))

        return alertas

    async def dispatch_alert(
        self,
        session: AsyncSession,
        alert_data: dict[str, Any],
        channels: list[str] | None = None,
    ) -> None:
        """Dispara alerta via canais configurados."""
        channels = channels or ["slack", "email"]

        message = self._format_message(alert_data)

        for channel in channels:
            try:
                if channel == "slack":
                    await self._send_slack(message, alert_data)
                elif channel == "email":
                    await self._send_email(message, alert_data)

                # Registrar alerta disparado
                alerta = AlertaDisparado(
                    proposicao_id=alert_data["proposicao_id"],
                    tipo_alerta=alert_data["tipo"],
                    canal=channel,
                    destinatarios=settings.ses_recipient_emails if channel == "email" else settings.slack_channel,
                    mensagem_resumo=message[:500],
                )
                session.add(alerta)
                logger.info("alerta_disparado", tipo=alert_data["tipo"], canal=channel, proposicao=alert_data["titulo"])
            except Exception as e:
                logger.error("alerta_erro", canal=channel, error=str(e))

        await session.commit()

    async def dispatch_all_pending(self, session: AsyncSession) -> int:
        """Verifica e dispara todos os alertas pendentes."""
        alertas = await self.check_votacoes_iminentes(session)

        for alerta in alertas:
            await self.dispatch_alert(session, alerta)

            # Marcar agenda como notificada
            stmt = (
                select(AgendaMonitoramento)
                .where(
                    and_(
                        AgendaMonitoramento.proposicao_id == alerta["proposicao_id"],
                        AgendaMonitoramento.alerta_enviado == False,
                    )
                )
            )
            result = await session.execute(stmt)
            for agenda in result.scalars().all():
                agenda.alerta_enviado = True

        await session.commit()
        return len(alertas)

    def _format_message(self, alert_data: dict[str, Any]) -> str:
        """Formata mensagem de alerta."""
        tipo_label = {
            "votacao_iminente": "VOTACAO IMINENTE",
            "nova_proposicao": "NOVA PROPOSICAO",
            "mudanca_relatoria": "MUDANCA DE RELATORIA",
            "discurso": "DISCURSO RELEVANTE",
            "mudanca_partido": "MUDANCA DE PARTIDO",
            "ausencia_votacao": "AUSENCIA EM VOTACAO",
        }

        label = tipo_label.get(alert_data["tipo"], "ALERTA")
        title = alert_data.get("titulo", "")
        ementa = alert_data.get("ementa", "")[:300]
        data_sessao = alert_data.get("data_sessao", "")
        keywords = ", ".join(alert_data.get("keywords", [])[:5])

        return (
            f"[{label}] {title}\n\n"
            f"Ementa: {ementa}\n"
            f"Relevancia: {alert_data.get('relevancia', '')} (Score: {alert_data.get('score', 0)})\n"
            f"Data da sessao: {data_sessao}\n"
            f"Orgao: {alert_data.get('orgao', '')}\n"
            f"Keywords: {keywords}\n"
        )

    async def _send_slack(self, message: str, alert_data: dict[str, Any]) -> None:
        """Envia notificacao via Slack webhook."""
        if not settings.slack_webhook_url:
            logger.warning("slack_webhook_not_configured")
            return

        import httpx

        emoji_map = {
            "votacao_iminente": ":rotating_light:",
            "nova_proposicao": ":page_facing_up:",
            "mudanca_relatoria": ":arrows_counterclockwise:",
            "discurso": ":mega:",
        }

        emoji = emoji_map.get(alert_data["tipo"], ":bell:")

        payload = {
            "channel": settings.slack_channel,
            "username": "Monitor Legislativo Abrasel",
            "icon_emoji": emoji,
            "text": message,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(settings.slack_webhook_url, json=payload)
            response.raise_for_status()

    async def _send_email(self, message: str, alert_data: dict[str, Any]) -> None:
        """Envia email via Amazon SES."""
        if not settings.ses_sender_email or not settings.ses_recipients_list:
            logger.warning("ses_not_configured")
            return

        import boto3

        ses = boto3.client("ses", region_name=settings.aws_region)

        tipo_label = alert_data.get("tipo", "alerta").replace("_", " ").title()
        subject = f"[Abrasel Monitor] {tipo_label}: {alert_data.get('titulo', '')}"

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="background-color: #1a5276; color: white; padding: 15px; border-radius: 5px;">
                <h2>Monitor Legislativo Abrasel</h2>
            </div>
            <div style="padding: 20px; border: 1px solid #ddd; margin-top: 10px; border-radius: 5px;">
                <h3 style="color: #e74c3c;">{tipo_label}</h3>
                <p><strong>{alert_data.get('titulo', '')}</strong></p>
                <p>{alert_data.get('ementa', '')[:500]}</p>
                <table style="border-collapse: collapse; width: 100%; margin-top: 10px;">
                    <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Relevancia</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{alert_data.get('relevancia', '')} (Score: {alert_data.get('score', 0)})</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Data da Sessao</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{alert_data.get('data_sessao', '')}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>Orgao</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{alert_data.get('orgao', '')}</td></tr>
                </table>
            </div>
            <p style="color: #888; font-size: 12px; margin-top: 20px;">
                Gerado automaticamente pelo Monitor Legislativo Abrasel
            </p>
        </body>
        </html>
        """

        ses.send_email(
            Source=settings.ses_sender_email,
            Destination={"ToAddresses": settings.ses_recipients_list},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": message, "Charset": "UTF-8"},
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                },
            },
        )
