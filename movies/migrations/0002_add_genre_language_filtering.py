# Generated migration for Genre, Language, and Movie model updates

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('movies', '0001_initial'),
    ]

    operations = [
        # Create Genre model
        migrations.CreateModel(
            name='Genre',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
            ],
            options={
                'verbose_name_plural': 'Genres',
                'indexes': [
                    models.Index(fields=['name'], name='movies_genr_name_idx'),
                ],
            },
        ),
        # Create Language model
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('code', models.CharField(max_length=5, unique=True)),
            ],
            options={
                'verbose_name_plural': 'Languages',
                'indexes': [
                    models.Index(fields=['code'], name='movies_lang_code_idx'),
                ],
            },
        ),
        # Add fields to Movie model
        migrations.AddField(
            model_name='movie',
            name='duration',
            field=models.IntegerField(blank=True, help_text='Duration in minutes', null=True),
        ),
        migrations.AddField(
            model_name='movie',
            name='release_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='movie',
            name='genres',
            field=models.ManyToManyField(blank=True, related_name='movies', to='movies.genre'),
        ),
        migrations.AddField(
            model_name='movie',
            name='languages',
            field=models.ManyToManyField(blank=True, related_name='movies', to='movies.language'),
        ),
        # Add database indexes
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(fields=['name'], name='movies_movi_name_idx'),
        ),
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(fields=['rating'], name='movies_movi_rating_idx'),
        ),
        migrations.AddIndex(
            model_name='movie',
            index=models.Index(fields=['release_date'], name='movies_movi_release_idx'),
        ),
    ]
