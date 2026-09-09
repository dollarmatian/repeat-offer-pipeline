from decimal import Decimal

import pytest

from engine.rules import Outcome
from rulesets.metering.amount import ChargeFromConsumption
from rulesets.metering.eligibility import (
    ConsumptionPlausible,
    PeriodKnown,
    ReadNotBelowPrevious,
    ReadSourceAccepted,
)
from rulesets.metering.pricing import UnitRate


def evaluate(rule_cls, inputs, config, decided=None):
    return rule_cls().run(inputs, decided or {}, config)


class TestPeriodKnown:
    def test_zero_days_fails(self, metering_config):
        assert evaluate(PeriodKnown, {"days_in_period": 0}, metering_config).outcome is Outcome.FAIL

    def test_a_period_passes(self, metering_config):
        assert evaluate(PeriodKnown, {"days_in_period": 1}, metering_config).outcome is Outcome.PASS


class TestReadSourceAccepted:
    @pytest.mark.parametrize("source", ["smart", "customer", "agent"])
    def test_actual_reads_pass(self, metering_config, source):
        assert (
            evaluate(ReadSourceAccepted, {"read_source": source}, metering_config).outcome
            is Outcome.PASS
        )

    def test_estimates_fail(self, metering_config):
        result = evaluate(ReadSourceAccepted, {"read_source": "estimated"}, metering_config)
        assert result.outcome is Outcome.FAIL
        assert "not billed" in result.reason


class TestReadNotBelowPrevious:
    def test_lower_read_refers(self, metering_config):
        result = evaluate(
            ReadNotBelowPrevious, {"previous_read": 500, "current_read": 20}, metering_config
        )
        assert result.outcome is Outcome.REFER

    def test_equal_read_is_zero_consumption(self, metering_config):
        result = evaluate(
            ReadNotBelowPrevious, {"previous_read": 500, "current_read": 500}, metering_config
        )
        assert result.outcome is Outcome.PASS
        assert result.values == {"consumption_kwh": 0}

    def test_higher_read_decides_the_consumption(self, metering_config):
        result = evaluate(
            ReadNotBelowPrevious, {"previous_read": 1000, "current_read": 1300}, metering_config
        )
        assert result.values == {"consumption_kwh": 300}


class TestConsumptionPlausible:
    def test_plausible_consumption_passes(self, metering_config):
        result = evaluate(
            ConsumptionPlausible, {"days_in_period": 30}, metering_config, {"consumption_kwh": 300}
        )
        assert result.outcome is Outcome.PASS
        assert "10.0 kWh/day" in result.reason

    def test_implausible_consumption_refers(self, metering_config):
        result = evaluate(
            ConsumptionPlausible, {"days_in_period": 30}, metering_config, {"consumption_kwh": 4000}
        )
        assert result.outcome is Outcome.REFER
        assert "ceiling" in result.reason


class TestUnitRate:
    def test_known_tariff(self, metering_config):
        result = evaluate(UnitRate, {"tariff_code": "economy"}, metering_config)
        assert result.values == {"rate": Decimal("21.00")}

    def test_unknown_tariff_refers(self, metering_config):
        assert (
            evaluate(UnitRate, {"tariff_code": "legacy"}, metering_config).outcome is Outcome.REFER
        )


class TestChargeFromConsumption:
    def test_pence_to_pounds_rounded(self, metering_config):
        decided = {"consumption_kwh": 301, "rate": Decimal("24.50")}
        result = evaluate(ChargeFromConsumption, {}, metering_config, decided)
        assert result.values == {"amount": Decimal("73.75")}

    def test_zero_consumption_is_a_zero_charge(self, metering_config):
        decided = {"consumption_kwh": 0, "rate": Decimal("24.50")}
        result = evaluate(ChargeFromConsumption, {}, metering_config, decided)
        assert result.outcome is Outcome.PASS
        assert result.values == {"amount": Decimal("0.00")}
