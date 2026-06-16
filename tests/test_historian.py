from datetime import datetime, timezone

from distillation.historian import Historian


def test_historian_writes_and_queries_recent_tag_values(tmp_path):
    db_path = tmp_path / "history.sqlite"
    historian = Historian(db_path)
    timestamp = datetime.now(timezone.utc)

    historian.write(timestamp, {"DT101.PV.TOP_TEMP": 78.4, "DT101.STATE.MODE": "NORMAL_OPERATION"})
    rows = historian.query(["DT101.PV.TOP_TEMP", "DT101.STATE.MODE"], seconds=60)

    assert len(rows) == 2
    values = {row["tag"]: row["value"] for row in rows}
    assert values["DT101.PV.TOP_TEMP"] == 78.4
    assert values["DT101.STATE.MODE"] == "NORMAL_OPERATION"
