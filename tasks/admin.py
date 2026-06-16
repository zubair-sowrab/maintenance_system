from django.contrib import admin

from .models import (
    Task,
    SubTask,
    Complaint,
    Profile,
    Notification,
TaskItem,
)
from django.contrib import admin
from .models import MaintenanceWorkItem

@admin.register(MaintenanceWorkItem)
class MaintenanceWorkItemAdmin(admin.ModelAdmin):
    list_display = ['project_type', 'name_english', 'name_arabic']
    list_filter = ['project_type']
    search_fields = ['name_english', 'name_arabic']

class TaskItemInline(admin.TabularInline):
    model = TaskItem
    extra = 1  # Shows one blank slot to add items manually if needed

admin.site.register(Profile)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'job_id',
        'location',
        'budget',
        'assigned_to_display',  # Use the new property here
        'status',
        'priority',
    )

    # This adds a nice selection box in the Admin UI
    filter_horizontal = ('assigned_technicians',)




    search_fields = (
        'title',
        'job_id',
        'location',
    )

    list_filter = (
        'status',
        'project_type',
        'priority',
    )

    inlines = [TaskItemInline]






    # Also register it individually just in case you want to view them raw
admin.site.register(TaskItem)


admin.site.register(SubTask)
admin.site.register(Complaint)
admin.site.register(Notification)
admin.site.site_header = "Maintenance System Admin"
admin.site.site_title = "Maintenance System Admin"
admin.site.index_title = "Welcome to Maintenance System"



