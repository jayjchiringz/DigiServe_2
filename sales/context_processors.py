from django.shortcuts import get_object_or_404
from sales.models import Business
from django.contrib.auth.models import Group

def selected_business_context(request):
    """
    Add the selected business to the context based on the user's association.
    """
    selected_business = None

    if request.user.is_authenticated:
        # Retrieve selected business from session
        business_id = request.session.get('selected_business')
        if business_id:
            selected_business = Business.objects.filter(id=business_id).first()
        
        # Validate the selected business or set default if not valid
        if not selected_business or not user_has_business_access(request.user, selected_business):
            user_businesses = Business.objects.filter(users=request.user, is_active=True)
            if user_businesses.exists():
                selected_business = user_businesses.first()
                request.session['selected_business'] = selected_business.id
            else:
                selected_business = None  # No valid business
        
    return {'selected_business': selected_business}


def user_has_business_access(user, business):
    """
    Determine if the user has access to the given business.
    """
    return (
        business.is_active and (
            business.users.filter(id=user.id).exists() or
            business.owners.filter(id=user.id).exists()
        )
    )
