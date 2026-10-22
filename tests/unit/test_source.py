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

import atr.attestable as attestable
import atr.models.attestable
import atr.models.github as github
import atr.models.safe as safe
import atr.models.sql as sql
import atr.source as source


@pytest.mark.parametrize("repository", ["apache/other", ""])
def test_advance_ignores_run_commit_from_other_repository(
    repository: str, github_payload: github.TrustedPublisherPayload
):
    # A workflow may run somewhere other than the source repository, so its starting commit means nothing here
    selected = atr.models.attestable.SourceV2(
        repository=repository, default="a" * 40, override="c" * 40, candidates=["apache/first", "apache/second"]
    )
    result = source.advance(selected, github_payload, declared=safe.CommitHash("e" * 40))
    assert result.default is None
    assert result.override is None
    assert result.declared == "e" * 40


def test_advance_keeps_override_without_payload():
    selected = atr.models.attestable.SourceV2(repository="apache/test", default="a" * 40, override="c" * 40)
    result = source.advance(selected, None)
    assert result.override == "c" * 40
    assert result.sha == "c" * 40


@pytest.mark.parametrize("override", [None, "c" * 40])
def test_advance_payload_replaces_override(override: str | None, github_payload: github.TrustedPublisherPayload):
    selected = atr.models.attestable.SourceV2(repository="apache/test", default="a" * 40, override=override)
    result = source.advance(selected, github_payload)
    assert result.default == github_payload.sha
    assert result.override is None
    assert result.sha == github_payload.sha
    assert selected.default == "a" * 40
    assert selected.override == override


def test_advance_prefers_declared_commit_over_payload(github_payload: github.TrustedPublisherPayload):
    selected = atr.models.attestable.SourceV2(repository="apache/test", default="a" * 40)
    result = source.advance(selected, github_payload, declared=safe.CommitHash("d" * 40))
    assert result.default == github_payload.sha
    assert result.declared == "d" * 40
    assert result.sha == "d" * 40
    assert source.advance(result, None, "c" * 40).sha == "c" * 40


def test_advance_without_declaration_clears_earlier_one(github_payload: github.TrustedPublisherPayload):
    selected = atr.models.attestable.SourceV2(repository="apache/test", default="a" * 40, declared="d" * 40)
    assert source.advance(selected, None).declared == "d" * 40
    result = source.advance(selected, github_payload)
    assert result.declared is None
    assert result.sha == github_payload.sha


async def test_initial_accepts_repository_configured_after_first_revision():
    release = sql.Release(
        project=sql.Project(key="test", name="Test", repositories=["https://github.com/apache/test"]), version="1.0"
    )
    previous = atr.models.attestable.AttestableV2(source=atr.models.attestable.SourceV2())
    selected = await source.initial(release, previous)
    assert selected.repository == "apache/test"
    assert previous.source.repository == ""


async def test_initial_follows_metadata_not_policy_or_earlier_record():
    project = sql.Project(
        key="test",
        name="Test",
        repositories=["https://github.com/apache/moved"],
        release_policy=sql.ReleasePolicy(github_repository_name="workflow-home"),
    )
    release = sql.Release(project=project, version="1.0")
    recorded = atr.models.attestable.SourceV2(repository="apache/test", override="c" * 40)
    previous = atr.models.attestable.AttestableV2(source=recorded)
    selected = await source.initial(release, previous)
    assert selected.repository == "apache/moved"
    assert selected.override == "c" * 40
    assert recorded.repository == "apache/test"


async def test_initial_refreshes_candidates():
    project = sql.Project(
        key="test",
        name="Test",
        repositories=["https://github.com/apache/second", "https://github.com/apache/first"],
    )
    release = sql.Release(project=project, version="1.0")
    recorded = atr.models.attestable.SourceV2(candidates=["apache/first"])
    selected = await source.initial(release, atr.models.attestable.AttestableV2(source=recorded))
    assert selected.repository == ""
    assert selected.candidates == ["apache/first", "apache/second"]
    assert recorded.candidates == ["apache/first"]


