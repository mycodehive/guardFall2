from django.contrib import admin
from .models import Menu
@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display=['title','code','parent','order','active','staff_only']
    list_filter=['active','staff_only']
    filter_horizontal=['groups']
