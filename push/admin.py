from django.contrib import admin

from .models import PushSubscription


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at", "updated_at", "user_agent")
    list_filter = ("created_at", "updated_at")
    search_fields = ("endpoint", "user__email")
