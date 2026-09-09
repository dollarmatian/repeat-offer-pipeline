from engine.rules import Context, Result, Rule, Stage


class BaseRate(Rule):
    name = "lending.base_rate"
    stage = Stage.PRICE
    description = "Monthly rate by repayment history: established customers get the lower band."
    requires = ("loans_repaid",)
    decides = ("rate",)

    def evaluate(self, ctx: Context) -> Result:
        if ctx.inputs["loans_repaid"] >= ctx.config["established_loans"]:
            return self.passes("established band", rate=ctx.config["rate_established"])
        return self.passes("standard band", rate=ctx.config["rate_standard"])


class SectorLoading(Rule):
    name = "lending.sector_loading"
    stage = Stage.PRICE
    description = (
        "Adds a loading to the rate already decided for listed sectors. Runs after BaseRate."
    )
    requires = ("sector",)
    decides = ("rate",)

    def evaluate(self, ctx: Context) -> Result:
        sector = ctx.inputs["sector"]
        if sector in ctx.config["loaded_sectors"]:
            loaded = ctx.decided["rate"] + ctx.config["sector_loading"]
            return self.passes(f"{sector} carries a loading", rate=loaded)
        return self.passes(f"no loading for {sector}")
