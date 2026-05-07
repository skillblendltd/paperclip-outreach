"""Add 'bounced' to Prospect.status choices.

Bounced is a terminal state for prospects with undeliverable emails (hard bounces).
Lifecycle.py also enforces send_enabled=False on enter (SUPPRESS_ON_ENTER).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0025_add_mcp_oauth'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prospect',
            name='status',
            field=models.CharField(
                choices=[
                    ('new', 'New'),
                    ('contacted', 'Contacted'),
                    ('engaged', 'Engaged'),
                    ('interested', 'Interested'),
                    ('demo_scheduled', 'Demo Scheduled'),
                    ('design_partner', 'Design Partner'),
                    ('customer', 'Customer'),
                    ('not_interested', 'Not Interested'),
                    ('opted_out', 'Opted Out'),
                    ('follow_up_later', 'Follow Up Later'),
                    ('bounced', 'Bounced (undeliverable email)'),
                ],
                default='new',
                max_length=20,
            ),
        ),
    ]
