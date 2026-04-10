import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-secret-change-me')
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'campaigns',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'outreach.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db" / "outreach.sqlite3"}',
        conn_max_age=600,
    )
}

STATIC_URL = 'static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email / SES
EMAIL_SERVICE_MODE = os.getenv('EMAIL_SERVICE_MODE', 'console')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
AWS_SMTP_USERNAME = os.getenv('AWS_SMTP_USERNAME', '')
AWS_SMTP_PASSWORD = os.getenv('AWS_SMTP_PASSWORD', '')
AWS_SES_FROM_EMAIL = os.getenv('AWS_SES_FROM_EMAIL', 'noreply@example.com')

# Zoho IMAP (reading replies)
ZOHO_IMAP_HOST = os.getenv('ZOHO_IMAP_HOST', 'imappro.zoho.eu')
ZOHO_IMAP_PORT = int(os.getenv('ZOHO_IMAP_PORT', '993'))
ZOHO_IMAP_EMAIL = os.getenv('ZOHO_IMAP_EMAIL', '')
ZOHO_IMAP_PASSWORD = os.getenv('ZOHO_IMAP_PASSWORD', '')

# Zoho SMTP (sending threaded replies)
ZOHO_SMTP_HOST = os.getenv('ZOHO_SMTP_HOST', 'smtppro.zoho.eu')
ZOHO_SMTP_PORT = int(os.getenv('ZOHO_SMTP_PORT', '465'))
ZOHO_SMTP_EMAIL = os.getenv('ZOHO_SMTP_EMAIL', '')
ZOHO_SMTP_PASSWORD = os.getenv('ZOHO_SMTP_PASSWORD', '')

# Vapi.ai (outbound calling)
VAPI_API_KEY = os.environ.get('VAPI_API_KEY', '')
VAPI_PHONE_NUMBER_ID = os.environ.get('VAPI_PHONE_NUMBER_ID', '')
VAPI_ASSISTANT_ID = os.environ.get('VAPI_ASSISTANT_ID', '')

# TaggIQ webhook integration
TAGGIQ_WEBHOOK_SECRET = os.environ.get('TAGGIQ_WEBHOOK_SECRET', '')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
