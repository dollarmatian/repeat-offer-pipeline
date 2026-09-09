from decimal import Decimal

import pytest
from django.test import Client

from rulesets.lending.ruleset import LendingV1
from rulesets.metering.ruleset import MeteringV1


@pytest.fixture
def lending_inputs():
    return {
        "loans_repaid": 3,
        "missed_payments_last_12m": 0,
        "outstanding_balance": Decimal("5000"),
        "average_monthly_revenue": Decimal("10000"),
        "requested_amount": Decimal("20000"),
        "sector": "retail",
    }


@pytest.fixture
def metering_inputs():
    return {
        "previous_read": 1000,
        "current_read": 1300,
        "days_in_period": 30,
        "read_source": "smart",
        "tariff_code": "standard",
    }


@pytest.fixture
def lending_config():
    return LendingV1.config


@pytest.fixture
def metering_config():
    return MeteringV1.config


@pytest.fixture
def api():
    return Client()
