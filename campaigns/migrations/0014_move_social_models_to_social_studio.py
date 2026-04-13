"""
Move SocialAccount, SocialPost, SocialPostDelivery from `campaigns` to
`social_studio`. This is a STATE-ONLY migration — the DB tables stay put.

Paired with `social_studio/migrations/0001_initial.py` which creates the
models in state (also DB-free) so the new app owns them.

See docs/social-studio-v1-plan.md.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0013_social_media_multi_platform'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Delete in FK-safe order: Delivery depends on Post + Account
                migrations.DeleteModel(name='SocialPostDelivery'),
                migrations.DeleteModel(name='SocialPost'),
                migrations.DeleteModel(name='SocialAccount'),
            ],
            database_operations=[
                # No-op: tables remain; ownership shifts to social_studio
            ],
        ),
    ]
