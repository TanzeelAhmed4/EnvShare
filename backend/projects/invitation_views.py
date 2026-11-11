import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Project, ProjectAccessAuditEvent, ProjectInvitation, ProjectMembership
from .permissions import can_access_project, has_project_permission
from .write_locks import lock_project_for_write

User = get_user_model()


def normalized_email(value):
    return value.strip().casefold()


def token_digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def usable(invitation):
    return (
        invitation.revoked_at is None
        and invitation.expires_at > timezone.now()
        and invitation.use_count < invitation.max_uses
    )


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    role = serializers.ChoiceField(choices=ProjectMembership.Role.choices)
    expires_in_hours = serializers.IntegerField(min_value=1, max_value=720, default=168)
    max_uses = serializers.IntegerField(min_value=1, max_value=1, default=1)


def claim_invitation_use(invitation_id, digest):
    """Atomically reserve a use only while the invitation remains valid and under its cap."""
    return ProjectInvitation.objects.filter(
        pk=invitation_id,
        token_hash=digest,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
        use_count__lt=F('max_uses'),
    ).update(use_count=F('use_count') + 1) == 1


class ProjectInvitationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_project(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)
        if not can_access_project(request.user, project):
            raise PermissionDenied('You do not have access to this project.')
        if not has_project_permission(request.user, project, 'manage_members'):
            raise PermissionDenied('You do not have permission to manage invitations.')
        return project

    def get(self, request, project_id):
        project = self.get_project(request, project_id)
        now = timezone.now()
        items = []
        for invitation in project.invitations.order_by('-created_at'):
            items.append({
                'id': invitation.pk, 'email': invitation.invited_email, 'role': invitation.role,
                'created_at': invitation.created_at, 'expires_at': invitation.expires_at,
                'max_uses': invitation.max_uses, 'use_count': invitation.use_count,
                'revoked': invitation.revoked_at is not None,
                'expired': invitation.expires_at <= now,
                'exhausted': invitation.use_count >= invitation.max_uses,
            })
        return Response(items)

    def post(self, request, project_id):
        project = self.get_project(request, project_id)
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = serializer.validated_data['role']
        if not has_project_permission(request.user, project, 'assign_' + role):
            raise PermissionDenied('You cannot invite someone with that project role.')
        token = secrets.token_urlsafe(32)
        data = serializer.validated_data
        try:
            with transaction.atomic():
                lock_project_for_write(project.pk)
                if not has_project_permission(request.user, project, 'manage_members') or not has_project_permission(
                    request.user, project, 'assign_' + role,
                ):
                    raise PermissionDenied('You cannot invite someone with that project role.')
                invitation = ProjectInvitation.objects.create(
                    project=project,
                    invited_email=normalized_email(data['email']),
                    token_hash=token_digest(token),
                    role=role,
                    created_by=request.user,
                    expires_at=timezone.now() + timedelta(hours=data['expires_in_hours']),
                    max_uses=data['max_uses'],
                )
                ProjectAccessAuditEvent.objects.create(
                    project=project, actor=request.user, actor_username=request.user.get_username(),
                    action=ProjectAccessAuditEvent.Action.INVITATION_CREATED,
                    target_email=invitation.invited_email, role_after=role,
                )
        except OperationalError:
            return Response({'detail': 'Invitation creation conflicted with another write. Try again.'}, status=409)
        return Response({
            'id': invitation.pk, 'email': invitation.invited_email, 'role': invitation.role,
            'expires_at': invitation.expires_at, 'max_uses': invitation.max_uses,
            'token': token,
        }, status=status.HTTP_201_CREATED)


class ProjectInvitationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id, invitation_id):
        project = get_object_or_404(Project, pk=project_id)
        if not can_access_project(request.user, project):
            raise PermissionDenied('You do not have access to this project.')
        if not has_project_permission(request.user, project, 'manage_members'):
            raise PermissionDenied('You do not have permission to revoke invitations.')
        invitation = get_object_or_404(ProjectInvitation, pk=invitation_id, project=project)
        if invitation.revoked_at is None:
            try:
                with transaction.atomic():
                    lock_project_for_write(project.pk)
                    if not has_project_permission(request.user, project, 'manage_members'):
                        raise PermissionDenied('You do not have permission to revoke invitations.')
                    invitation = get_object_or_404(
                        ProjectInvitation.objects.select_for_update(), pk=invitation_id, project=project,
                    )
                    if invitation.revoked_at is None:
                        invitation.revoked_at = timezone.now()
                        invitation.save(update_fields=('revoked_at',))
                        ProjectAccessAuditEvent.objects.create(
                            project=project, actor=request.user, actor_username=request.user.get_username(),
                            action=ProjectAccessAuditEvent.Action.INVITATION_REVOKED,
                            target_email=invitation.invited_email, role_before=invitation.role,
                        )
            except OperationalError:
                return Response({'detail': 'Invitation revocation conflicted with another write. Try again.'}, status=409)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationInspectView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get('token', '')
        if not isinstance(token, str) or not token or len(token) > 256:
            return Response({'detail': 'Invitation is invalid or unavailable.'}, status=404)
        invitation = ProjectInvitation.objects.select_related('project').filter(token_hash=token_digest(token)).first()
        if invitation is None or not usable(invitation):
            return Response({'detail': 'Invitation is invalid or unavailable.'}, status=404)
        return Response({
            'project_name': invitation.project.name,
            'role': invitation.role,
            'expires_at': invitation.expires_at,
            'uses_remaining': invitation.max_uses - invitation.use_count,
        })


class InvitationAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get('token', '')
        if not isinstance(token, str) or not token or len(token) > 256:
            return Response({'detail': 'Invitation is invalid or unavailable.'}, status=404)
        digest = token_digest(token)
        invitation = ProjectInvitation.objects.select_related('project').filter(token_hash=digest).first()
        if invitation is None or not usable(invitation):
            return Response({'detail': 'Invitation is invalid or unavailable.'}, status=404)
        if normalized_email(request.user.email) != invitation.invited_email:
            return Response({'detail': 'Sign in with the email address invited to this project.'}, status=403)
        if ProjectMembership.objects.filter(project=invitation.project, user=request.user).exists() or invitation.project.creator_id == request.user.pk:
            return Response({'detail': 'You already have access to this project.'}, status=409)
        try:
            with transaction.atomic():
                lock_project_for_write(invitation.project_id)
                if not claim_invitation_use(invitation.pk, digest):
                    return Response({'detail': 'Invitation is invalid or unavailable.'}, status=404)
                if ProjectMembership.objects.filter(project=invitation.project, user=request.user).exists() or invitation.project.creator_id == request.user.pk:
                    return Response({'detail': 'You already have access to this project.'}, status=409)
                ProjectMembership.objects.create(
                    project=invitation.project, user=request.user,
                    added_by=invitation.created_by or invitation.project.creator,
                    role=invitation.role,
                )
                ProjectAccessAuditEvent.objects.create(
                    project=invitation.project, actor=request.user,
                    actor_username=request.user.get_username(),
                    action=ProjectAccessAuditEvent.Action.INVITATION_ACCEPTED,
                    target_email=invitation.invited_email,
                    target_username=request.user.get_username(), role_after=invitation.role,
                )
        except IntegrityError:
            return Response({'detail': 'You already have access to this project.'}, status=409)
        except OperationalError:
            # SQLite may reject one side of a concurrent write; its transaction rolls back the claim.
            return Response({'detail': 'Invitation acceptance conflicted with another request. Try again.'}, status=409)
        return Response({'project_id': invitation.project_id, 'project_name': invitation.project.name, 'role': invitation.role}, status=200)
