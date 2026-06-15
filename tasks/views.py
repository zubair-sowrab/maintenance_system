from django.shortcuts import render, redirect
from .models import Task, Complaint, SubTask, Notification
from .forms import TaskForm
import json
import logging
from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import LoginView
from django.http import JsonResponse, Http404
from django.db import models
from .models import MaintenanceWorkItem
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.db.models.functions import TruncMonth
from django.db.models.functions import TruncMonth, Extract
from django.db.models import Sum, Count, Case, When, IntegerField, Avg, F, ExpressionWrapper, DurationField
from django.contrib.auth.models import User
from django.views.decorators.csrf import csrf_exempt
import os
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime, timedelta
from django.contrib import messages
from .models import TaskAttachment # Ensure you import this at the top
import uuid
from .models import Profile
from .forms import (
   TaskForm,
   ComplaintForm,
   SubTaskForm
)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
from .models import MaintenanceWorkItem

from django.http import JsonResponse
from .models import MaintenanceWorkItem

from .serializers import TaskSerializer
from django.db.models import Sum
from .models import Task, Complaint, SubTask, Notification, Profile, TaskItem




def home(request):


   return redirect('dashboard')


# Better pattern:
def get_authorized_task(user, task_id):
    if user.is_staff or user.is_superuser or user.groups.filter(name="Admin").exists():
        return get_object_or_404(Task, id=task_id)
    return get_object_or_404(Task, id=task_id, assigned_to=user)

def is_admin(user):
   return hasattr(user, "profile") and user.profile.role == "Admin"


@login_required
def task_list(request):
   user = request.user

   project_types = MaintenanceWorkItem.PROJECT_TYPE_CHOICES
   # 1. FIXED ROLE CHECKING
   # Try every possible way to find the user's role string.
   user_role = getattr(user, 'role', None)
   if not user_role and hasattr(user, 'profile'):
       user_role = getattr(user.profile, 'role', None)


   # If the user is a Superuser, or has an explicit Admin/Supervisor role,
   # OR if they belong to a Django Group named Admin/Supervisor:
   if user.is_superuser or \
           user.is_staff or \
           user_role in ['Admin'] or \
           user.groups.filter(name__in=['Admin']).exists():


       # Admins and Supervisors see ALL tasks (This keeps the list full so date filtering works!)
       tasks = Task.objects.all()


   else:
       # Technicians see only tasks explicitly assigned to them
       tasks = Task.objects.filter(assigned_to=user)


   check_and_update_overdue_tasks(tasks)
   # FILTERS FROM URL
   status = request.GET.get('status')
   project_type = request.GET.get('project_type')
   completed_at = request.GET.get('completed_at')
   job_id = request.GET.get('job_id')


   if job_id:
       tasks = tasks.filter(job_id__icontains=job_id)


   if completed_at:
       selected_date = datetime.strptime(completed_at, '%Y-%m-%d')


       next_day = selected_date + timedelta(days=1)


       tasks = tasks.filter(
           completed_at__gte=selected_date,
           completed_at__lt=next_day
       )


   if status:
       tasks = tasks.filter(status=status)


   if project_type:
       tasks = tasks.filter(project_type=project_type)

   pending_tasks = tasks.filter(Q(status='Pending') | Q(status='Pending(قيد الانتظار)'))
   active_tasks = tasks.filter(Q(status='In Progress') | Q(status='قيد التنفيذ'))
   completed_tasks = tasks.filter(Q(status='Completed') | Q(status='مكتمل'))
   overdue_tasks = tasks.filter(status='Overdue')


   context = {
       'project_types': project_types,
       'pending_tasks': pending_tasks,
       'active_tasks': active_tasks,
       'completed_tasks': completed_tasks,
       'overdue_tasks': overdue_tasks,
       'tasks': tasks,
   }


   return render(request, 'tasks/task_list.html', context)


