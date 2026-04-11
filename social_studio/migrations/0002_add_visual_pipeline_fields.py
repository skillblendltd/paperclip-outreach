"""
Add v1 visual pipeline fields to SocialPost: headline, visual_intent,
bespoke_html_path, media_path.

These are real ALTER TABLE changes.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('social_studio', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='socialpost',
            name='headline',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Short hook used as the visual headline. Separate from body.',
                max_length=280,
            ),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='visual_intent',
            field=models.CharField(
                choices=[
                    ('typography_only', 'Text / typography only'),
                    ('product_screenshot', 'Product screenshot composite'),
                    ('bespoke_html', 'Bespoke HTML authored by designer'),
                ],
                default='bespoke_html',
                help_text='Author-declared rendering strategy',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='bespoke_html_path',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Relative path to the bespoke HTML file (e.g. rendered_html/post_01.html)',
                max_length=500,
            ),
        ),
        migrations.AddField(
            model_name='socialpost',
            name='media_path',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Relative path to the rendered PNG (e.g. rendered_images/post_01.png)',
                max_length=500,
            ),
        ),
    ]
