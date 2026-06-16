from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0028_suppression_bounce_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='ses_config_set',
            field=models.CharField(
                blank=True,
                default='',
                help_text='SES Configuration Set name for this campaign. Overrides AWS_SES_CONFIGURATION_SET env var. Leave blank to use the global setting. Use fp-outreach for FP campaigns.',
                max_length=100,
            ),
        ),
    ]
