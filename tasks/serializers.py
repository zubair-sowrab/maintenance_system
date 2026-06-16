from rest_framework import serializers

from .models import Task


# In your serializers.py
class TaskSerializer(serializers.ModelSerializer):
    # If you want to show the technicians in your API response:
    assigned_technicians = serializers.StringRelatedField(many=True)

    class Meta:
        model = Task
        fields = '__all__' # Or list them explicitly