from decimal import ROUND_HALF_UP, Decimal

from engine.rules import Context, Result, Rule, Stage


class ChargeFromConsumption(Rule):
    name = "metering.charge_from_consumption"
    stage = Stage.AMOUNT
    description = (
        "Consumption times unit rate, in pounds. Standing charges are billed daily elsewhere."
    )
    decides = ("amount",)

    def evaluate(self, ctx: Context) -> Result:
        kwh = ctx.decided["consumption_kwh"]
        pence = Decimal(kwh) * ctx.decided["rate"]
        pounds = (pence / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return self.passes(f"{kwh} kWh at {ctx.decided['rate']}p", amount=pounds)
