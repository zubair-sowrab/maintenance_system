from django.shortcuts import render, redirect
from .models import Task, Complaint, SubTask, Notification
from .forms import TaskForm
import json
import logging
from django.contrib.auth.views import LoginView
from django.views.decorators.http import require_POST
from django.http import JsonResponse
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
import pytz # Import pytz
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
from deep_translator import GoogleTranslator
from .notifications import send_telegram_msg

def translate_to_english(text):
   if not text or not text.strip():
       return text
   try:
       # Detects language automatically and translates to English
       return GoogleTranslator(source='auto', target='en').translate(text)
   except Exception as e:
       print(f"Translation error: {e}")
       return text # Return original if translation fails








def home(request):




  return redirect('dashboard')








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
      # UPDATED: Admin/Supervisor logic
      if user.is_superuser or user.is_staff or user_role in ['Admin'] or \
              user.groups.filter(name__in=['Admin']).exists():
          tasks = Task.objects.all()
      else:
          # UPDATED: Many-to-Many filter
          # Django automatically checks if 'user' is in the 'assigned_technicians' set
          tasks = Task.objects.filter(assigned_technicians=user)


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

  pending_tasks = tasks.filter(Q(status='Pending') | Q(status='Pending(قيد الانتظار)')).order_by('-created_at')
  active_tasks = tasks.filter(Q(status='In Progress') | Q(status='قيد التنفيذ')).order_by('-created_at')
  completed_tasks = tasks.filter(Q(status='Completed') | Q(status='مكتمل')).order_by('-completed_at')
  overdue_tasks = tasks.filter(status='Overdue').order_by(
      '-deadline')  # Assuming you want the closest deadline or oldest overdue




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
   tech_ids = []
   user_role = getattr(user.profile, 'role', None)
   # Simplified role check
   is_admin = user.is_superuser or user.groups.filter(name="Admin").exists()


   if request.method == 'POST':
       # 1. Create a mutable copy of the POST data
       post_data = request.POST.copy()



       # 2. Check role and set priority if it's missing or if it's a technician
       # Assuming you determine role via user.profile.role
       user_role = getattr(user.profile, 'role', None)


       if user_role == 'Technician' or not post_data.get('priority'):
           post_data['priority'] = 'Medium'
       form = TaskForm(post_data, request.FILES)


       if form.is_valid():
           task = form.save(commit=False)

           if task.status == 'In Progress' and not task.started_at:
               task.started_at = timezone.now()

           # Set the dates directly on the object
           now = timezone.now()
           task.start_date = now
           task.deadline = now + timedelta(days=60)


           translator = GoogleTranslator(source='auto', target='en')




           # Translate Description if it exists
           if task.description:
               try:
                   task.description = translator.translate(task.description)
               except Exception as e:
                   print(f"Translation error: {e}")








           # 1. AUTO-TITLE GENERATION (Updated to use first tech instead of old assigned_to)
           project_type = request.GET.get('project_type')
           # 1. EXTRACT ARRAYS
           sub_categories = request.POST.getlist('sub_category[]')
           quantities = request.POST.getlist('quantity[]')

           translated_subs = []
           translated_qtys = []

           # 2. SAFELY LOOP AND TRANSLATE BOTH ARRAYS
           for i, sub in enumerate(sub_categories):
               # Safely get the corresponding quantity, default to "0" if missing
               raw_qty = quantities[i] if i < len(quantities) else "0"

               # --- Translate Sub-Category ---
               if sub and sub.strip():
                   try:
                       translated_subs.append(translator.translate(sub.strip()))
                   except Exception:
                       translated_subs.append(sub.strip())  # Fallback to original if translation fails
               else:
                   translated_subs.append("General")

               # --- Translate Quantity / Details ---
               clean_qty = str(raw_qty).strip()
               if clean_qty and not clean_qty.isdigit():
                   # Only translate if it contains text (e.g., "مترين" or "2 doors")
                   try:
                       translated_qtys.append(translator.translate(clean_qty))
                   except Exception:
                       translated_qtys.append(clean_qty)
               else:
                   # If it's just a number like "2" or empty, skip the translator to prevent API errors
                   translated_qtys.append(clean_qty if clean_qty else "0")




           first_sub = next((s for s in sub_categories if s and s.strip()), "General")
           first_qty = next((q for q, s in zip(quantities, sub_categories) if s and s.strip()), "0")




           loc_parts = [str(task.building), str(task.unit)]
           location = "-".join([p for p in loc_parts if p]) or "No Location"


           # Use the first assigned technician's username for the title
           tech_ids = request.POST.getlist('technicians')
           first_tech = User.objects.filter(id__in=tech_ids).first()
           #assigned_name = first_tech.username if first_tech else "Unassigned"


           #task.title = f"{location}-{first_sub}({first_qty})"[:200]






           # To something that handles the case explicitly:
           if not tech_ids:
               task.title = f"{location}-{first_sub}({first_qty}) - [UNASSIGNED]"[:200]
           else:
               task.title = f"{location}-{first_sub}({first_qty})"[:200]


           first_sub = translated_subs[0] if translated_subs else "General"
           tech_ids = request.POST.getlist('technicians')


           # If the user is a technician and they didn't select anyone,
           # auto-assign to self (optional safety)
           if not tech_ids and hasattr(user, 'profile') and user.profile.role == 'Technician':
               tech_ids = [user.id]
           # Save task and M2M
           task.save()
           task.assigned_technicians.set(tech_ids)  # Correctly save ManyToMany

           for tech in task.assigned_technicians.all():
               if tech.profile.telegram_chat_id:
                   msg = f"New Task: {task.title}\nBuilding: {task.building}\nCheck your dashboard."
                   send_telegram_msg(tech.profile.telegram_chat_id, msg)


           # Save items
           for sub, qty in zip(translated_subs, translated_qtys):
               if sub:
                   TaskItem.objects.create(task=task, sub_category=sub, quantity=qty)


           messages.success(request, "Task saved successfully.")
           return redirect('dashboard')


       else:
           print("Form Errors:", form.errors)
   else:
       dubai_tz = pytz.timezone('Asia/Dubai')
       now_dubai = timezone.now().astimezone(dubai_tz)

       # 2. Add 60 days to the UAE time
       deadline_dubai = now_dubai + timedelta(days=60)

       # 3. Format it for the HTML input
       initial_data = {
           'start_date': now_dubai.strftime('%Y-%m-%dT%H:%M'),
           'deadline': deadline_dubai.strftime('%Y-%m-%dT%H:%M')
       }
       form = TaskForm(initial=initial_data)


   # Pass the technicians list to the template for the dropdown
   all_maintenance_items = MaintenanceWorkItem.objects.all()
   technicians = User.objects.filter(profile__role='Technician')
   if request.method == 'POST':
       # Create a mutable copy of the POST data
       post_data = request.POST.copy()


       # If 'priority' is missing or empty, set it to default
       if not post_data.get('priority'):
           post_data['priority'] = 'Medium'






       if form.is_valid():
           task = form.save(commit=False)



           task.save()
           task.assigned_technicians.set(tech_ids)
           # ... rest of code
       else:
           # THIS IS CRITICAL
           print("❌ FORM ERRORS:", form.errors)
           # If you are in development, return an error page or print to logs
   return render(request, 'tasks/create_task.html', {
       'form': form,
       'technicians': technicians,
       'project_types': MaintenanceWorkItem.PROJECT_TYPE_CHOICES,
       'all_maintenance_items': all_maintenance_items,
   })
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
   task = get_object_or_404(Task, id=task_id)





   task.status = 'In Progress'
   task.started_at = timezone.now()
   task.save()
   return redirect('dashboard')


