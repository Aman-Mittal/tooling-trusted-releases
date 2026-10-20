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

import atr.form as form
import atr.models.safe as safe


class ArchiveSourceForm(form.Form):
    repository: str = form.label("Repository", widget=form.Widget.SELECT, required=True)
    commit: safe.CommitHash = form.label(
        "Source commit hash",
        "The full 40-character commit this archive was built from.",
        widget=form.Widget.TEXT,
        required=True,
    )
    rendered_revision: safe.RevisionNumber = form.label("Rendered revision", widget=form.Widget.HIDDEN)


class ClearQuarantineForm(form.Form):
    quarantined_id: form.Int = form.label("Quarantine ID", widget=form.Widget.HIDDEN)


class DeleteFileForm(form.Form):
    file_path: safe.RelPath = form.label("File path", widget=form.Widget.HIDDEN)


class HashGen(form.Empty):
    pass
