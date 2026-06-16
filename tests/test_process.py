from distillation.process import ProcessState


def test_reflux_loss_raises_top_temperature_and_lowers_purity():
    baseline = ProcessState()
    low_reflux = ProcessState()

    for _ in range(80):
        baseline = baseline.step(
            {"reflux_valve": 70.0, "reboiler_duty": 55.0, "condenser_valve": 55.0},
            {},
            1.0,
        )
        low_reflux = low_reflux.step(
            {"reflux_valve": 5.0, "reboiler_duty": 55.0, "condenser_valve": 55.0},
            {},
            1.0,
        )

    assert low_reflux.top_temperature > baseline.top_temperature + 1.0
    assert low_reflux.purity_proxy < baseline.purity_proxy - 1.0


def test_higher_reboiler_duty_raises_bottom_temperature_and_pressure():
    low_duty = ProcessState()
    high_duty = ProcessState()

    for _ in range(80):
        low_duty = low_duty.step(
            {"reflux_valve": 50.0, "reboiler_duty": 25.0, "condenser_valve": 55.0},
            {},
            1.0,
        )
        high_duty = high_duty.step(
            {"reflux_valve": 50.0, "reboiler_duty": 85.0, "condenser_valve": 55.0},
            {},
            1.0,
        )

    assert high_duty.bottom_temperature > low_duty.bottom_temperature + 3.0
    assert high_duty.column_pressure > low_duty.column_pressure + 3.0


def test_condenser_opening_reduces_pressure_trend():
    restricted_cooling = ProcessState(column_pressure=120.0)
    strong_cooling = ProcessState(column_pressure=120.0)

    for _ in range(50):
        restricted_cooling = restricted_cooling.step(
            {"reboiler_duty": 70.0, "condenser_valve": 10.0, "reflux_valve": 50.0},
            {},
            1.0,
        )
        strong_cooling = strong_cooling.step(
            {"reboiler_duty": 70.0, "condenser_valve": 100.0, "reflux_valve": 50.0},
            {},
            1.0,
        )

    assert strong_cooling.column_pressure < restricted_cooling.column_pressure - 8.0
