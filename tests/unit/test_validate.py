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

import collections.abc as abc
import datetime
from typing import Any

import pytest
import sqlalchemy.ext.asyncio
import sqlalchemy.pool
import sqlmodel

import atr.db as db
import atr.models.results as results
import atr.models.sql as sql
import atr.validate as validate

CREATED = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
DRAFT = sql.ReleasePhase.RELEASE_CANDIDATE_DRAFT
CANDIDATE = sql.ReleasePhase.RELEASE_CANDIDATE
PREVIEW = sql.ReleasePhase.RELEASE_PREVIEW
RELEASE = sql.ReleasePhase.RELEASE
EMAIL = sql.VoteMode.EMAIL
SHAPE = "vote or announce recipients with to, cc, and bcc"


def release(phase: sql.ReleasePhase, version: str = "1.0", project_key: str = "proj", **fields: Any) -> sql.Release:
    return sql.Release(project_key=project_key, version=version, phase=phase, created=CREATED, **fields)


@pytest.fixture
async def sqlite_sessionmaker() -> abc.AsyncIterator[sqlalchemy.ext.asyncio.async_sessionmaker[db.Session]]:
    engine = sqlalchemy.ext.asyncio.create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=sqlalchemy.pool.StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(sqlmodel.SQLModel.metadata.create_all)
    yield sqlalchemy.ext.asyncio.async_sessionmaker(bind=engine, class_=db.Session, expire_on_commit=False)
    await engine.dispose()


def task(
    task_id: int,
    task_type: sql.TaskType,
    status: sql.TaskStatus,
    version: str | None = None,
    revision: str | None = None,
    task_args: Any = None,
    **fields: Any,
) -> sql.Task:
    return sql.Task(
        id=task_id,
        task_type=task_type,
        status=status,
        task_args=task_args or {},
        asf_uid="alice",
        completed=CREATED if (status != sql.TaskStatus.QUEUED) else None,
        project_key="proj",
        version_key=version,
        revision_number=revision,
        **fields,
    )


@pytest.mark.parametrize(
    ("suffix", "count"),
    [(None, 0), ("", 0), ("{{PROJECT_KEY}}/{{VERSION}}", 0), ("/absolute", 1), ("a/../b", 1)],
)
def test_download_path_suffix(suffix: str | None, count: int) -> None:
    policy = sql.ReleasePolicy(download_path_suffix=suffix or "")
    project = sql.Project(key="proj", release_policy=policy)

    assert len(list(validate.release_download_path_suffix(release(DRAFT, download_path_suffix=suffix)))) == count
    assert len(list(validate.project_download_path_suffix(project))) == count