@login_required
def create_task(request):
    user = request.user
    is_admin = user.is_superuser or user.is_staff or getattr(user, "role", None) == "Admin" or user.groups.filter(name="Admin").exists()

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES)
        if not is_admin:
            form.fields['priority'].required = False
        if form.is_valid():
            task = form.save(commit=False)
            if not is_admin:
                task.priority = 'Medium'  # Or whatever your default is
                task.assigned_to = user
        if not form.is_valid():
            print("Form Errors:", form.errors)  # Check your terminal for this!
        if form.is_valid():
            task = form.save(commit=False)

            # --- AUTO-TITLE GENERATION ---
            sub_categories = request.POST.getlist('sub_category[]')
            quantities = request.POST.getlist('quantity[]')

            # Get first item for the title
            first_sub = next((s for s in sub_categories if s and s.strip()), "General")
            first_qty = next((q for q, s in zip(quantities, sub_categories) if s and s.strip()), "0")

            # Get Location and Assigned To
            loc_parts = [str(task.building), str(task.unit)]
            location = "-".join([p for p in loc_parts if p]) or "No Location"
            assigned = task.assigned_to.username if task.assigned_to else "Unassigned"

            # Format: subcategory(quantity)-location-assigned_to
            task.title = f"{first_sub}({first_qty}) - {location} - {assigned}"[:200]
            # -----------------------------

            if not is_admin:
                task.assigned_to = user

            task.save()
            form.save_m2m()

            for sub, qty in zip(sub_categories, quantities):
                if sub:
                    TaskItem.objects.create(task=task, sub_category=sub, quantity=qty)

            messages.success(request, "Task saved successfully.")
            return redirect('dashboard')
    else:
        form = TaskForm()
        if not is_admin:
            form.fields['assigned_to'].queryset = User.objects.filter(id=user.id)
            form.fields['assigned_to'].initial = user

    return render(request, 'tasks/create_task.html', {'form': form})
# Update your view logic to this:
@login_required
def award_reward_points_ajax(request, task_id):
    # 1. Ensure method is POST
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method.'}, status=405)

    # 2. Permissions check (Reuse your existing logic)
    task = get_object_or_404(Task, id=task_id)
    is_admin = request.user.is_superuser or (hasattr(request.user, 'profile') and request.user.profile.role == 'Admin')
    if not is_admin:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized.'}, status=403)

    # 3. Process Input (Supports standard form POST data)
    # Using request.POST.get helps this work with both standard forms and FormData
    submitted_points = request.POST.get('points_awarded')

    try:
        if not submitted_points or submitted_points.strip() == '':
            task.reward_points_awarded = 0
            task.is_rewarded = False
        else:
            points = int(submitted_points)
            if points < 0:
                return JsonResponse({'status': 'error', 'message': 'Negative points.'}, status=400)

            task.reward_points_awarded = points
            task.is_rewarded = True  # Mark as rewarded

        task.save()

        # Return success with the updated state for the frontend
        return JsonResponse({
            'status': 'success',
            'message': 'Updated!',
            'points': task.reward_points_awarded,
            'is_rewarded': task.is_rewarded
        })

    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid number format.'}, status=400)


@login_required
def start_task(request, task_id):


   task = get_object_or_404(
       Task,
       id=task_id,
   )


   if task.assigned_to != request.user:
       messages.error(request, "unauthorized-task-action")
       return redirect('task_list')


   task.status = 'In Progress'


   task.started_at = timezone.now()


   task.save()


   return redirect('task_list')


@login_required
def end_task(request, task_id):


   task = get_object_or_404(
       Task,
       id=task_id,
   )
   if task.assigned_to != request.user:
       messages.error(request, "unauthorized-task-action")
       return redirect('task_list')
   task.status = 'Completed'


   task.completed_at = timezone.now()


   task.save()


   return redirect('task_list')


@login_required
def dashboard(request):
   tasks = Task.objects.filter(assigned_to=request.user)
   user = request.user
   project_types = MaintenanceWorkItem.PROJECT_TYPE_CHOICES

   # 1. Check user roles dynamically
   user_role = getattr(user, 'role', None)
   if not user_role and hasattr(user, 'profile'):
       user_role = getattr(user.profile, 'role', None)


   # Admins see all tasks, Technicians/Supervisors see only their assigned tasks
   if user.is_superuser or \
           user.is_staff or \
           user_role in ["Admin"] or \
           user.groups.filter(name__in=["Admin"]).exists():
       tasks = Task.objects.all()
   else:
       tasks = Task.objects.filter(assigned_to=user)


   check_and_update_overdue_tasks(tasks)


   status = request.GET.get('status')
   project_type = request.GET.get('project_type')
   completed_at = request.GET.get('completed_at')


   if status:
       tasks = tasks.filter(status=status)


   if project_type:
       tasks = tasks.filter(project_type=project_type)


   if completed_at:
       selected_date = datetime.strptime(completed_at, '%Y-%m-%d')


       next_day = selected_date + timedelta(days=1)


       tasks = tasks.filter(
           completed_at__gte=selected_date,
           completed_at__lt=next_day
       )


   pending_tasks = tasks.filter(status='Pending(قيد الانتظار)')
   active_tasks = tasks.filter(status='In Progress')
   completed_tasks = tasks.filter(status='Completed')
   overdue_tasks = tasks.filter(status='Overdue')


   context = {
       'project_types': project_types,
       'pending_tasks': pending_tasks,
       'active_tasks': active_tasks,
       'completed_tasks': completed_tasks,
       'overdue_tasks': overdue_tasks,
   }


   return render(request, 'tasks/task_list.html', context)


