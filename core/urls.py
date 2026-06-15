from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView
from tasks.forms import CustomLoginForm
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import set_language


urlpatterns = [

    path('admin/', admin.site.urls),

    path('', include('tasks.urls')),

    path(
        'accounts/login/',
        LoginView.as_view(
            template_name='registration/login.html',
            authentication_form=CustomLoginForm
        ),
        name='login'
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('i18n/', include('django.conf.urls.i18n')),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)