from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta
from django.utils import timezone
import uuid
class Task(models.Model):




  PROJECT_TYPES = [
      ('Paint', 'Paint(صباغة)'),
      ('Electric', 'Electric(كهرباء)'),
      ('Plumbing', 'Plumbing(سباكة)'),
      ('Cleaning', 'Cleaning(تنظيف'),
      ('Carpenter', 'Carpenter(نجارة)'),
      ('AC', 'AC(تكييف)'),
      ('Mason', 'Mason(بناء)'),
      ('Ceiling', 'Ceiling(سقف)')
  ]




  STATUS_CHOICES = [ ('Pending(قيد الانتظار)', 'Pending'), ('In Progress', 'In Progress (نشط)'), ('Completed', 'Completed (مكتمل)'), ('Overdue', 'Overdue (متأخر)'), ]




  PRIORITY_CHOICES = [
      ('Low', 'Low'),
      ('Medium', 'Medium'),
      ('High', 'High'),
      ('Emergency', 'Emergency'),
  ]












  title = models.CharField(max_length=200)
  reward_points_awarded = models.IntegerField(default=0)
  job_id = models.CharField(
      max_length=100,
      unique=True,
      blank=True
  )




  description = models.TextField(null=True, blank=True)
  final_delay_duration = models.DurationField(null=True, blank=True)




  building = models.CharField(
      max_length=150,
      help_text="Select building complex or project zone"
  )
  unit = models.CharField(
      max_length=150,
      help_text="Specific flat, room, floor or system zone designation"
  )
  custom_location = models.CharField(
      max_length=300,
      blank=True,
      null=True,
      help_text="Used dynamically if 'Other' is checked by user"
  )




  project_type = models.CharField(
      max_length=50,
      choices=PROJECT_TYPES
  )




  assigned_technicians = models.ManyToManyField(
      User,
      related_name='assigned_tasks',
      blank=True
  )




  supervisor = models.ForeignKey(
      User,
      on_delete=models.SET_NULL,
      null=True,
      related_name='supervised_tasks'
  )




  status = models.CharField(
      max_length=50,
      choices=STATUS_CHOICES,
      default='Pending'
  )




  priority = models.CharField(
      max_length=50,
      choices=PRIORITY_CHOICES,
      default='Medium'
  )




  budget = models.DecimalField(
      max_digits=10,
      decimal_places=2,
      null=True,
      blank=True
  )




  start_date = models.DateTimeField()




  deadline = models.DateTimeField()




  started_at = models.DateTimeField(
      null=True,
      blank=True
  )




  completed_at = models.DateTimeField(
      null=True,
      blank=True
  )




  is_overdue = models.BooleanField(
      default=False
  )




  created_at = models.DateTimeField(
      auto_now_add=True
  )
  reward_points_awarded = models.IntegerField(default=0,null=True)
  is_rewarded = models.BooleanField(default=False)
  def __str__(self):
      return self.title





  @property
  def assigned_to_display(self):
      names = [tech.username for tech in self.assigned_technicians.all()]
      return ", ".join(names)




  @property
  def location(self):
      if self.building == 'Other (آخر)':
          return self.custom_location or "Custom Location"
      if self.unit == 'Other (آخر)':
          return f"{self.building} - {self.custom_location or 'Custom Unit'}"
      return f"{self.building} ({self.unit})"




  def save(self, *args, **kwargs):
      if not self.job_id:
          self.job_id = f"JOB-{uuid.uuid4().hex[:8].upper()}"




      if self.deadline and timezone.now() > self.deadline and self.status not in ['Completed']:
          self.status = 'Overdue'
          self.is_overdue = True
      elif self.deadline and timezone.now() <= self.deadline and self.status == 'Overdue':
          # Fallback if a supervisor extends a deadline later
          self.status = 'In Progress' if self.started_at else 'Pending'
          self.is_overdue = False




      super().save(*args, **kwargs)








      super().save(*args, **kwargs)












  @property
  def time_taken(self):




      if not self.started_at or not self.completed_at:
          return "-"




      duration = self.completed_at - self.started_at




      days = duration.days
      hours, remainder = divmod(duration.seconds, 3600)
      minutes, seconds = divmod(remainder, 60)




      parts = []




      if days > 0:
          parts.append(f"{days} day{'s' if days != 1 else ''}")




      if hours > 0:
          parts.append(f"{hours} hour{'s' if hours != 1 else ''}")




      if minutes > 0:
          parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")




      if seconds > 0:
          parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")




      return ", ".join(parts) if parts else "0 seconds"




  @property
  def work_delay(self):
      """
      Calculates how long a task has been overdue based on the current time minus the deadline.
      Follows a precise single-unit rule (only seconds, only minutes, or structured combinations)
      and omits zero values.
      """
      # If the task isn't overdue yet, or hasn't hit its deadline, there is no delay
      if self.status != 'Overdue' or not self.deadline or timezone.now() <= self.deadline:
          return "-"




      # Calculate the dynamic difference between right now and the deadline
      duration = timezone.now() - self.deadline
      total_seconds = int(duration.total_seconds())




      # Rule 1: If it's less than a minute, show ONLY seconds
      if total_seconds < 60:
          return f"{total_seconds} second{'s' if total_seconds != 1 else ''}"




      # Rule 2: If it's less than an hour, show ONLY minutes
      if total_seconds < 3600:
          minutes = total_seconds // 60
          return f"{minutes} minute{'s' if minutes != 1 else ''}"




      # Rule 3: For hours and days, pull components and omit any zeroes (similar to time_taken)
      days = duration.days
      hours, remainder = divmod(duration.seconds, 3600)
      minutes, _ = divmod(remainder, 60)




      parts = []
      if days > 0:
          parts.append(f"{days} day{'s' if days != 1 else ''}")
      if hours > 0:
          parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
      if minutes > 0:
          parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")




      return ", ".join(parts) if parts else "0 seconds"








