from django.urls import path
from . import views
from django.contrib.auth.views import LogoutView
from .views import add_sub_category_ajax
from .views import CustomLoginView
urlpatterns = [
path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path("", views.dashboard, name="task_list"),
    path(
        'dashboard/',
        views.dashboard,
        name='dashboard'
    ),

    path(
        'tasks/',
        views.task_list,
        name='task_list'
    ),

path('tasks/<int:task_id>/upload-attachment/', views.upload_task_attachment, name='upload_task_attachment'),
path('task/<int:task_id>/add-item/', views.add_task_item_detail, name='add_task_item_detail'),

path('tasks/award-reward-points-ajax/<int:task_id>/', views.award_reward_points_ajax, name='award_reward_points_ajax'),
    path(
        'create-task/',
        views.create_task,
        name='create_task'
    ),

    path(
        'task/<int:task_id>/',
        views.task_detail,
        name='task_detail'
    ),

path('ajax/get-sub-categories/', views.get_sub_categories_ajax, name='get_sub_categories_ajax'),

    path(
        'start-task/<int:task_id>/',
        views.start_task,
        name='start_task'
    ),

    path(
        'end-task/<int:task_id>/',
        views.end_task,
        name='end_task'
    ),

    path(
        'submit-complaint/<int:task_id>/',
        views.submit_complaint,
        name='submit_complaint'
    ),

    path(
        'add-subtask/<int:task_id>/',
        views.add_subtask,
        name='add_subtask'
    ),

    path(
        'toggle-subtask/<int:subtask_id>/',
        views.toggle_subtask,
        name='toggle_subtask'
    ),

path('reports/', views.reports, name='reports'),

path(
    'api/tasks/',
    views.api_tasks,
    name='api_tasks'
),
path('add-maintenance-item/', views.add_maintenance_item, name='add_maintenance_item'),

path('tasks/completed/all/', views.all_completed_tasks, name='all_completed_tasks'),
path('tasks/pending/all/', views.all_pending_tasks, name='all_pending_tasks')
,path('tasks/overdue/all/', views.all_overdue_tasks, name='all_overdue_tasks')
,path('tasks/active/all/', views.all_active_tasks, name='all_active_tasks'),
path('attachments/<int:attachment_id>/delete/', views.delete_task_attachment, name='delete_task_attachment'),
path('tasks/update-budget-ajax/<int:task_id>/', views.update_budget_ajax, name='update_budget_ajax'),
path(
    'tasks/update-description-ajax/<int:task_id>/',
    views.update_description_ajax,
    name='update_description_ajax'
),
path('ajax/add-sub-category/', add_sub_category_ajax, name='add_sub_category'),
path('delete-task-item/<int:item_id>/', views.delete_task_item_ajax, name='delete_task_item_ajax'),
path('tasks/update-budget-ajax/<int:task_id>/', views.update_budget_ajax, name='update_budget_ajax'),
    path('tasks/update-start-date-ajax/<int:task_id>/', views.update_start_date_ajax, name='update_start_date_ajax'),
    path('tasks/update_location_ajax/<int:task_id>/', views.update_location_ajax, name='update_location_ajax'),

    path('tasks/update-completed-date-ajax/<int:task_id>/', views.update_completed_date_ajax,
         name='update_completed_date_ajax'),
path('process-audio/', views.process_audio_file, name='process_audio_file'),
path('task/<int:task_id>/update_technicians/', views.update_technicians_ajax, name='update_technicians_ajax')
#path('data-audit/', views.data_audit_dashboard, name='data_audit_dashboard'),
 #   path('api/standardize-item/<int:task_id>/', views.api_get_standardized_items, name='api_get_standardized_items'),
]