async def test_initial_keeps_workflow_repository(github_payload: github.TrustedPublisherPayload):
    project = sql.Project(key="test", name="Test", repositories=["https://github.com/Berri-AI/test"])
    release = sql.Release(project=project, version="1.0")
    recorded = source.advance(atr.models.attestable.SourceV2(repository="Berri-AI/test"), github_payload)
    selected = await source.initial(release, atr.models.attestable.AttestableV2(source=recorded))
    assert (selected.repository, selected.sha) == (github_payload.repository, github_payload.sha)


@pytest.mark.parametrize("recorded_hash", ["b" * 40, "c" * 40])
async def test_initial_preserves_legacy_choice(
    monkeypatch: pytest.MonkeyPatch, github_payload: github.TrustedPublisherPayload, recorded_hash: str
):
    release = sql.Release(
        project=sql.Project(key="test", name="Test"), project_key="test", version="1.0", commit_hash=recorded_hash
    )
    monkeypatch.setattr(attestable, "latest_github_tp_payload", mock.AsyncMock(return_value=github_payload))
    selected = await source.initial(release, None)
    assert selected.repository == github_payload.repository
    assert selected.default == github_payload.sha
    assert selected.sha == recorded_hash
    assert selected.override == (recorded_hash if (recorded_hash != github_payload.sha) else None)


@pytest.mark.parametrize(
    ("candidates", "declared", "expected_commit"),
    [
        (["apache/other", "apache/test"], None, "payload"),
        (["apache/other", "apache/test"], "d" * 40, "d" * 40),
    ],
)
def test_uploaded_declares_changed_source_archives_from_the_workflow_repository(
    github_payload: github.TrustedPublisherPayload, candidates: list[str], declared: str | None, expected_commit: str
):
    record = atr.models.attestable.SourceV2(candidates=candidates, declared=declared)
    previous = atr.models.attestable.AttestableV2(
        paths={
            "same-src.tar.gz": atr.models.attestable.PathEntryV2(content_hash="h1", classification="source"),
            "changed-src.tar.gz": atr.models.attestable.PathEntryV2(content_hash="h2", classification="source"),
        }
    )
    path_to_hash = {
        safe.RelPath("same-src.tar.gz"): "h1",
        safe.RelPath("changed-src.tar.gz"): "h2-new",
        safe.RelPath("new-src.tar.gz"): "h3",
        safe.RelPath("new-bin.tar.gz"): "h4",
    }
    classifications = {path: ("binary" if ("bin" in str(path)) else "source") for path in path_to_hash}

    result = source.uploaded(record, github_payload, path_to_hash, classifications, previous)

    commit = github_payload.sha if (expected_commit == "payload") else expected_commit
    expected = atr.models.attestable.ArchiveSourceV2(repository=github_payload.repository, commit=commit)
    # Unchanged archives keep whatever they had, and binaries have no source to declare
    assert result == {safe.RelPath("changed-src.tar.gz"): expected, safe.RelPath("new-src.tar.gz"): expected}


@pytest.mark.parametrize(
    "candidates",
    [
        pytest.param(["apache/test"], id="one-repository"),
        pytest.param(["apache/other", "apache/another"], id="workflow-not-a-source"),
    ],
)
def test_uploaded_declares_nothing_outside_the_several_source_case(
    github_payload: github.TrustedPublisherPayload, candidates: list[str]
):
    record = atr.models.attestable.SourceV2(candidates=candidates)
    path_to_hash = {safe.RelPath("a-src.tar.gz"): "h1"}

    assert source.uploaded(record, github_payload, path_to_hash, {safe.RelPath("a-src.tar.gz"): "source"}, None) == {}


def test_override_can_be_set_or_cleared():
    selected = atr.models.attestable.SourceV2(repository="apache/test", default="a" * 40, override="b" * 40)
    confirmed = source.advance(selected, None, "b" * 40)
    cleared = source.advance(selected, None, None)
    assert confirmed.sha == "b" * 40
    assert cleared.sha == "a" * 40
    assert cleared.override is None
    # An override is recorded even with no configured repository
    recorded = source.advance(atr.models.attestable.SourceV2(), None, "b" * 40)
    assert recorded.override == "b" * 40
    assert recorded.sha == "b" * 40