async def test_everything_audits_cross_record_consistency(sqlite_sessionmaker) -> None:
    async with sqlite_sessionmaker() as data:
        data.add(sql.Committee(key="proj", name="Proj"))
        policy = sql.ReleasePolicy(download_path_suffix="/absolute", recipient_defaults={"vote": "dev@proj.apache.org"})
        data.add(sql.Project(key="proj", name="Apache Proj", committee_key="proj", release_policy=policy))
        data.add(sql.Project(key="gone", name="Apache Gone", committee_key="proj", status=sql.ProjectStatus.RETIRED))
        voting = {"vote_started": CREATED, "vote_mode": EMAIL, "voted_revision_number": "00001"}
        data.add(release(CANDIDATE, "1.0", current_vote_seq=1, **voting))
        data.add(release(PREVIEW, "2.0", current_vote_seq=3, vote_resolved=CREATED, **voting))
        data.add(release(DRAFT, "1.0", "gone"))
        for version in ("0.5", "4.0", "5.0"):
            phase = RELEASE if (version == "0.5") else DRAFT
            data.add(release(phase, version, current_vote_seq=2, vote_started=CREATED))
        await data.commit()
        for release_key in ("proj-1.0", "proj-1.0", "proj-2.0"):
            data.add(sql.Revision(release_key=release_key, asfuid="alice", phase=DRAFT))
        data.add(sql.RevisionCounter(release_key="proj-0.9", last_allocated_number=7))
        for release_key, last in (("proj-1.0", 4), ("proj-4.0", 2), ("proj-5.0", 2)):
            data.add(sql.VoteCounter(release_key=release_key, last_allocated_number=last))
        data.add(
            sql.BallotPaper(
                release_key="proj-4.0",
                vote_seq=9,
                voter_asf_uid="alice",
                voter_fullname="Alice",
                choice=sql.VoteChoice.YES,
                is_binding_at_cast=True,
                revision_number_at_cast="00001",
                receipt_message_id="receipt",
            )
        )
        await data.commit()
        counter = await data.get(sql.RevisionCounter, "proj-2.0")
        assert counter is not None
        counter.last_allocated_number = 0

        published = results.SvnPublish(kind="svn_publish", svn_revision=10, message="Published")
        unusable = results.ReleaseFinalise(kind="release_finalise", audit_events=0, message="Wrong kind")
        finalise = sql.TaskType.RELEASE_FINALISE
        publish = sql.TaskType.SVN_PUBLISH
        validation = sql.TaskType.QUARANTINE_VALIDATE
        queued = sql.TaskStatus.QUEUED
        completed = sql.TaskStatus.COMPLETED
        failed = sql.TaskStatus.FAILED
        data.add(task(1, finalise, queued, "3.1", "00002"))
        data.add(task(2, publish, completed, "3.1", "00001", result=published))
        data.add(task(3, finalise, queued, "3.2", "00001"))
        data.add(task(4, publish, completed, "3.2", "00001", result=published))
        data.add(task(5, finalise, queued, "3.3", "00001"))
        data.add(task(6, publish, completed, "3.3", "00001", result=unusable))
        data.add(task(7, publish, completed, "3.3", "00001", result=published))
        data.add(task(8, validation, queued, "1.0", task_args={"quarantined_id": 1}))
        data.add(task(9, validation, failed, "1.0", task_args={"quarantined_id": 2}, error="Failed"))
        data.add(task(10, sql.TaskType.VOTE_INITIATE, failed, "5.0", task_args={"vote_seq": 6}, error="Failed"))
        data.add(task(11, sql.TaskType.VOTE_INITIATE, failed, "1.0", task_args={"vote_seq": "legacy"}, error="Failed"))

        for quarantined_id in (1, 2, 3):
            data.add(
                sql.Quarantined(
                    id=quarantined_id,
                    release_key="proj-1.0",
                    asf_uid="alice",
                    status=sql.QuarantineStatus.PENDING,
                    token=f"token{quarantined_id}",
                )
            )

        for token_id, asfuid, created_by, is_system in [
            (1, "alice", "alice", False),
            (2, None, "admin", True),
            (3, "bob", "admin", False),
            (4, "admin", "admin", True),
        ]:
            data.add(
                sql.PersonalAccessToken(
                    id=token_id,
                    asfuid=asfuid,
                    created_by=created_by,
                    is_system=is_system,
                    token_hash=f"hash{token_id}",
                    expires=CREATED,
                )
            )

        data.add(sql.Artifact(project_key="proj", version="0.1", artifact_path="old.tar.gz"))
        data.add(
            sql.Artifact(
                project_key="proj",
                version="1.0",
                artifact_path="a.tar.gz",
                release_key="proj-1.0",
                signature_path="a.tar.gz.asc",
                signature_sha3_256="0" * 64,
            )
        )
        data.add(sql.Artifact(project_key="proj", version="1.0", artifact_path="b.tar.gz", release_key="proj-2.0"))
        data.add(sql.Artifact(project_key="proj", version="1.0", artifact_path="c.tar.gz", signature_sha3_256="A" * 64))
        await data.commit()
        malformed = {"kind": "svn_publish", "svn_revision": 123}
        await data.execute(sqlalchemy.update(sql.Task).where(sql.Task.id == 4).values(result=malformed))
        await data.commit()

    async with sqlite_sessionmaker() as data:
        found = sorted([(d.validator, d.source) async for d in validate.everything(data)])

    assert [divergence for divergence in found if divergence[0] != "release_on_disk"] == [
        ("allocation_counters", "proj-2.0"),
        ("allocation_counters", "proj-2.0"),
        ("allocation_counters", "proj-4.0"),
        ("allocation_counters", "proj-5.0"),
        ("artifact_release_key", "proj 1.0 b.tar.gz"),
        ("artifact_signature", "proj 1.0 c.tar.gz"),
        ("artifact_signature", "proj 1.0 c.tar.gz"),
        ("personal_access_token_owner", "token 3"),
        ("personal_access_token_owner", "token 4"),
        ("project_download_path_suffix", "proj"),
        ("project_recipient_defaults", "proj"),
        ("quarantine_pending", "proj-1.0 quarantine 2"),
        ("quarantine_pending", "proj-1.0 quarantine 3"),
        ("release_finalise_publication", "proj 3.1 task 1"),
        ("release_finalise_publication", "proj 3.2 task 3"),
        ("release_project_active", "gone-1.0"),
        ("release_voted_revision", "proj-1.0"),
    ]


