"""Exactly 11 specialised agents + 1 Supervisor."""

from __future__ import annotations

from app.agents.analytics import AnalyticsAgent
from app.agents.base import BaseAgent
from app.agents.customer_support import CustomerSupportAgent
from app.agents.fraud_detection import FraudDetectionAgent
from app.agents.inventory import InventoryAgent
from app.agents.logistics import LogisticsAgent
from app.agents.notification import NotificationAgent
from app.agents.order_management import OrderManagementAgent
from app.agents.payment import PaymentAgent
from app.agents.product_intelligence import ProductIntelligenceAgent
from app.agents.returns import ReturnRefundAgent
from app.agents.shopping import ShoppingAgent
from app.agents.supervisor import SupervisorAgent

SPECIALISED_AGENTS: tuple[type[BaseAgent], ...] = (
    ShoppingAgent,
    ProductIntelligenceAgent,
    InventoryAgent,
    OrderManagementAgent,
    PaymentAgent,
    ReturnRefundAgent,
    CustomerSupportAgent,
    LogisticsAgent,
    FraudDetectionAgent,
    AnalyticsAgent,
    NotificationAgent,
)


class AgentRegistry:
    def __init__(self) -> None:
        self.specialised: dict[str, BaseAgent] = {}
        for cls in SPECIALISED_AGENTS:
            agent = cls()
            self.specialised[agent.name] = agent
        self.supervisor = SupervisorAgent(self.specialised)

    def all(self) -> list[BaseAgent]:
        return [self.supervisor, *self.specialised.values()]

    def get(self, name: str) -> BaseAgent | None:
        if name == self.supervisor.name:
            return self.supervisor
        return self.specialised.get(name)
