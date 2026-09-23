import sqlite3
from unittest.mock import patch

import pytest

from eidos.adapters.sqlite_jobs import SQLiteJobStore


@pytest.mark.parametrize("fail", [False, True])
def test_queue_connections_close_after_transactions(tmp_path, fail):
    store = SQLiteJobStore(tmp_path / "jobs.sqlite3")
    opened = []
    real_connect = sqlite3.connect

    def track(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        opened.append(connection)
        return connection

    with patch("eidos.adapters.sqlite_jobs.sqlite3.connect", side_effect=track):
        for _ in range(100):
            try:
                with store._connect() as connection:
                    connection.execute("SELECT 1")
                    if fail:
                        raise RuntimeError("rollback")
            except RuntimeError:
                pass
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
