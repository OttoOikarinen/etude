# SPDX-FileCopyrightText: 2026 Otto Oikarinen
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import UTC
from pathlib import Path
from zoneinfo import ZoneInfo

from etude.audio.null import NullBackend
from etude.services import DATABASE_NAME, Services, local_timezone, user_data_dir


def test_data_dir_follows_xdg_and_override(tmp_path: Path) -> None:
    assert user_data_dir({'ETUDE_DATA_DIR': str(tmp_path)}) == tmp_path
    assert user_data_dir({'XDG_DATA_HOME': '/data'}) == Path('/data/etude')
    assert user_data_dir({}).name == 'etude'


def test_timezone_from_tz_variable() -> None:
    assert local_timezone({'TZ': 'Europe/Helsinki'}) == ZoneInfo('Europe/Helsinki')
    assert local_timezone({'TZ': ':Europe/Helsinki'}) == ZoneInfo('Europe/Helsinki')


def test_timezone_falls_back_without_a_valid_zone() -> None:
    assert local_timezone({'TZ': 'Not/AZone'}) is not None


def test_services_open_a_database_and_run_a_session(tmp_path: Path) -> None:
    services = Services.open(tmp_path)
    try:
        assert (tmp_path / DATABASE_NAME).exists()
        assert 'keysig' in services.registry.exercise_ids()
        audio = NullBackend()
        services._audio = audio
        assert services.audio is audio
    finally:
        services.close()


def test_audio_is_created_lazily(tmp_path: Path, monkeypatch) -> None:
    import etude.audio.service as service

    created = []

    def fake_backend() -> NullBackend:
        created.append(True)
        return NullBackend()

    monkeypatch.setattr(service, 'create_backend', fake_backend)
    services = Services.open(tmp_path)
    try:
        assert created == []
        services.audio  # noqa: B018
        services.audio  # noqa: B018
        assert created == [True]
    finally:
        services.close()
    assert services.timezone is not None or services.timezone is UTC
