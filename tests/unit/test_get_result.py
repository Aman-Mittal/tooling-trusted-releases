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

import types
import unittest.mock as mock

import atr.attestable as attestable
import atr.get.result as result
import atr.models.safe as safe


async def test_excludes_text_reads_policy_from_revision_snapshot() -> None:
    check_result = types.SimpleNamespace(
        data={"excludes_source": "policy"}, revision_number="00002", primary_rel_path="example-1.0-src.tar.gz"
    )
    snapshot = types.SimpleNamespace(policy={"source_excludes_rat": ["*.txt", "docs/**"]})
    with mock.patch.object(attestable, "load", new=mock.AsyncMock(return_value=snapshot)):
        text = await result._excludes_text(safe.ProjectKey("example"), safe.VersionKey("1.0"), check_result)
    assert text == "*.txt\ndocs/**\n"
