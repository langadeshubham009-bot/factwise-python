from django.urls import path

from .views import ROUTES, make_view

urlpatterns = [path(f"{route}/", make_view(*target), name=route)
               for route, target in ROUTES.items()]
