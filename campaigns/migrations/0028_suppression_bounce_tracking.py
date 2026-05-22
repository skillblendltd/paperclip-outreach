# Generated migration - add bounce tracking to Suppression model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0027_add_domain_daily_limit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='suppression',
            name='reason',
            field=models.CharField(
                choices=[
                    ('opt_out', 'Opted Out'),
                    ('hard_bounce', 'Hard Bounce (permanent)'),
                    ('soft_bounce', 'Soft Bounce (transient)'),
                    ('complained', 'User Complained / Spam'),
                    ('test_address', 'Test Address'),
                    ('role_account', 'Role Account (noreply, postmaster, etc)'),
                    ('manual', 'Manually Added'),
                ],
                max_length=30
            ),
        ),
        migrations.AlterField(
            model_name='suppression',
            name='notes',
            field=models.TextField(blank=True, default='', help_text='Bounce type, complaint category, or other context'),
        ),
        migrations.AddField(
            model_name='suppression',
            name='soft_bounce_count',
            field=models.IntegerField(default=0, help_text='Number of soft bounces before suppression. Suppressed when >= 3.'),
        ),
    ]
