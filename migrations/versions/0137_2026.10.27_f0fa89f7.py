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

"""Distinguish full .asf.yaml syncs in update_type

Revision ID: 0137_2026.10.27_f0fa89f7
Revises: 0136_2026.10.23_8bb200dc
Create Date: 2026-10-27 11:17:01.621463+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Revision identifiers, used by Alembic
revision: str = "0137_2026.10.27_f0fa89f7"
down_revision: str | None = "0136_2026.10.23_8bb200dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD = sa.Enum("MANUAL", "BOOTSTRAP", "ASFYAML", name="updatetype")
_NEW = sa.Enum("MANUAL", "BOOTSTRAP", "ASFYAML", "ASFYAML_FULL", name="updatetype")


def upgrade() -> None:
    # The enum is stored by member name, and both tables share it
    for table in ("project", "committee"):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                "update_type", existing_type=_OLD, type_=_NEW, existing_nullable=False, existing_server_default="MANUAL"
            )


def downgrade() -> None:
    for table in ("project", "committee"):
        op.execute(f"UPDATE {table} SET update_type = 'ASFYAML' WHERE update_type = 'ASFYAML_FULL'")
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                "update_type", existing_type=_NEW, type_=_OLD, existing_nullable=False, existing_server_default="MANUAL"
            )
