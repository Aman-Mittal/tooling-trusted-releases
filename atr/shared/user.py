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

from typing import Annotated, Literal

import atr.form as form
import atr.models.sql as sql

type CACHE = Literal["cache"]
type DELETE = Literal["delete"]
type TERMINATE_ALL = Literal["terminate_all"]
type TERMINATE_ONE = Literal["terminate_one"]


class CacheUserForm(form.Empty):
    variant: CACHE = form.value(CACHE)


class DeleteCacheForm(form.Empty):
    variant: DELETE = form.value(DELETE)


type SessionsForm = Annotated[
    TerminateAllSessionsForm | TerminateSessionForm,
    form.DISCRIMINATOR,
]


class TallyForm(form.Form):
    thread: str = form.label("Thread URL or ID", required=True)


class TerminateAllSessionsForm(form.Empty):
    variant: TERMINATE_ALL = form.value(TERMINATE_ALL)


class TerminateSessionForm(form.Empty):
    variant: TERMINATE_ONE = form.value(TERMINATE_ONE)
    sid_hash: str = form.label("Session", widget=form.Widget.HIDDEN)


type UserCacheForm = Annotated[
    CacheUserForm | DeleteCacheForm,
    form.DISCRIMINATOR,
]


class UserPreferencesForm(form.Form):
    colour_blindness_mode: form.Enum[sql.ColourBlindnessMode] = form.label(
        "Colour blindness mode", widget=form.Widget.SELECT
    )
    nav_pinned: form.Bool = form.label(
        "Pin navigation to top of viewport",
        documentation="When enabled, the top navigation bar stays visible as you scroll.",
    )
