# Central Database Schema & Persistence Foundation

## 1. Overview & Architecture

The JARVIS Database Subsystem provides a centralized, thread-safe, transaction-secure, WAL-mode SQLite persistence foundation for all JARVIS subsystems (tasks, security, sessions, policies, approvals, metadata).

```
┌────────────────────────────────────────────────────────┐
│                   DatabaseManager                      │
│    (UNINITIALIZED -> INITIALIZING -> READY -> CLOSED)  │
├────────────────────────────────────────────────────────┤
│  ConnectionFactory  │  TransactionManager │ BackupMgr  │
│  (WAL Mode, FK=ON,  │  (Atomic Commits,   │ (Online    │
│   Busy Timeout=5s)  │   Savepoint Nesting)│  Backups)  │
├─────────────────────┼─────────────────────┴────────────┤
│   MigrationRunner   │       DatabaseHealthCheck        │
│ (SHA-256 Checksums) │ (PRAGMA integrity_check / FK)    │
└─────────────────────┴──────────────────────────────────┘
                          │
                          ▼
            SQLite Database (data/jarvis.db)
```

---

## 2. Directory Structure

```text
jarvis/database/
    __init__.py
    manager.py          # Authoritative DatabaseManager (LifecycleComponent)
    connection.py       # Connection factory, connection scope, async executor
    settings.py        # DatabaseSettings configuration
    exceptions.py      # Database exception hierarchy
    health.py          # DatabaseHealthCheck & SQLite integrity validator
    transactions.py    # TransactionManager & Savepoint nested scope
    schema.py          # Core schema DDL definitions
    backup.py          # Online SQLite backup engine & candidate restore validator
    migrations/
        __init__.py
        runner.py      # MigrationRunner with SHA-256 checksum validation
        versions/      # Versioned migration DDL files
    repositories/
        __init__.py
        base.py        # BaseRepository abstract base class
    scripts/
        init_db.py     # python -m jarvis.database.scripts.init_db
        migrate.py     # python -m jarvis.database.scripts.migrate
        check_db.py    # python -m jarvis.database.scripts.check_db
        backup_db.py   # python -m jarvis.database.scripts.backup_db
```

---

## 3. SQLite Pragmas & Configuration

- **Location**: `data/jarvis.db` (outside source tree, ignored by `.gitignore`).
- **PRAGMA foreign_keys**: `ON` (enforced on every connection).
- **PRAGMA journal_mode**: `WAL` (Write-Ahead Logging for concurrent readers/single-writer).
- **PRAGMA synchronous**: `NORMAL` (safe durability under WAL mode).
- **PRAGMA busy_timeout**: `5000` (5-second wait before `SQLITE_BUSY`).

---

## 4. Maintenance Commands

```bash
# Initialize Database
python -m jarvis.database.scripts.init_db

# Run Pending Migrations
python -m jarvis.database.scripts.migrate

# Run Database Integrity Check
python -m jarvis.database.scripts.check_db

# Create Online Database Backup
python -m jarvis.database.scripts.backup_db
```

---

## 5. Verification Commands

```bash
.venv\Scripts\python.exe -m pytest tests/unit/test_database_*.py -v
.venv\Scripts\python.exe scripts/quality_gate.py
```
