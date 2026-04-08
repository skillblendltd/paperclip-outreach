# Data migration: seed Organization + Products, link Campaign.product_ref FK

from django.db import migrations


def seed_and_link(apps, schema_editor):
    Organization = apps.get_model('campaigns', 'Organization')
    Product = apps.get_model('campaigns', 'Product')
    Campaign = apps.get_model('campaigns', 'Campaign')

    # 1. Create Skillblend organization
    org, _ = Organization.objects.get_or_create(
        slug='skillblend',
        defaults={'name': 'Skillblend Ltd', 'is_active': True},
    )

    # 2. Create products
    product_map = {}
    for slug, name in [
        ('taggiq', 'TaggIQ'),
        ('fullypromoted', 'Fully Promoted Ireland'),
        ('kritno', 'Kritno'),
        ('other', 'Other'),
    ]:
        product, _ = Product.objects.get_or_create(
            organization=org, slug=slug,
            defaults={'name': name, 'is_active': True},
        )
        product_map[slug] = product

    # 3. Link Campaign.product_ref FK based on Campaign.product CharField
    for campaign in Campaign.objects.all():
        legacy_slug = campaign.product or 'other'
        if legacy_slug in product_map:
            campaign.product_ref = product_map[legacy_slug]
            campaign.save(update_fields=['product_ref'])


def reverse_link(apps, schema_editor):
    Campaign = apps.get_model('campaigns', 'Campaign')
    Campaign.objects.all().update(product_ref=None)


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0010_v2_multi_tenant_models'),
    ]

    operations = [
        migrations.RunPython(seed_and_link, reverse_link),
    ]