@login_required
def end_task(request, task_id):
   task = get_object_or_404(Task, id=task_id)

   if request.method == 'POST':
       # Get the budget from the modal input
       final_budget = request.POST.get('final_budget')
       if final_budget:
           task.budget = final_budget

           # 2. Save Image if uploaded
           image = request.FILES.get('task_image')
           if image:
               # Assuming you have a TaskAttachment model like the one in your detail page
               TaskAttachment.objects.create(
                   task=task,
                   image=image,
                   uploaded_by=request.user
               )

   task.status = 'Completed'
   task.completed_at = timezone.now()
   task.save()
   return redirect('dashboard')
@login_required
def dashboard(request):
   user = request.user
   project_types = MaintenanceWorkItem.PROJECT_TYPE_CHOICES


   # 1. Check user roles dynamically
   user_role = getattr(user, 'role', None)
   if not user_role and hasattr(user, 'profile'):
       user_role = getattr(user.profile, 'role', None)


   # 2. Base QuerySet with prefetch_related
   # PREFETCH is critical here so the template can see the assigned technicians
   base_queryset = Task.objects.prefetch_related('assigned_technicians')


   # 3. Logic for Admin vs Technicians
   if user.is_superuser or \
           user.is_staff or \
           user_role in ["Admin"] or \
           user.groups.filter(name__in=["Admin"]).exists():
       tasks = base_queryset.all()
   else:
       # Filter tasks where the user is one of the assigned technicians
       tasks = base_queryset.filter(assigned_technicians=user)


   check_and_update_overdue_tasks(tasks)


   # 4. Filtering logic
   user_filter = request.GET.get('user')
   status = request.GET.get('status')
   project_type = request.GET.get('project_type')
   completed_at = request.GET.get('completed_at')


   if status:
       tasks = tasks.filter(status=status)
   if project_type:
       tasks = tasks.filter(project_type=project_type)
   if completed_at:
       try:
           selected_date = datetime.strptime(completed_at, '%Y-%m-%d')
           next_day = selected_date + timedelta(days=1)
           tasks = tasks.filter(completed_at__gte=selected_date, completed_at__lt=next_day)
       except ValueError:
           pass # Ignore invalid date formats


   if user_filter:
           # We filter the 'tasks' queryset to only include those
           # where an assigned technician's username matches the search
           tasks = tasks.filter(assigned_technicians__username__icontains=user_filter.strip()).distinct()
   # 5. Categorize tasks
   # Using 'distinct()' is good practice when filtering ManyToMany fields
   # to avoid duplicate task objects in the list
   # 5. Categorize tasks
   # We use order_by('-created_at') to ensure the newest ones appear first.
   # (Ensure 'created_at' exists in your Task model, otherwise use '-id')

   pending_tasks = tasks.filter(status='Pending(قيد الانتظار)').distinct().order_by('-created_at')
   active_tasks = tasks.filter(status='In Progress').distinct().order_by('-created_at')
   completed_tasks = tasks.filter(status='Completed').distinct().order_by('-completed_at')  # Newest completions first
   overdue_tasks = tasks.filter(status='Overdue').distinct().order_by('deadline')  # Closest to deadline first


   context = {
       'project_types': project_types,
       'pending_tasks': pending_tasks,
       'active_tasks': active_tasks,
       'completed_tasks': completed_tasks,
       'overdue_tasks': overdue_tasks,
       'tasks': tasks
   }


   return render(request, 'tasks/task_list.html', context)












