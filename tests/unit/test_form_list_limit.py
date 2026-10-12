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
import enum
import functools
from typing import Any

import pydantic
import pytest
import quart.datastructures as datastructures

import atr.form as form

_URI = "https://example.org/x"


class Colour(enum.Enum):
    RED = "red"


class ListForm(form.Form):
    names: form.StrList = form.label("Names")


@pytest.mark.parametrize(
    ("convert", "valid", "invalid"),
    [
        (form.to_str_list, "alice", ""),
        (form.to_safe_path_list, "a.txt", "/etc/passwd"),
        (form.to_repository_uri_list, _URI, "javascript:alert(1)"),
        (form.to_standard_uri_list, _URI, ""),
        (form.to_filestorage_list, datastructures.FileStorage(filename="a.txt"), "a.txt"),
        (functools.partial(form.to_enum_set, enum_class=Colour), "red", "red"),
    ],
)
def test_list_converters_limit_items(convert: abc.Callable[[Any], Any], valid: object, invalid: object) -> None:
    assert convert([valid] * 1000)
    with pytest.raises(ValueError, match="Expected at most 1000 items, got 1001"):
        convert([invalid] * 1001)


def test_list_limit_is_a_field_error() -> None:
    validated = form.validate(ListForm, {"csrf_token": "x", "names": ["alice"] * 1000})
    assert isinstance(validated, ListForm)
    assert len(validated.names) == 1000
    with pytest.raises(pydantic.ValidationError) as exc_info:
        form.validate(ListForm, {"csrf_token": "x", "names": ["alice"] * 1001})
    errors = exc_info.value.errors()
    assert [(error["loc"], error["type"]) for error in errors] == [(("names",), "value_error")]
    flash_data = form.flash_error_data(ListForm, errors, {})
    assert flash_data["names"]["msg"] == "Expected at most 1000 items, got 1001"


@pytest.mark.parametrize("convert", [form.to_repository_uri_list, form.to_standard_uri_list])
def test_uri_text_limits_entries(convert: abc.Callable[[Any], list[str]]) -> None:
    assert convert("\n\n".join([_URI] * 1000)) == [_URI] * 1000
    with pytest.raises(ValueError, match="Expected at most 1000 items, got 1001"):
        convert("\n".join(["javascript:alert(1)"] * 1001))
