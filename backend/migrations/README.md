# Migration-ready database structure

The SQLAlchemy models are centralized in `backend/app/db/models.py` and exposed through
`Base.metadata`. The MVP initializer uses `Base.metadata.create_all()` explicitly; it does
not run implicitly when the API module is imported.

When schema evolution is needed, configure Alembic against:

```python
from backend.app.db.base import Base
from backend.app.db import models

target_metadata = Base.metadata
```

The database URL is controlled by `INCIDENT_DATABASE_URL`, defaulting to the SQLite file
`database/incident_commander.db`.