@login_required
def task_detail(request, task_id):
   # 1. UPDATED: Visibility restriction for Technicians
   # We check if the current user is in the assigned_technicians ManyToMany set
   if request.user.profile.role == 'Technician':
       task = get_object_or_404(
           Task,
           id=task_id,
           assigned_technicians=request.user # Django handles the 'in' logic automatically
       )
   else:
       # Admins/Supervisors can see everything
       task = get_object_or_404(Task, id=task_id)


   # Rest of your logic remains the same
   complaints = Complaint.objects.filter(task=task)
   subtasks = SubTask.objects.filter(task=task)
   task_items = task.items.all()
   attachments = task.attachments.all().order_by('-created_at')


   complaint_form = ComplaintForm()
   subtask_form = SubTaskForm()


   context = {
       'task': task,
       'complaints': complaints,
       'subtasks': subtasks,
       'task_items': task_items,
       'attachments': attachments,
       'complaint_form': complaint_form,
       'subtask_form': subtask_form,
   }


   return render(request, 'tasks/task_detail.html', context)
















@login_required
def submit_complaint(request, task_id):
   # 1. UPDATED: Visibility restriction for Technicians
   # We check if the current user is in the assigned_technicians ManyToMany set
   if request.user.profile.role == 'Technician':
       task = get_object_or_404(
           Task,
           id=task_id,
           assigned_technicians=request.user # Many-to-Many query
       )
   else:
       # Admins/Supervisors can access any task
       task = get_object_or_404(Task, id=task_id)


   if request.method == 'POST':
       form = ComplaintForm(request.POST, request.FILES)
       if form.is_valid():
           complaint = form.save(commit=False)
           complaint.task = task
           # Assuming your Complaint model has a technician field
           try:
               complaint.message = GoogleTranslator(source='auto', target='en').translate(complaint.message)
           except:
               pass
           complaint.technician = request.user
           complaint.save()
           messages.success(request, "Complaint submitted.")
           return redirect('task_detail', task_id=task.id)


   return redirect('task_detail', task_id=task.id)




