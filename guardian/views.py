from django.shortcuts import render

# Create your views here.
from django.http import JsonResponse, HttpResponse
from .models import GuardianControl, GuardianLog
from django.views.decorators.csrf import csrf_exempt

def control_json(request):
    try:
        control = GuardianControl.objects.first()
        if not control:
            control = GuardianControl.objects.create(enabled=True)
        return JsonResponse({'status': 'on' if control.enabled else 'off'})
    except Exception as e:
        return JsonResponse({'status': 'on'})  # fail-safe default

@csrf_exempt
def upload_log(request):
    if request.method == 'POST':
        content = request.body.decode('utf-8')
        GuardianLog.objects.create(log_text=content)
        return HttpResponse("OK", status=200)
    return HttpResponse("Method Not Allowed", status=405)
