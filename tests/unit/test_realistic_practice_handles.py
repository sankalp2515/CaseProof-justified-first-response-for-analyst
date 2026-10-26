from local_services.bank_network import BankNetwork


def test_practice_handles_are_compact_independent_and_not_derived_from_complaint_text():
    handles = []
    for seed in range(36, 48):
        world = BankNetwork._generate(None, f"new-world-{seed}", seed, "demo")
        payment = next(t for t in world["dataset"]["transactions"] if t["txn_id"].endswith("-T1"))
        handle = payment["payee"]
        assert handle.startswith("narmada.traders.") and handle.endswith("@cedardemo")
        assert len(handle) < 50
        assert len(handle.split(".")[2].split("@")[0]) == 10
        handles.append(handle)
    assert len(set(handles)) == 12