class MaintenanceWorkItem(models.Model):
  PROJECT_TYPE_CHOICES = [
      ('Paint', 'Paint(صباغة)'),
      ('Electric', 'Electric(كهرباء)'),
      ('Plumbing', 'Plumbing(سباكة)'),
      ('Cleaning', 'Cleaning(تنظيف'),
      ('Carpenter', 'Carpenter(نجارة)'),
      ('AC', 'AC(تكييف)'),
      ('Mason', 'Mason(بناء)'),
      ('Ceiling', 'Ceiling(سقف)')
  ]




  project_type = models.CharField(max_length=50, choices=PROJECT_TYPE_CHOICES)
  name_english = models.CharField(max_length=150, help_text="e.g., Wiring 2.5 mm")
  name_arabic = models.CharField(max_length=150, help_text="e.g., تمديد أسلاك 2.5 مم")




  class Meta:
      ordering = ['project_type', 'name_english']
      unique_together = ('project_type', 'name_english')  # Prevents duplicate items




  def __str__(self):
      return f"{self.name_english} ({self.name_arabic})"




  @property
  def formatted_display(self):
      return f"{self.name_english} ({self.name_arabic})"
class SubTask(models.Model):




  task = models.ForeignKey(
      Task,
      on_delete=models.CASCADE,
      related_name='subtasks'
  )




  title = models.CharField(max_length=200)




  completed = models.BooleanField(default=False)




  def __str__(self):




      return self.title












class Complaint(models.Model):




  task = models.ForeignKey(
      Task,
      on_delete=models.CASCADE
  )




  technician = models.ForeignKey(
      User,
      on_delete=models.CASCADE
  )




  message = models.TextField()




  voice_note = models.FileField(
      upload_to='voice_notes/',
      null=True,
      blank=True
  )




  created_at = models.DateTimeField(
      auto_now_add=True
  )




  def __str__(self):




      return self.message[:30]








class Profile(models.Model):




  ROLE_CHOICES = [




      ('Admin', 'Admin'),




      ('Supervisor', 'Supervisor'),




      ('Technician', 'Technician'),




  ]




  user = models.OneToOneField(
      User,
      on_delete=models.CASCADE
  )




  role = models.CharField(
      max_length=50,
      choices=ROLE_CHOICES,
      default='Technician'
  )




  phone = models.CharField(
      max_length=20,
      blank=True,
      null=True
  )
  reward_points = models.IntegerField(default=0)
  reward_points = models.IntegerField(default=0)

  telegram_chat_id = models.CharField(max_length=50, blank=True, null=True)
  def __str__(self):




      return self.user.username




  @receiver(post_save, sender=User)
  def create_profile(sender, instance, created, **kwargs):
      if created:
          Profile.objects.create(user=instance)








class Notification(models.Model):




  user = models.ForeignKey(
      User,
      on_delete=models.CASCADE
  )




  message = models.CharField(
      max_length=300
  )




  is_read = models.BooleanField(
      default=False
  )




  created_at = models.DateTimeField(
      auto_now_add=True
  )




  def __str__(self):




      return self.message








class TaskItem(models.Model):
  task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='items')
  sub_category = models.CharField(max_length=250)
  quantity = models.TextField()




  def __str__(self):
      return f"{self.sub_category} ({self.quantity})"




class TaskAttachment(models.Model):
  task = models.ForeignKey(
      Task,
      on_delete=models.CASCADE,
      related_name='attachments'
  )
  uploaded_by = models.ForeignKey(
      User,
      on_delete=models.CASCADE
  )
  image = models.ImageField(
      upload_to='task_attachments/',
      help_text="Upload a picture for location reference or job verification"
  )
  created_at = models.DateTimeField(
      auto_now_add=True
  )




  def __str__(self):
      return f"Attachment for {self.task.title} by {self.uploaded_by.username}"