def get_authorized_task(user, task_id):
    """Centralized authorization check for Task access."""
    # Define admin check logic in one place
    is_admin = (
            user.is_superuser or
            user.is_staff or
            (hasattr(user, 'profile') and user.profile.role == "Admin") or
            user.groups.filter(name="Admin").exists()
    )

    if is_admin:
        return get_object_or_404(Task, id=task_id)

    # Non-admins can only access tasks assigned to them
    return get_object_or_404(Task, id=task_id, assigned_to=user)



@login_required
def task_detail(request, task_id):
    # Use the helper to automatically handle the authorization

    try:
        task = get_authorized_task(request.user, task_id)
    except PermissionDenied:
        messages.error(request, "You do not have permission to view this task.")
        return redirect('task_list')
    except Exception:
        # If it's a 404, it means the ID simply doesn't exist
        raise Http404("Task has not been assigned to you.")

    task = get_authorized_task(request.user, task_id)
    complaints = Complaint.objects.filter(task=task)
    subtasks = SubTask.objects.filter(task=task)
    task_items = task.items.all()
    attachments = task.attachments.all().order_by('-created_at')

    context = {
        'task': task,
        'complaints': complaints,
        'subtasks': subtasks,
        'task_items': task_items,
        'attachments': attachments,
        'complaint_form': ComplaintForm(),
        'subtask_form': SubTaskForm(),
    }
    return render(request, 'tasks/task_detail.html', context)






@login_required
def submit_complaint(request, task_id):
   if request.user.profile.role == 'Technician':


       task = get_object_or_404(
           Task,
           id=task_id,
           assigned_to=request.user
       )


   else:


       task = get_object_or_404(
           Task,
           id=task_id
       )


   if request.method == 'POST':


       form = ComplaintForm(
           request.POST,
           request.FILES
       )


       if form.is_valid():


           complaint = form.save(commit=False)


           complaint.task = task


           complaint.technician = request.user


           complaint.save()


   return redirect(
       'task_detail',
       task_id=task.id
   )


@login_required
def add_subtask(request, task_id):
   if request.user.profile.role == 'Technician':


       task = get_object_or_404(
           Task,
           id=task_id,
           assigned_to=request.user
       )


   else:


       task = get_object_or_404(
           Task,
           id=task_id
       )


   if request.method == 'POST':


       form = SubTaskForm(request.POST)


       if form.is_valid():


           subtask = form.save(commit=False)


           subtask.task = task


           subtask.save()


   return redirect(
       'task_detail',
       task_id=task.id
   )


@login_required
def toggle_subtask(request, subtask_id):
   if request.user.profile.role == 'Technician':


       subtask = get_object_or_404(
           Task,
           id=subtask_id,
           assigned_to=request.user
       )


   else:


       subtask = get_object_or_404(
           Task,
           id=subtask_id
       )


   subtask.completed = not subtask.completed
   subtask.save()


   return redirect(
       'task_detail',
       task_id=subtask.task.id
   )


@login_required
def submit_complaint(request, task_id):


   task = get_object_or_404(
       Task,
       id=task_id
   )


   if request.method == 'POST':


       form = ComplaintForm(
           request.POST,
           request.FILES
       )


       if form.is_valid():


           complaint = form.save(commit=False)


           complaint.task = task


           complaint.technician = request.user


           complaint.save()


   return redirect(
       'task_detail',
       task_id=task.id
   )




@login_required
def add_subtask(request, task_id):


   task = get_object_or_404(
       Task,
       id=task_id
   )


   if request.method == 'POST':


       form = SubTaskForm(request.POST)


       if form.is_valid():


           subtask = form.save(commit=False)


           subtask.task = task


           subtask.save()


   return redirect(
       'task_detail',
       task_id=task.id
   )




