"""Validate and restore an Atlas workspace backup into a NEW data directory."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile


def restore(archive_path, target):
    target = Path(target).resolve()
    if target.exists():
        raise ValueError('Choose a new, non-existing destination folder. Existing data is never overwritten.')
    with zipfile.ZipFile(archive_path) as archive:
        if sorted(archive.namelist()) != ['atlas.sqlite3', 'manifest.json']:
            raise ValueError('Unexpected backup files. Choose an Atlas workspace backup.')
        if archive.getinfo('atlas.sqlite3').file_size > 2_000_000_000 or archive.getinfo('manifest.json').file_size > 10000:
            raise ValueError('Backup exceeds the supported restore size.')
        manifest = json.loads(archive.read('manifest.json'))
        database = archive.read('atlas.sqlite3')
    if manifest.get('format') != 'atlas-backup-v1' or hashlib.sha256(database).hexdigest() != manifest.get('sha256'):
        raise ValueError('Backup integrity check failed.')
    target.mkdir(parents=True)
    path = target / 'atlas.sqlite3'
    path.write_bytes(database)
    connection = sqlite3.connect(path)
    try:
        if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('The restored database failed its integrity check.')
        # Scheduled requests never restart automatically after a restore.
        for identity, raw in connection.execute('SELECT id,data FROM monitors').fetchall():
            record = json.loads(raw)
            record['enabled'] = False
            connection.execute('UPDATE monitors SET data=? WHERE id=?', (json.dumps(record), identity))
        for table in ('jobs', 'runs'):
            for identity, raw in connection.execute(f'SELECT id,data FROM {table}').fetchall():
                record = json.loads(raw)
                if record.get('status') in ('queued', 'running', 'cancel_requested'):
                    record.update(status='interrupted', message='Restored from backup. Review before retrying any source request.')
                    connection.execute(f'UPDATE {table} SET data=? WHERE id=?', (json.dumps(record), identity))
        connection.commit()
    finally:
        connection.close()
    (target / 'free-mode.json').write_text(json.dumps({'enabled':manifest.get('free_only') is True}),encoding='utf-8')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup')
    parser.add_argument('destination')
    args = parser.parse_args()
    restored = restore(args.backup, args.destination)
    print(f'Restored database: {restored}. Monitors are paused; active requests will not replay.')
