"""G1 — reply window + grace columns on Campaign.

Part of the reply safety batch (2026-04-15). Adds DB-configurable
business-hours gating and a grace window so AI auto-replies:

  - Only fire during the campaign's configured local business hours
  - Only on configured weekdays
  - Never within `reply_grace_minutes` of initial capture (gives the
    human operator time to open and claim the thread manually)

Defaults are conservative: 9am-6pm Mon-Fri Europe/Dublin with 5-min
grace. Every existing campaign inherits these defaults on migrate
with zero data loss.

Columns are additive. No backfill, no data migration.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0018_inboundemail_needs_manual_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='reply_window_timezone',
            field=models.CharField(
                default='Europe/Dublin',
                help_text='Timezone for reply window (IANA name, e.g. Europe/Dublin)',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='reply_window_start_hour',
            field=models.IntegerField(
                default=9,
                help_text='Earliest hour AI replies may go out (0-23, local time)',
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='reply_window_end_hour',
            field=models.IntegerField(
                default=18,
                help_text='Latest hour AI replies may go out (0-23, local time)',
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='reply_window_days',
            field=models.CharField(
                default='0,1,2,3,4',
                help_text='Comma-separated weekday numbers AI replies may run (0=Mon ... 6=Sun)',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='reply_grace_minutes',
            field=models.IntegerField(
                default=5,
                help_text='Delay after an inbound is captured before AI may reply '
                          'to it. Gives the human operator time to open and claim '
                          'it manually.',
            ),
        ),
    ]
