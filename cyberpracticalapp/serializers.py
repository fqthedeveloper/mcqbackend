from rest_framework import serializers
from .models import (
    CyberMachineTemplate,
    CyberTopology,
    CyberPracticalTask,
    CyberSession,
    CyberMachineSession
)


class CyberMachineTemplateSerializer(serializers.ModelSerializer):

    class Meta:
        model = CyberMachineTemplate
        fields = '__all__'


class CyberTopologySerializer(serializers.ModelSerializer):

    class Meta:
        model = CyberTopology
        fields = '__all__'


class CyberPracticalTaskSerializer(serializers.ModelSerializer):

    subject_name = serializers.CharField(
        source='subject.name',
        read_only=True
    )

    topology_name = serializers.CharField(
        source='topology.name',
        read_only=True
    )

    class Meta:
        model = CyberPracticalTask
        fields = '__all__'


class CyberMachineSessionSerializer(serializers.ModelSerializer):

    class Meta:
        model = CyberMachineSession
        fields = '__all__'


class CyberSessionSerializer(serializers.ModelSerializer):

    machines = CyberMachineSessionSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = CyberSession
        fields = '__all__'