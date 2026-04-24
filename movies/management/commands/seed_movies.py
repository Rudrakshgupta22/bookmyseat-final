from django.core.management.base import BaseCommand
from movies.apps import seed_sample_movies


class Command(BaseCommand):
    help = 'Seed the database with sample movie data'

    def handle(self, *args, **options):
        self.stdout.write('Starting to seed movies...')
        try:
            seed_sample_movies()
            self.stdout.write(
                self.style.SUCCESS('Successfully seeded movies!')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to seed movies: {e}')
            )