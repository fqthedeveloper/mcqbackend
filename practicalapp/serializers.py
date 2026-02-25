from rest_framework import serializers
from .models import PracticalTask


class PracticalTaskSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(
        source="subject.name",
        read_only=True
    )

    class Meta:
        model = PracticalTask
        fields = "__all__"
        read_only_fields = ("id", "created_at")

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance