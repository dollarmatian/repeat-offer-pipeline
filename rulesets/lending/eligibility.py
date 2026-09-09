from engine.rules import Context, Result, Rule, Stage


class RepaymentHistory(Rule):
    name = "lending.repayment_history"
    stage = Stage.ELIGIBILITY
    description = "A repeat offer needs at least one loan repaid in full."
    requires = ("loans_repaid",)

    def evaluate(self, ctx: Context) -> Result:
        repaid = ctx.inputs["loans_repaid"]
        if repaid < 1:
            return self.fails("no loan repaid in full yet")
        return self.passes(f"{repaid} loan(s) repaid")


class MissedPayments(Rule):
    name = "lending.missed_payments"
    stage = Stage.ELIGIBILITY
    description = "One missed payment in the last year goes to a human; two or more is a decline."
    requires = ("missed_payments_last_12m",)

    def evaluate(self, ctx: Context) -> Result:
        missed = ctx.inputs["missed_payments_last_12m"]
        if missed >= ctx.config["missed_payments_fail_at"]:
            return self.fails(f"{missed} missed payments in the last 12 months")
        if missed >= ctx.config["missed_payments_refer_at"]:
            return self.refers(f"{missed} missed payment in the last 12 months needs a look")
        return self.passes("no missed payments in the last 12 months")


class BalanceToRevenue(Rule):
    name = "lending.balance_to_revenue"
    stage = Stage.ELIGIBILITY
    description = "Outstanding balance must sit within a multiple of monthly revenue."
    requires = ("outstanding_balance", "average_monthly_revenue")

    def evaluate(self, ctx: Context) -> Result:
        balance = ctx.inputs["outstanding_balance"]
        revenue = ctx.inputs["average_monthly_revenue"]
        multiple = ctx.config["max_balance_to_revenue"]
        limit = revenue * multiple
        if revenue <= 0:
            return self.fails("no revenue on file")
        if balance > limit:
            return self.fails(f"balance {balance} exceeds {limit} ({multiple}x revenue)")
        return self.passes(f"balance {balance} within {limit}")


class BureauScore(Rule):
    name = "lending.bureau_score"
    stage = Stage.ELIGIBILITY
    description = "A bureau score below the floor is a decline. No score at all goes to a human."
    requires = ("bureau_score", "bureau_status")

    def evaluate(self, ctx: Context) -> Result:
        score = ctx.inputs["bureau_score"]
        if score is None:
            status = ctx.inputs["bureau_status"] or "not requested"
            return self.refers(f"no bureau score ({status})")
        floor = ctx.config["bureau_score_floor"]
        if score < floor:
            return self.fails(f"bureau score {score} below floor {floor}")
        return self.passes(f"bureau score {score}")
