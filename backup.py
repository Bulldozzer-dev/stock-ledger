"""Create a consistent SQLite backup; refuses to overwrite an existing destination."""
import argparse
import sqlite3
from pathlib import Path

def backup(source,destination):
    source=Path(source);destination=Path(destination)
    if not source.is_file():raise ValueError('Source database does not exist.')
    # Exclusive creation protects existing backups; SQLite then opens this empty file.
    with destination.open('xb'):pass
    try:
        src=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
        try:
            dst=sqlite3.connect(destination)
            try:src.backup(dst)
            finally:dst.close()
        finally:src.close()
    except Exception:
        destination.unlink();raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path);a=p.parse_args();backup(a.source,a.destination);print('Backup created:',a.destination)