@pytest.mark.parametrize(
    ("defaults", "expected"),
    [
        pytest.param({}, [], id="empty"),
        pytest.param({"vote": {"to": "", "cc": [], "bcc": []}}, [], id="empty-block"),
        pytest.param(
            {"vote": {"to": "dev@proj.apache.org", "cc": [], "bcc": ["private@proj.apache.org"]}}, [], id="committee"
        ),
        pytest.param(
            {"vote": {"to": "user-tests@tooling.apache.org", "cc": ["alice@apache.org"], "bcc": []}}, [], id="alpha"
        ),
        pytest.param({"announce": {"to": "", "cc": ["announce@apache.org"], "bcc": []}}, [], id="cc-only"),
        pytest.param(
            {"announce": {"to": "announce@example.org", "cc": [], "bcc": []}},
            ["announce recipients on apache.org or a subdomain"],
            id="external",
        ),
        pytest.param({"vote": "dev@proj.apache.org"}, [SHAPE], id="string-entry"),
        pytest.param({"release": {"to": "dev@proj.apache.org", "cc": [], "bcc": []}}, [SHAPE], id="unknown-action"),
        pytest.param({"vote": {"to": "dev@proj.apache.org", "cc": "a@apache.org", "bcc": []}}, [SHAPE], id="string-cc"),
        pytest.param(["dev@proj.apache.org"], ["a mapping of actions to recipients"], id="list"),
    ],
)
def test_project_recipient_defaults(defaults: Any, expected: list[str]) -> None:
    project = sql.Project(key="proj", release_policy=sql.ReleasePolicy(recipient_defaults=defaults))

    assert [d.divergence.expected for d in validate.project_recipient_defaults(project)] == expected


def test_release_project_active_without_project() -> None:
    divergences = list(validate.release_project_active(release(DRAFT, project_key="missing")))

    assert [(d.divergence.expected, d.divergence.actual) for d in divergences] == [("'active'", "None")]


@pytest.mark.parametrize(
    ("phase", "fields", "expected"),
    [
        pytest.param(DRAFT, {"vote_started": CREATED, "current_vote_seq": 2}, [], id="failed-vote-draft"),
        pytest.param(
            DRAFT,
            {"vote_mode": EMAIL, "podling_thread_id": "thread"},
            [f"{name} to be unset in release_candidate_draft" for name in ("vote_mode", "podling_thread_id")],
            id="draft-with-vote-state",
        ),
        pytest.param(CANDIDATE, {"vote_started": CREATED, "vote_mode": EMAIL}, [], id="legacy-candidate"),
        pytest.param(
            CANDIDATE, {"vote_started": CREATED}, ["vote_mode to be set in release_candidate"], id="candidate-no-mode"
        ),
        pytest.param(
            CANDIDATE,
            {"vote_started": CREATED, "vote_mode": EMAIL, "voted_revision_number": "00001"},
            ["current_vote_seq to be set with voted_revision_number"],
            id="voted-without-serial",
        ),
        pytest.param(PREVIEW, {"vote_started": CREATED, "vote_mode": EMAIL}, [], id="legacy-preview"),
        pytest.param(
            PREVIEW,
            {},
            [f"{name} to be set in release_preview" for name in ("vote_started", "vote_mode")],
            id="legacy-preview-unstarted",
        ),
        pytest.param(
            PREVIEW,
            {"vote_started": CREATED, "vote_mode": EMAIL, "current_vote_seq": 0},
            ["vote_resolved to be set in release_preview"],
            id="numbered-preview-unresolved",
        ),
        pytest.param(RELEASE, {}, [], id="catalogued-release"),
        pytest.param(
            RELEASE, {"current_vote_seq": 1}, ["vote_started to be set with current_vote_seq"], id="serial-not-started"
        ),
    ],
)
def test_release_vote_state(phase: sql.ReleasePhase, fields: dict[str, Any], expected: list[str]) -> None:
    candidate = release(phase, **fields)

    divergences = [*validate.release_vote_fields(candidate), *validate.release_vote_prerequisites(candidate)]

    assert [d.divergence.expected for d in divergences] == expected
