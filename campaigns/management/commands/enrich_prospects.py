"""
Prospect enrichment pipeline.
Looks up decision-maker names, titles, and LinkedIn URLs from free public sources.

Sources (in priority order):
    1. companies_house - UK Companies House API (London prospects)
    2. cro             - Irish CRO public search (Ireland prospects)
    3. website         - Scrape /about /team pages from prospect website
    4. google          - Google Custom Search for LinkedIn profiles (100 free/day)

Usage:
    python manage.py enrich_prospects                        # All unenriched
    python manage.py enrich_prospects --source companies_house
    python manage.py enrich_prospects --campaign "London"     # Name substring
    python manage.py enrich_prospects --product taggiq
    python manage.py enrich_prospects --dry-run               # Just count
    python manage.py enrich_prospects --limit 50              # Cap per run
    python manage.py enrich_prospects --source website --use-claude  # AI extraction
"""

import logging
import time
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from campaigns.models import Prospect, Campaign

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Enrich prospects with decision-maker names from public sources"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            choices=["companies_house", "cro", "website", "google", "all"],
            default="all",
            help="Which enrichment source to use",
        )
        parser.add_argument("--product", help="Filter by product slug (e.g. taggiq)")
        parser.add_argument("--campaign", help="Filter by campaign name substring")
        parser.add_argument("--campaign-id", help="Filter by campaign UUID")
        parser.add_argument("--dry-run", action="store_true", help="Count eligible without enriching")
        parser.add_argument("--limit", type=int, default=0, help="Max prospects to process (0=unlimited)")
        parser.add_argument("--use-claude", action="store_true", help="Use Claude AI for website text extraction")
        parser.add_argument("--ch-api-key", help="Companies House API key (or set CH_API_KEY env var)")
        parser.add_argument("--google-api-key", help="Google CSE API key (or set GOOGLE_CSE_API_KEY env var)")
        parser.add_argument("--google-cse-id", help="Google CSE ID (or set GOOGLE_CSE_ID env var)")
        parser.add_argument(
            "--cleanup", action="store_true",
            help="Post-processing: clear likely false positives (same director name appearing 3+ times)",
        )

    def handle(self, *args, **options):
        import os

        source = options["source"]
        dry_run = options["dry_run"]
        limit = options["limit"]
        use_claude = options["use_claude"]

        # Cleanup mode: clear false positives and exit
        if options.get("cleanup"):
            self._run_cleanup()
            return

        # API keys from args or env
        ch_api_key = options.get("ch_api_key") or os.environ.get("CH_API_KEY", "")
        google_api_key = options.get("google_api_key") or os.environ.get("GOOGLE_CSE_API_KEY", "")
        google_cse_id = options.get("google_cse_id") or os.environ.get("GOOGLE_CSE_ID", "")

        # Build prospect queryset - only prospects without decision_maker_name
        prospects = Prospect.objects.filter(
            Q(decision_maker_name="") | Q(decision_maker_name__isnull=True),
        ).select_related("campaign", "campaign__product_ref")

        # Apply filters
        if options.get("product"):
            prospects = prospects.filter(campaign__product_ref__slug=options["product"])
        if options.get("campaign"):
            prospects = prospects.filter(campaign__name__icontains=options["campaign"])
        if options.get("campaign_id"):
            prospects = prospects.filter(campaign_id=options["campaign_id"])

        # For source-specific filtering
        if source == "companies_house":
            # Only UK prospects (London campaigns or UK region)
            prospects = prospects.filter(
                Q(campaign__name__icontains="London") |
                Q(region__icontains="London") |
                Q(region__icontains="England") |
                Q(city__icontains="London")
            )
        elif source == "cro":
            # Only Ireland prospects
            prospects = prospects.filter(
                Q(campaign__name__icontains="Ireland") |
                Q(region__icontains="Ireland") |
                Q(region__icontains="Dublin") |
                Q(city__icontains="Dublin") |
                Q(city__icontains="Cork") |
                Q(city__icontains="Galway") |
                Q(city__icontains="Limerick")
            )

        # Only prospects with a website (needed for website scraping)
        if source in ("website", "all"):
            prospects_with_website = prospects.filter(
                ~Q(website=""), website__isnull=False,
            )

        total = prospects.count()
        if limit > 0:
            prospects = prospects[:limit]
            limited_count = min(limit, total)
        else:
            limited_count = total

        self.stdout.write(f"\nFound {total} unenriched prospects (processing {limited_count})")

        if dry_run:
            self._print_breakdown(prospects)
            return

        # Run enrichment
        stats = {"found": 0, "not_found": 0, "errors": 0, "skipped": 0}

        if source in ("companies_house", "all"):
            self._run_companies_house(prospects, stats, source == "all")

        if source in ("cro", "all"):
            self._run_cro(prospects, stats, source == "all")

        if source in ("website", "all"):
            qs = prospects_with_website if source in ("website", "all") else prospects
            # Re-filter to only those still unenriched (may have been filled by earlier source)
            if source == "all":
                qs = qs.filter(Q(decision_maker_name="") | Q(decision_maker_name__isnull=True))
            self._run_website(qs, use_claude, stats)

        if source in ("google", "all"):
            if not google_api_key or not google_cse_id:
                self.stdout.write(self.style.WARNING(
                    "No Google CSE credentials. Set GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID env vars."
                ))
            else:
                # Google is for finding LinkedIn URLs for already-enriched prospects
                # or as a last resort for unenriched ones
                self._run_google(prospects, google_api_key, google_cse_id, stats)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone! Found: {stats['found']}, Not found: {stats['not_found']}, "
            f"Errors: {stats['errors']}, Skipped: {stats['skipped']}"
        ))
        self.stdout.flush()

    def _print_breakdown(self, prospects):
        """Print breakdown of unenriched prospects by campaign."""
        from django.db.models import Count
        breakdown = prospects.values("campaign__name").annotate(
            count=Count("id"),
        ).order_by("-count")

        self.stdout.write(f"\n{'Campaign':<50} {'Count':>6}")
        self.stdout.write("-" * 58)
        for row in breakdown:
            self.stdout.write(f"{row['campaign__name']:<50} {row['count']:>6}")

    def _save_enrichment(self, prospect, result):
        """Save enrichment data to a prospect."""
        name = (result.get("name") or "").strip()
        if not name or name.lower() in ("null", "none", "n/a", "unknown"):
            return False

        # Validate: must look like a real person name
        words = name.split()
        if len(words) < 2:
            return False  # Need at least first + last name
        if len(words) > 4:
            return False  # Too many words, likely garbage
        # Check for obvious non-names
        bad_words = {
            "the", "and", "or", "in", "of", "at", "for", "with", "by",
            "project", "team", "staff", "leads", "company", "ltd", "limited",
            "director", "owner", "manager", "becoming", "co",
        }
        if any(w.lower() in bad_words for w in words):
            return False

        prospect.decision_maker_name = name
        prospect.decision_maker_title = result.get("title") or "Owner"
        prospect.enrichment_source = result.get("source") or ""
        prospect.enriched_at = timezone.now()

        update_fields = [
            "decision_maker_name", "decision_maker_title",
            "enrichment_source", "enriched_at", "updated_at",
        ]

        if result.get("linkedin_url"):
            prospect.linkedin_url = result["linkedin_url"]
            update_fields.append("linkedin_url")

        if result.get("email"):
            prospect.decision_maker_email = result["email"]
            update_fields.append("decision_maker_email")

        prospect.save(update_fields=update_fields)

    def _run_companies_house(self, prospects, stats, is_all_mode):
        """Run Companies House enrichment for UK prospects."""
        from campaigns.services.enrichment.companies_house import enrich_prospect

        if is_all_mode:
            qs = prospects.filter(
                Q(campaign__name__icontains="London") |
                Q(region__icontains="London") |
                Q(region__icontains="England") |
                Q(city__icontains="London")
            )
        else:
            qs = prospects

        # Materialize to avoid async conflicts
        prospect_list = list(qs.values_list("id", "business_name", "city"))
        count = len(prospect_list)
        self.stdout.write(f"\n--- Companies House ({count} UK prospects) ---")

        for i, (pid, biz_name, city) in enumerate(prospect_list, 1):
            try:
                result = enrich_prospect(biz_name, city)
                if result:
                    prospect = Prospect.objects.get(id=pid)
                    self._save_enrichment(prospect, result)
                    stats["found"] += 1
                    self.stdout.write(
                        f"  [{i}/{count}] {biz_name} -> "
                        f"{result['name']} ({result['title']})"
                    )
                else:
                    stats["not_found"] += 1
                    if i <= 20 or i % 50 == 0:
                        self.stdout.write(f"  [{i}/{count}] {biz_name} -> not found")
            except Exception as e:
                stats["errors"] += 1
                logger.error("CH error for %s: %s", biz_name, e)

            # Rate limit: ~1 req/sec (2 web requests per prospect: search + officers)
            time.sleep(1)

    def _run_cro(self, prospects, stats, is_all_mode):
        """Run Irish CRO enrichment."""
        from campaigns.services.enrichment.irish_cro import search_company_cro

        if is_all_mode:
            qs = prospects.filter(
                Q(campaign__name__icontains="Ireland") |
                Q(region__icontains="Ireland") |
                Q(region__icontains="Dublin") |
                Q(city__icontains="Dublin") |
                Q(city__icontains="Cork") |
                Q(city__icontains="Galway") |
                Q(city__icontains="Limerick")
            )
        else:
            qs = prospects

        count = qs.count()
        if count == 0:
            self.stdout.write("\n--- Irish CRO (0 Irish prospects to enrich) ---")
            return

        self.stdout.write(f"\n--- Irish CRO ({count} Irish prospects) ---")
        self.stdout.write("  Note: CRO uses Playwright browser scraping. Slower than API calls.")

        try:
            from playwright.async_api import async_playwright
            import asyncio

            async def _run_cro_batch():
                async with async_playwright() as pw:
                    browser = await pw.chromium.launch(headless=True)
                    context = await browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    )
                    page = await context.new_page()

                    for i, prospect in enumerate(qs.iterator(), 1):
                        try:
                            directors = await search_company_cro(page, prospect.business_name)
                            if directors:
                                result = {
                                    "name": directors[0]["name"],
                                    "title": directors[0]["title"],
                                    "source": "cro",
                                }
                                self._save_enrichment(prospect, result)
                                stats["found"] += 1
                                self.stdout.write(
                                    f"  [{i}/{count}] {prospect.business_name} -> "
                                    f"{result['name']} ({result['title']})"
                                )
                            else:
                                stats["not_found"] += 1
                                if i <= 20 or i % 50 == 0:
                                    self.stdout.write(
                                        f"  [{i}/{count}] {prospect.business_name} -> not found"
                                    )
                        except Exception as e:
                            stats["errors"] += 1
                            logger.error("CRO error for %s: %s", prospect.business_name, e)

                        time.sleep(2)  # Be gentle with CRO

                    await context.close()
                    await browser.close()

            asyncio.run(_run_cro_batch())

        except ImportError:
            self.stdout.write(self.style.WARNING(
                "  Playwright not installed. Run: pip install playwright && playwright install chromium"
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  CRO enrichment failed: {e}"))

    def _run_website(self, prospects, use_claude, stats):
        """Run website team page scraping with a shared browser instance."""
        from playwright.sync_api import sync_playwright
        from campaigns.services.enrichment.website_scraper import (
            scrape_team_pages, extract_owner_regex, extract_owner_claude,
        )

        # Materialize queryset to avoid async/sync conflict with Playwright
        prospect_list = list(prospects.values_list(
            "id", "business_name", "website", "decision_maker_name",
        ))
        count = len(prospect_list)
        self.stdout.write(f"\n--- Website Scraping ({count} prospects with websites) ---")
        if use_claude:
            self.stdout.write("  Claude AI extraction enabled (falls back to regex first)")
        self.stdout.write("  Using shared browser instance for batch speed")

        # Launch ONE browser for the entire batch
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            for i, (pid, biz_name, website, existing_dm) in enumerate(prospect_list, 1):
                if existing_dm:
                    stats["skipped"] += 1
                    continue

                try:
                    text = scrape_team_pages(website, page=page)
                    result = None
                    if text:
                        result = extract_owner_regex(text)
                        if result:
                            result["source"] = "website"
                        elif use_claude:
                            result = extract_owner_claude(text, biz_name)
                            if result:
                                result["source"] = "website_ai"

                    if result:
                        prospect = Prospect.objects.get(id=pid)
                        saved = self._save_enrichment(prospect, result)
                        if saved is not False:
                            stats["found"] += 1
                            self.stdout.write(
                                f"  [{i}/{count}] {biz_name} -> "
                                f"{result['name']} ({result.get('title', '?')}) [{result['source']}]"
                            )
                        else:
                            stats["not_found"] += 1
                    else:
                        stats["not_found"] += 1
                        if i <= 20 or i % 100 == 0:
                            self.stdout.write(f"  [{i}/{count}] {biz_name} -> not found")
                except Exception as e:
                    stats["errors"] += 1
                    logger.error("Website error for %s: %s", biz_name, e)

                # Brief pause between sites
                time.sleep(0.3)
        finally:
            context.close()
            browser.close()
            pw.stop()

    def _run_google(self, prospects, api_key, cse_id, stats):
        """Run Google CSE for LinkedIn URL lookup."""
        from campaigns.services.enrichment.google_search import (
            search_decision_maker, search_linkedin_profile,
        )

        # Two modes:
        # 1. Prospects WITH decision_maker_name but no linkedin_url -> find their LinkedIn
        # 2. Prospects WITHOUT decision_maker_name -> try to find via Google

        # Mode 1: Find LinkedIn URLs for enriched prospects
        enriched_no_linkedin = Prospect.objects.filter(
            ~Q(decision_maker_name=""),
            Q(linkedin_url="") | Q(linkedin_url__isnull=True),
        ).select_related("campaign", "campaign__product_ref")

        if self._apply_filters_from_qs(enriched_no_linkedin, prospects):
            linkedin_count = enriched_no_linkedin.count()
            self.stdout.write(f"\n--- Google CSE: LinkedIn URL lookup ({linkedin_count} enriched, no LinkedIn) ---")
            self.stdout.write("  Note: 100 free queries/day limit")

            queries_used = 0
            for prospect in enriched_no_linkedin.iterator():
                if queries_used >= 95:  # Leave 5 for mode 2
                    self.stdout.write("  Approaching daily limit, stopping LinkedIn lookup")
                    break

                url = search_linkedin_profile(
                    api_key, cse_id,
                    prospect.decision_maker_name, prospect.business_name,
                )
                if url:
                    prospect.linkedin_url = url
                    prospect.save(update_fields=["linkedin_url", "updated_at"])
                    stats["found"] += 1
                    self.stdout.write(f"  {prospect.decision_maker_name} -> {url}")
                else:
                    stats["not_found"] += 1

                queries_used += 1
                time.sleep(1)

        # Mode 2: Find decision makers via Google (remaining budget)
        unenriched = prospects.filter(
            Q(decision_maker_name="") | Q(decision_maker_name__isnull=True),
        )
        unenriched_count = unenriched.count()
        if unenriched_count > 0:
            remaining_budget = 100 - stats.get("google_queries", 0)
            self.stdout.write(
                f"\n--- Google CSE: Decision maker search ({unenriched_count} unenriched) ---"
            )

            for prospect in unenriched.iterator():
                if remaining_budget <= 0:
                    self.stdout.write("  Daily query limit reached")
                    break

                result = search_decision_maker(
                    api_key, cse_id,
                    prospect.business_name, prospect.city,
                )
                if result:
                    self._save_enrichment(prospect, result)
                    stats["found"] += 1
                    self.stdout.write(
                        f"  {prospect.business_name} -> {result['name']} "
                        f"({result.get('linkedin_url', 'no LinkedIn')})"
                    )
                else:
                    stats["not_found"] += 1

                remaining_budget -= 1
                time.sleep(1)

    def _apply_filters_from_qs(self, target_qs, source_qs):
        """Apply same campaign/product filters. Returns True if any results."""
        # This is a simplified check - the queryset filtering was already
        # applied in the source queryset
        return target_qs.exists()

    def _run_cleanup(self):
        """Clear likely false positive enrichments.

        False positives occur when Companies House fuzzy search matches the
        wrong company. Symptom: same director name appearing across 3+ unrelated
        prospects. Legitimate cases (franchise chains) are rare in our dataset.
        """
        from django.db.models import Count

        self.stdout.write("\n--- Cleanup: detecting false positive enrichments ---")

        # Find director names appearing 3+ times
        suspects = Prospect.objects.filter(
            enrichment_source="companies_house",
        ).values("decision_maker_name").annotate(
            cnt=Count("id"),
        ).filter(cnt__gte=3).order_by("-cnt")

        if not suspects.exists():
            self.stdout.write("  No false positives detected.")
            return

        total_cleared = 0
        for row in suspects:
            name = row["decision_maker_name"]
            count = row["cnt"]
            self.stdout.write(f"  {name} appears {count} times - clearing")

            cleared = Prospect.objects.filter(
                enrichment_source="companies_house",
                decision_maker_name=name,
            ).update(
                decision_maker_name="",
                decision_maker_title="",
                enrichment_source="",
                enriched_at=None,
            )
            total_cleared += cleared

        self.stdout.write(self.style.SUCCESS(
            f"\n  Cleared {total_cleared} false positive enrichments"
        ))

        remaining = Prospect.objects.filter(enrichment_source="companies_house").count()
        self.stdout.write(f"  Remaining clean enrichments: {remaining}")
