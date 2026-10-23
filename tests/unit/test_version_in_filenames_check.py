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
import types

import pytest

import atr.models.safe as safe
import atr.models.sql as sql
import atr.tasks.checks as checks
import atr.tasks.checks.paths as paths


@pytest.mark.parametrize(
    ("filename", "version"),
    [
        ("apache-example-1.2.3-src.tar.gz", "1.2.3"),
        ("apache-example-1.2-src.tar.gz", "1.2"),
        ("apache-example-1.2.tar.gz", "1.2"),
        ("apache_beam-v2.61.0-prism-linux-amd64.zip", "2.61.0"),
        ("Apache.NMS.ActiveMQ.2.1.1.nupkg", "2.1.1"),
        ("Xerces-J-bin.2.9.1.tar.gz", "2.9.1"),
        ("apacheds-2.0.0-M10.exe", "2.0.0-m10"),
        ("torque-3.3-rc1-src.tar.gz", "3.3-RC1"),
        ("apache-example-1.0.0-incubating-src.tar.gz", "1.0.0-incubating"),
    ],
)
def test_filename_has_version_accepts(filename: str, version: str) -> None:
    assert paths._filename_has_version(filename, version)


@pytest.mark.parametrize(
    ("filename", "version"),
    [
        ("apache-tomcat-9.0.121.tar.gz", "9"),
        ("apache-maven-4.0.0-rc-6-bin.tar.gz", "4"),
        ("qumat-0.6.0-py3-none-any.whl", "0.6"),
        ("maven-clean-plugin-3.5.0.jar", "2.5"),
        ("apache-example-11.2-src.tar.gz", "1.2"),
        ("apache-example-0.1.2-src.tar.gz", "1.2"),
        ("jsonic-1.2.11.jar", "2.1"),
        ("Qpid.NET-1.0-incubating-M2.1-mono-2.0.zip", "1.0-incubating-m2"),
        ("apache-pekko-connectors-1.3.0-src-20260310.tgz", "1.3.0-RC1"),
    ],
)
def test_filename_has_version_rejects(filename: str, version: str) -> None:
    assert not paths._filename_has_version(filename, version)


async def test_artifact_without_version_records_blocker_when_required(tmp_path) -> None:
    blockers = await _artifact_blockers(tmp_path, "apache-example-1.2.3-src.tar.gz", "1.2.4")
    assert blockers == ["Artifact filename must include the release version '1.2.4'"]


async def test_artifact_with_version_records_no_blocker_when_required(tmp_path) -> None:
    blockers = await _artifact_blockers(tmp_path, "apache-example-1.2.4-src.tar.gz", "1.2.4")
    assert blockers == []


async def test_artifact_without_version_records_no_blocker_when_not_required(tmp_path) -> None:
    blockers = await _artifact_blockers(tmp_path, "apache-example-src.tar.gz", None)
    assert blockers == []


def test_paths_check_declares_policy_flag_and_version_as_inputs() -> None:
    assert "require_version_in_filenames" in paths.INPUT_POLICY_KEYS
    assert "release_version" in paths.INPUT_EXTRA_ARGS


async def test_release_version_extra_arg_differs_by_version() -> None:
    first = await checks.resolve_extra_args(["release_version"], _release("1.2.3"))
    second = await checks.resolve_extra_args(["release_version"], _release("1.2.4"))
    assert first == {"release_version": "1.2.3"}
    assert second == {"release_version": "1.2.4"}


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        ({"require_version_in_filenames": True}, "1.2.3"),
        ({"require_version_in_filenames": False}, None),
        # An attestable written before the option existed has no key for it
        ({}, None),
    ],
)
async def test_required_filename_version_reads_attestable_policy(
    monkeypatch: pytest.MonkeyPatch, policy: dict, expected: str | None
) -> None:
    async def load(*_args):
        return types.SimpleNamespace(policy=policy)

    async def recorder(_version: str | None) -> checks.Recorder:
        raise RuntimeError("Not used")

    monkeypatch.setattr(paths.attestable, "load", load)
    args = checks.FunctionArguments(
        recorder=recorder,
        asf_uid="alice",
        project_key=safe.ProjectKey("example"),
        version_key=safe.VersionKey("1.2.3"),
        revision_number=safe.RevisionNumber("00001"),
        primary_rel_path=None,
        extra_args={},
    )
    assert await paths._required_filename_version(args) == expected


async def _artifact_blockers(tmp_path, name: str, required_version: str | None) -> list[str]:
    (tmp_path / name).write_bytes(b"")
    (tmp_path / f"{name}.asc").write_bytes(b"")
    relative_paths = {name, f"{name}.asc", f"{name}.sha512"}
    errors: list[str] = []
    blockers: list[str] = []
    await paths._check_artifact_rules(
        safe.StatePath(tmp_path),
        safe.RelPath(name),
        relative_paths,
        errors,
        blockers,
        False,
        required_version,
    )
    return blockers


def _release(version: str) -> sql.Release:
    return sql.Release(
        phase=sql.ReleasePhase.RELEASE_CANDIDATE_DRAFT,
        project_key="example",
        version=version,
        created=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
    )
