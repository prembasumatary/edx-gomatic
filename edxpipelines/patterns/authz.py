"""
GoCD Authorization primitives.
"""

from xml.etree import ElementTree as ET

from enum import Enum

from gomatic.xml_operations import Ensurance


class Permission(Enum):
    """An enumeration of valid GoCD authorizations"""
    ADMINS = "admins"
    OPERATE = "operate"
    VIEW = "view"


def ensure_permissions(pipeline_group, permission, roles):
    """
    Ensure that only the ``roles`` are given the ``permission``
    in the ``pipeline_group``.

    Arguments:
        pipeline_group (gomatic.PipelineGroup)
        permission (Permission)
        roles (list): List of role names to ensure
    """
    authorization_element = Ensurance(pipeline_group.element).ensure_child('authorization').element
    permission_element = Ensurance(authorization_element).ensure_child(permission.value).element
    permission_element[:] = []
    for role in roles:
        role_element = ET.SubElement(permission_element, tag='role')
        role_element.text = role
