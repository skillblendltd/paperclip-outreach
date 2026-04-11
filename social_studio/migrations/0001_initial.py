"""
Take ownership of SocialAccount, SocialPost, SocialPostDelivery from the
`campaigns` app. Paired with `campaigns/0014_move_social_models_to_social_studio`.

State-only: tables already exist in the database, only Django's internal
state tracking changes.

See docs/social-studio-v1-plan.md.
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('campaigns', '0014_move_social_models_to_social_studio'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='SocialAccount',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('platform', models.CharField(choices=[('linkedin', 'LinkedIn'), ('facebook', 'Facebook'), ('instagram', 'Instagram'), ('twitter', 'Twitter / X'), ('google', 'Google Business')], max_length=20)),
                        ('account_name', models.CharField(help_text='Display name (e.g. "TaggIQ LinkedIn Page")', max_length=300)),
                        ('page_id', models.CharField(blank=True, default='', help_text='Platform page/org ID', max_length=200)),
                        ('access_token', models.TextField(blank=True, default='', help_text='OAuth access token')),
                        ('refresh_token', models.TextField(blank=True, default='', help_text='OAuth refresh token (if applicable)')),
                        ('token_expires_at', models.DateTimeField(blank=True, null=True)),
                        ('is_active', models.BooleanField(default=True)),
                        ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='social_studio_accounts', to='campaigns.product')),
                    ],
                    options={
                        'db_table': 'social_accounts',
                        'ordering': ['product', 'platform'],
                        'unique_together': {('product', 'platform')},
                    },
                ),
                migrations.CreateModel(
                    name='SocialPost',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('post_number', models.IntegerField(help_text='Sequential number within the content plan')),
                        ('content', models.TextField(help_text='Post body text (full LinkedIn post text)')),
                        ('hashtags', models.CharField(blank=True, default='', max_length=500)),
                        ('link_url', models.URLField(blank=True, default='', help_text='URL to include (as first comment on LinkedIn)')),
                        ('media_url', models.URLField(blank=True, default='', help_text='[Legacy] Image/video URL')),
                        ('media_description', models.CharField(blank=True, default='', max_length=500)),
                        ('pillar', models.CharField(blank=True, default='', help_text='Content pillar category', max_length=50)),
                        ('scheduled_date', models.DateField(blank=True, null=True)),
                        ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='social_studio_posts', to='campaigns.product')),
                    ],
                    options={
                        'db_table': 'social_posts',
                        'ordering': ['scheduled_date', 'post_number'],
                        'unique_together': {('product', 'post_number')},
                    },
                ),
                migrations.CreateModel(
                    name='SocialPostDelivery',
                    fields=[
                        ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ('created_at', models.DateTimeField(auto_now_add=True)),
                        ('updated_at', models.DateTimeField(auto_now=True)),
                        ('status', models.CharField(choices=[('pending', 'Pending'), ('published', 'Published'), ('failed', 'Failed'), ('skipped', 'Skipped')], default='pending', max_length=20)),
                        ('platform_post_id', models.CharField(blank=True, default='', max_length=200)),
                        ('error', models.TextField(blank=True, default='')),
                        ('published_at', models.DateTimeField(blank=True, null=True)),
                        ('account', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='social_studio.socialaccount')),
                        ('post', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='social_studio.socialpost')),
                    ],
                    options={
                        'db_table': 'social_post_deliveries',
                        'ordering': ['-created_at'],
                        'unique_together': {('post', 'account')},
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
