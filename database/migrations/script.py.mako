"""Generic single-database configuration."""

from alembic import context
from sqlalchemy import pool
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "${head}"
down_revision = ${down_revision}
branch_labels = ${branch_labels}
create_date_utc = "${create_date_utc}"

depends_on = None


def upgrade() -> None:
    """Apply this migration (forward)."""
    # Placeholder: Alembic autogenerate will fill this in
    pass


def downgrade() -> None:
    """Revert this migration (backward)."""
    # Placeholder: Alembic autogenerate will fill this in
    pass
