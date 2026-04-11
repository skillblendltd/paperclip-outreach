"""
Render a SocialPost's bespoke HTML to a PNG via Playwright.

Usage:
    python manage.py render_post --post-number 1
    python manage.py render_post --post-number 1 --html rendered_html/post_01.html
    python manage.py render_post --all
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from social_studio.models import SocialPost
from social_studio.services.renderer import (
    render_html_to_png,
    resolve_post_html,
    default_png_path_for,
)


class Command(BaseCommand):
    help = 'Render a SocialPost bespoke HTML to a 1200x1200 PNG'

    def add_arguments(self, parser):
        parser.add_argument('--post-number', type=int)
        parser.add_argument('--all', action='store_true', help='Render every post that has bespoke_html_path set')
        parser.add_argument('--html', type=str, help='Override HTML path (relative to social_studio/)')
        parser.add_argument('--out', type=str, help='Override output PNG path (absolute)')

    def handle(self, *args, **options):
        if options['all']:
            return self._render_all()

        if not options['post_number']:
            raise CommandError('Specify --post-number or --all')

        post = SocialPost.objects.filter(post_number=options['post_number']).first()
        if not post:
            raise CommandError(f'SocialPost not found: post_number={options["post_number"]}')

        # Resolve HTML source
        if options['html']:
            base = Path(settings.BASE_DIR) / 'social_studio'
            html_path = (base / options['html']).resolve()
            # Also record it on the post
            if str(post.bespoke_html_path) != options['html']:
                post.bespoke_html_path = options['html']
        else:
            html_path = resolve_post_html(post)
            if not html_path:
                raise CommandError(
                    f'Post #{post.post_number} has no bespoke_html_path. '
                    f'Pass --html or set post.bespoke_html_path first.'
                )

        # Resolve output
        out_path = Path(options['out']).resolve() if options['out'] else default_png_path_for(post)

        self.stdout.write(f'Rendering {html_path}')
        self.stdout.write(f'      -> {out_path}')

        result = render_html_to_png(html_path, out_path)

        # Update media_path on post (relative to social_studio/)
        base = Path(settings.BASE_DIR) / 'social_studio'
        try:
            rel_media = result.relative_to(base)
            post.media_path = str(rel_media)
        except ValueError:
            post.media_path = str(result)
        post.save(update_fields=['media_path', 'bespoke_html_path', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(f'Rendered post #{post.post_number} -> {result}'))

    def _render_all(self):
        posts = SocialPost.objects.exclude(bespoke_html_path='').order_by('post_number')
        if not posts.exists():
            self.stdout.write('No posts with bespoke_html_path set.')
            return

        rendered = 0
        for post in posts:
            html_path = resolve_post_html(post)
            if not html_path or not html_path.exists():
                self.stdout.write(self.style.WARNING(f'Post #{post.post_number}: HTML not found ({post.bespoke_html_path})'))
                continue
            out_path = default_png_path_for(post)
            try:
                render_html_to_png(html_path, out_path)
                base = Path(settings.BASE_DIR) / 'social_studio'
                post.media_path = str(out_path.relative_to(base))
                post.save(update_fields=['media_path', 'updated_at'])
                rendered += 1
                self.stdout.write(f'  #{post.post_number:2d} -> {out_path.name}')
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'  #{post.post_number}: {exc}'))

        self.stdout.write(self.style.SUCCESS(f'Rendered {rendered} post(s)'))
