# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
import datetime
import json
import logging
import pathlib
import types
import unittest.mock as mock

import asfquart
import pytest

import atr.admin as admin
import atr.blueprints.common as common
import atr.cache as cache
import atr.daylog as daylog
import atr.log as log
import atr.models.safe as safe
import atr.models.sql as sql
import atr.notify as notify
import atr.user as user


@pytest.mark.parametrize(
    ("session", "version_key", "events"),
    [(None, "1.0", 1), (None, "2.0", 0), (None, "", 0), (mock.sentinel.session, "1.0", 0)],
)
async def test_anonymous_embargo_probe_records_only_existing_embargoed_releases(
    monkeypatch: pytest.MonkeyPatch, session: object, version_key: str, events: int
) -> None:
    log.clear_context()
    captured = _capture_auth_log()
    data = mock.MagicMock()
    data.release.side_effect = lambda **kwargs: mock.MagicMock(
        get=mock.AsyncMock(return_value=_release(True) if (kwargs["version"] == "1.0") else None)
    )
    context = mock.AsyncMock()
    context.__aenter__.return_value = data
    monkeypatch.setattr(asfquart, "APP", mock.MagicMock())
    monkeypatch.setattr(common.db, "session", lambda: context)
    monkeypatch.setattr(common.sessions, "read", mock.AsyncMock(return_value=session))
    inner = mock.AsyncMock(return_value="login redirect")
    probe = common.anonymous_embargo_probe(inner, [("project_key", safe.ProjectKey), ("version_key", safe.VersionKey)])

    assert await probe(project_key="example", version_key=version_key) == "login redirect"

    inner.assert_awaited_once_with(project_key="example", version_key=version_key)
    assert len(captured) == events


def test_auth_log_carries_request_id_and_source_ip_from_the_log_context() -> None:
    log.clear_context()
    log.add_context(request_id="req-123", source_ip="203.0.113.7")
    captured = _capture_auth_log()
    try:
        log.auth_failure(type="jwt", reason="bad token", asfuid="bob")

        entry = json.loads(captured[-1])
        assert entry["request_id"] == "req-123"
        assert entry["source_ip"] == "203.0.113.7"
    finally:
        log.clear_context()


def test_auth_log_omits_request_fields_when_no_request_context_is_bound() -> None:
    log.clear_context()
    captured = _capture_auth_log()

    log.auth_success(type="oauth", asfuid="alice")

    entry = json.loads(captured[-1])
    assert "request_id" not in entry
    assert "source_ip" not in entry


async def test_embargo_denial_notifies_every_admin_on_admin_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "admins_get_async", mock.AsyncMock(return_value=frozenset({"bob", "alice"})))
    waus = mock.MagicMock(notifications_create=mock.AsyncMock())
    context = mock.AsyncMock()
    context.__aenter__.return_value = waus
    write_as_user_service = mock.MagicMock(return_value=context)
    monkeypatch.setattr(notify.storage, "write_as_user_service", write_as_user_service)

    await notify.embargo_denial("example-1.0")

    assert write_as_user_service.call_args_list == [mock.call("alice"), mock.call("bob")]
    waus.notifications_create.assert_awaited_with(
        "Access to embargoed release example-1.0 was denied",
        sql.NotificationLevel.WARNING,
        link="/admin/users?tab=embargo-denials",
        link_text="Review embargo denials",
        is_admin=True,
    )


def test_embargo_denials_keep_the_newest_recent_auth_denials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    entries = [
        ("2026-09-30T13:00:00.000000Z", "atr.auth", {"event": "embargo_denied", "release_key": "old"}),
        ("2026-10-01T11:59:59.999999Z", "atr.auth", {"event": "embargo_denied", "release_key": "early"}),
        ("2026-10-01T12:00:00.000000Z", "atr.auth", {"event": "embargo_denied", "release_key": "a"}),
        ("2026-10-01T13:00:00.000000Z", "atr.storage.audit", {"action": "x", "event": "embargo_denied"}),
        ("2026-10-01T14:00:00.000000Z", "atr.auth", {"event": "auth_success"}),
        ("2026-10-02T00:00:00.000000Z", "atr.auth", {"event": "embargo_denied", "release_key": "b"}),
        ("2026-10-02T00:00:01.000000Z", "atr.auth", {"event": "embargo_denied", "release_key": "c"}),
    ]
    records = [{"event": event, "level": "info", "logger": name, "timestamp": stamp} for stamp, name, event in entries]
    for day, content in daylog.build(records, datetime.date(2026, 9, 30), datetime.date(2026, 10, 2)).items():
        (tmp_path / f"{day}.jsonl").write_bytes(content)
    with (tmp_path / "2026-10-02.jsonl").open("ab") as handle:
        handle.write(b'{"event":{"event":"embargo_denied","release_key":"partial"}')
    monkeypatch.setattr(admin.paths, "get_audit_log_dir", lambda: types.SimpleNamespace(path=tmp_path))
    monkeypatch.setattr(admin, "_EMBARGO_DENIAL_LIMIT", 2)

    denials, total = admin._embargo_denials("2026-10-01T12:00:00.000000Z")

    assert [denial["event"]["release_key"] for denial in denials] == ["c", "b"]
    assert total == 3


@pytest.mark.parametrize(
    ("uid", "is_member", "is_embargoed", "denied"),
    [
        (None, False, True, True),
        ("outsider", False, True, True),
        ("outsider", True, True, False),
        ("member", False, True, False),
        ("root", False, True, False),
        (None, False, False, False),
    ],
)
def test_embargo_denies_records_and_notifies_only_hidden_releases(
    monkeypatch: pytest.MonkeyPatch, uid: str | None, is_member: bool, is_embargoed: bool, denied: bool
) -> None:
    log.clear_context()
    captured = _capture_auth_log()
    app = mock.MagicMock(extensions={"admins": frozenset({"root"})})
    monkeypatch.setattr(asfquart, "APP", app)

    assert user.embargo_denies(_release(is_embargoed), uid, is_member=is_member) is denied

    entries = [json.loads(entry) for entry in captured]
    expected = [("embargo_denied", "example-1.0", uid)] if denied else []
    assert [(entry["event"], entry["release_key"], entry.get("request_user_id")) for entry in entries] == expected
    calls = [mock.call(notify.embargo_denial, "example-1.0")] if denied else []
    assert app.add_background_task.call_args_list == calls


def _capture_auth_log() -> list[str]:
    captured: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    logger = logging.getLogger("atr.auth")
    logger.handlers.clear()
    logger.addHandler(_Handler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return captured


def _release(is_embargoed: bool) -> types.SimpleNamespace:
    committee = sql.Committee(key="example", committee_members=["member"])
    return types.SimpleNamespace(key="example-1.0", is_embargoed=is_embargoed, committee=committee)
