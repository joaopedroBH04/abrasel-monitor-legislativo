"""Cliente HTTP compartilhado com rate limiting, retry e exponential backoff.

Inspirado no padrao do mcp-brasil, adaptado para as necessidades da Abrasel
com controle rigoroso de rate limiting para APIs publicas.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from abrasel_monitor.settings import settings

logger = structlog.get_logger()


class RateLimiter:
    """Rate limiter baseado em token bucket para respeitar limites de API."""

    def __init__(self, requests_per_second: float = 1.0):
        self.rps = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()


class RetryableHTTPError(Exception):
    """Erro HTTP que pode ser retentado (429, 5xx)."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}")


class MonitorHTTPClient:
    """Cliente HTTP async com rate limiting, retry e logging estruturado."""

    def __init__(
        self,
        base_url: str,
        rate_limiter: RateLimiter | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter or RateLimiter(1.0)
        self._timeout = timeout or settings.http_timeout_seconds
        self._headers = {
            "User-Agent": "AbraselMonitorLegislativo/1.0 (contato@abrasel.com.br)",
            "Accept": "application/json",
            **(headers or {}),
        }
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=httpx.Timeout(self._timeout),
                http2=True,
                follow_redirects=True,
            )
        return self._client

    @retry(
        retry=retry_if_exception_type(RetryableHTTPError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        reraise=True,
    )
    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        await self.rate_limiter.acquire()
        client = await self._get_client()

        url = f"/{endpoint.lstrip('/')}"
        logger.debug("http_request", method="GET", url=f"{self.base_url}{url}", params=params)

        response = await client.get(url, params=params)

        if response.status_code in (429, 500, 502, 503, 504):
            raise RetryableHTTPError(response.status_code, response.text[:200])

        response.raise_for_status()
        return response.json()

    async def get_paginated(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        page_param: str = "pagina",
        items_param: str = "itens",
        items_per_page: int = 100,
        data_key: str = "dados",
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Coleta paginada automatica. Retorna todos os itens de todas as paginas."""
        all_items: list[dict[str, Any]] = []
        page = 1
        params = dict(params or {})
        params[items_param] = items_per_page

        while True:
            params[page_param] = page
            response = await self.get(endpoint, params=params)

            if isinstance(response, dict):
                items = response.get(data_key, [])
            elif isinstance(response, list):
                items = response
            else:
                break

            if not items:
                break

            all_items.extend(items)
            logger.info("paginated_fetch", endpoint=endpoint, page=page, items_fetched=len(items), total=len(all_items))

            if len(items) < items_per_page:
                break

            if max_pages and page >= max_pages:
                logger.info("max_pages_reached", endpoint=endpoint, max_pages=max_pages)
                break

            page += 1

        return all_items

    async def get_xml(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        """Requisicao que retorna XML (usado pelo Senado)."""
        await self.rate_limiter.acquire()
        client = await self._get_client()
        url = f"/{endpoint.lstrip('/')}"

        headers = {**self._headers, "Accept": "application/xml"}
        response = await client.get(url, params=params, headers=headers)

        if response.status_code in (429, 500, 502, 503, 504):
            raise RetryableHTTPError(response.status_code, response.text[:200])

        response.raise_for_status()
        return response.text

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> MonitorHTTPClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


# Clientes pre-configurados para cada fonte
def create_camara_client() -> MonitorHTTPClient:
    return MonitorHTTPClient(
        base_url="https://dadosabertos.camara.leg.br/api/v2",
        rate_limiter=RateLimiter(settings.camara_rate_limit_rps),
    )


def create_senado_client() -> MonitorHTTPClient:
    return MonitorHTTPClient(
        base_url="https://legis.senado.leg.br/dadosabertos",
        rate_limiter=RateLimiter(settings.senado_rate_limit_rps),
        headers={"Accept": "application/json"},
    )


def create_assembleia_client(base_url: str) -> MonitorHTTPClient:
    return MonitorHTTPClient(
        base_url=base_url,
        rate_limiter=RateLimiter(settings.assembleia_rate_limit_rps),
    )
