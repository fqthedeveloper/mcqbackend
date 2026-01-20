from rest_framework import serializers
from .models import PracticalTask


class PracticalTaskSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)

    class Meta:
        model = PracticalTask
        fields = "__all__"
