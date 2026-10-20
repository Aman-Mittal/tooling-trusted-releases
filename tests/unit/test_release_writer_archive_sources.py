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

import unittest.mock as mock

import pytest

import atr.models.api as api
import atr.models.attestable as attestable_models
import atr.models.safe as safe
import atr.models.sql as sql
import atr.storage as storage
import atr.storage.datatypes as datatypes
import atr.storage.writers.release as release

PK, VK = safe.ProjectKey("project"), safe.VersionKey("1.0.0")


@pytest.fixture
def create() -> mock.AsyncMock:
    return mock.AsyncMock(return_value=mock.MagicMock(spec=sql.Revision, number="00003"))


@pytest.fixture
def load(monkeypatch: pytest.MonkeyPatch) -> mock.AsyncMock:
    recorded = attestable_models.AttestableV2(
        paths={
            "a-src.tar.gz": attestable_models.PathEntryV2(content_hash="h1", classification="source"),
            "b-src.tar.gz": attestable_models.PathEntryV2(content_hash="h2", classification="source"),
            "c-bin.tar.gz": attestable_models.PathEntryV2(content_hash="h3", classification="binary"),
        }
    )
    load = mock.AsyncMock(return_value=recorded)
    monkeypatch.setattr(release.attestable, "load", load)
    return load


@pytest.fixture
def writer(create: mock.AsyncMock, load: mock.AsyncMock) -> release.CommitteeParticipant:
    release_row = mock.MagicMock()
    release_row.project.github_repositories = {"apache/first", "apache/second"}
    release_row.latest_revision_number = "00002"
    release_row.safe_latest_revision_number = safe.RevisionNumber("00002")
    data = mock.MagicMock()
    data.release.return_value.demand = mock.AsyncMock(return_value=release_row)
    write = mock.MagicMock()
    write.authorisation.asf_uid = "tester"
    write_as = mock.MagicMock()
    write_as.revision.create_revision_with_quarantine = create
    return release.CommitteeParticipant(write, write_as, data, "project")


async def test_set_archive_sources_makes_one_revision_for_all_declarations(
    writer: release.CommitteeParticipant, create: mock.AsyncMock
):
    result = await writer.set_archive_sources(
        PK,
        VK,
        [_declaration("a-src.tar.gz", "apache/first"), _declaration("b-src.tar.gz", "apache/second", "b" * 40)],
    )

    assert result.number == "00003"
    create.assert_awaited_once()
    kwargs = create.call_args_list[0].kwargs
    assert {str(path): source for path, source in kwargs["path_sources"].items()} == {
        "a-src.tar.gz": attestable_models.ArchiveSourceV2(repository="apache/first", commit="a" * 40),
        "b-src.tar.gz": attestable_models.ArchiveSourceV2(repository="apache/second", commit="b" * 40),
    }
    assert kwargs["expected_revision"] == safe.RevisionNumber("00002")
    assert kwargs["description"] == "Source declared for 2 archives"


async def test_set_archive_sources_checks_the_revision_the_caller_saw(
    writer: release.CommitteeParticipant, create: mock.AsyncMock, load: mock.AsyncMock
):
    await writer.set_archive_sources(PK, VK, [_declaration()], safe.RevisionNumber("00001"))

    load.assert_awaited_once_with(PK, VK, safe.RevisionNumber("00001"))
    kwargs = create.call_args_list[0].kwargs
    assert kwargs["expected_revision"] == safe.RevisionNumber("00001")
    assert kwargs["description"] == "Source declared for a-src.tar.gz"


@pytest.mark.parametrize(
    ("archives", "status"),
    [
        pytest.param([], 400, id="none"),
        pytest.param([("a-src.tar.gz", "apache/first")] * 2, 400, id="twice"),
        pytest.param([("a-src.tar.gz", "apache/other")], 400, id="other-repository"),
        pytest.param([("missing.tar.gz", "apache/first")], 404, id="not-in-draft"),
        pytest.param([("c-bin.tar.gz", "apache/first")], 400, id="not-source"),
    ],
)
async def test_set_archive_sources_rejects_bad_declarations(
    writer: release.CommitteeParticipant,
    create: mock.AsyncMock,
    archives: list[tuple[str, str]],
    status: int,
):
    declarations = [_declaration(relpath, repository) for relpath, repository in archives]

    with pytest.raises(storage.AccessError) as exc:
        await writer.set_archive_sources(PK, VK, declarations)

    assert exc.value.status == status
    create.assert_not_awaited()


async def test_set_archive_sources_reports_a_changed_release_as_a_conflict(
    writer: release.CommitteeParticipant, create: mock.AsyncMock
):
    create.side_effect = datatypes.RevisionMismatchError("Revision 00002 is no longer the latest")

    with pytest.raises(storage.AccessError) as exc:
        await writer.set_archive_sources(PK, VK, [_declaration()])

    assert exc.value.status == 409


async def test_set_archive_sources_refuses_a_quarantine(writer: release.CommitteeParticipant, create: mock.AsyncMock):
    create.return_value = mock.MagicMock(spec=sql.Quarantined)

    with pytest.raises(storage.AccessError) as exc:
        await writer.set_archive_sources(PK, VK, [_declaration()])

    assert exc.value.status == 409


def _declaration(
    relpath: str = "a-src.tar.gz", repository: str = "apache/first", commit: str = "a" * 40
) -> api.SourceDeclaration:
    return api.SourceDeclaration(relpath=safe.RelPath(relpath), repository=repository, commit=safe.CommitHash(commit))
