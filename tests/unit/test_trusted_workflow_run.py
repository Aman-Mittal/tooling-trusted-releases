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

import pytest
import sqlalchemy.ext.asyncio
import sqlalchemy.pool
import sqlmodel

import atr.db as db
import atr.db.interaction as interaction
import atr.models.github as github
import atr.models.safe as safe
import atr.models.sql as sql


@pytest.fixture
async def recorded_run(monkeypatch: pytest.MonkeyPatch) -> abc.AsyncIterator[None]:
    engine = sqlalchemy.ext.asyncio.create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=sqlalchemy.pool.StaticPool
    )
    async with engine.begin() as connection:
        await connection.run_sync(sqlmodel.SQLModel.metadata.create_all)
    maker = sqlalchemy.ext.asyncio.async_sessionmaker(engine, class_=db.Session, expire_on_commit=False)
    async with maker() as data:
        data.add(
            sql.WorkflowStatus(
                workflow_id="distribute-mavencentral.yml", run_id=100, project_key="example", task_id=7, status=""
            )
        )
        await data.commit()
    monkeypatch.setattr(db, "session", maker)
    yield
    await engine.dispose()


async def test_a_run_that_atr_recorded_is_trusted(recorded_run: None, github_payload: github.TrustedPublisherPayload):
    github_payload.run_id = "100"
    await interaction.trusted_workflow_run(github_payload, 7, safe.ProjectKey("example"))


@pytest.mark.parametrize(
    ("run_id", "task_id", "project_key"),
    [
        pytest.param("101", 7, "example", id="other-run"),
        pytest.param("100", 8, "example", id="other-task"),
        pytest.param("100", 7, "other", id="other-project"),
        pytest.param(None, 7, "example", id="no-run-id"),
    ],
)
async def test_any_other_run_is_refused(
    recorded_run: None,
    github_payload: github.TrustedPublisherPayload,
    run_id: str | None,
    task_id: int,
    project_key: str,
):
    github_payload.run_id = run_id
    with pytest.raises(interaction.InteractionError):
        await interaction.trusted_workflow_run(github_payload, task_id, safe.ProjectKey(project_key))
