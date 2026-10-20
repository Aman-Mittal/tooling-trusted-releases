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

import atr.db.interaction as interaction
import atr.models.sql as sql

WORKFLOW_REF = "apache/first/.github/workflows/release.yml@refs/heads/main"


@pytest.mark.parametrize(
    ("policy_name", "metadata", "matches"),
    [
        pytest.param("first", [], True, id="named-repository"),
        pytest.param("elsewhere", ["https://github.com/apache/first"], False, id="named-other-repository"),
        pytest.param("", ["https://github.com/apache/first", "https://github.com/apache/second"], True, id="metadata"),
        pytest.param("", ["https://github.com/apache/second"], False, id="not-in-metadata"),
        pytest.param("", ["https://gitbox.apache.org/repos/asf/first.git"], False, id="not-github"),
    ],
)
async def test_matches_follow_the_policy_or_the_metadata(policy_name: str, metadata: list[str], matches: bool):
    project = sql.Project(key="one", name="One", repositories=metadata)
    data = _data({1: project})

    found = await interaction._trusted_project_matches(
        data, [sql.ReleasePolicy(id=1, github_repository_name=policy_name)], "apache/first"
    )

    assert found == ([project] if matches else [])


async def test_two_projects_with_the_same_repository_are_refused(monkeypatch: pytest.MonkeyPatch):
    first = sql.Project(key="one", name="One", repositories=["https://github.com/apache/first"])
    fork = sql.Project(key="fork", name="Fork", repositories=["https://github.com/apache/first"])
    _patch_lookup(monkeypatch, [sql.ReleasePolicy(id=1), sql.ReleasePolicy(id=2)], {1: first, 2: fork})

    with pytest.raises(interaction.InteractionError, match="more than one project: fork, one"):
        await interaction._trusted_project("apache/first", WORKFLOW_REF, interaction.TrustedProjectPhase.COMPOSE)


async def test_a_policy_without_a_project_is_skipped(monkeypatch: pytest.MonkeyPatch):
    project = sql.Project(
        key="one",
        name="One",
        repositories=["https://github.com/apache/first"],
        committee=sql.Committee(key="one", name="One"),
    )
    _patch_lookup(monkeypatch, [sql.ReleasePolicy(id=1), sql.ReleasePolicy(id=2)], {1: None, 2: project})
    monkeypatch.setattr(interaction, "ci_builds_enabled", mock.AsyncMock(return_value=True))

    found = await interaction._trusted_project("apache/first", WORKFLOW_REF, interaction.TrustedProjectPhase.COMPOSE)

    assert found is project


async def test_no_matching_project_is_not_found(monkeypatch: pytest.MonkeyPatch):
    other = sql.Project(key="other", name="Other", repositories=["https://github.com/apache/second"])
    _patch_lookup(monkeypatch, [sql.ReleasePolicy(id=1)], {1: other})

    with pytest.raises(interaction.ReleasePolicyNotFoundError):
        await interaction._trusted_project("apache/first", WORKFLOW_REF, interaction.TrustedProjectPhase.COMPOSE)


async def test_one_matching_project_is_returned(monkeypatch: pytest.MonkeyPatch):
    project = sql.Project(
        key="one",
        name="One",
        repositories=["https://github.com/apache/first"],
        committee=sql.Committee(key="one", name="One"),
    )
    _patch_lookup(monkeypatch, [sql.ReleasePolicy(id=1)], {1: project})
    monkeypatch.setattr(interaction, "ci_builds_enabled", mock.AsyncMock(return_value=True))

    found = await interaction._trusted_project("apache/first", WORKFLOW_REF, interaction.TrustedProjectPhase.COMPOSE)

    assert found is project


def _data(projects: dict[int, sql.Project | None]) -> mock.MagicMock:
    def project(release_policy_id: int) -> mock.MagicMock:
        query = mock.MagicMock()
        query.get = mock.AsyncMock(return_value=projects[release_policy_id])
        return query

    data = mock.MagicMock()
    data.project.side_effect = project
    return data


def _patch_lookup(
    monkeypatch: pytest.MonkeyPatch, policies: list[sql.ReleasePolicy], projects: dict[int, sql.Project | None]
) -> None:
    data = _data(projects)
    data.release_policy.return_value.all = mock.AsyncMock(return_value=policies)
    session = mock.AsyncMock()
    session.__aenter__.return_value = data
    monkeypatch.setattr(interaction.db, "session", mock.MagicMock(return_value=session))