@login_required
def add_subtask(request, task_id):
   # 1. UPDATED: Visibility restriction using ManyToMany field
   if request.user.profile.role == 'Technician':
       task = get_object_or_404(
           Task,
           id=task_id,
           assigned_technicians=request.user  # Many-to-Many lookup
       )
   else:
       task = get_object_or_404(Task, id=task_id)


   if request.method == 'POST':
       form = SubTaskForm(request.POST)
       if form.is_valid():
           subtask = form.save(commit=False)
           subtask.task = task
           subtask.save()


   return redirect('task_detail', task_id=task.id)




@login_required
def toggle_subtask(request, subtask_id):
   # 2. UPDATED: Fetching the SubTask itself, then checking its parent Task
   subtask = get_object_or_404(SubTask, id=subtask_id)
   task = subtask.task


   # Check permissions on the parent task
   if request.user.profile.role == 'Technician':
       if not task.assigned_technicians.filter(id=request.user.id).exists():
           messages.error(request, "Unauthorized")
           return redirect('task_list')


   subtask.completed = not subtask.completed
   subtask.save()


   return redirect('task_detail', task_id=task.id)


















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


  techs_summary = User.objects.annotate(
      assigned_count=Count(
          Case(When(assigned_tasks__id__in=base_tasks.values('id'), then=1), output_field=IntegerField())
      ),
      completed_count=Count(
          Case(When(assigned_tasks__id__in=base_tasks.values('id'), assigned_tasks__status='Completed', then=1),
               output_field=IntegerField())
      )
  ).filter(assigned_count__gt=0).order_by('-completed_count')




  tech_labels = [t.username for t in techs_summary]
  tech_assigned = [t.assigned_count for t in techs_summary]
  tech_completed = [t.completed_count for t in techs_summary]




  # 6. Simplified Individual Worker Overview
  tech_stats = None
  # 6. Simplified Individual Worker Overview
  if selected_tech_id:
      try:
          target_tech = User.objects.get(id=selected_tech_id)
          # UPDATED: Use the ManyToMany field lookup
          tech_jobs = base_tasks.filter(assigned_technicians=target_tech)


          # ... rest of your logic remains the same ...




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
   # PREFETCH is added here so the template can display assigned technicians correctly
   base_queryset = Task.objects.filter(status="Completed").prefetch_related("assigned_technicians")


   if (
           user.is_superuser
           or user.is_staff
           or user_role in ["Admin"]
           or user.groups.filter(name__in=["Admin"]).exists()
   ):
       base_tasks = base_queryset
   else:
       # FIXED: Use ManyToMany filter
       base_tasks = base_queryset.filter(assigned_technicians=user)


   # 3. Apply Filters from URL Query Parameters
   job_id = request.GET.get("job_id")
   user_query = request.GET.get("user")
   project_type = request.GET.get("project_type")
   date_from = request.GET.get("date_from")
   date_to = request.GET.get("date_to")


   if job_id and job_id.strip():
       base_tasks = base_tasks.filter(job_id__icontains=job_id.strip())


   # FIXED: Filter by technician username in ManyToMany
   if user_query and user_query.strip():
       base_tasks = base_tasks.filter(
           assigned_technicians__username__icontains=user_query.strip()
       ).distinct()


   if project_type and project_type.strip():
       base_tasks = base_tasks.filter(project_type=project_type)


   if date_from and date_from.strip():
       base_tasks = base_tasks.filter(completed_at__date__gte=date_from)


   if date_to and date_to.strip():
       try:
           parsed_date_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").date()
           next_day = parsed_date_to + timedelta(days=1)
           base_tasks = base_tasks.filter(completed_at__lt=next_day)
       except ValueError:
           base_tasks = base_tasks.filter(completed_at__date__lte=date_to)


   return render(
       request,
       "tasks/all_tasks.html",
       {"tasks": base_tasks.distinct(), "title": "Completed Tasks (المهام المكتملة)"},
   )












