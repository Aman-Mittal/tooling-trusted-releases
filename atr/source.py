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

from __future__ import annotations

import atr.attestable as attestable
import atr.db as db
import atr.models.attestable
import atr.models.github as github
import atr.models.safe as safe
import atr.models.sql as sql


def advance(
    source: atr.models.attestable.SourceV2,
    payload: github.TrustedPublisherPayload | None,
    override: db.Opt[str | None] = db.NOT_SET,
    *,
    declared: safe.CommitHash | None = None,
) -> atr.models.attestable.SourceV2:
    source = source.model_copy()
    if payload is not None:
        if len(source.candidates) < 2:
            source.repository = payload.repository
        # The run's starting commit only describes the source when the workflow ran in the source repository
        source.default = payload.sha if (payload.repository == source.repository) else None
        # The payload sha is only the commit the run started from, so the workflow can tell us what it checked out
        # An upload that doesn't say should clear any earlier value, otherwise it'd be stale
        source.declared = str(declared) if (declared is not None) else None
        # Any manual override described the earlier files, so the upload should win until someone corrects it again
        source.override = None
    if not isinstance(override, db.NotSet):
        # An override is kept even with no configured repository - there's then nothing
        # to compare it against, but the recorded commit is still worth having.
        source.override = override
    return source


async def archive(
    project_key: safe.ProjectKey, version_key: safe.VersionKey, revision_number: safe.RevisionNumber, rel_path: str
) -> atr.models.attestable.ArchiveSourceV2 | None:
    recorded = await attestable.load(project_key, version_key, revision_number)
    if not isinstance(recorded, atr.models.attestable.AttestableV2):
        return None
    entry = recorded.paths.get(rel_path)
    return entry.source if (entry is not None) else None


async def current(release: sql.Release) -> atr.models.attestable.SourceV2:
    previous = None
    if release.latest_revision_number is not None:
        previous = await attestable.load(
            release.safe_project_key, release.safe_version_key, release.safe_latest_revision_number
        )
    return await initial(release, previous)


async def initial(
    release: sql.Release, previous: atr.models.attestable.Attestable | None
) -> atr.models.attestable.SourceV2:
    candidates = sorted(release.project.github_repositories)
    if isinstance(previous, atr.models.attestable.AttestableV2) and (previous.source is not None):
        source = previous.source.model_copy()
        # Both follow the metadata, so a repository added or corrected since the last revision shows up
        if not (source.default and source.repository and (len(candidates) < 2)):
            source.repository = repository(release.project)
        source.candidates = candidates
        return source
    source = atr.models.attestable.SourceV2(repository=repository(release.project), candidates=candidates)
    if not release.commit_hash:
        return source
    payload = await attestable.latest_github_tp_payload(release.safe_project_key, release.safe_version_key)
    if payload is not None:
        source.repository = payload.repository
        source.default = payload.sha
    if release.commit_hash != source.default:
        source.override = release.commit_hash
    return source


async def inputs(
    project_key: safe.ProjectKey,
    version_key: safe.VersionKey,
    revision_number: safe.RevisionNumber,
    *,
    rel_path: str | None = None,
) -> dict[str, str]:
    source = await read(project_key, version_key, revision_number)
    # The candidates decide whether a comparison is even possible, so they belong in the cache key too
    values = {
        "source_repository": source.repository,
        "source_commit": source.sha,
        "source_default": source.default or "",
        "source_override": source.override or "",
        "source_candidates": ",".join(source.candidates),
    }
    if rel_path is not None:
        declared = await archive(project_key, version_key, revision_number, rel_path)
        values["archive_repository"] = declared.repository if (declared is not None) else ""
        values["archive_commit"] = declared.commit if (declared is not None) else ""
    return values


async def read(
    project_key: safe.ProjectKey, version_key: safe.VersionKey, revision_number: safe.RevisionNumber
) -> atr.models.attestable.SourceV2:
    recorded = await attestable.load(project_key, version_key, revision_number)
    if isinstance(recorded, atr.models.attestable.AttestableV2) and (recorded.source is not None):
        return recorded.source
    payload = await attestable.github_tp_payload_read(project_key, version_key, revision_number)
    if payload is not None:
        return atr.models.attestable.SourceV2(repository=payload.repository, default=payload.sha)
    return atr.models.attestable.SourceV2()


def repository(project: sql.Project) -> str:
    # More than one candidate means we can't say which repository a given archive came from, so nothing is chosen
    repositories = project.github_repositories
    return repositories.pop() if (len(repositories) == 1) else ""


def uploaded(
    record: atr.models.attestable.SourceV2,
    payload: github.TrustedPublisherPayload,
    path_to_hash: dict[safe.RelPath, str],
    classifications: dict[safe.RelPath, str],
    previous: atr.models.attestable.Attestable | None,
) -> dict[safe.RelPath, atr.models.attestable.ArchiveSourceV2]:
    # A workflow's archives come from the repository it ran in, when that is one of the source repositories
    # With one repository the release level record already says so, and an earlier upload's archives aren't ours
    if (len(record.candidates) < 2) or (payload.repository not in record.candidates):
        return {}
    declared = atr.models.attestable.ArchiveSourceV2(
        repository=payload.repository, commit=record.declared or payload.sha
    )
    previous_hashes = attestable.path_hashes(previous) if (previous is not None) else {}
    return {
        path: declared
        for path, content_hash in path_to_hash.items()
        if (classifications[path] == "source") and (previous_hashes.get(str(path)) != content_hash)
    }
