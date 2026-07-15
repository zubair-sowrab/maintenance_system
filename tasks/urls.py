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
path('task/<int:task_id>/update_technicians/', views.update_technicians_ajax, name='update_technicians_ajax'),
path('tasks/bulk-print-invoices/', views.bulk_print_invoices, name='bulk_print_invoices'),
path('hidden-audit-dashboard/', views.ai_audit_dashboard, name='ai_audit_dashboard'),
path('task/<int:task_id>/calculate-ai-charge/', views.calculate_ai_charge_ajax, name='calculate_ai_charge_ajax'),
# Overtime Features (Admin Only)
#path('data-audit/', views.data_audit_dashboard, name='data_audit_dashboard'),
 #   path('api/standardize-item/<int:task_id>/', views.api_get_standardized_items, name='api_get_standardized_items'),

# Overtime System (Admin Only)
path('overtime/', views.all_overtime_tasks, name='all_overtime_tasks'),
path('overtime/reports/', views.overtime_reports, name='overtime_reports'),
path('overtime/ajax/update/<int:task_id>/', views.update_overtime_ajax, name='update_overtime_ajax'),
path('overtime/ajax/get-tasks/', views.get_assignable_overtime_tasks_ajax, name='get_assignable_overtime_tasks_ajax'),
# Add these beneath your existing AJAX paths:
path('tasks/update-status-ajax/<int:task_id>/', views.update_status_ajax, name='update_status_ajax'),
path('tasks/delete-task-ajax/<int:task_id>/', views.delete_task_ajax, name='delete_task_ajax'),
# Technician Overtime Management
path('overtime/technicians/', views.overtime_technicians, name='overtime_technicians'),
path('overtime/technicians/update/<int:tech_id>/', views.update_tech_overtime_ajax, name='update_tech_overtime_ajax'),
path('overtime/technicians/details/<int:tech_id>/', views.get_tech_overtime_details_ajax, name='get_tech_overtime_details_ajax'),
# Material Approvals System
    path('materials/approvals/', views.material_approvals_view, name='material_approvals'),
    path('materials/task/<int:task_id>/save/', views.save_material_request_ajax, name='save_material_request_ajax'),
    path('materials/task/<int:task_id>/get/', views.get_material_request_ajax, name='get_material_request_ajax'),
    path('materials/task/<int:task_id>/disapprove/', views.disapprove_material_request_ajax, name='disapprove_material_request_ajax'),
path('materials/approved-list/', views.approved_materials_list, name='approved_materials_list'),
path('materials/print-voucher/<int:req_id>/', views.print_material_approval, name='print_material_approval'),
]