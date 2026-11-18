"""
One-time: push every file already committed under media/ (repo's local
dish images) into the configured storage backend (S3, once
AWS_STORAGE_BUCKET_NAME is set). The seed migration sets each dish's
image path as a string; this command makes sure the actual file exists
at that path in the bucket.

Usage (run once, after AWS_STORAGE_BUCKET_NAME is set and deployed):
    python manage.py upload_media_to_s3
"""
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Upload the repo media/ folder into the configured storage backend (S3).'

    def handle(self, *args, **options):
        if not getattr(settings, 'AWS_STORAGE_BUCKET_NAME', ''):
            raise CommandError('AWS_STORAGE_BUCKET_NAME not set. Nothing to upload to.')

        source = Path(settings.PROJECT_ROOT) / 'media'
        if not source.is_dir():
            raise CommandError(f'Folder not found: {source}')

        uploaded = skipped = 0
        for f in source.rglob('*'):
            if not f.is_file():
                continue
            dest_name = str(f.relative_to(source))
            if default_storage.exists(dest_name):
                skipped += 1
                continue
            with open(f, 'rb') as fh:
                default_storage.save(dest_name, File(fh))
            uploaded += 1
            self.stdout.write(f'Uploaded: {dest_name}')

        self.stdout.write(self.style.SUCCESS(f'\nDone: {uploaded} uploaded, {skipped} already present.'))