# 1. New Pending Tasks View
def all_pending_tasks(request):
  # Base query for tasks that are currently pending
  # Added distinct() because filtering by ManyToMany can return duplicates
  tasks = Task.objects.filter(status='Pending(قيد الانتظار)').distinct()


  # Gather URL Query Parameters
  job_id = request.GET.get('job_id')
  user = request.GET.get('user')
  project_type = request.GET.get('project_type')
  date_from = request.GET.get('date_from')
  date_to = request.GET.get('date_to')


  if job_id and job_id.strip():
      tasks = tasks.filter(job_id__icontains=job_id.strip())


  # FIXED: Changed 'assigned_to' to 'assigned_technicians'
  if user and user.strip():
      tasks = tasks.filter(assigned_technicians__username__icontains=user.strip()).distinct()


  if project_type and project_type.strip():
      tasks = tasks.filter(project_type=project_type)


  # Filter Pending tasks by creation date
  if date_from and date_from.strip():
      tasks = tasks.filter(created_at__date__gte=date_from)


  if date_to and date_to.strip():
      try:
          parsed_date_to = datetime.strptime(date_to.strip(), "%Y-%m-%d").date()
          next_day = parsed_date_to + timedelta(days=1)
          tasks = tasks.filter(created_at__lt=next_day)
      except ValueError:
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
  tasks = Task.objects.filter(status='In Progress').distinct()


  job_id = request.GET.get('job_id')
  user = request.GET.get('user')
  project_type = request.GET.get('project_type')
  date_from = request.GET.get('date_from')
  date_to = request.GET.get('date_to')


  if job_id and job_id.strip():
      tasks = tasks.filter(job_id__icontains=job_id.strip())


  # FIXED: Changed 'assigned_to' to 'assigned_technicians'
  if user and user.strip():
      tasks = tasks.filter(assigned_technicians__username__icontains=user.strip()).distinct()


  if project_type and project_type.strip():
      tasks = tasks.filter(project_type=project_type)


  if date_from and date_from.strip():
      tasks = tasks.filter(started_at__date__gte=date_from)


  if date_to and date_to.strip():
      tasks = tasks.filter(started_at__date__lte=date_to)


  return render(request, 'tasks/all_tasks.html', {'tasks': tasks, 'title': 'Active Tasks'})




def all_overdue_tasks(request):
  tasks = Task.objects.filter(status='Overdue').distinct()


  job_id = request.GET.get('job_id')
  user = request.GET.get('user')
  project_type = request.GET.get('project_type')
  date_from = request.GET.get('date_from')
  date_to = request.GET.get('date_to')


  if job_id and job_id.strip():
      tasks = tasks.filter(job_id__icontains=job_id.strip())


  # FIXED: Changed 'assigned_to' to 'assigned_technicians'
  if user and user.strip():
      tasks = tasks.filter(assigned_technicians__username__icontains=user.strip()).distinct()


  if project_type and project_type.strip():
      tasks = tasks.filter(project_type=project_type)


  if date_from and date_from.strip():
      tasks = tasks.filter(created_at__date__gte=date_from)


  if date_to and date_to.strip():
      tasks = tasks.filter(created_at__date__lte=date_to)


  return render(request, 'tasks/all_tasks.html', {'tasks': tasks, 'title': 'Overdue Tasks'})








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
   # 1. Base query: get the task
   task = get_object_or_404(Task, id=task_id)


   # 2. Authorization check: If technician, ensure they are in the assigned_technicians list
   if request.user.profile.role == 'Technician':
       if not task.assigned_technicians.filter(id=request.user.id).exists():
           messages.error(request, "You are not authorized to upload to this task.")
           return redirect('task_detail', task_id=task.id)


   if request.method == 'POST':
       uploaded_image = request.FILES.get('task_image')


       if uploaded_image:
           allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
           ext = os.path.splitext(uploaded_image.name)[1].lower()


           if ext in allowed_extensions:
               attachment = TaskAttachment.objects.create(
                   task=task,
                   uploaded_by=request.user,
                   image=uploaded_image
               )
               messages.success(request, "Picture uploaded successfully!")
           else:
               messages.error(request, f"Unsupported file format: {ext}")
       else:
           messages.error(request, "No image file was received by the server.")


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


