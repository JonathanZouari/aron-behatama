"""חיווט תלויות: בסיס נתונים, repositories, שירותים וסוכן AI לפי התצורה."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Settings
from .repositories.customer_repo import AccessTokenRepository, AdminRepository, CustomerRepository
from .repositories.db import Database
from .repositories.inquiry_repo import InquiryRepository
from .repositories.pricebook_repo import PriceBookRepository
from .repositories.quote_repo import QuoteRepository
from .services.auth_admin import AdminAuthenticator
from .services.inquiry_service import InquiryService
from .services.quote_service import QuoteService
from .services.security import RateLimiter

log = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    db: Database
    inquiries: InquiryRepository
    quotes: QuoteRepository
    pricebooks: PriceBookRepository
    customers: CustomerRepository
    admins: AdminRepository
    tokens: AccessTokenRepository
    inquiry_service: InquiryService
    quote_service: QuoteService
    auth: AdminAuthenticator
    ai_limiter: RateLimiter
    agent_is_mock: bool


def build_container(settings: Settings, db: Database | None = None) -> Container:
    if db is None:
        db = Database.sqlite(settings.sqlite_path) if settings.demo_mode else Database.postgres(settings.database_url)

    inquiries = InquiryRepository(db)
    quotes = QuoteRepository(db)
    pricebooks = PriceBookRepository(db)
    customers = CustomerRepository(db)
    admins = AdminRepository(db)
    tokens = AccessTokenRepository(db)

    agent, is_mock = _build_agent(settings, pricebooks)
    return Container(
        settings=settings, db=db, inquiries=inquiries, quotes=quotes, pricebooks=pricebooks,
        customers=customers, admins=admins, tokens=tokens,
        inquiry_service=InquiryService(inquiries, agent, is_mock),
        quote_service=QuoteService(inquiries, quotes, pricebooks, settings.is_production),
        auth=AdminAuthenticator(settings, admins),
        ai_limiter=RateLimiter(settings.ai_messages_per_window, settings.ai_window_seconds),
        agent_is_mock=is_mock,
    )


def _build_agent(settings: Settings, pricebooks: PriceBookRepository):
    if settings.use_real_ai:
        from .services.ai.agent import OpenAIPlanningAgent

        return OpenAIPlanningAgent(settings.openai_model, pricebooks.list_catalog), False

    from .services.ai.mock_agent import run_mock_agent

    class MockAgent:
        def run(self, message, current_spec, history):
            return run_mock_agent(message, current_spec)

    log.warning("סוכן AI מדומה פעיל (AI_ENABLED=false או ללא OPENAI_API_KEY)")
    return MockAgent(), True
