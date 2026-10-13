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

import io
import pathlib
import unittest.mock as mock

import pytest
import werkzeug.datastructures as datastructures

import atr.models.safe as safe
import atr.storage.writers.release as release


async def test_upload_files_rejects_symlink_escaping_revision(tmp_path: pathlib.Path):
    revision_dir = tmp_path / "revision"
    outside_dir = tmp_path / "outside"
    revision_dir.mkdir()
    outside_dir.mkdir()
    (revision_dir / "dir").symlink_to(outside_dir, target_is_directory=True)
    write_as = mock.MagicMock()
    write_as.revision.create_revision_with_quarantine = mock.AsyncMock()
    participant = release.CommitteeParticipant(mock.MagicMock(), write_as, mock.MagicMock(), "test")
    upload = datastructures.FileStorage(io.BytesIO(b"payload"), filename="dir/new/escaped.txt")

    await participant.upload_files(safe.ProjectKey("proj"), safe.VersionKey("1.0"), [upload])
    modify = write_as.revision.create_revision_with_quarantine.call_args.kwargs["modify"]

    with pytest.raises(ValueError):
        await modify(safe.StatePath(revision_dir, tmp_path), None)

    assert list(outside_dir.iterdir()) == []
