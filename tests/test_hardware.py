from core.hardware import hardware_inventory


def test_missing_gpu_tools_is_explicit(monkeypatch):
    monkeypatch.setattr("core.hardware.shutil.which", lambda _: None)
    result = hardware_inventory()
    assert result["gpu_detection"] == "unavailable"
    assert result["nvidia_devices"] == []