@login_required
def toggle_subtask(request, subtask_id):


   subtask = get_object_or_404(
       SubTask,
       id=subtask_id
   )


   subtask.completed = not subtask.completed


   subtask.save()


   return redirect(
       'task_detail',
       task_id=subtask.task.id
   )









@login_required
def reports(request):
   # 1. Capture Filters
   date_from = request.GET.get('date_from', '')
   date_to = request.GET.get('date_to', '')
   project_type = request.GET.get('project_type', '')
   selected_tech_id = request.GET.get('tech_id', '')


   base_tasks = Task.objects.all()


   # Get staff list safely
   all_technicians = User.objects.filter(groups__name='Technician') | User.objects.filter(profile__role='Technician') | User.objects.filter(groups__name='Supervisor') | User.objects.filter(profile__role='Supervisor')
   if not all_technicians.exists():
       all_technicians = User.objects.annotate(t_count=Count('assigned_tasks')).filter(t_count__gt=0)


   # Apply standard page filters
   if date_from:
       base_tasks = base_tasks.filter(created_at__date__gte=date_from)
   if date_to:
       base_tasks = base_tasks.filter(created_at__date__lte=date_to)
   if project_type:
       base_tasks = base_tasks.filter(project_type=project_type)


   # 2. Simple Status Counters
   total_tasks = base_tasks.count()
   completed = base_tasks.filter(status='Completed').count()
   active = base_tasks.filter(status__in=['In Progress', 'Active']).count()
   pending = base_tasks.filter(status__in=['Pending', 'Pending(قيد الانتظار)']).count()
   overdue = base_tasks.filter(status='Overdue').count()

   # 3. Cost Calculations (AED)
   def get_cost(work_type):
       res = base_tasks.filter(project_type=work_type).aggregate(total=Sum('budget'))
       try:
           return float(res['total']) if res['total'] else 0.0
       except:
           return 0.0


   cost_data = {
       'Paint': get_cost('Paint'), 'Electric': get_cost('Electric'),
       'Plumbing': get_cost('Plumbing'), 'Cleaning': get_cost('Cleaning'),
       'AC': get_cost('AC'), 'Carpenter': get_cost('Carpenter'),
       'Mason': get_cost('Mason') or get_cost('Mason(بناء)'),
       'Ceiling': get_cost('Ceiling') or get_cost('Ceiling(سقف)'),
   }
   total_expenses = sum(cost_data.values())


   # 4. Monthly History Logs
   monthly_trends = (
       base_tasks.filter(completed_at__isnull=False)
       .annotate(month=TruncMonth('completed_at'))
       .values('month')
       .annotate(count=Count('id'))
       .order_by('month')
   )
   months_labels = [trend['month'].strftime('%b %Y') for trend in monthly_trends]
   months_data = [trend['count'] for trend in monthly_trends]


   # 5. Team Output Chart Breakdown
   techs_summary = User.objects.annotate(
       assigned_count=Count(
           Case(When(assigned_tasks__id__in=base_tasks.values('id'), then=1), output_field=IntegerField())),
       completed_count=Count(
           Case(When(assigned_tasks__id__in=base_tasks.values('id'), assigned_tasks__status='Completed', then=1),
                output_field=IntegerField()))
   ).filter(assigned_count__gt=0).order_by('-completed_count')


   tech_labels = [t.username for t in techs_summary]
   tech_assigned = [t.assigned_count for t in techs_summary]
   tech_completed = [t.completed_count for t in techs_summary]


   # 6. Simplified Individual Worker Overview
   tech_stats = None
   if selected_tech_id:
       try:
           target_tech = User.objects.get(id=selected_tech_id)
           tech_jobs = base_tasks.filter(assigned_to=target_tech)


           t_total = tech_jobs.count()
           t_completed = tech_jobs.filter(status='Completed').count()


           financials = tech_jobs.aggregate(total_cost=Sum('budget'), avg_cost=Avg('budget'))
           t_total_cost = financials['total_cost'] or 0.0
           t_avg_cost = financials['avg_cost'] or 0.0


           timed_jobs = tech_jobs.filter(status='Completed', completed_at__isnull=False, created_at__isnull=False)
           avg_hours_logged = 0.0
           if timed_jobs.exists():
               duration_query = timed_jobs.annotate(
                   duration=ExpressionWrapper(F('completed_at') - F('created_at'), output_field=DurationField())
               ).aggregate(avg_time=Avg('duration'))
               avg_time = duration_query['avg_time']

               if avg_time:
                   total_minutes = int(avg_time.total_seconds() // 60)

                   hours = total_minutes // 60
                   minutes = total_minutes % 60

                   if hours > 0 and minutes > 0:
                       avg_hours_logged = f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
                   elif hours > 0:
                       avg_hours_logged = f"{hours} hour{'s' if hours != 1 else ''}"
                   else:
                       avg_hours_logged = f"{minutes} minute{'s' if minutes != 1 else ''}"

           tech_stats = {
               'username': target_tech.username,
               'total_tasks': t_total,
               'completed': t_completed,
               'total_cost': float(t_total_cost),
               'avg_cost': float(t_avg_cost),
               #'avg_hours': round(avg_hours_logged, 1),
               'avg_hours': avg_hours_logged,
               'success_rate': round((t_completed / t_total * 100), 0) if t_total > 0 else 0
           }
       except User.DoesNotExist:
           pass


   context = {
       'total_tasks': total_tasks, 'completed': completed, 'active': active,
       'pending': pending, 'overdue': overdue, 'total_expenses': total_expenses,
       'all_technicians': all_technicians, 'selected_tech_id': selected_tech_id,
       'tech_stats': tech_stats,
       'cost_keys_json': json.dumps(list(cost_data.keys())),
       'cost_values_json': json.dumps(list(cost_data.values())),
       'months_labels_json': json.dumps(months_labels),
       'months_data_json': json.dumps(months_data),
       'tech_labels_json': json.dumps(tech_labels),
       'tech_assigned_json': json.dumps(tech_assigned),
       'tech_completed_json': json.dumps(tech_completed),
   }
   return render(request, 'tasks/reports.html', context)




@api_view(['GET'])
def api_tasks(request):


   tasks = Task.objects.all()


   serializer = TaskSerializer(
       tasks,
       many=True
   )


   return Response(serializer.data)








from django.db.models import Q


def all_completed_tasks(request):
   user = request.user


   # 1. Gather Role Configuration Strings
   user_role = getattr(user, "role", None)
   if not user_role and hasattr(user, "profile"):
       user_role = getattr(user.profile, "role", None)


   # 2. Enforce Role Visibility Restrictions
   if (
           user.is_superuser
           or user.is_staff
           or user_role in ["Admin"]
           or user.groups.filter(name__in=["Admin"]).exists()
   ):
       base_tasks = Task.objects.filter(status="Completed")
   else:
       base_tasks = Task.objects.filter(status="Completed", assigned_to=user)


   # 3. Apply Filters from URL Query Parameters
   job_id = request.GET.get("job_id")
   user_query = request.GET.get("user")
   project_type = request.GET.get("project_type")
   date_from = request.GET.get("date_from")
   date_to = request.GET.get("date_to")


   if job_id and job_id.strip():
       base_tasks = base_tasks.filter(job_id__icontains=job_id.strip())


   if user_query and user_query.strip():
       base_tasks = base_tasks.filter(
           assigned_to__username__icontains=user_query.strip()
       )


   if project_type and project_type.strip():
       base_tasks = base_tasks.filter(project_type=project_type)


   # Safe Date parsing to handle timezone shifts smoothly
   if date_from and date_from.strip():
       base_tasks = base_tasks.filter(completed_at__date__gte=date_from)


   if date_to and date_to.strip():
       try:
           # Parse 'YYYY-MM-DD' and add 1 full day to make the filter inclusive
           parsed_date_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").date()
           next_day = parsed_date_to + timedelta(days=1)
           # Find everything strictly before the next day (covers up to 23:59:59 of selected date)
           base_tasks = base_tasks.filter(completed_at__lt=next_day)
       except ValueError:
           # Fallback handling if format string parsing encounters exceptions
           base_tasks = base_tasks.filter(completed_at__date__lte=date_to)


   return render(
       request,
       "tasks/all_tasks.html",
       {"tasks": base_tasks, "title": "Completed Tasks (المهام المكتملة)"},
   )


# 1. New Pending Tasks View
def all_pending_tasks(request):
   # Base query for tasks that are currently pending
   tasks = Task.objects.filter(status='Pending(قيد الانتظار)')


   # Gather URL Query Parameters
   job_id = request.GET.get('job_id')
   user = request.GET.get('user')
   project_type = request.GET.get('project_type')
   date_from = request.GET.get('date_from')
   date_to = request.GET.get('date_to')


   if job_id and job_id.strip():
       tasks = tasks.filter(job_id__icontains=job_id.strip())


   if user and user.strip():
       tasks = tasks.filter(assigned_to__username__icontains=user.strip())


   if project_type and project_type.strip():
       tasks = tasks.filter(project_type=project_type)


   # FIX: Filter Pending tasks by creation date (created_at) instead of completion date
   if date_from and date_from.strip():
       tasks = tasks.filter(created_at__date__gte=date_from)


   if date_to and date_to.strip():
       try:
           # Parse date string and add 1 day to make the upper boundary fully inclusive
           parsed_date_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").date()
           next_day = parsed_date_to + timedelta(days=1)
           # Captures everything up to 23:59:59 on the selected date safely
           tasks = tasks.filter(created_at__lt=next_day)
       except ValueError:
           # Fallback block if parsing strings fails
           tasks = tasks.filter(created_at__date__lte=date_to)


   return render(
       request,
       'tasks/all_tasks.html',
       {
           'tasks': tasks,
           'title': 'Pending Tasks'
       }
   )


# 2. New Active Tasks View
def all_active_tasks(request):


   tasks = Task.objects.filter(status='In Progress')


   job_id = request.GET.get('job_id')
   user = request.GET.get('user')
   project_type = request.GET.get('project_type')
   date_from = request.GET.get('date_from')
   date_to = request.GET.get('date_to')


   if job_id:
       tasks = tasks.filter(job_id__icontains=job_id)


   if user:
       tasks = tasks.filter(
           assigned_to__username__icontains=user
       )


   if project_type:
       tasks = tasks.filter(project_type=project_type)


   if date_from:
       tasks = tasks.filter(
           completed_at__date__gte=date_from
       )


   if date_to:
       tasks = tasks.filter(
           completed_at__date__lte=date_to
       )


   return render(
       request,
       'tasks/all_tasks.html',
       {
           'tasks': tasks,
           'title': 'Active Tasks'
       }
   )




# 3. New Overdue Tasks View
def all_overdue_tasks(request):


   tasks = Task.objects.filter(status='Overdue')


   job_id = request.GET.get('job_id')
   user = request.GET.get('user')
   project_type = request.GET.get('project_type')
   date_from = request.GET.get('date_from')
   date_to = request.GET.get('date_to')


   if job_id:
       tasks = tasks.filter(job_id__icontains=job_id)


   if user:
       tasks = tasks.filter(
           assigned_to__username__icontains=user
       )


   if project_type:
       tasks = tasks.filter(project_type=project_type)


   if date_from:
       tasks = tasks.filter(
           completed_at__date__gte=date_from
       )


   if date_to:
       tasks = tasks.filter(
           completed_at__date__lte=date_to
       )


   return render(
       request,
       'tasks/all_tasks.html',
       {
           'tasks': tasks,
           'title': 'Overdue Tasks'
       }
   )




def check_and_update_overdue_tasks(queryset):
   """
   Scans a queryset of tasks and bulk-updates records that have passed
   their deadlines but are not yet marked as 'Completed' or 'Overdue'.
   """
   now = timezone.now()
   expired_tasks = queryset.filter(
       deadline__lt=now
   ).exclude(
       status__in=['Completed', 'Overdue']
   )


   if expired_tasks.exists():
       expired_tasks.update(status='Overdue', is_overdue=True)






@login_required
def add_task_item_detail(request, task_id):
   if request.method == 'POST':
       task = get_object_or_404(Task, id=task_id)
       sub_cat = request.POST.get('sub_category')
       qty = request.POST.get('quantity')


       if sub_cat and sub_cat.strip():
           TaskItem.objects.create(
               task=task,
               sub_category=sub_cat.strip(),
               quantity=qty.strip() if qty else "-"
           )
           messages.success(request, "New item appended to breakdown successfully!")


   return redirect('task_detail', task_id=task_id)




@login_required
def upload_task_attachment(request, task_id):
   if request.user.profile.role == 'Technician':
       task = get_object_or_404(Task, id=task_id, assigned_to=request.user)
   else:
       task = get_object_or_404(Task, id=task_id)


   if request.method == 'POST':
       print("\n=== 🛠️ DEBUGGING ATTACHMENT UPLOAD ===")
       print(f"Request POST keys: {list(request.POST.keys())}")
       print(f"Request FILES keys: {list(request.FILES.keys())}")


       uploaded_image = request.FILES.get('task_image')
       print(f"Fetched 'task_image': {uploaded_image}")


       if uploaded_image:
           print(f"File Name: {uploaded_image.name}")
           print(f"File Size: {uploaded_image.size} bytes")


           allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
           ext = os.path.splitext(uploaded_image.name)[1].lower()
           print(f"Detected Extension: '{ext}'")


           if ext in allowed_extensions:
               attachment = TaskAttachment.objects.create(
                   task=task,
                   uploaded_by=request.user,
                   image=uploaded_image
               )
               print(f"✅ SUCCESS: Created database attachment record with ID {attachment.id}")
               messages.success(request, "Picture uploaded successfully!")
           else:
               print(f"❌ ERROR: Extension '{ext}' is not in allowed list {allowed_extensions}")
               messages.error(request, f"Unsupported file format: {ext}")
       else:
           print("❌ ERROR: 'task_image' was completely empty in request.FILES!")
           messages.error(request, "No image file was received by the server.")


       print("=======================================\n")


   return redirect('task_detail', task_id=task.id)




@login_required
def delete_task_attachment(request, attachment_id):
   # Fetch attachment checking authorization constraints
   attachment = get_object_or_404(TaskAttachment, id=attachment_id)
   task_id = attachment.task.id


   # Restrict deletion capability rules: Only Admin or the specific User who uploaded it
   if request.user.is_superuser or request.user.profile.role == 'Admin' or attachment.uploaded_by == request.user:
       # Delete file from local media storage disk safely
       if attachment.image and os.path.exists(attachment.image.path):
           os.remove(attachment.image.path)


       attachment.delete()
       messages.success(request, "Image deleted successfully! (تم حذف الصورة بنجاح)")
   else:
       messages.error(request, "Unauthorized action. You cannot delete this picture.")


   return redirect('task_detail', task_id=task_id)



@csrf_exempt
def update_budget_ajax(request, task_id):
   # Ensure request method parameter is a POST structure
   if request.method != 'POST':
       return JsonResponse({'status': 'error', 'message': 'Invalid request action method'}, status=400)


   user = request.user
   user_role = getattr(user, "role", None)
   if not user_role and hasattr(user, "profile"):
       user_role = getattr(user.profile, "role", None)


   # STRICT ACCESS CHECK: Only Superusers or users assigned an 'Admin' status role can write updates
   is_admin = (
           user.is_superuser
           or user.is_staff
           or user_role == "Admin"
           or user.groups.filter(name="Admin").exists()
   )


   if not is_admin:
       return JsonResponse({'status': 'error', 'message': 'Access Denied. Administrative check failed.'}, status=403)


   try:
       data = json.loads(request.body)
       new_budget = data.get('budget', '').strip()


       task = get_object_or_404(Task, id=task_id)
       task.budget = new_budget  # Saved into task database instance
       task.save()


       return JsonResponse({'status': 'success', 'message': 'Service charge budget updated successfully'})
   except Exception as e:
       return JsonResponse({'status': 'error', 'message': str(e)}, status=500)




logger = logging.getLogger(__name__)





def get_sub_categories_ajax(request):
    raw_project_type = request.GET.get('project_type', '').strip()
    project_type = raw_project_type.split('(')[0].strip()

    # Fetch directly from the database only
    items = list(MaintenanceWorkItem.objects.filter(project_type=project_type)
                 .values_list('name_english', flat=True))

    return JsonResponse({'items': sorted(items)})




@csrf_exempt
def add_sub_category_ajax(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        # No need to split/parse, just take the value directly from the select box
        p_type = data.get('project_type')
        eng = data.get('name_english')
        arb = data.get('name_arabic')

        item, created = MaintenanceWorkItem.objects.get_or_create(
            project_type=p_type,
            name_english=eng,
            name_arabic=arb
        )
        if created:
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Already exists'})
    return JsonResponse({'success': False}, status=400)

class CustomLoginView(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_redirect_url(self):
        # This ensures it uses your LOGIN_REDIRECT_URL setting
        return super().get_redirect_url()