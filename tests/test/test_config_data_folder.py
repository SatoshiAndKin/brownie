from brownie import _config, exceptions


def test_native_callers_use_active_data_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(_config, "DATA_FOLDER", tmp_path)

    assert _config._get_data_folder() == tmp_path
    assert exceptions.__get_path() == tmp_path / "errors.json"