logger = logging.getLogger(__name__)


def update_budget_ajax(request, task_id):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

    try:
        data = json.loads(request.body)
        new_budget = data.get('budget', '').strip()

        task = get_object_or_404(Task, id=task_id)
        task.budget = new_budget
        task.save()

        return JsonResponse({'status': 'success', 'message': 'Budget updated successfully'})
    except Exception as e:
        logger.error(f"Error updating budget for task {task_id}: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)









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




# In your views.py or your AJAX endpoint for completing a task
def complete_overdue_task(request, task_id):
   task = get_object_or_404(Task, id=task_id)


   # Calculate the delay before marking it completed
   if task.deadline and task.status == 'Overdue':
       task.final_delay_duration = timezone.now() - task.deadline


   task.status = 'Completed'
   task.completed_at = timezone.now()
   task.save()
   return JsonResponse({'status': 'success'})




@login_required
def add_maintenance_item(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        # Assuming you have a model named MaintenanceWorkItem
        MaintenanceWorkItem.objects.create(
            project_type=data.get('project_type'),
            name_english=data.get('name_en'),
            name_arabic=data.get('name_ar')
        )
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'message': 'Invalid request'})



def update_description_ajax(request, task_id):
    if request.method != "POST":
        return JsonResponse(
            {
                "status":"error",
                "message":"Invalid request"
            },
            status=400
        )

    try:
        data = json.loads(request.body)
        description = data.get("description","").strip()
        task = get_object_or_404(Task,id=task_id)

        # --- TRANSLATION INTEGRATION ---
        if description:
            try:
                translator = GoogleTranslator(source='auto', target='en')
                task.description = translator.translate(description)
            except Exception as e:
                # Fallback to the original text if the translation API experiences an outage
                print(f"Translation failed: {e}")
                task.description = description
        else:
            task.description = description

        task.save()

        # Return the saved description text so the frontend can display the newly translated string
        return JsonResponse(
            {
                "status":"success",
                "description": task.description
            }
        )

    except Exception as e:
        return JsonResponse(
            {
                "status":"error",
                "message":str(e)
            },
            status=500
        )


@require_POST
def delete_task_item_ajax(request, item_id):
    # Replace 'TaskItem' with your actual model name for the sub-items
    item = get_object_or_404(TaskItem, id=item_id)
    item.delete()

    return JsonResponse({'status': 'success', 'message': 'Item deleted successfully.'})


def add_task_item_detail(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if request.method == 'POST':
        # Grab raw form values
        sub = request.POST.get('sub_category', '').strip()
        qty = request.POST.get('quantity', '').strip()

        translator = GoogleTranslator(source='auto', target='en')

        # --- 1. Translate Sub-Category ---
        if sub:
            try:
                translated_sub = translator.translate(sub)
            except Exception:
                translated_sub = sub  # Fallback to original if API drops out
        else:
            translated_sub = "General"

        # --- 2. Translate Quantity / Details ---
        if qty:
            if qty.isdigit():
                translated_qty = qty  # Skip translator entirely for pure numbers
            else:
                try:
                    translated_qty = translator.translate(qty)
                except Exception:
                    translated_qty = qty  # Fallback
        else:
            translated_qty = "0"

        # --- 3. Save to Database ---
        TaskItem.objects.create(
            task=task,
            sub_category=translated_sub,
            quantity=translated_qty
        )

        messages.success(request, "Missed maintenance item added successfully in English!")

    return redirect('task_detail', task_id=task.id)  # Change to your actual detail view name