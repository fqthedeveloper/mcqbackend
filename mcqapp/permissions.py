from rest_framework import permissions


class IsAdminUserOnly(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.user_type == 'admin'
        )


class IsStudentUserOnly(permissions.BasePermission):
    """
    Custom permission to only allow student users to access.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.user_type == 'student'
        )


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admins to edit.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.user_type == 'admin'
        )


class IsSubjectOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow subject creator or admin to modify.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        return bool(
            request.user and 
            request.user.is_authenticated and 
            (request.user.user_type == 'admin' or obj.created_by == request.user)
        )


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to edit it.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Check if user is admin
        if request.user.user_type == 'admin':
            return True
        
        # Check if user is the owner
        if hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        elif hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'student'):
            return obj.student == request.user
        
        return False