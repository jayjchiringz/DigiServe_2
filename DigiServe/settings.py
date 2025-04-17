from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponse

from pathlib import Path

import logging
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-4^t+$^ud9(d3m65i+gg#3br_)72-c3)e7gr4(*z)^$z=*n_@h_'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['technothrone.pythonanywhere.com']

CORS_ALLOW_ALL_ORIGINS = True  # Only for testing, not recommended for production

CSRF_COOKIE_SAMESITE = 'Lax' # or 'Strict'
CSRF_COOKIE_SECURE = False  # Since you are using HTTP for now, set this to False
SESSION_COOKIE_SECURE = False  # Ensure this is consistent with CSRF_COOKIE_SECURE
SESSION_COOKIE_SAMESITE = 'Lax'  # (or 'Strict') Ensure this setting is consistent with your security needs

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://127.0.0.1:8000',
    'https://technothrone.pythonanywhere.com',
]

# Set up logging for CSRF failures
logger = logging.getLogger('django')

def log_csrf_failure(request, reason):
    logger.error(f"CSRF failure: {reason} for {request}")
    return HttpResponse('Forbidden', status=403)

# CSRF_FAILURE_VIEW = 'DigiServe.settings.log_csrf_failure'  # Ensure this points to the correct module and function

CSRF_FAILURE_VIEW = 'sales.views.csrf_failure'

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'sales',
    'django.contrib.humanize',
    'rest_framework',
    'guardian'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'DigiServe.middleware.OriginLoggingMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'sales.middleware.selected_business.SelectedBusinessMiddleware',
]

ROOT_URLCONF = 'DigiServe.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'sales.context_processors.selected_business_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'DigiServe.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = '/static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATICFILES_DIRS = [BASE_DIR / "static"]

# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'  # Optimize static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


LOGIN_REDIRECT_URL = '/redirect/'
LOGOUT_REDIRECT_URL = '/accounts/login/'  # Optional but recommended for clean logout

SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# MPESA Configuration
MPESA_CONSUMER_KEY = 'fpe6F7erWAsWay6KJ6q7zu3Qui02I82TPALhG81QUqiELSkB'
MPESA_CONSUMER_SECRET = 'By7y1OTe2zjCrkN7Qt5DxO1RwvP6vX2Cmxi4vrzbD2bBhn8HHR2ytwfsYwRZgmid'
MPESA_SHORTCODE = '174379'
MPESA_PASSKEY = 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919'
MPESA_CALLBACK_URL = 'https://0aeb-102-209-18-80.ngrok-free.app/mpesa-callback/'

'''
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',  # Capture debug logs
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'level': 'DEBUG',  # Write debug logs to a file as well
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'debug.log'),  # Log file path
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        },
        'sales': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',  # Set to DEBUG to capture detailed logs in the sales app
            'propagate': False,
        },
    },
}
'''