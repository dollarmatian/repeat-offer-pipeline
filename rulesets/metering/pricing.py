from engine.rules import Context, Result, Rule, Stage


class UnitRate(Rule):
    name = "metering.unit_rate"
    stage = Stage.PRICE
    description = "The unit rate in pence per kWh for the tariff on the meter."
    requires = ("tariff_code",)
    decides = ("rate",)

    def evaluate(self, ctx: Context) -> Result:
        tariff = ctx.inputs["tariff_code"]
        rates = ctx.config["unit_rates_pence"]
        if tariff not in rates:
            return self.refers(f"no unit rate on file for tariff {tariff}")
        return self.passes(f"{tariff} tariff", rate=rates[tariff])
