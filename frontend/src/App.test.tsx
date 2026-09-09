import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { ApiError } from "./api";
import { fakeApi } from "./test/fixtures";

describe("exception queue", () => {
  it("lists open exceptions with the rule that raised them", async () => {
    render(<App api={fakeApi()} />);

    const row = await screen.findByRole("row", { name: /CUST-3/ });
    expect(within(row).getByText("lending.missed_payments")).toBeInTheDocument();
    expect(within(row).getByText(/needs a look/)).toBeInTheDocument();
  });

  it("opens an exception and shows the decision record that produced it", async () => {
    const user = userEvent.setup();
    render(<App api={fakeApi()} />);

    await user.click(await screen.findByRole("button", { name: "Open" }));

    const record = await screen.findByRole("region", { name: "Decision record" });
    expect(within(record).getByText("dec_0123456789abcdef")).toBeInTheDocument();
    const rows = within(record).getAllByRole("row");
    expect(rows.map((r) => r.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining("lending.repayment_history")]),
    );
    expect(within(record).getByText("refer")).toBeInTheDocument();
  });

  it("resolves an exception by overriding the rule and writes to the record", async () => {
    const user = userEvent.setup();
    const api = fakeApi();
    render(<App api={api} />);

    await user.click(await screen.findByRole("button", { name: "Open" }));
    const form = await screen.findByRole("form", { name: "Resolve exception" });
    await user.type(within(form).getByLabelText("Resolved by"), "ops@example");
    await user.type(within(form).getByLabelText("Note"), "spoke to the customer");
    await user.click(within(form).getByRole("button", { name: "Resolve" }));

    expect(api.calls).toEqual([
      { action: "override", resolved_by: "ops@example", note: "spoke to the customer" },
    ]);
    expect(await screen.findByText("resolved")).toBeInTheDocument();
    expect(screen.getByText(/resolved by ops@example/)).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /lending.missed_payments \(overridden\)/ })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Resolve exception" })).not.toBeInTheDocument();
  });

  it("sends stated values with an override", async () => {
    const user = userEvent.setup();
    const api = fakeApi();
    render(<App api={api} />);

    await user.click(await screen.findByRole("button", { name: "Open" }));
    const form = await screen.findByRole("form", { name: "Resolve exception" });
    await user.type(within(form).getByLabelText("Resolved by"), "ops");
    await user.type(within(form).getByLabelText(/key=value/), "rate=0.03, amount=1500");
    await user.click(within(form).getByRole("button", { name: "Resolve" }));

    expect(api.calls[0].values).toEqual({ rate: "0.03", amount: "1500" });
  });

  it("shows the server's reason when a resolution is refused", async () => {
    const user = userEvent.setup();
    const api = fakeApi({
      resolveException: async () => {
        throw new ApiError(400, "lending.missed_payments cannot decide ['amount']");
      },
    });
    render(<App api={api} />);

    await user.click(await screen.findByRole("button", { name: "Open" }));
    const form = await screen.findByRole("form", { name: "Resolve exception" });
    await user.type(within(form).getByLabelText("Resolved by"), "ops");
    await user.click(within(form).getByRole("button", { name: "Resolve" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("cannot decide");
  });

  it("switches to resolved exceptions", async () => {
    const user = userEvent.setup();
    render(<App api={fakeApi()} />);

    await screen.findByRole("row", { name: /CUST-3/ });
    await user.click(screen.getByRole("button", { name: "resolved" }));

    expect(await screen.findByText("No resolved exceptions.")).toBeInTheDocument();
  });
});