async def test_read_and_cache_inputs_use_requested_snapshot(
    monkeypatch: pytest.MonkeyPatch, github_payload: github.TrustedPublisherPayload
):
    pk, vk, rev = safe.ProjectKey("test"), safe.VersionKey("1.0"), safe.RevisionNumber("00001")
    selected = atr.models.attestable.SourceV2(repository="apache/test", default=github_payload.sha, override="c" * 40)
    monkeypatch.setattr(
        attestable, "load", mock.AsyncMock(return_value=atr.models.attestable.AttestableV2(source=selected))
    )
    original = mock.AsyncMock(return_value=github_payload)
    monkeypatch.setattr(attestable, "github_tp_payload_read", original)
    assert (await source.read(pk, vk, rev)).sha == "c" * 40
    assert await source.inputs(pk, vk, rev) == {
        "source_repository": "apache/test",
        "source_commit": "c" * 40,
        "source_default": github_payload.sha,
        "source_override": "c" * 40,
        "source_candidates": "",
    }
    attestable.load.assert_awaited_with(pk, vk, rev)
    original.assert_not_awaited()
    monkeypatch.setattr(attestable, "load", mock.AsyncMock(return_value=None))
    assert (await source.read(pk, vk, rev)).sha == github_payload.sha
    original.assert_awaited_once_with(pk, vk, rev)


@pytest.mark.parametrize(
    ("repositories", "policy_name", "expected"),
    [
        (["https://github.com/apache/test.git"], "", "apache/test"),
        (["https://github.com/apache/first", "https://github.com/apache/second"], "", ""),
        (["https://github.com/apache/first"], "configured", "apache/first"),
        ([], "", ""),
    ],
)
def test_repository_requires_one_choice(repositories: list[str], policy_name: str, expected: str):
    project = sql.Project(
        key="test",
        name="Test",
        repositories=repositories,
        release_policy=sql.ReleasePolicy(github_repository_name=policy_name),
    )
    assert source.repository(project) == expected


@pytest.mark.parametrize(
    ("repositories", "policy_name", "expected"),
    [
        (["https://github.com/apache/test.git"], "", {"apache/test"}),
        (
            ["https://github.com/apache/first", "https://github.com/apache/second"],
            "",
            {"apache/first", "apache/second"},
        ),
        (
            ["https://github.com/apache/first", "https://github.com/apache/second"],
            "configured",
            {"apache/first", "apache/second"},
        ),
        (["https://gitbox.apache.org/repos/asf/test.git"], "", set()),
        ([], "configured", set()),
    ],
)
def test_github_repositories_ignores_policy_and_other_hosts(
    repositories: list[str], policy_name: str, expected: set[str]
):
    project = sql.Project(
        key="test",
        name="Test",
        repositories=repositories,
        release_policy=sql.ReleasePolicy(github_repository_name=policy_name),
    )
    assert project.github_repositories == expected


async def test_inputs_include_declaration(monkeypatch: pytest.MonkeyPatch):
    pk, vk, rev = safe.ProjectKey("test"), safe.VersionKey("1.0"), safe.RevisionNumber("00001")
    declared = atr.models.attestable.ArchiveSourceV2(repository="apache/second", commit="c" * 40)
    recorded = atr.models.attestable.AttestableV2(
        paths={
            "a.tar.gz": atr.models.attestable.PathEntryV2(content_hash="h", classification="source", source=declared)
        },
        source=atr.models.attestable.SourceV2(candidates=["apache/first", "apache/second"]),
    )
    monkeypatch.setattr(attestable, "load", mock.AsyncMock(return_value=recorded))
    common = {
        "source_repository": "",
        "source_commit": "",
        "source_default": "",
        "source_override": "",
        "source_candidates": "apache/first,apache/second",
    }
    assert await source.archive(pk, vk, rev, "a.tar.gz") == declared
    assert await source.inputs(pk, vk, rev, rel_path="a.tar.gz") == {
        **common,
        "archive_repository": "apache/second",
        "archive_commit": "c" * 40,
    }
    assert await source.inputs(pk, vk, rev, rel_path="b.tar.gz") == {
        **common,
        "archive_repository": "",
        "archive_commit": "",
    }
