from local_services.bank_network import BankNetwork


def test_independent_seed_worlds_have_different_topology_and_conserve_observed_money():
    network = object.__new__(BankNetwork)
    simple = network._generate("SHALLOW", 143, "demo")
    deep = network._generate("DEEPER", 1042, "demo")
    assert len(simple["reports"]) == 3 and len(deep["reports"]) == 4
    assert len(deep["reports"][1]["onward_transfers"]) == 1
    for world in (simple, deep):
        roots = world["dataset"]["transactions"][2:4]
        root_total = sum(t["amount_minor"] for t in roots)
        cash = sum(
            t["amount_minor"]
            for r in world["reports"]
            for t in r["onward_transfers"]
            if t["channel"] == "ATM"
        )
        assert sum(r["balance_minor"] for r in world["reports"]) + cash == root_total
