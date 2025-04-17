import os
import django
from django.urls import reverse

# Set the DJANGO_SETTINGS_MODULE environment variable
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DigiServe.settings')

# Initialize Django
django.setup()

# Test reverse URL resolution
try:
    print(reverse('table-update', kwargs={'pk': 1}))  # Should output: /tables/1/edit/
    print(reverse('table-delete', kwargs={'pk': 1}))  # Should output: /tables/1/delete/
except Exception as e:
    print(f"Error: {e}")
