from rest_framework.permissions import BasePermission


# =========================================================
# ADMIN ONLY
# =========================================================

class IsCyberAdmin(BasePermission):

    message = (
        'Only administrators can access this resource.'
    )

    def has_permission(self, request, view):

        return bool(

            request.user and
            request.user.is_authenticated and
            request.user.is_staff
        )


# =========================================================
# STUDENT ONLY
# =========================================================

class IsCyberStudent(BasePermission):

    message = (
        'Only students can access this resource.'
    )

    def has_permission(self, request, view):

        return bool(
            request.user and
            request.user.is_authenticated
        )


# =========================================================
# SESSION OWNER
# =========================================================

class IsSessionOwner(BasePermission):

    message = (
        'You do not own this session.'
    )

    def has_object_permission(
        self,
        request,
        view,
        obj
    ):

        return bool(
            request.user and
            request.user.is_authenticated and
            obj.user == request.user
        )


# =========================================================
# MACHINE SESSION OWNER
# =========================================================

class IsMachineSessionOwner(BasePermission):

    message = (
        'You do not own this machine session.'
    )

    def has_object_permission(
        self,
        request,
        view,
        obj
    ):

        return bool(
            request.user and
            request.user.is_authenticated and
            obj.session.user == request.user
        )


# =========================================================
# ACTIVE SESSION ONLY
# =========================================================

class IsActiveCyberSession(BasePermission):

    message = (
        'Session is not active.'
    )

    def has_object_permission(
        self,
        request,
        view,
        obj
    ):

        return obj.status in [
            'starting',
            'running'
        ]


# =========================================================
# SUBMITTED SESSION ONLY
# =========================================================

class IsSubmittedCyberSession(BasePermission):

    message = (
        'Session has not been submitted.'
    )

    def has_object_permission(
        self,
        request,
        view,
        obj
    ):

        return obj.status == 'submitted'


# =========================================================
# PREVENT MULTIPLE ACTIVE SESSIONS
# =========================================================

class HasNoRunningCyberSession(BasePermission):

    message = (
        'You already have an active practical session.'
    )

    def has_permission(
        self,
        request,
        view
    ):

        if not request.user.is_authenticated:
            return False

        from .models import CyberSession

        exists = CyberSession.objects.filter(

            user=request.user,

            status__in=[
                'starting',
                'running'
            ]

        ).exists()

        return not exists


# =========================================================
# TASK MUST BE PUBLISHED
# =========================================================

class IsPublishedTask(BasePermission):

    message = (
        'This practical task is not published.'
    )

    def has_object_permission(
        self,
        request,
        view,
        obj
    ):

        return bool(
            obj.is_published and
            obj.is_active
        )


# =========================================================
# MACHINE MUST BE RUNNING
# =========================================================

class IsRunningMachine(BasePermission):

    message = (
        'Machine is not running.'
    )

    def has_object_permission(
        self,
        request,
        view,
        obj
    ):

        return obj.status == 'running'


# =========================================================
# READ ONLY AFTER SUBMISSION
# =========================================================

class ReadOnlyAfterSubmission(BasePermission):

    message = (
        'Submitted sessions are read-only.'
    )

    def has_object_permission(
        self,
        request,
        view,
        obj
    ):

        if obj.status == 'submitted':

            return request.method in [
                'GET',
                'HEAD',
                'OPTIONS'
            ]

        return True