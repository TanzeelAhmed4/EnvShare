from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Project, ProjectMembership


User = get_user_model()


class ProjectSerializer(serializers.ModelSerializer):
    creator_id = serializers.IntegerField(read_only=True)
    creator_username = serializers.CharField(source='creator.username', read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = (
            'id',
            'name',
            'description',
            'creator_id',
            'creator_username',
            'member_count',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'creator_id', 'creator_username', 'member_count', 'created_at', 'updated_at')

    def get_member_count(self, project):
        if hasattr(project, 'member_count'):
            return project.member_count
        return project.memberships.count()


class AddProjectMemberSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)

    def validate_username(self, value):
        try:
            user = User.objects.get(username__iexact=value)
        except User.DoesNotExist:
            raise serializers.ValidationError('No registered user has that username.') from None

        project = self.context['project']
        if user.pk == project.creator_id:
            raise serializers.ValidationError('The project creator is already an owner.')
        if ProjectMembership.objects.filter(project=project, user=user).exists():
            raise serializers.ValidationError('That user is already a project member.')
        self.user = user
        return value


class ProjectMembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = ProjectMembership
        fields = ('user_id', 'username', 'email', 'role', 'created_at')
        read_only_fields = fields
