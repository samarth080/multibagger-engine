from mbe.universal.benchmarks import score_net_margin


def test_net_margin_thresholds():
    assert score_net_margin(0.20) == (90, ">= 0.15 earns 90")
    assert score_net_margin(0.12) == (75, ">= 0.10 earns 75")
    assert score_net_margin(0.07) == (60, ">= 0.05 earns 60")
    assert score_net_margin(0.01) == (40, ">= 0.00 earns 40")
    assert score_net_margin(-0.05) == (10, "negative net margin, floor 10")
