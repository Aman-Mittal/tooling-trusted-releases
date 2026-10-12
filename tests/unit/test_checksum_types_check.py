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

import pytest

import atr.models.safe as safe
import atr.tasks.checks.paths as paths
import tests.unit.recorders as recorders


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("relative_paths", "sha256_file_count", "sha512_file_count"),
    [
        ({"a.tar.gz", "a.tar.gz.sha256", "a.tar.gz.sha512"}, 1, 1),
        ({"a.tar.gz.sha256", "bin/a-bin.tar.gz.sha512", "bin/a-bin.zip.sha512"}, 1, 2),
        ({"a.tar.gz.sha512", "a.cdx.json.sha256"}, 1, 1),
    ],
)
async def test_mixed_checksum_types_record_suggestion(
    tmp_path, relative_paths: set[str], sha256_file_count: int, sha512_file_count: int
) -> None:
    recorder = _recorder(tmp_path)
    await paths._check_checksum_types(recorder, relative_paths)
    assert [(status, data) for status, _, data in recorder.messages] == [
        ("suggestion", {"sha256_file_count": sha256_file_count, "sha512_file_count": sha512_file_count})
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "relative_paths",
    [
        set(),
        {"a.tar.gz", "a.tar.gz.sha256", "bin/a-bin.zip.sha256"},
        {"a.tar.gz", "a.tar.gz.sha512", "bin/a-bin.zip.sha512"},
        {"a.tar.gz.sha512", "a.tar.gz.sha256.asc"},
        {"a.tar.gz.sha512", "notes.sha256/README.txt"},
    ],
)
async def test_uniform_checksum_types_record_no_suggestion(tmp_path, relative_paths: set[str]) -> None:
    recorder = _recorder(tmp_path)
    await paths._check_checksum_types(recorder, relative_paths)
    assert recorder.messages == []


def _recorder(tmp_path) -> recorders.RecorderStub:
    return recorders.RecorderStub(safe.StatePath(tmp_path), "atr.tasks.checks.paths.check_warnings", "11")
