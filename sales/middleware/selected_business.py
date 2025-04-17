# sales/middleware/selected_business.py

from django.shortcuts import get_object_or_404
from sales.models import Business

class SelectedBusinessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        business_id = request.session.get('selected_business')
        if business_id:
            request.selected_business = get_object_or_404(Business, id=business_id)
        else:
            request.selected_business = None
        return self.get_response(request)