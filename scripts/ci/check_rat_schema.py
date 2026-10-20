#!/usr/bin/env python3

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

import sys
import zipfile
from typing import Final

import defusedxml.ElementTree as ElementTree

_NAMESPACES: Final = {"xs": "http://www.w3.org/2001/XMLSchema"}
_REQUIRED: Final = (
    ("xs:element[@name='rat-report']/xs:complexType/*/xs:element[@name='version']", set()),
    (".//xs:element[@name='resource']", {"name", "type"}),
    (".//xs:element[@name='resource']/xs:complexType/*/xs:element[@name='license']", {"approval", "name"}),
)


def main() -> None:
    with zipfile.ZipFile(sys.argv[1]) as jar:
        schema = ElementTree.fromstring(jar.read("org/apache/rat/rat-report.xsd"))
    if schema.get("targetNamespace") is not None:
        sys.exit("ERROR: the RAT report schema has a target namespace")
    for path, required in _REQUIRED:
        child = schema.find(path, _NAMESPACES)
        if child is None:
            sys.exit(f"ERROR: the RAT report schema does not declare {path}")
        attributes = child.findall("xs:complexType/xs:attribute", _NAMESPACES)
        missing = required - {attribute.get("name") for attribute in attributes}
        if missing:
            sys.exit(f"ERROR: the RAT report schema does not declare {sorted(missing)} on {path}")


if __name__ == "__main__":
    main()
