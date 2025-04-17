from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponse

from pathlib import Path
import logging
import os


class OriginLoggingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        origin = request.META.get('HTTP_ORIGIN')
        host = request.META.get('HTTP_HOST')
        logging.debug(f"Origin: {origin}, Host: {host}")
        return None
