"""
AI usage logging and cost calculation.
Tracks every AI call for cost allocation and observability.
"""
from decimal import Decimal

from campaigns.models import AIUsageLog, PromptTemplate

# Pricing per 1M tokens (as of 2026-04)
MODEL_PRICING = {
    'claude-sonnet-4-6': {'input': Decimal('3.00'), 'output': Decimal('15.00')},
    'claude-haiku-4-5': {'input': Decimal('0.80'), 'output': Decimal('4.00')},
    'claude-opus-4-6': {'input': Decimal('15.00'), 'output': Decimal('75.00')},
}


def calculate_cost(model, input_tokens, output_tokens):
    """Calculate USD cost for a given model and token counts."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        return Decimal('0')
    input_cost = pricing['input'] * Decimal(input_tokens) / Decimal('1000000')
    output_cost = pricing['output'] * Decimal(output_tokens) / Decimal('1000000')
    return (input_cost + output_cost).quantize(Decimal('0.0001'))


def log_ai_call(campaign, prospect, feature, model, input_tokens, output_tokens,
                latency_ms, success, error_message='', prompt_version=None):
    """
    Log an AI call to AIUsageLog. Resolves organization and product from campaign FK chain.
    Returns the created AIUsageLog record.
    """
    product = campaign.product_ref if campaign else None
    organization = product.organization if product else None

    if not organization or not product:
        return None

    cost = calculate_cost(model, input_tokens, output_tokens)

    return AIUsageLog.objects.create(
        organization=organization,
        product=product,
        campaign=campaign,
        prospect=prospect,
        feature=feature,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        success=success,
        error_message=error_message,
        prompt_version=prompt_version,
    )


def get_prompt(product, feature):
    """
    Return active PromptTemplate for this product+feature, or None.
    Falls back to None (caller should use skill file as default).
    """
    if not product:
        return None
    return PromptTemplate.objects.filter(
        product=product,
        feature=feature,
        is_active=True,
    ).order_by('-version').first()


def get_usage_summary(organization, date_from, date_to):
    """Return usage summary for an organization over a date range."""
    qs = AIUsageLog.objects.filter(
        organization=organization,
        created_at__gte=date_from,
        created_at__lte=date_to,
    )
    total_cost = sum(log.cost_usd for log in qs)
    total_calls = qs.count()
    error_count = qs.filter(success=False).count()

    by_product = {}
    for log in qs:
        slug = log.product.slug
        if slug not in by_product:
            by_product[slug] = {'cost': Decimal('0'), 'calls': 0}
        by_product[slug]['cost'] += log.cost_usd
        by_product[slug]['calls'] += 1

    by_feature = {}
    for log in qs:
        feat = log.feature
        if feat not in by_feature:
            by_feature[feat] = {'cost': Decimal('0'), 'calls': 0}
        by_feature[feat]['cost'] += log.cost_usd
        by_feature[feat]['calls'] += 1

    return {
        'total_cost': total_cost,
        'total_calls': total_calls,
        'error_rate': round(error_count / total_calls * 100, 1) if total_calls else 0,
        'by_product': by_product,
        'by_feature': by_feature,
    }
