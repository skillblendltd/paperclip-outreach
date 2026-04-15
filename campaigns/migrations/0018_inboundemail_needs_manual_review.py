"""F2 — add needs_manual_review column to InboundEmail.

Part of the reply-matching tenant-isolation fix (2026-04-15).

When `check_replies._match_to_prospect` cannot confidently disambiguate
which tenant (Organization/Product/Campaign) an inbound belongs to — e.g.,
a sender email that matches prospect rows in multiple Products with no
In-Reply-To thread ancestor — the inbound is saved with
`needs_manual_review=True` and `needs_reply=False`, blocking the AI reply
pipeline from auto-handling it. A human reviews these via the admin list
filter.

Additive only. Nullable boolean default False. No data backfill.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0017_sprint7_product_brain'),
    ]

    operations = [
        migrations.AddField(
            model_name='inboundemail',
            name='needs_manual_review',
            field=models.BooleanField(
                default=False,
                help_text='True when reply matching could not confidently attribute '
                          'this inbound to a single tenant (Organization/Product/Campaign). '
                          'Blocks auto-reply. Human reviews via admin.',
            ),
        ),
    ]
