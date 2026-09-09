from decimal import ROUND_DOWN

from engine.rules import Context, Result, Rule, Stage


class AmountFromRevenue(Rule):
    name = "lending.amount_from_revenue"
    stage = Stage.AMOUNT
    description = "The lesser of the amount asked for and a multiple of monthly revenue."
    requires = ("requested_amount", "average_monthly_revenue")
    decides = ("amount",)

    def evaluate(self, ctx: Context) -> Result:
        affordable = ctx.inputs["average_monthly_revenue"] * ctx.config["revenue_multiple"]
        amount = min(ctx.inputs["requested_amount"], affordable)
        step = ctx.config["rounding"]
        amount = (amount / step).quantize(1, rounding=ROUND_DOWN) * step
        return self.passes(f"min(requested, {affordable}) rounded down to {step}", amount=amount)


class OfferCap(Rule):
    name = "lending.offer_cap"
    stage = Stage.AMOUNT
    description = "No offer above the cap, whatever the revenue says."
    decides = ("amount",)

    def evaluate(self, ctx: Context) -> Result:
        cap = ctx.config["offer_cap"]
        if ctx.decided["amount"] > cap:
            return self.passes(f"capped at {cap}", amount=cap)
        return self.passes(f"within cap {cap}")


class MinimumOffer(Rule):
    name = "lending.minimum_offer"
    stage = Stage.AMOUNT
    description = "An offer below the minimum is not worth making."

    def evaluate(self, ctx: Context) -> Result:
        minimum = ctx.config["minimum_offer"]
        if ctx.decided["amount"] < minimum:
            return self.fails(f"{ctx.decided['amount']} is below the minimum offer {minimum}")
        return self.passes(f"at or above minimum {minimum}")
