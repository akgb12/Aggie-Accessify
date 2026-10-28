from django.urls import path
from ninja import NinjaAPI

from accounts.api import router as accounts_router
from projects.api import router

api = NinjaAPI(title="Honors Thesis Accessibility API", version="1.0.0")
api.add_router("/auth", accounts_router)
api.add_router("", router)

urlpatterns = [
    path("api/", api.urls),
]
