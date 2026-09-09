from decimal import Decimal

from engine.rules import Context, Result, Rule, Stage


class PeriodKnown(Rule):
    name = "metering.period_known"
    stage = Stage.ELIGIBILITY
    description = "A read with no billing period behind it cannot be charged."
    requires = ("days_in_period",)

    def evaluate(self, ctx: Context) -> Result:
        days = ctx.inputs["days_in_period"]
        if days < 1:
            return self.fails("no billing period")
        return self.passes(f"{days} day period")


class ReadSourceAccepted(Rule):
    name = "metering.read_source_accepted"
    stage = Stage.ELIGIBILITY
    description = "Only actual reads are billed. Estimates wait for a real read."
    requires = ("read_source",)

    def evaluate(self, ctx: Context) -> Result:
        source = ctx.inputs["read_source"]
        if source not in ctx.config["accepted_sources"]:
            return self.fails(f"{source} reads are not billed")
        return self.passes(f"{source} read")


class ReadNotBelowPrevious(Rule):
    name = "metering.read_not_below_previous"
    stage = Stage.ELIGIBILITY
    description = (
        "Consumption is the difference between the reads. A read below the last one is a "
        "rollover or a misread, and whoever resolves it states the consumption."
    )
    requires = ("previous_read", "current_read")
    decides = ("consumption_kwh",)

    def evaluate(self, ctx: Context) -> Result:
        previous, current = ctx.inputs["previous_read"], ctx.inputs["current_read"]
        if current < previous:
            return self.refers(f"read {current} is below previous {previous}")
        return self.passes(
            f"{current - previous} kWh since previous read", consumption_kwh=current - previous
        )


class ConsumptionPlausible(Rule):
    name = "metering.consumption_plausible"
    stage = Stage.ELIGIBILITY
    description = "Daily consumption above the ceiling is more likely a misread than real."
    requires = ("days_in_period",)

    def evaluate(self, ctx: Context) -> Result:
        consumption = ctx.decided.get("consumption_kwh")
        if consumption is None:
            return self.refers("consumption not stated")
        per_day = Decimal(consumption) / ctx.inputs["days_in_period"]
        ceiling = ctx.config["max_daily_kwh"]
        if per_day > ceiling:
            return self.refers(f"{per_day:.1f} kWh/day is above the {ceiling} kWh/day ceiling")
        return self.passes(f"{per_day:.1f} kWh/day")
