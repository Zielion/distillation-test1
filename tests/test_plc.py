from distillation.plc import PLCController
from distillation.process import ProcessState


def test_high_high_pressure_forces_shutdown_actions():
    controller = PLCController(mode="NORMAL_OPERATION")
    state = ProcessState(column_pressure=145.0)

    output = controller.scan(state.to_tags(), 1.0)

    assert output.commands["reboiler_duty"] == 0.0
    assert output.commands["condenser_valve"] == 100.0
    assert output.commands["feed_pump"] is False
    assert output.mode == "SHUTDOWN"
    assert "DT101.ALARM.HIGH_HIGH_PRESSURE" in output.alarms


def test_low_feed_tank_level_stops_feed_pump():
    controller = PLCController(mode="NORMAL_OPERATION")
    state = ProcessState(feed_tank_level=5.0)

    output = controller.scan(state.to_tags(), 1.0)

    assert output.commands["feed_pump"] is False
    assert "DT101.ALARM.FEED_TANK_LOW_LOW" in output.alarms


def test_normal_operation_outputs_are_bounded():
    controller = PLCController(mode="NORMAL_OPERATION")
    state = ProcessState()

    output = controller.scan(state.to_tags(), 1.0)

    for key in [
        "feed_valve",
        "reboiler_duty",
        "condenser_valve",
        "reflux_valve",
        "distillate_valve",
        "bottoms_valve",
    ]:
        assert 0.0 <= output.commands[key] <= 100.0
